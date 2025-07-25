FROM python:3.13.5-slim-bookworm

# Install sqlite3 for database console access
RUN apt-get update && apt-get install -y sqlite3 && rm -rf /var/lib/apt/lists/*

# Create app user with home directory for console access
RUN groupadd -g 1000 frediet && \
    useradd --create-home --no-log-init -u 1000 -g 1000 frediet

# Set up application
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Create data directory with proper permissions
RUN mkdir -p /app/data && chown frediet:frediet /app/data

# Switch to non-root user
USER frediet

ENTRYPOINT ["/entrypoint.sh"]