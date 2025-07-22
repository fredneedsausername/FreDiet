from flask import Flask, request, render_template, redirect, url_for, session
import pymysql
from datetime import datetime, time, timedelta
import pytz
import re
from waitress import serve
import passwords

app = Flask(__name__)
app.secret_key = passwords.app_secret_key

app.permanent_session_lifetime = timedelta(days=31)

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

def validate_meal_data(proteins_str, calories_str):
    """Validate meal input data"""
    errors = []
    
    # Validate proteins (max 999.9, 1 decimal place)
    try:
        # Remove any whitespace
        proteins_str = proteins_str.strip()
        
        # Check format with regex - up to 3 digits before decimal, exactly 1 after (or no decimal)
        protein_pattern = r'^\d{1,3}(\.\d)?$'
        if not re.match(protein_pattern, proteins_str):
            errors.append("Proteins must be a number with up to 3 digits before decimal and exactly 1 digit after (e.g., 25.5, 100, 999.9)")
        else:
            proteins = float(proteins_str)
            if proteins < 0 or proteins > 999.9:
                errors.append("Proteins must be between 0.0 and 999.9 grams")
    except (ValueError, TypeError):
        errors.append("Proteins must be a valid number")
        proteins = None
    
    # Validate calories (max 9999, integers only)
    try:
        # Remove any whitespace
        calories_str = calories_str.strip()
        
        # Check if it's a valid integer string
        if not calories_str.isdigit():
            errors.append("Calories must be a whole number (no decimals)")
        else:
            calories = int(calories_str)
            if calories < 0 or calories > 9999:
                errors.append("Calories must be between 0 and 9999")
    except (ValueError, TypeError):
        errors.append("Calories must be a valid whole number")
        calories = None
    
    if errors:
        return None, None, errors
    
    return proteins, calories, []

def validate_user_data(username, password):
    """Validate user input data"""
    errors = []
    
    if len(username) > 12:
        errors.append("Username must be 12 characters or fewer")
    
    if len(password) > 50:
        errors.append("Password must be 50 characters or fewer")
    
    return errors

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
        
        validation_errors = validate_user_data(username, password)
        if validation_errors:
            return render_template('login.html', error="Invalid username or password")
        
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT id, password FROM users WHERE username = %s", (username,))
                user = cursor.fetchone()
                
                if user and user[1] == password:
                    session.permanent = True
                    session['user_id'] = user[0]
                    session['username'] = username
                    return redirect(url_for('dashboard'))
                else:
                    return render_template('login.html', error="Invalid username or password")
        finally:
            conn.close()
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/dashboard')
@require_login
def dashboard():
    now = get_italy_now()
    today = now.date()
    
    # Get selected date from query parameter, default to today
    selected_date_str = request.args.get('date')
    if selected_date_str:
        try:
            selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
        except ValueError:
            selected_date = today
    else:
        selected_date = today
    
    # Get any error messages from the session
    error_message = session.pop('error_message', None)
    
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Get selected date's meals
            cursor.execute("""
                SELECT id, proteins, calories, meal_time 
                FROM meals 
                WHERE user_id = %s AND meal_date = %s 
                ORDER BY meal_time DESC
            """, (session['user_id'], selected_date))
            selected_meals = []
            for row in cursor.fetchall():
                meal_time = row[3]
                # Convert timedelta to time object if necessary
                if hasattr(meal_time, 'total_seconds'):  # It's a timedelta
                    meal_time = timedelta_to_time(meal_time)
                
                selected_meals.append({
                    'id': row[0],
                    'proteins': float(row[1]),
                    'calories': int(row[2]),
                    'meal_time': meal_time
                })
            
            # Get selected date's totals
            cursor.execute("""
                SELECT COALESCE(SUM(calories), 0), COALESCE(SUM(proteins), 0)
                FROM meals 
                WHERE user_id = %s AND meal_date = %s
            """, (session['user_id'], selected_date))
            selected_calories, selected_proteins = cursor.fetchone()
            selected_calories = float(selected_calories)
            selected_proteins = float(selected_proteins)
    finally:
        conn.close()
    
    return render_template('dashboard.html',
                         selected_meals=selected_meals,
                         selected_calories=selected_calories,
                         selected_proteins=selected_proteins,
                         selected_date=selected_date.isoformat(),
                         selected_date_obj=selected_date,
                         today_date=today.isoformat(),
                         current_time=now.strftime('%H:%M'),
                         is_today=selected_date == today,
                         username=session['username'],
                         error_message=error_message)

@app.route('/add_meal', methods=['POST'])
@require_login
def add_meal():
    proteins_str = request.form['proteins']
    calories_str = request.form['calories']
    meal_date = request.form['meal_date']
    meal_time = request.form['meal_time']
    
    # Validate the input data
    proteins, calories, validation_errors = validate_meal_data(proteins_str, calories_str)
    
    if validation_errors:
        session['error_message'] = "; ".join(validation_errors)
        return redirect(url_for('dashboard', date=meal_date))
    
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO meals (user_id, proteins, calories, meal_date, meal_time) 
                VALUES (%s, %s, %s, %s, %s)
            """, (session['user_id'], proteins, calories, meal_date, meal_time))
            conn.commit()
    except Exception as e:
        session['error_message'] = "Database error: Unable to save meal"
        return redirect(url_for('dashboard', date=meal_date))
    finally:
        conn.close()
    
    # Redirect back to the same date
    return redirect(url_for('dashboard', date=meal_date))

@app.route('/delete_meal/<int:meal_id>', methods=['POST'])
@require_login
def delete_meal(meal_id):
    # Get the meal date before deleting so we can redirect back to it
    selected_date = request.form.get('meal_date', datetime.now(ITALY_TZ).date().isoformat())
    
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM meals WHERE id = %s AND user_id = %s", 
                         (meal_id, session['user_id']))
            conn.commit()
    finally:
        conn.close()
    
    # Redirect back to the same date
    return redirect(url_for('dashboard', date=selected_date))

@app.route('/view_range')
@require_login
def view_range():
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    page = int(request.args.get('page', 1))
    per_page = 30  # Days per page
    
    range_data = None
    avg_calories = 0
    avg_proteins = 0
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
                    total_proteins = sum(day['proteins'] for day in all_data)
                    avg_calories = sum(day['calories'] for day in all_data) / total_days
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
            print("Please select an appropriate passwords.flask_environment")