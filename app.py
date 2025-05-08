# app.py
from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
import os
import re
from datetime import datetime

app = Flask(__name__)

CORS(app, resources={
    r"/*": {
        "origins": ["http://localhost:3000", "https://ultravidz.com", "https://www.ultravidz.com"],
        "methods": ["POST", "GET", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"]
    }
})

# SQLite database file from environment variable with fallback
DATABASE_FILE = os.environ.get('DATABASE_FILE', 'visitor_tracking.db')

def init_db():
    """Initialize the SQLite database with required tables"""
    # Ensure data directory exists
    os.makedirs(os.path.dirname(DATABASE_FILE), exist_ok=True)
    
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    
    # Create visitors table if it doesn't exist
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS visits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        visitor_id TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        page_url TEXT NOT NULL,
        referrer TEXT,
        is_new_visitor BOOLEAN NOT NULL
    )
    ''')
    
    # Create stats table for aggregate data
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS stats (
        id INTEGER PRIMARY KEY,
        visit_count INTEGER DEFAULT 0,
        new_visitor_count INTEGER DEFAULT 0
    )
    ''')
    
    # Insert initial stats row if it doesn't exist
    cursor.execute('INSERT OR IGNORE INTO stats (id, visit_count, new_visitor_count) VALUES (1, 0, 0)')
    
    # Create email subscribers table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS subscribers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        name TEXT,
        subscribed_at TEXT NOT NULL,
        visitor_id TEXT,
        source_page TEXT,
        comments TEXT,
        active BOOLEAN DEFAULT 1
    )
    ''')
    
    conn.commit()
    conn.close()

def get_db_connection():
    """Get a database connection"""
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row  # Enables column name access
    return conn

def is_valid_email(email):
    """Basic email validation"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

@app.route('/track', methods=['POST'])
def track_visitor():
    try:
        # Get data from request
        visitor_data = request.json
        
        # Validate required fields
        required_fields = ['visitor_id', 'is_new', 'timestamp', 'page_url']
        if not all(field in visitor_data for field in required_fields):
            return jsonify({"error": "Missing required fields"}), 400
        
        # Connect to database
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Insert visit record
        cursor.execute('''
        INSERT INTO visits (visitor_id, timestamp, page_url, referrer, is_new_visitor)
        VALUES (?, ?, ?, ?, ?)
        ''', (
            visitor_data["visitor_id"],
            visitor_data["timestamp"],
            visitor_data["page_url"],
            visitor_data.get("referrer", "unknown"),
            visitor_data["is_new"]
        ))
        
        # Update stats
        cursor.execute('UPDATE stats SET visit_count = visit_count + 1 WHERE id = 1')
        
        if visitor_data["is_new"]:
            cursor.execute('UPDATE stats SET new_visitor_count = new_visitor_count + 1 WHERE id = 1')
        
        # Commit changes and close connection
        conn.commit()
        conn.close()
        
        return jsonify({"success": True}), 200
    
    except Exception as e:
        app.logger.error(f"Error processing tracking data: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500

@app.route('/subscribe', methods=['POST'])
def subscribe():
    """Endpoint to register a user's email"""
    try:
        # Get data from request
        data = request.json
        
        # Check required fields
        if not data or 'email' not in data:
            return jsonify({"error": "Email is required"}), 400
        
        email = data['email'].strip().lower()
        
        # Validate email format
        if not is_valid_email(email):
            return jsonify({"error": "Invalid email format"}), 400
        
        # Optional fields
        name = data.get('name', '').strip()
        visitor_id = data.get('visitor_id', '')
        source_page = data.get('source_page', '')
        comments = data.get('comments', '')  # Add comments field
        
        # Get current timestamp
        current_time = datetime.now().isoformat()
        
        # Connect to database
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            # Check if email already exists
            existing = cursor.execute('SELECT email FROM subscribers WHERE email = ?', (email,)).fetchone()
            
            if existing:
                # Update existing subscription if needed
                cursor.execute('''
                UPDATE subscribers 
                SET active = 1, 
                    name = CASE WHEN ? != '' THEN ? ELSE name END,
                    visitor_id = CASE WHEN ? != '' THEN ? ELSE visitor_id END,
                    source_page = CASE WHEN ? != '' THEN ? ELSE source_page END,
                    comments = CASE WHEN ? != '' THEN ? ELSE comments END
                WHERE email = ?
                ''', (name, name, visitor_id, visitor_id, source_page, source_page, comments, comments, email))
                
                message = "Email subscription updated"
            else:
                # Insert new subscription
                cursor.execute('''
                INSERT INTO subscribers (email, name, subscribed_at, visitor_id, source_page, comments)
                VALUES (?, ?, ?, ?, ?, ?)
                ''', (email, name, current_time, visitor_id, source_page, comments))
                
                message = "Email subscription successful"
            
            conn.commit()
            return jsonify({"success": True, "message": message}), 200
            
        except sqlite3.IntegrityError:
            # Handle race condition if two subscriptions happen simultaneously
            conn.rollback()
            return jsonify({"success": True, "message": "Email already registered"}), 200
        
    except Exception as e:
        app.logger.error(f"Error processing subscription: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if 'conn' in locals():
            conn.close()

@app.route('/unsubscribe', methods=['POST'])
def unsubscribe():
    """Endpoint to unsubscribe an email"""
    try:
        # Get data from request
        data = request.json
        
        # Check required fields
        if not data or 'email' not in data:
            return jsonify({"error": "Email is required"}), 400
        
        email = data['email'].strip().lower()
        
        # Connect to database
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Mark as inactive rather than deleting
        cursor.execute('UPDATE subscribers SET active = 0 WHERE email = ?', (email,))
        
        if cursor.rowcount > 0:
            conn.commit()
            return jsonify({"success": True, "message": "Successfully unsubscribed"}), 200
        else:
            return jsonify({"error": "Email not found"}), 404
        
    except Exception as e:
        app.logger.error(f"Error processing unsubscribe: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if 'conn' in locals():
            conn.close()

@app.route('/subscribers', methods=['GET'])
def get_subscribers():
    """Endpoint to get subscribers with optional filtering and pagination"""
    try:
        # Pagination parameters
        page = request.args.get('page', 1, type=int)
        limit = min(request.args.get('limit', 50, type=int), 100)
        
        # Filter parameters
        active_only = request.args.get('active', 'true').lower() == 'true'
        
        # Calculate offset
        offset = (page - 1) * limit
        
        # Connect to database
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Build query based on filters
        query = "SELECT id, email, name, subscribed_at, visitor_id, source_page, comments, active FROM subscribers"
        params = []
        
        if active_only:
            query += " WHERE active = 1"
        
        # Add ordering and pagination
        query += " ORDER BY id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        # Execute query
        subscribers = cursor.execute(query, params).fetchall()
        
        # Get total count for pagination info
        count_query = "SELECT COUNT(*) as count FROM subscribers"
        if active_only:
            count_query += " WHERE active = 1"
        
        total = cursor.execute(count_query).fetchone()['count']
        
        # Convert to list of dictionaries
        subscriber_list = []
        for sub in subscribers:
            subscriber_list.append({
                "id": sub["id"],
                "email": sub["email"],
                "name": sub["name"],
                "subscribed_at": sub["subscribed_at"],
                "visitor_id": sub["visitor_id"],
                "source_page": sub["source_page"],
                "comments": sub["comments"],
                "active": bool(sub["active"])
            })
        
        conn.close()
        
        return jsonify({
            "subscribers": subscriber_list,
            "page": page,
            "limit": limit,
            "total": total,
            "total_pages": (total + limit - 1) // limit
        }), 200
        
    except Exception as e:
        app.logger.error(f"Error retrieving subscribers: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500

@app.route('/stats', methods=['GET'])
def get_stats():
    """Endpoint to get basic visitor statistics"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get aggregate stats
        stats_row = cursor.execute('SELECT visit_count, new_visitor_count FROM stats WHERE id = 1').fetchone()
        
        # Get latest visits (last 10)
        latest_visits = cursor.execute('''
        SELECT visitor_id, timestamp, page_url, referrer
        FROM visits
        ORDER BY id DESC
        LIMIT 10
        ''').fetchall()
        
        # Get subscriber count
        subscriber_count = cursor.execute('SELECT COUNT(*) as count FROM subscribers WHERE active = 1').fetchone()['count']
        
        # Convert latest visits to list of dictionaries
        latest_visits_list = []
        for visit in latest_visits:
            latest_visits_list.append({
                "visitor_id": visit["visitor_id"],
                "timestamp": visit["timestamp"],
                "page_url": visit["page_url"],
                "referrer": visit["referrer"]
            })
        
        stats = {
            "total_visits": stats_row["visit_count"],
            "total_unique_visitors": stats_row["new_visitor_count"],
            "total_subscribers": subscriber_count,
            "latest_visits": latest_visits_list
        }
        
        conn.close()
        return jsonify(stats), 200
    
    except Exception as e:
        app.logger.error(f"Error retrieving stats: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500

@app.route('/visitors', methods=['GET'])
def get_visitors():
    """Endpoint to get more detailed visitor information with optional filtering"""
    try:
        # Get query parameters for filtering
        page = request.args.get('page', 1, type=int)
        limit = min(request.args.get('limit', 50, type=int), 100)  # Cap at 100 for performance
        page_url = request.args.get('page_url')
        
        # Calculate offset for pagination
        offset = (page - 1) * limit
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Build query based on filters
        query = "SELECT visitor_id, timestamp, page_url, referrer FROM visits"
        params = []
        
        if page_url:
            query += " WHERE page_url LIKE ?"
            params.append(f"%{page_url}%")
        
        query += " ORDER BY id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        # Execute query
        visitors = cursor.execute(query, params).fetchall()
        
        # Convert to list of dictionaries
        visitor_list = []
        for visit in visitors:
            visitor_list.append({
                "visitor_id": visit["visitor_id"],
                "timestamp": visit["timestamp"],
                "page_url": visit["page_url"],
                "referrer": visit["referrer"]
            })
        
        conn.close()
        return jsonify({"visitors": visitor_list, "page": page, "limit": limit}), 200
    
    except Exception as e:
        app.logger.error(f"Error retrieving visitors: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500

# Add a simple health check endpoint
@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy"}), 200

# Initialize database when the application starts
init_db()