from flask import Flask, jsonify, request, send_from_directory, render_template, redirect, url_for, flash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from reportlab.lib.pagesizes import letter, A4, A5
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from reportlab.lib import colors
from werkzeug.security import generate_password_hash, check_password_hash
import os
import google.generativeai as genai
from textwrap import wrap
import sqlite3
from datetime import datetime
import secrets
import time
import io
from reportlab.pdfbase.pdfmetrics import stringWidth

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)  # Secure random secret key

# Configure Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Configure SQLite Database
def init_db():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS files (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        filename TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS password_resets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        token TEXT NOT NULL,
        expires_at INTEGER NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )''')
    conn.commit()
    conn.close()

init_db()

# User Model for Flask-Login
class User(UserMixin):
    def __init__(self, id, username):
        self.id = id
        self.username = username

@login_manager.user_loader
def load_user(user_id):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('SELECT id, username FROM users WHERE id = ?', (user_id,))
    user_data = c.fetchone()
    conn.close()
    if user_data:
        return User(user_data[0], user_data[1])
    return None

# Configure Gemini API
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', 'AIzaSyCN0iEm3n5gsECoJQN7whd_kjiT0kkyvdg')  # Use env var in production
genai.configure(api_key=GEMINI_API_KEY)

# Helper to clean and format lines
def clean_line(line):
    line = line.replace("**", "").strip()
    line = line.replace("*", "•").strip()
    if line.startswith("-") or line.startswith("*"):
        return "• " + line.lstrip("-•").strip()
    return line

# Get answer from Gemini
def get_topic_solution(topic):
    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content(topic)
        return response.text
    except Exception as e:
        return f"Error: {e}"

# Signup Route
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        email = request.form.get('email')
        if not all([username, password, email]):
            flash('All fields are required.', 'error')
            return render_template('signup.html')
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        try:
            c.execute('INSERT INTO users (username, password, email) VALUES (?, ?, ?)',
                      (username, generate_password_hash(password), email))
            conn.commit()
            flash('Signup successful! Please log in.', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Username or email already exists.', 'error')
        finally:
            conn.close()
    return render_template('signup.html')

# Login Route
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('SELECT id, username, password FROM users WHERE username = ?', (username,))
        user_data = c.fetchone()
        conn.close()
        if user_data and check_password_hash(user_data[2], password):
            user = User(user_data[0], user_data[1])
            login_user(user)
            flash('Logged in successfully!', 'success')
            return redirect(url_for('dashboard'))
        flash('Invalid username or password.', 'error')
    return render_template('login.html')

# Forgot Password Route
@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email')
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('SELECT id FROM users WHERE email = ?', (email,))
        user_data = c.fetchone()
        if user_data:
            token = secrets.token_urlsafe(32)
            expires_at = int(time.time()) + 3600  # Token expires in 1 hour
            c.execute('INSERT INTO password_resets (user_id, token, expires_at) VALUES (?, ?, ?)',
                      (user_data[0], token, expires_at))
            conn.commit()
            print(f"Password reset token for {email}: {token}")
            flash('A password reset link has been sent to your email.', 'success')
        else:
            flash('Email not found.', 'error')
        conn.close()
    return render_template('forgot_password.html')

# Reset Password Route
@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('SELECT user_id, expires_at FROM password_resets WHERE token = ?', (token,))
    reset_data = c.fetchone()
    if not reset_data or reset_data[1] < int(time.time()):
        flash('Invalid or expired token.', 'error')
        conn.close()
        return redirect(url_for('forgot_password'))
    if request.method == 'POST':
        password = request.form.get('password')
        c.execute('UPDATE users SET password = ? WHERE id = ?',
                  (generate_password_hash(password), reset_data[0]))
        c.execute('DELETE FROM password_resets WHERE token = ?', (token,))
        conn.commit()
        conn.close()
        flash('Password reset successfully. Please log in.', 'success')
        return redirect(url_for('login'))
    conn.close()
    return render_template('reset_password.html', token=token)

# Logout Route
@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out successfully.', 'success')
    return redirect(url_for('login'))

# Dashboard Route
@app.route('/dashboard')
@login_required
def dashboard():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('SELECT filename, created_at FROM files WHERE user_id = ? ORDER BY created_at DESC', (current_user.id,))
    files = c.fetchall()
    conn.close()
    return render_template('dashboard.html', files=files)

# PDF Generation Endpoint
@app.route('/generate-pdf', methods=['POST'])
@login_required
def generate_pdf():
    data = request.json
    topics = data.get('topics', [])
    book_name = data.get('bookName', 'Generated Topic Book')
    paper_size_name = data.get('paperSize', 'Letter')
    font_size = int(data.get('fontSize', 12))
    font_style = data.get('fontStyle', 'Helvetica')

    if not topics:
        return jsonify({"error": "No topics provided"}), 400

    # Map paper size and font style
    paper_size_map = {'A4': A4, 'A5': A5, 'Letter': letter}
    font_map = {'Helvetica': 'Helvetica', 'Times': 'Times-Roman', 'Courier': 'Courier'}
    paper_size = paper_size_map.get(paper_size_name, letter)
    font_style = font_map.get(font_style, 'Helvetica')

    # Sanitize book name for filename
    safe_book_name = ''.join(c for c in book_name if c.isalnum() or c in (' ', '_')).replace(' ', '_')
    user_dir = os.path.join('user_files', str(current_user.id))
    os.makedirs(user_dir, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"{safe_book_name}_{timestamp}.pdf"
    filepath = os.path.join(user_dir, filename)

    # Cache Gemini responses
    topic_responses = {}
    for topic in topics:
        topic_responses[topic] = get_topic_solution(topic)

    # Initialize PDF
    c = canvas.Canvas(filepath, pagesize=paper_size)
    width, height = paper_size
    margin = 0.75 * inch
    top_margin = inch
    bottom_margin = 0.75 * inch
    page_number = 1
    toc_entries = []

    # Cover Page
    c.setFont(f"{font_style}-Bold", font_size + 16)
    c.drawCentredString(width / 2, height * 0.6, book_name)
    c.setFont(font_style, font_size + 4)
    c.drawCentredString(width / 2, height * 0.5, f"By {current_user.username}")
    c.setFont(font_style, font_size)
    c.drawCentredString(width / 2, height * 0.45, f"Generated on {datetime.now().strftime('%B %d, %Y')}")
    c.rect(margin, margin, width - 2 * margin, height - 2 * margin, stroke=1, fill=0)
    c.showPage()

    # Copyright Page (Roman numeral i)
    c.setFont(font_style, font_size - 2)
    c.drawCentredString(width / 2, height * 0.5, f"Copyright © {datetime.now().year} {current_user.username}")
    c.drawCentredString(width / 2, height * 0.45, "All rights reserved.")
    c.drawCentredString(width / 2, 0.5 * inch, "i")
    c.showPage()

    # Table of Contents (Roman numeral ii)
    toc_start_page = "ii"
    c.setFont(f"{font_style}-Bold", font_size + 6)
    c.drawCentredString(width / 2, height - top_margin, "Table of Contents")
    toc_y = height - top_margin - 40
    c.setFont(font_style, font_size)
    c.drawCentredString(width / 2, 0.5 * inch, toc_start_page)
    c.showPage()

    # Content Pages (Arabic numerals)
    page_number = 1
    for i, topic in enumerate(topics, 1):
        start_page = page_number
        # Chapter Title Page
        c.setFont(f"{font_style}-Bold", font_size + 8)
        chapter_title = f"Chapter {i}: {topic}"
        c.drawCentredString(width / 2, height * 0.6, chapter_title)
        title_width = stringWidth(chapter_title, f"{font_style}-Bold", font_size + 8)
        underline_x_start = (width - title_width) / 2
        underline_x_end = underline_x_start + title_width
        c.line(underline_x_start, height * 0.6 - 10, underline_x_end, height * 0.6 - 10)
        c.showPage()
        page_number += 1

        # Chapter Content
        answer = topic_responses[topic]
        lines = [clean_line(line) for line in answer.splitlines() if line.strip()]
        text_object = c.beginText(margin, height - top_margin - 20)
        text_object.setFont(font_style, font_size)
        text_object.setLeading(font_size * 1.2)  # 1.2x line spacing
        text_object.setTextOrigin(margin, height - top_margin - 20)

        for line in lines:
            is_heading = line.strip().lower().endswith(":") or line.strip().lower().startswith("example:")
            is_bullet = line.startswith("•")
            wrapped = wrap(line, width=int((width - 2 * margin) / (font_size / 2)))

            for wline in wrapped:
                if text_object.getY() < bottom_margin + 60:
                    c.drawText(text_object)
                    c.setFont(font_style, font_size - 2)
                    c.drawString(margin, height - 0.5 * inch, book_name[:30])
                    c.drawRightString(width - margin, height - 0.5 * inch, f"Chapter {i}: {topic}"[:30])
                    c.drawCentredString(width / 2, 0.5 * inch, str(page_number))
                    c.line(margin, height - 0.6 * inch, width - margin, height - 0.6 * inch)
                    c.showPage()
                    page_number += 1
                    text_object = c.beginText(margin, height - top_margin - 20)
                    text_object.setFont(font_style, font_size)
                    text_object.setLeading(font_size * 1.2)

                if is_heading:
                    text_object.setFont(f"{font_style}-Bold", font_size + 2)
                    text_object.textLine(wline)
                    text_object.setFont(font_style, font_size)
                elif is_bullet:
                    text_object.textLine(f"    {wline}")  # Indent bullets
                else:
                    text_object.textLine(wline)

        c.drawText(text_object)
        c.setFont(font_style, font_size - 2)
        c.drawString(margin, height - 0.5 * inch, book_name[:30])
        c.drawRightString(width - margin, height - 0.5 * inch, f"Chapter {i}: {topic}"[:30])
        c.drawCentredString(width / 2, 0.5 * inch, str(page_number))
        c.line(margin, height - 0.6 * inch, width - margin, height - 0.6 * inch)
        c.showPage()
        page_number += 1
        toc_entries.append((f"Chapter {i}: {topic}", start_page + 2))  # +2 for copyright and TOC pages

    # Update TOC
    c = canvas.Canvas(filepath, pagesize=paper_size)
    c.setFont(f"{font_style}-Bold", font_size + 16)
    c.drawCentredString(width / 2, height * 0.6, book_name)
    c.setFont(font_style, font_size + 4)
    c.drawCentredString(width / 2, height * 0.5, f"By {current_user.username}")
    c.setFont(font_style, font_size)
    c.drawCentredString(width / 2, height * 0.45, f"Generated on {datetime.now().strftime('%B %d, %Y')}")
    c.rect(margin, margin, width - 2 * margin, height - 2 * margin, stroke=1, fill=0)
    c.showPage()

    c.setFont(font_style, font_size - 2)
    c.drawCentredString(width / 2, height * 0.5, f"Copyright © {datetime.now().year} {current_user.username}")
    c.drawCentredString(width / 2, height * 0.45, "All rights reserved.")
    c.drawCentredString(width / 2, 0.5 * inch, "i")
    c.showPage()

    c.setFont(f"{font_style}-Bold", font_size + 6)
    c.drawCentredString(width / 2, height - top_margin, "Table of Contents")
    toc_y = height - top_margin - 40
    c.setFont(font_style, font_size)
    for topic, page in toc_entries:
        c.drawString(margin, toc_y, topic)
        c.drawRightString(width - margin, toc_y, str(page))
        dots = "." * int((width - 2 * margin - stringWidth(topic, font_style, font_size) - stringWidth(str(page), font_style, font_size)) / stringWidth(".", font_style, font_size))
        c.drawString(margin + stringWidth(topic, font_style, font_size), toc_y, dots)
        toc_y -= 20
        if toc_y < bottom_margin:
            c.drawCentredString(width / 2, 0.5 * inch, "ii")
            c.showPage()
            toc_y = height - top_margin
            c.setFont(font_style, font_size)
    c.drawCentredString(width / 2, 0.5 * inch, "ii")
    c.showPage()

    for i, topic in enumerate(topics, 1):
        c.setFont(f"{font_style}-Bold", font_size + 8)
        chapter_title = f"Chapter {i}: {topic}"
        c.drawCentredString(width / 2, height * 0.6, chapter_title)
        title_width = stringWidth(chapter_title, f"{font_style}-Bold", font_size + 8)
        underline_x_start = (width - title_width) / 2
        underline_x_end = underline_x_start + title_width
        c.line(underline_x_start, height * 0.6 - 10, underline_x_end, height * 0.6 - 10)
        c.showPage()

        answer = topic_responses[topic]
        lines = [clean_line(line) for line in answer.splitlines() if line.strip()]
        text_object = c.beginText(margin, height - top_margin - 20)
        text_object.setFont(font_style, font_size)
        text_object.setLeading(font_size * 1.2)

        for line in lines:
            is_heading = line.strip().lower().endswith(":") or line.strip().lower().startswith("example:")
            is_bullet = line.startswith("•")
            wrapped = wrap(line, width=int((width - 2 * margin) / (font_size / 2)))

            for wline in wrapped:
                if text_object.getY() < bottom_margin + 60:
                    c.drawText(text_object)
                    c.setFont(font_style, font_size - 2)
                    c.drawString(margin, height - 0.5 * inch, book_name[:30])
                    c.drawRightString(width - margin, height - 0.5 * inch, f"Chapter {i}: {topic}"[:30])
                    c.drawCentredString(width / 2, 0.5 * inch, str(page_number))
                    c.line(margin, height - 0.6 * inch, width - margin, height - 0.6 * inch)
                    c.showPage()
                    page_number += 1
                    text_object = c.beginText(margin, height - top_margin - 20)
                    text_object.setFont(font_style, font_size)
                    text_object.setLeading(font_size * 1.2)

                if is_heading:
                    text_object.setFont(f"{font_style}-Bold", font_size + 2)
                    text_object.textLine(wline)
                    text_object.setFont(font_style, font_size)
                elif is_bullet:
                    text_object.textLine(f"    {wline}")
                else:
                    text_object.textLine(wline)

        c.drawText(text_object)
        c.setFont(font_style, font_size - 2)
        c.drawString(margin, height - 0.5 * inch, book_name[:30])
        c.drawRightString(width - margin, height - 0.5 * inch, f"Chapter {i}: {topic}"[:30])
        c.drawCentredString(width / 2, 0.5 * inch, str(page_number))
        c.line(margin, height - 0.6 * inch, width - margin, height - 0.6 * inch)
        c.showPage()
        page_number += 1

    c.save()

    # Store file metadata in database
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('INSERT INTO files (user_id, filename, created_at) VALUES (?, ?, ?)',
              (current_user.id, filename, datetime.now().isoformat()))
    conn.commit()
    conn.close()

    return jsonify({"message": "PDF generated successfully", "file": filename})

# Serve user-specific PDF
@app.route('/files/<filename>')
@login_required
def download_pdf(filename):
    user_dir = os.path.join('user_files', str(current_user.id))
    return send_from_directory(user_dir, filename)

# Delete user-specific PDF
@app.route('/delete-file/<filename>', methods=['POST'])
@login_required
def delete_file(filename):
    user_dir = os.path.join('user_files', str(current_user.id))
    filepath = os.path.join(user_dir, filename)
    
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('SELECT id FROM files WHERE user_id = ? AND filename = ?', (current_user.id, filename))
    file_data = c.fetchone()
    
    if not file_data or not os.path.exists(filepath):
        flash('File not found or you do not have permission to delete it.', 'error')
        conn.close()
        return redirect(url_for('dashboard'))
    
    try:
        os.remove(filepath)
        c.execute('DELETE FROM files WHERE user_id = ? AND filename = ?', (current_user.id, filename))
        conn.commit()
        flash('File deleted successfully.', 'success')
    except Exception as e:
        flash(f'Error deleting file: {str(e)}', 'error')
    finally:
        conn.close()
    
    return redirect(url_for('dashboard'))

# Home Route
@app.route('/')
def home():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

if __name__ == '__main__':
    app.run(debug=True, port=5500)