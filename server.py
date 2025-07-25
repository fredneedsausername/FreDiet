from flask import Flask, request, render_template, redirect, url_for, session, jsonify, g
import sqlite3
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
    """Get database connection using Flask's g object for per-request connections."""
    if 'db' not in g:
        g.db = sqlite3.connect(passwords.DB_FILE_PATH, timeout=30.0)
        g.db.row_factory = sqlite3.Row  # Enable dict-like access to rows
        # Enable foreign key constraints
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db

@app.teardown_appcontext
def close_db(error):
    """Close database connection at the end of each request."""
    db = g.pop('db', None)
    if db is not None:
        db.close()

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
    errors = {}
    
    # Validate proteins (max 999.9, 1 decimal place)
    try:
        # Remove any whitespace
        proteins_str = proteins_str.strip()
        
        # Check format with regex - up to 3 digits before decimal, exactly 1 after (or no decimal)
        protein_pattern = r'^\d{1,3}(\.\d)?$'
        if not re.match(protein_pattern, proteins_str):
            errors["proteins"] = "Max 3 digits before decimal, 1 digit after (e.g. 25.5, 100, 999.9)"
        else:
            proteins = float(proteins_str)
            if proteins < 0 or proteins > 999.9:
                errors["proteins"] = "Must be between 0.0 and 999.9"
    except (ValueError, TypeError):
        errors["proteins"] = "Must be a valid number"
        proteins = None
    
    # Validate calories (max 9999, integers only)
    try:
        # Remove any whitespace
        calories_str = calories_str.strip()
        
        # Check if it's a valid integer string
        if not calories_str.isdigit():
            errors["calories"] = "Must be a whole number (no decimals)"
        else:
            calories = int(calories_str)
            if calories < 0 or calories > 9999:
                errors["calories"] = "Must be between 0 and 9999"
    except (ValueError, TypeError):
        errors["calories"] = "Must be a valid whole number"
        calories = None
    
    if errors:
        return None, None, errors
    
    return proteins, calories, {}

def validate_user_data(username, password):
    """Validate user input data"""
    errors = []
    
    if len(username) > 12:
        errors.append("Username must be 12 characters or fewer")
    
    if len(password) > 50:
        errors.append("Password must be 50 characters or fewer")
    
    return errors

def validate_date_time(meal_date, meal_time):
    """Validate date and time format for SQLite"""
    errors = {}
    
    # Validate date format (YYYY-MM-DD)
    date_pattern = r'^\d{4}-\d{2}-\d{2}$'
    if not re.match(date_pattern, meal_date):
        errors["meal_date"] = "Invalid date format, must be YYYY-MM-DD"
    
    # Validate time format (HH:MM)
    time_pattern = r'^\d{2}:\d{2}$'
    if not re.match(time_pattern, meal_time):
        errors["meal_time"] = "Invalid time format, must be HH:MM"
    
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
            cursor = conn.cursor()
            cursor.execute("SELECT id, password FROM users WHERE username = ?", (username,))
            user = cursor.fetchone()
            
            if user and user['password'] == password:
                session.permanent = True
                session['user_id'] = user['id']
                session['username'] = username
                return redirect(url_for('dashboard'))
            else:
                return render_template('login.html', error="Invalid username or password")
        except sqlite3.Error as e:
            app.logger.error(f"Database error during login: {e}")
            return render_template('login.html', error="Database error: Unable to process login")
    
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
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        # Get selected date's meals
        cursor.execute("""
            SELECT id, proteins, calories, meal_time 
            FROM meals 
            WHERE user_id = ? AND meal_date = ? 
            ORDER BY meal_time DESC
        """, (session['user_id'], selected_date.isoformat()))
        
        selected_meals = []
        for row in cursor.fetchall():
            meal_time = row['meal_time']
            # Parse time string back to time object for formatting
            try:
                time_obj = datetime.strptime(meal_time, '%H:%M').time()
                formatted_time = time_obj.strftime('%H:%M')
                
                selected_meals.append({
                    'id': row['id'],
                    'proteins': float(row['proteins']),
                    'calories': int(row['calories']),
                    'formatted_time': formatted_time
                })
            except ValueError:
                app.logger.warning(f"Skipping meal ID {row['id']} with corrupt time format: '{meal_time}' for user {session['user_id']}")
                continue
        
        # Get selected date's totals
        cursor.execute("""
            SELECT COALESCE(SUM(calories), 0), COALESCE(SUM(proteins), 0)
            FROM meals 
            WHERE user_id = ? AND meal_date = ?
        """, (session['user_id'], selected_date.isoformat()))
        totals = cursor.fetchone()
        selected_calories = float(totals[0])
        selected_proteins = float(totals[1])
        
    except sqlite3.Error as e:
        app.logger.error(f"Database error in dashboard: {e}")
        # Provide fallback data to prevent page crash
        selected_meals = []
        selected_calories = 0.0
        selected_proteins = 0.0
    
    return render_template('dashboard.html',
                         selected_meals=selected_meals,
                         selected_calories=selected_calories,
                         selected_proteins=selected_proteins,
                         selected_date=selected_date.isoformat(),
                         selected_date_obj=selected_date,
                         today_date=today.isoformat(),
                         current_time=now.strftime('%H:%M'),
                         is_today=selected_date == today,
                         username=session['username'])

