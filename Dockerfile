# Use Python 3.10 as the base image
FROM python:3.13-slim

# Set working directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY app.py gunicorn_config.py ./

# Create a volume mount point for the SQLite database
VOLUME /app/data
VOLUME /app/logs

# Set environment variables
ENV DATABASE_FILE=/app/data/visitor_tracking.db

# Expose port 5000
EXPOSE 5000

# Run Gunicorn with the application
CMD ["gunicorn", "--config", "gunicorn_config.py", "app:app"]