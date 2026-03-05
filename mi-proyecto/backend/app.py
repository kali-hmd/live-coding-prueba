"""
PRIVATE NOTES API - Flask Backend
All functionality in one file for simplicity
Auth: JWT + Bcrypt password hashing
DB: SQLite with proper foreign keys
"""

import os
import sqlite3
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path

import jwt
from bcrypt import checkpw, gensalt, hashpw
from flask import Flask, jsonify, request
from flask_cors import CORS

# ========================================
# CONFIGURATION
# ========================================

app = Flask(__name__)
CORS(app)

# Configuration
app.config['JSON_SORT_KEYS'] = False
app.config['MAX_CONTENT_LENGTH'] = 1 * 1024 * 1024  # 1MB max request size
JWT_SECRET = os.getenv('JWT_SECRET', 'your_super_secret_key_change_in_prod')
JWT_EXPIRATION = timedelta(days=7)
DB_PATH = os.getenv('DB_PATH', 'data/notes.db')

# Rate limiting dictionary (simple in-memory rate limiting)
# In production, use Redis or similar
login_attempts = {}  # Format: {email: (count, timestamp)}

# Ensure data directory exists
Path('data').mkdir(exist_ok=True)

# ========================================
# DATABASE INITIALIZATION
# ========================================

def get_db_connection():
    """Get database connection with row factory"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


def init_db():
    """Initialize database tables"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Notes table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')

    conn.commit()
    conn.close()
    print('✅ Database initialized')


# ========================================
# PASSWORD HASHING UTILITIES
# ========================================

def hash_password(password: str) -> str:
    """Hash password using bcrypt"""
    return hashpw(password.encode('utf-8'), gensalt(10)).decode('utf-8')


def verify_password(password: str, password_hash: str) -> bool:
    """Verify password against hash"""
    return checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))


# ========================================
# JWT UTILITIES
# ========================================

def generate_token(user_id: int) -> str:
    """Generate JWT token"""
    payload = {
        'userId': user_id,
        'exp': datetime.utcnow() + JWT_EXPIRATION,
        'iat': datetime.utcnow()
    }
    return jwt.encode(payload, JWT_SECRET, algorithm='HS256')


def verify_token(token: str) -> dict:
    """Verify JWT token and return payload"""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
        return payload
    except jwt.ExpiredSignatureError:
        raise ValueError('Token expired')
    except jwt.InvalidTokenError:
        raise ValueError('Invalid token')


# ========================================
# AUTH DECORATOR
# ========================================

