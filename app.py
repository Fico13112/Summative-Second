import os
import io
import uuid
import qrcode
from flask import Flask, request, render_template, redirect, url_for, session, send_file
import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__, template_folder='templates', static_folder='static')
app.secret_key = '3ec069627e241d7e50cbb4f1e54c0f627540bf5af9f287ee14d331ec0cf56feb'

# Configure upload directory for payment proof screenshots
UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}

# MySQL Configuration (XAMPP / Localhost)
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': 'Messithegoat',
    'database': 'theater_dramus'
}

def get_db():
    return mysql.connector.connect(**DB_CONFIG)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ---------------- AUTO DATABASE & TABLE INITIALIZATION ----------------
def init_db():
    try:
        # Create database if missing
        conn = mysql.connector.connect(
            host=DB_CONFIG['host'],
            user=DB_CONFIG['user'],
            password=DB_CONFIG['password']
        )
        cursor = conn.cursor()
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{DB_CONFIG['database']}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
        cursor.close()
        conn.close()

        # Connect to target DB and create tables
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                email VARCHAR(150) NOT NULL UNIQUE,
                password_hash VARCHAR(255) NOT NULL,
                is_admin BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bookings (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                show_id INT NOT NULL,
                show_title VARCHAR(255) NOT NULL,
                show_time VARCHAR(100) DEFAULT '19:30',
                amount DECIMAL(10, 2) DEFAULT 50000.00,
                payment_proof VARCHAR(255) DEFAULT NULL,
                status ENUM('pending', 'approved', 'rejected') DEFAULT 'pending',
                ticket_code VARCHAR(64) UNIQUE DEFAULT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)

        # Auto Seed Default Admin Account (admin@gmail.com / AdminPassword123!)
        admin_pw_hash = generate_password_hash('AdminPassword123!')
        cursor.execute("""
            INSERT INTO users (name, email, password_hash, is_admin)
            VALUES ('Admin Dramus', 'admin@gmail.com', %s, TRUE)
            ON DUPLICATE KEY UPDATE is_admin = TRUE;
        """, (admin_pw_hash,))

        conn.commit()
        cursor.close()
        conn.close()
        print("Database & Tables Initialized Successfully!")
    except mysql.connector.Error as err:
        print(f"Database setup notice: {err}")

init_db()

# Helper to retrieve logged-in user state
def get_current_user():
    if 'user_id' in session:
        return {
            'id': session.get('user_id'),
            'name': session.get('user_name'),
            'email': session.get('user_email'),
            'is_admin': session.get('is_admin', False)
        }
    return None

# Master show data dictionary
SHOWS_DATA = {
    1: {"id": 1, "t": "Perahu Kertas", "price": 50000},
    2: {"id": 2, "t": "Payung Fantasy", "price": 50000},
    3: {"id": 3, "t": "Ten Minutes to Curtain", "price": 50000},
    4: {"id": 4, "t": "Salt & Violin", "price": 50000}
}

# ---------------- HOME / INDEX ROUTE ----------------
@app.route('/')
@app.route('/index.html')
def index():
    return render_template('index.html', user=get_current_user())

# ---------------- LOG OUT ROUTE ----------------
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# ---------------- SIGN UP ROUTES ----------------
@app.route('/signup', methods=['GET'])
@app.route('/signup.html', methods=['GET'])
def signup_page():
    return render_template('signup.html', user=get_current_user())

@app.route('/signup', methods=['POST'])
@app.route('/signup.html', methods=['POST'])
def handle_signup():
    name = request.form.get('name', '').strip()
    email = request.form.get('email', '').strip().lower()
    password = request.form.get('pw', '')

    if not name or not email or not password:
        return render_template('signup.html', msg='All fields are required.', msg_type='error', user=get_current_user())

    if not email.endswith('@gmail.com'):
        return render_template('signup.html', msg='Only @gmail.com email addresses are allowed.', msg_type='error', user=get_current_user())

    if len(password) < 6:
        return render_template('signup.html', msg='Password must be at least 6 characters.', msg_type='error', user=get_current_user())

    hashed_pw = generate_password_hash(password)

    try:
        conn = get_db()
        cursor = conn.cursor()
        query = "INSERT INTO users (name, email, password_hash, is_admin) VALUES (%s, %s, %s, FALSE)"
        cursor.execute(query, (name, email, hashed_pw))
        conn.commit()
        user_id = cursor.lastrowid
        cursor.close()
        conn.close()

        session['user_id'] = user_id
        session['user_name'] = name
        session['user_email'] = email
        session['is_admin'] = False

        return redirect(url_for('index'))
    except mysql.connector.Error as err:
        if err.errno == 1062:
            return render_template('signup.html', msg='Email address is already registered.', msg_type='error', user=get_current_user())
        return render_template('signup.html', msg=f'Database error: {err}', msg_type='error', user=get_current_user())

# ---------------- LOG IN ROUTES ----------------
@app.route('/login', methods=['GET'])
@app.route('/login.html', methods=['GET'])
def login_page():
    return render_template('login.html', user=get_current_user())

