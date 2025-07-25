# Create a copy of this file in the same directory, and call it "passwords.py", then personalize the configuration

app_secret_key = "your_flask_secret_key" # generate a long alphanumeric string and put it here. Never divulge it, because whoever has it can forge false user sessions, that means that they can log in as any user and expose their data.

DB_FILE_PATH = "frediet.db" # SQLite database file path, relative to the server.py file

flask_port = 15346 # Don't change this. If the app's errors complain that the port is occupied, then change this, and remember to also update the port in your reverse proxy's configuration

flask_environment = 'production' # don't change this. If you're a developer who's looking to modify the code, set this to this exact string: 'development'