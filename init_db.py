#!/usr/bin/env python3
"""
Database initialization script for Frediet SQLite database.
Run this script to create a fresh, empty database with proper schema.
"""

import sqlite3
import passwords

def create_database():
    """Create the SQLite database with proper schema, constraints, and indexes."""
    
    conn = sqlite3.connect(passwords.DB_FILE_PATH, timeout=30.0)
    try:
        # Enable foreign key constraints
        conn.execute("PRAGMA foreign_keys = ON")
        
        # Create users table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE 
                    CHECK (LENGTH(username) <= 12 AND LENGTH(username) > 0),
                password TEXT NOT NULL 
                    CHECK (LENGTH(password) <= 50 AND LENGTH(password) > 0)
            )
        """)
        
        # Create meals table  
        conn.execute("""
            CREATE TABLE IF NOT EXISTS meals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                proteins REAL NOT NULL 
                    CHECK (proteins >= 0.0 AND proteins <= 999.9 AND proteins = ROUND(proteins, 1)),
                calories INTEGER NOT NULL 
                    CHECK (calories >= 0 AND calories <= 9999),
                meal_date TEXT NOT NULL 
                    CHECK (meal_date GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]'),
                meal_time TEXT NOT NULL 
                    CHECK (meal_time GLOB '[0-2][0-9]:[0-5][0-9]'),
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            )
        """)
        
        # Create indexes for better query performance
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_user_date 
            ON meals (user_id, meal_date)
        """)
        
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_meal_date 
            ON meals (meal_date)
        """)
        
        conn.commit()
        print(f"✅ Database '{passwords.DB_FILE_PATH}' created successfully!")
        print("📊 Schema created with tables: users, meals")
        print("🔗 Indexes created: idx_user_date, idx_meal_date")
        print("🔒 Foreign key constraints enabled")
        print("📝 Database is ready for use - completely empty, no default users")
        
    except sqlite3.Error as e:
        print(f"❌ Error creating database: {e}")
        conn.rollback()
    finally:
        conn.close()

def check_database():
    """Check if database exists and show basic info."""
    try:
        conn = sqlite3.connect(passwords.DB_FILE_PATH, timeout=30.0)
        cursor = conn.cursor()
        
        # Check if tables exist
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name NOT LIKE 'sqlite_%'
        """)
        tables = cursor.fetchall()
        
        if not tables:
            print(f"❌ Database '{passwords.DB_FILE_PATH}' exists but has no tables")
            return False
            
        print(f"✅ Database '{passwords.DB_FILE_PATH}' exists")
        print(f"📊 Tables found: {', '.join([table[0] for table in tables])}")
        
        # Count users and meals
        cursor.execute("SELECT COUNT(*) FROM users")
        user_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM meals")
        meal_count = cursor.fetchone()[0]
        
        print(f"👥 Users: {user_count}")
        print(f"🍽️ Meals: {meal_count}")
        
        conn.close()
        return True
        
    except sqlite3.Error as e:
        print(f"❌ Error checking database: {e}")
        return False

if __name__ == "__main__":
    import sys
    import os
    
    # Check if passwords.py exists
    if not os.path.exists("passwords.py"):
        print("❌ passwords.py not found!")
        print("📝 Please copy passwords.example.py to passwords.py and configure it")
        sys.exit(1)
    
    if len(sys.argv) > 1 and sys.argv[1] == "check":
        check_database()
    else:
        print("🗄️ Initializing Frediet SQLite database...")
        
        # Check if database already exists
        if os.path.exists(passwords.DB_FILE_PATH):
            response = input(f"⚠️  Database '{passwords.DB_FILE_PATH}' already exists. Overwrite? (y/N): ")
            if response.lower() != 'y':
                print("❌ Aborted")
                sys.exit(1)
            os.remove(passwords.DB_FILE_PATH)
            print(f"🗑️ Removed existing database")
        
        create_database()