@app.route('/login', methods=['POST'])
@app.route('/login.html', methods=['POST'])
def handle_login():
    email = request.form.get('email', '').strip().lower()
    password = request.form.get('pw', '')

    if not email or not password:
        return render_template('login.html', msg='Email and password are required.', msg_type='error', user=get_current_user())

    if not email.endswith('@gmail.com'):
        return render_template('login.html', msg='Only @gmail.com accounts are allowed.', msg_type='error', user=get_current_user())

    try:
        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        user_record = cursor.fetchone()
        cursor.close()
        conn.close()

        if not user_record or not check_password_hash(user_record['password_hash'], password):
            return render_template('login.html', msg='Incorrect credentials. Access denied.', msg_type='error', user=get_current_user())

        session['user_id'] = user_record['id']
        session['user_name'] = user_record['name']
        session['user_email'] = user_record['email']
        session['is_admin'] = bool(user_record.get('is_admin', False))

        next_url = request.args.get('next') or url_for('index')
        return redirect(next_url)

    except mysql.connector.Error as err:
        return render_template('login.html', msg=f'Database error: {err}', msg_type='error', user=get_current_user())

# ---------------- SHOWS / DETAIL FILM ROUTE ----------------
@app.route('/shows')
@app.route('/shows.html')
def shows_page():
    return render_template('shows.html', user=get_current_user())

# ---------------- CHECKOUT & BCA PAYMENT ROUTE ----------------
@app.route('/checkout/<int:show_id>', methods=['GET', 'POST'])
def checkout(show_id):
    user = get_current_user()
    
    # Check authentication before showing checkout
    if not user:
        return redirect(url_for('login_page', next=request.url))

    show = SHOWS_DATA.get(show_id, SHOWS_DATA[1])

    if request.method == 'POST':
        if 'proof' not in request.files:
            return render_template('checkout.html', show=show, show_id=show_id, user=user, error="Payment proof file is required.")
        
        file = request.files['proof']
        if file.filename == '' or not allowed_file(file.filename):
            return render_template('checkout.html', show=show, show_id=show_id, user=user, error="Please upload a valid image file (PNG, JPG, JPEG).")

        filename = secure_filename(f"bca_proof_{user['id']}_{int(uuid.uuid4())}.{file.filename.rsplit('.', 1)[1].lower()}")
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO bookings (user_id, show_id, show_title, amount, payment_proof, status) VALUES (%s, %s, %s, %s, %s, 'pending')",
            (user['id'], show_id, show['t'], show['price'], filename)
        )
        conn.commit()
        cursor.close()
        conn.close()

        return redirect(url_for('account'))

    return render_template('checkout.html', show=show, show_id=show_id, user=user)

# ---------------- USER ACCOUNT & MY TICKETS ----------------
@app.route('/account')
@app.route('/account.html')
def account():
    user = get_current_user()
    if not user:
        return redirect(url_for('login_page', next=url_for('account')))

    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM bookings WHERE user_id = %s ORDER BY created_at DESC", (user['id'],))
    bookings = cursor.fetchall()
    cursor.close()
    conn.close()

    return render_template('account.html', user=user, bookings=bookings)

# ---------------- DYNAMIC QR CODE GENERATOR ----------------
@app.route('/qrcode/<code_text>')
def generate_qr(code_text):
    qr = qrcode.QRCode(version=1, box_size=6, border=2)
    qr.add_data(code_text)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    img_io = io.BytesIO()
    img.save(img_io, 'PNG')
    img_io.seek(0)
    return send_file(img_io, mimetype='image/png')

# ---------------- ADMIN PANEL: VERIFICATION & SCANNER ----------------
@app.route('/admin')
def admin_panel():
    user = get_current_user()
    if not user or not user.get('is_admin'):
        return "Access denied. Admin account required.", 403

    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT b.*, u.name as user_name, u.email as user_email 
        FROM bookings b 
        JOIN users u ON b.user_id = u.id 
        ORDER BY b.created_at DESC
    """)
    bookings = cursor.fetchall()
    cursor.close()
    conn.close()

    return render_template('admin.html', user=user, bookings=bookings)

@app.route('/admin/approve/<int:booking_id>', methods=['POST'])
def admin_approve(booking_id):
    user = get_current_user()
    if not user or not user.get('is_admin'):
        return "Unauthorized", 403

    ticket_code = f"DRAMUS-{uuid.uuid4().hex[:8].upper()}"

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE bookings SET status = 'approved', ticket_code = %s WHERE id = %s", (ticket_code, booking_id))
    conn.commit()
    cursor.close()
    conn.close()

    return redirect(url_for('admin_panel'))

@app.route('/admin/validate', methods=['POST'])
def admin_validate():
    user = get_current_user()
    if not user or not user.get('is_admin'):
        return {"valid": False, "message": "Unauthorized access"}, 403

    data = request.get_json() or {}
    code = data.get('code', '').strip()

    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT b.*, u.name as user_name 
        FROM bookings b 
        JOIN users u ON b.user_id = u.id 
        WHERE b.ticket_code = %s AND b.status = 'approved'
    """, (code,))
    ticket = cursor.fetchone()
    cursor.close()
    conn.close()

    if ticket:
        return {
            "valid": True,
            "message": "VALID TICKET",
            "holder": ticket['user_name'],
            "show": ticket['show_title'],
            "code": ticket['ticket_code']
        }
    else:
        return {"valid": False, "message": "INVALID OR UNAPPROVED TICKET CODE"}

if __name__ == '__main__':
    print("Server running at http://localhost:5000")
    app.run(port=5000, debug=True)