def require_auth(f):
    """Decorator to require valid JWT token"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization')

        if not auth_header:
            return jsonify({'error': 'No token provided'}), 401

        try:
            # Extract token from "Bearer <token>"
            token = auth_header.split(' ')[1]
            payload = verify_token(token)
            request.user_id = payload['userId']
        except (IndexError, ValueError, jwt.InvalidTokenError):
            return jsonify({'error': 'Invalid or expired token'}), 401

        return f(*args, **kwargs)

    return decorated_function


# ========================================
# VALIDATION UTILITIES
# ========================================

def validate_email(email: str) -> bool:
    """Validate email format and length - prevent DOS attacks"""
    import re
    if not email:
        return False
    # Limit email length to prevent DOS
    if len(email) > 32:
        return False
    # Prevent extremely long local part
    if len(email.split('@')[0]) > 32:
        return False
    pattern = r'^[^\s@]+@[^\s@]+\.[^\s@]+$'
    return re.match(pattern, email) is not None


def validate_password(password: str) -> bool:
    """Validate password (min 6 chars, max 128 chars) - prevent DOS and memory attacks"""
    if not password:
        return False
    # Min length
    if len(password) < 6:
        return False
    # Max length to prevent DOS/memory exhaustion attacks on bcrypt
    # bcrypt can be slow with very long passwords
    if len(password) > 25:
        return False
    return True


def validate_note(title: str, content: str) -> bool:
    """Validate note title and content - prevent DOS and injection attacks"""
    if not title or not content:
        return False
    # Prevent empty after strip
    if len(title.strip()) == 0 or len(content.strip()) == 0:
        return False
    # Strict length limits
    if len(title) > 200:  # Max 200 chars for title
        return False
    if len(content) > 10000:  # Max 10KB for content
        return False
    # Prevent notes with only whitespace
    if title.strip() == '' or content.strip() == '':
        return False
    return True


# ========================================
# AUTH ROUTES
# ========================================

@app.route('/api/auth/register', methods=['POST'])
def register():
    """Register new user with security validations"""
    data = request.get_json() or {}

    email = data.get('email', '').strip().lower()  # Normalize email
    password = data.get('password', '')
    confirm_password = data.get('confirmPassword', '')

    # Validation
    if not email:
        return jsonify({'error': 'Email is required'}), 400

    if not validate_email(email):
        return jsonify({'error': 'Invalid email format or too long'}), 400

    if not validate_password(password):
        return jsonify({'error': 'Password must be 6-128 characters'}), 400

    if password != confirm_password:
        return jsonify({'error': 'Passwords do not match'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Check if user exists
        cursor.execute('SELECT id FROM users WHERE LOWER(email) = ?', (email.lower(),))
        if cursor.fetchone():
            conn.close()
            return jsonify({'error': 'Email already registered'}), 409

        # Hash password (bcrypt handles the heavy lifting)
        password_hash = hash_password(password)
        
        # Insert user
        cursor.execute(
            'INSERT INTO users (email, password_hash) VALUES (?, ?)',
            (email, password_hash)
        )
        conn.commit()
        user_id = cursor.lastrowid

        # Generate token
        token = generate_token(user_id)

        return jsonify({
            'message': 'User created',
            'token': token
        }), 201

    except Exception as e:
        conn.close()
        print(f'Registration error: {e}')
        return jsonify({'error': 'Registration failed'}), 500

    finally:
        conn.close()


@app.route('/api/auth/login', methods=['POST'])
def login():
    """Login user with rate limiting"""
    from datetime import datetime
    
    data = request.get_json() or {}
    email = data.get('email', '').strip().lower()  # Normalize email
    password = data.get('password', '')

    if not email or not password:
        return jsonify({'error': 'Email and password required'}), 400

    # Rate limiting: max 5 attempts per 15 minutes
    now = datetime.utcnow()
    if email in login_attempts:
        count, timestamp = login_attempts[email]
        # Reset if older than 15 minutes
        if (now - timestamp).total_seconds() > 900:
            login_attempts[email] = (0, now)
        # Block if too many attempts
        elif count >= 5:
            return jsonify({'error': 'Too many login attempts. Try again later'}), 429
        else:
            login_attempts[email] = (count + 1, timestamp)
    else:
        login_attempts[email] = (1, now)

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            'SELECT id, password_hash FROM users WHERE email = ?',
            (email,)
        )
        user = cursor.fetchone()

        if not user or not verify_password(password, user['password_hash']):
            conn.close()
            # Don't reset attempts here, let them accumulate
            return jsonify({'error': 'Invalid credentials'}), 401

        # Reset login attempts on successful login
        if email in login_attempts:
            del login_attempts[email]

        # Generate token
        token = generate_token(user['id'])

        return jsonify({
            'message': 'Login successful',
            'token': token
        }), 200

    except Exception as e:
        conn.close()
        print(f'Login error: {e}')
        return jsonify({'error': 'Login failed'}), 500

    finally:
        conn.close()


# ========================================
# NOTES ROUTES
# ========================================

@app.route('/api/notes', methods=['GET'])
@require_auth
def get_notes():
    """Get all notes for authenticated user (newest first)"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            '''SELECT id, title, created_at FROM notes 
               WHERE user_id = ? 
               ORDER BY created_at DESC''',
            (request.user_id,)
        )
        notes = [dict(row) for row in cursor.fetchall()]

        return jsonify(notes), 200

    except Exception as e:
        print(f'Get notes error: {e}')
        return jsonify({'error': 'Failed to fetch notes'}), 500

    finally:
        conn.close()


@app.route('/api/notes', methods=['POST'])
@require_auth
def create_note():
    """Create new note with strict validation"""
    data = request.get_json() or {}

    title = data.get('title', '').strip()
    content = data.get('content', '').strip()
    user_id = request.user_id

    # Strict validation
    if not validate_note(title, content):
        return jsonify({'error': 'Invalid title or content'}), 400

    # Additional length checks (prevent resource exhaustion)
    if len(title.encode('utf-8')) > 512:  # 512 bytes max for title
        return jsonify({'error': 'Title too long'}), 400
    
    if len(content.encode('utf-8')) > 100000:  # ~100KB max for content
        return jsonify({'error': 'Content too long'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            '''INSERT INTO notes (user_id, title, content) 
               VALUES (?, ?, ?)''',
            (user_id, title, content)
        )
        conn.commit()
        note_id = cursor.lastrowid

        return jsonify({
            'id': note_id,
            'title': title,
            'content': content
        }), 201

    except Exception as e:
        conn.close()
        print(f'Create note error: {e}')
        return jsonify({'error': 'Failed to create note'}), 500

    finally:
        conn.close()


@app.route('/api/notes/<int:note_id>', methods=['GET'])
@require_auth
def get_note(note_id):
    """Get single note (ownership check)"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            '''SELECT id, title, content, created_at, updated_at 
               FROM notes 
               WHERE id = ? AND user_id = ?''',
            (note_id, request.user_id)
        )
        note = cursor.fetchone()

        if not note:
            conn.close()
            return jsonify({'error': 'Note not found'}), 404

        return jsonify(dict(note)), 200

    except Exception as e:
        print(f'Get note error: {e}')
        return jsonify({'error': 'Failed to fetch note'}), 500

    finally:
        conn.close()


@app.route('/api/notes/<int:note_id>', methods=['PUT'])
@require_auth
def update_note(note_id):
    """Update note (ownership check)"""
    data = request.get_json() or {}

    title = data.get('title', '').strip()
    content = data.get('content', '').strip()

    # Validation
    if not validate_note(title, content):
        return jsonify({'error': 'Invalid title or content'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Check ownership
        cursor.execute(
            'SELECT id FROM notes WHERE id = ? AND user_id = ?',
            (note_id, request.user_id)
        )
        if not cursor.fetchone():
            conn.close()
            return jsonify({'error': 'Note not found'}), 404

        # Update note
        cursor.execute(
            '''UPDATE notes 
               SET title = ?, content = ?, updated_at = CURRENT_TIMESTAMP 
               WHERE id = ?''',
            (title, content, note_id)
        )
        conn.commit()

        return jsonify({'message': 'Note updated'}), 200

    except Exception as e:
        conn.close()
        print(f'Update note error: {e}')
        return jsonify({'error': 'Failed to update note'}), 500

    finally:
        conn.close()


@app.route('/api/notes/<int:note_id>', methods=['DELETE'])
@require_auth
def delete_note(note_id):
    """Delete note (ownership check)"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Check ownership
        cursor.execute(
            'SELECT id FROM notes WHERE id = ? AND user_id = ?',
            (note_id, request.user_id)
        )
        if not cursor.fetchone():
            conn.close()
            return jsonify({'error': 'Note not found'}), 404

        # Delete note
        cursor.execute('DELETE FROM notes WHERE id = ?', (note_id,))
        conn.commit()

        return jsonify({'message': 'Note deleted'}), 200

    except Exception as e:
        conn.close()
        print(f'Delete note error: {e}')
        return jsonify({'error': 'Failed to delete note'}), 500

    finally:
        conn.close()


# ========================================
# HEALTH CHECK
# ========================================

@app.route('/api/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({'status': 'ok'}), 200


# ========================================
# ERROR HANDLERS
# ========================================

@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return jsonify({'error': 'Endpoint not found'}), 404


@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    print(f'Internal server error: {error}')
    return jsonify({'error': 'Internal server error'}), 500


# ========================================
# MAIN
# ========================================

if __name__ == '__main__':
    init_db()
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)