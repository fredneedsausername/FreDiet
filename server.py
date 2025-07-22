from flask import Flask, request, render_template, redirect, url_for, session
import pymysql
from datetime import datetime, time
import pytz
from werkzeug.security import generate_password_hash, check_password_hash
from waitress import serve
import passwords

app = Flask(__name__)
app.secret_key = passwords.app_secret_key

ITALY_TZ = pytz.timezone('Europe/Rome')

def get_db_connection():
    return pymysql.connect(**passwords.DB_CONFIG)

def get_italy_now():
    return datetime.now(ITALY_TZ)

def timedelta_to_time(td):
    """Convert timedelta to time object"""
    if td is None:
        return None
    total_seconds = int(td.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return time(hours % 24, minutes, seconds)

def require_login(f):
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

# Routes
@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT id, password_hash FROM users WHERE username = %s", (username,))
                user = cursor.fetchone()
                
                if user and check_password_hash(user[1], password):
                    session['user_id'] = user[0]
                    session['username'] = username
                    return redirect(url_for('dashboard'))
                else:
                    return render_template('login.html', error="Invalid username or password")
        finally:
            conn.close()
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        
        if password != confirm_password:
            return render_template('register.html', error="Passwords don't match")
        
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                # Check if username exists
                cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
                if cursor.fetchone():
                    return render_template('register.html', error="Username already exists")
                
                # Create new user
                password_hash = generate_password_hash(password)
                cursor.execute("INSERT INTO users (username, password_hash) VALUES (%s, %s)", 
                             (username, password_hash))
                conn.commit()
                
                # Auto-login
                cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
                user_id = cursor.fetchone()[0]
                session['user_id'] = user_id
                session['username'] = username
                
                return redirect(url_for('dashboard'))
        finally:
            conn.close()
    
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/dashboard')
@require_login
def dashboard():
    now = get_italy_now()
    today = now.date()
    
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Get today's meals
            cursor.execute("""
                SELECT id, proteins, calories, meal_time 
                FROM meals 
                WHERE user_id = %s AND meal_date = %s 
                ORDER BY meal_time DESC
            """, (session['user_id'], today))
            today_meals = []
            for row in cursor.fetchall():
                meal_time = row[3]
                # Convert timedelta to time object if necessary
                if hasattr(meal_time, 'total_seconds'):  # It's a timedelta
                    meal_time = timedelta_to_time(meal_time)
                
                today_meals.append({
                    'id': row[0],
                    'proteins': float(row[1]),
                    'calories': float(row[2]),
                    'meal_time': meal_time
                })
            
            # Get today's totals
            cursor.execute("""
                SELECT COALESCE(SUM(calories), 0), COALESCE(SUM(proteins), 0)
                FROM meals 
                WHERE user_id = %s AND meal_date = %s
            """, (session['user_id'], today))
            today_calories, today_proteins = cursor.fetchone()
            today_calories = float(today_calories)
            today_proteins = float(today_proteins)
    finally:
        conn.close()
    
    return render_template('dashboard.html',
                         today_meals=today_meals,
                         today_calories=today_calories,
                         today_proteins=today_proteins,
                         today_date=today.isoformat(),
                         current_time=now.strftime('%H:%M'),
                         username=session['username'])

@app.route('/add_meal', methods=['POST'])
@require_login
def add_meal():
    proteins = float(request.form['proteins'])
    calories = float(request.form['calories'])
    meal_date = request.form['meal_date']
    meal_time = request.form['meal_time']
    
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO meals (user_id, proteins, calories, meal_date, meal_time) 
                VALUES (%s, %s, %s, %s, %s)
            """, (session['user_id'], proteins, calories, meal_date, meal_time))
            conn.commit()
    finally:
        conn.close()
    
    return redirect(url_for('dashboard'))

@app.route('/delete_meal/<int:meal_id>', methods=['POST'])
@require_login
def delete_meal(meal_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM meals WHERE id = %s AND user_id = %s", 
                         (meal_id, session['user_id']))
            conn.commit()
    finally:
        conn.close()
    
    return redirect(url_for('dashboard'))

@app.route('/view_range')
@require_login
def view_range():
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    page = int(request.args.get('page', 1))
    per_page = 10  # Days per page
    
    range_data = None
    avg_calories = 0
    avg_proteins = 0
    total_calories = 0
    total_pages = 0
    total_days = 0
    
    if start_date and end_date:
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                # Get summary statistics (all data for averages)
                cursor.execute("""
                    SELECT meal_date, 
                           SUM(calories) as total_calories, 
                           SUM(proteins) as total_proteins,
                           COUNT(*) as meal_count
                    FROM meals 
                    WHERE user_id = %s AND meal_date BETWEEN %s AND %s
                    GROUP BY meal_date
                    ORDER BY meal_date DESC
                """, (session['user_id'], start_date, end_date))
                
                all_data = []
                for row in cursor.fetchall():
                    all_data.append({
                        'date': row[0],
                        'calories': float(row[1]),
                        'proteins': float(row[2]),
                        'meal_count': row[3]
                    })
                
                if all_data:
                    total_days = len(all_data)
                    total_calories = sum(day['calories'] for day in all_data)
                    total_proteins = sum(day['proteins'] for day in all_data)
                    avg_calories = total_calories / total_days
                    avg_proteins = total_proteins / total_days
                    
                    # Calculate pagination
                    total_pages = (total_days + per_page - 1) // per_page
                    offset = (page - 1) * per_page
                    range_data = all_data[offset:offset + per_page]
        finally:
            conn.close()
    
    return render_template('view_range.html',
                         start_date=start_date,
                         end_date=end_date,
                         range_data=range_data,
                         avg_calories=avg_calories,
                         avg_proteins=avg_proteins,
                         total_calories=total_calories,
                         total_days=total_days,
                         current_page=page,
                         total_pages=total_pages,
                         per_page=per_page,
                         username=session['username'])

if __name__ == '__main__':
    match passwords.flask_environment:
        case 'production':
            serve(app, host='127.0.0.1', port=passwords.flask_port)
        case 'development':
            app.run(debug=True, host='127.0.0.1', port=passwords.flask_port)
        case _:
            print("Please select an appropriate passwords.flask_port")