"""
Database initialization script for Frediet SQLite database.
Run this script to create a fresh, empty database with proper schema.
"""

import sqlite3
import logging
import os

DB_FILE_PATH = "/app/data/frediet.db"

logger = logging.getLogger(__name__)

def create_database():
    """Create the SQLite database with proper schema, constraints, and indexes."""
    
    logger.info("Starting database initialization", extra={'db_path': DB_FILE_PATH})
    
    conn = sqlite3.connect(DB_FILE_PATH, timeout=5.0)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE 
                    CHECK (LENGTH(username) <= 12 AND LENGTH(username) > 0),
                password TEXT NOT NULL 
                    CHECK (LENGTH(password) <= 50 AND LENGTH(password) > 0)
            )
        """)
        
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
        
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_user_date 
            ON meals (user_id, meal_date)
        """)
        
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_meal_date 
            ON meals (meal_date)
        """)
        
        conn.commit()
        logger.info("Database created successfully", extra={
            'db_path': DB_FILE_PATH,
            'tables': ['users', 'meals'],
            'indexes': ['idx_user_date', 'idx_meal_date']
        })
        print(f"✅ Database '{DB_FILE_PATH}' created successfully!")
        print("📊 Schema created with tables: users, meals")
        print("🔗 Indexes created: idx_user_date, idx_meal_date")
        print("🔒 Foreign key constraints enabled")
        print("📝 Database is ready for use - completely empty, no default users")
        
    except sqlite3.Error as e:
        logger.error("Error creating database", extra={'db_path': DB_FILE_PATH, 'error': str(e)})
        print(f"❌ Error creating database: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":

    print("🗄️ Frediet database initialization...")
    
    if os.path.exists(DB_FILE_PATH):
        print(f"✅ Database '{DB_FILE_PATH}' already exists, skipping initialization")
    else:
        print(f"📊 Database not found. Creating new database...")
        create_database()