@app.route('/api/add_meal', methods=['POST'])
@require_login
def api_add_meal():
    proteins_str = request.form['proteins']
    calories_str = request.form['calories']
    meal_date = request.form['meal_date']
    meal_time = request.form['meal_time']
    
    # Validate the input data
    proteins, calories, validation_errors = validate_meal_data(proteins_str, calories_str)
    
    if validation_errors:
        return jsonify({
            "success": False,
            "field_errors": validation_errors
        }), 400
    
    # Validate date and time formats
    datetime_errors = validate_date_time(meal_date, meal_time)
    if datetime_errors:
        return jsonify({
            "success": False,
            "field_errors": datetime_errors
        }), 400
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO meals (user_id, proteins, calories, meal_date, meal_time) 
            VALUES (?, ?, ?, ?, ?)
        """, (session['user_id'], proteins, calories, meal_date, meal_time))
        
        # Get the inserted meal ID
        meal_id = cursor.lastrowid
        conn.commit()
        
        # Get updated totals for the date
        cursor.execute("""
            SELECT COALESCE(SUM(calories), 0), COALESCE(SUM(proteins), 0)
            FROM meals 
            WHERE user_id = ? AND meal_date = ?
        """, (session['user_id'], meal_date))
        totals = cursor.fetchone()
        total_calories = float(totals[0])
        total_proteins = float(totals[1])
        
        # Format the time for display
        time_obj = datetime.strptime(meal_time, '%H:%M').time()
        
        return jsonify({
            "success": True,
            "meal": {
                "id": meal_id,
                "proteins": float(proteins),
                "calories": int(calories),
                "meal_time": meal_time,
                "formatted_time": time_obj.strftime('%H:%M')
            },
            "updated_totals": {
                "calories": total_calories,
                "proteins": total_proteins
            }
        })
    except sqlite3.IntegrityError as e:
        app.logger.error(f"Database integrity error adding meal: {e}")
        return jsonify({
            "success": False,
            "field_errors": {"general": "Database error: Invalid data provided"}
        }), 400
    except sqlite3.Error as e:
        app.logger.error(f"Database error adding meal: {e}")
        return jsonify({
            "success": False,
            "field_errors": {"general": "Database error: Unable to save meal"}
        }), 500

@app.route('/api/delete_meal/<int:meal_id>', methods=['POST'])
@require_login
def api_delete_meal(meal_id):
    meal_date = request.form.get('meal_date')
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        # Get meal data before deleting (for totals calculation)
        cursor.execute("SELECT proteins, calories FROM meals WHERE id = ? AND user_id = ?", 
                     (meal_id, session['user_id']))
        meal_data = cursor.fetchone()
        
        if not meal_data:
            return jsonify({
                "success": False,
                "error": "Meal not found"
            }), 404
        
        deleted_proteins = float(meal_data['proteins'])
        deleted_calories = float(meal_data['calories'])
        
        # Delete the meal
        cursor.execute("DELETE FROM meals WHERE id = ? AND user_id = ?", 
                     (meal_id, session['user_id']))
        conn.commit()
        
        # Get updated totals for the date
        cursor.execute("""
            SELECT COALESCE(SUM(calories), 0), COALESCE(SUM(proteins), 0)
            FROM meals 
            WHERE user_id = ? AND meal_date = ?
        """, (session['user_id'], meal_date))
        totals = cursor.fetchone()
        total_calories = float(totals[0])
        total_proteins = float(totals[1])
        
        return jsonify({
            "success": True,
            "deleted_meal": {
                "proteins": deleted_proteins,
                "calories": deleted_calories
            },
            "updated_totals": {
                "calories": total_calories,
                "proteins": total_proteins
            }
        })
    except sqlite3.Error as e:
        app.logger.error(f"Database error deleting meal: {e}")
        return jsonify({
            "success": False,
            "error": "Database error: Unable to delete meal"
        }), 500

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
            cursor = conn.cursor()
            # Get summary statistics (all data for averages)
            cursor.execute("""
                SELECT meal_date, 
                       SUM(calories) as total_calories, 
                       SUM(proteins) as total_proteins,
                       COUNT(*) as meal_count
                FROM meals 
                WHERE user_id = ? AND meal_date BETWEEN ? AND ?
                GROUP BY meal_date
                ORDER BY meal_date DESC
            """, (session['user_id'], start_date, end_date))
            
            all_data = []
            for row in cursor.fetchall():
                # Parse the date string back to a date object
                try:
                    date_obj = datetime.strptime(row['meal_date'], '%Y-%m-%d').date()
                    
                    all_data.append({
                        'date': date_obj,
                        'calories': float(row['total_calories']),
                        'proteins': float(row['total_proteins']),
                        'meal_count': row['meal_count']
                    })
                except ValueError:
                    app.logger.warning(f"Skipping date record with corrupt date format: '{row['meal_date']}' for user {session['user_id']}")
                    continue
            
            if all_data:
                total_days = len(all_data)
                total_proteins = sum(day['proteins'] for day in all_data)
                avg_calories = sum(day['calories'] for day in all_data) / total_days
                avg_proteins = total_proteins / total_days
                
                # Calculate pagination
                total_pages = (total_days + per_page - 1) // per_page
                offset = (page - 1) * per_page
                range_data = all_data[offset:offset + per_page]
                
        except sqlite3.Error as e:
            app.logger.error(f"Database error in view_range: {e}")
            # Provide fallback empty data
            range_data = None
    
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