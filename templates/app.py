from flask import Flask, render_template, request, redirect, url_for, session, send_file
import sqlite3
from datetime import datetime
import io
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

def get_db_connection():
    conn = sqlite3.connect('shop_data.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shop_name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            number TEXT NOT NULL,
            password TEXT NOT NULL
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            date TEXT NOT NULL,
            day_name TEXT NOT NULL,
            morning_amount REAL,
            afternoon_amount REAL,
            total_amount REAL,
            pinned INTEGER DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    conn.commit()
    conn.close()

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE email = ? AND password = ?', (email, password)).fetchone()
        conn.close()
        if user:
            session['user_id'] = user['id']
            session['shop_name'] = user['shop_name']
            return redirect(url_for('dashboard'))
        else:
            return render_template('login.html', error='Invalid Credentials')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        shop_name = request.form['shop_name']
        email = request.form['email']
        number = request.form['number']
        password = request.form['password']
        conn = get_db_connection()
        try:
            conn.execute('INSERT INTO users (shop_name, email, number, password) VALUES (?, ?, ?, ?)',
                         (shop_name, email, number, password))
            conn.commit()
        except sqlite3.IntegrityError:
            conn.close()
            return render_template('register.html', error='Email already exists')
        conn.close()
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    
    if request.method == 'POST':
        date = request.form['date']
        morning = float(request.form['morning'] or 0)
        afternoon = float(request.form['afternoon'] or 0)
        total = morning + afternoon
        day_name = datetime.strptime(date, '%Y-%m-%d').strftime('%A')
        
        existing = conn.execute('SELECT id FROM transactions WHERE user_id = ? AND date = ?', (user_id, date)).fetchone()
        if existing:
            conn.execute('UPDATE transactions SET morning_amount = ?, afternoon_amount = ?, total_amount = ?, day_name = ? WHERE id = ?',
                         (morning, afternoon, total, day_name, existing['id']))
        else:
            conn.execute('INSERT INTO transactions (user_id, date, day_name, morning_amount, afternoon_amount, total_amount, pinned) VALUES (?, ?, ?, ?, ?, ?, 0)',
                         (user_id, date, day_name, morning, afternoon, total))
        conn.commit()
        return redirect(url_for('dashboard'))
    
    all_records = conn.execute('SELECT * FROM transactions WHERE user_id = ? ORDER BY pinned DESC, date DESC', (user_id,)).fetchall()
    
    today_date = datetime.now().strftime('%Y-%m-%d')
    weekly_total = sum([row['total_amount'] for row in all_records[:7]]) if all_records else 0
    monthly_total = sum([row['total_amount'] for row in all_records if row['date'][:7] == today_date[:7]]) if all_records else 0
    yearly_total = sum([row['total_amount'] for row in all_records if row['date'][:4] == today_date[:4]]) if all_records else 0
    
    conn.close()
    
    return render_template('dashboard.html', 
                           shop_name=user['shop_name'],
                           number=user['number'],
                           email=user['email'],
                           today_date=today_date,
                           all_records=all_records,
                           weekly_total=weekly_total,
                           monthly_total=monthly_total,
                           yearly_total=yearly_total)

@app.route('/pin_transaction/<int:id>')
def pin_transaction(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = get_db_connection()
    record = conn.execute('SELECT pinned FROM transactions WHERE id = ? AND user_id = ?', (id, session['user_id'])).fetchone()
    if record:
        new_pinned = 0 if record['pinned'] == 1 else 1
        conn.execute('UPDATE transactions SET pinned = ? WHERE id = ?', (new_pinned, id))
        conn.commit()
    conn.close()
    return redirect(url_for('dashboard'))

@app.route('/settings', methods=['GET', 'POST'])
def settings():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user_id = session['user_id']
    conn = get_db_connection()
    if request.method == 'POST':
        shop_name = request.form['shop_name']
        number = request.form['number']
        email = request.form['email']
        conn.execute('UPDATE users SET shop_name = ?, number = ?, email = ? WHERE id = ?', (shop_name, number, email, user_id))
        conn.commit()
        conn.close()
        session['shop_name'] = shop_name
        return redirect(url_for('dashboard'))
    user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    conn.close()
    return render_template('settings.html', user=user)

@app.route('/weekly_details')
def weekly_details():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = get_db_connection()
    records = conn.execute('SELECT * FROM transactions WHERE user_id = ? ORDER BY date DESC LIMIT 7', (session['user_id'],)).fetchall()
    total = sum([r['total_amount'] for r in records])
    conn.close()
    return render_template('details.html', title="Weekly Details", records=records, total=total)

@app.route('/monthly_details')
def monthly_details():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    current_month = datetime.now().strftime('%Y-%m')
    conn = get_db_connection()
    records = conn.execute('SELECT * FROM transactions WHERE user_id = ? AND date LIKE ? ORDER BY date DESC', (session['user_id'], current_month + '%')).fetchall()
    total = sum([r['total_amount'] for r in records])
    conn.close()
    return render_template('details.html', title="Monthly Details", records=records, total=total)

@app.route('/yearly_details')
def yearly_details():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    current_year = datetime.now().strftime('%Y')
    conn = get_db_connection()
    records = conn.execute('SELECT * FROM transactions WHERE user_id = ? AND date LIKE ? ORDER BY date DESC', (session['user_id'], current_year + '%')).fetchall()
    total = sum([r['total_amount'] for r in records])
    conn.close()
    return render_template('details.html', title="Yearly Details", records=records, total=total)

@app.route('/reports')
def reports():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    conn = get_db_connection()
    all_records = conn.execute('SELECT * FROM transactions WHERE user_id = ? ORDER BY date ASC', (user_id,)).fetchall()
    conn.close()
    
    daily_dates = [row['date'] for row in all_records]
    daily_totals = [row['total_amount'] for row in all_records]
    
    temp_weekly = {}
    for row in all_records:
        dt = datetime.strptime(row['date'], '%Y-%m-%d')
        year_week = dt.strftime('%Y-W%U')
        if year_week not in temp_weekly:
            temp_weekly[year_week] = 0
        temp_weekly[year_week] += row['total_amount']
    weekly_labels = [f"Week {i}" for i in range(1, len(temp_weekly) + 1)]
    weekly_data = list(temp_weekly.values())

    temp_monthly = {}
    for row in all_records:
        month_key = row['date'][:7]
        if month_key not in temp_monthly:
            dt_month = datetime.strptime(month_key, '%Y-%m').strftime('%B')
            temp_monthly[dt_month] = 0
        dt_month = datetime.strptime(row['date'][:7], '%Y-%m').strftime('%B')
        temp_monthly[dt_month] += row['total_amount']
    monthly_labels = list(temp_monthly.keys())
    monthly_data = list(temp_monthly.values())

    temp_yearly = {}
    for row in all_records:
        year_key = row['date'][:4]
        if year_key not in temp_yearly:
            temp_yearly[year_key] = 0
        temp_yearly[year_key] += row['total_amount']
    yearly_labels = list(temp_yearly.keys())
    yearly_data = list(temp_yearly.values())

    today_date = datetime.now().strftime('%Y-%m-%d')
    weekly_total = sum([row['total_amount'] for row in all_records[:7]]) if all_records else 0
    monthly_total = sum([row['total_amount'] for row in all_records if row['date'][:7] == today_date[:7]]) if all_records else 0
    yearly_total = sum([row['total_amount'] for row in all_records if row['date'][:4] == today_date[:4]]) if all_records else 0
    
    return render_template('reports.html', 
                           daily_dates=daily_dates, 
                           daily_totals=daily_totals,
                           weekly_labels=weekly_labels,
                           weekly_data=weekly_data,
                           monthly_labels=monthly_labels,
                           monthly_data=monthly_data,
                           yearly_labels=yearly_labels,
                           yearly_data=yearly_data,
                           weekly_total=weekly_total,
                           monthly_total=monthly_total,
                           yearly_total=yearly_total)

@app.route('/download_pdf')
def download_pdf():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user_id = session['user_id']
    conn = get_db_connection()
    
    # Fetching user shop details
    user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    all_records = conn.execute('SELECT * FROM transactions WHERE user_id = ? ORDER BY date DESC', (user_id,)).fetchall()
    conn.close()
    
    shop_name = user['shop_name'] if user else "Shop"
    
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    
    y = 750
    p.setFont("Helvetica-Bold", 14)
    # Replaced 'Shop Ledger Report' with actual Shop Name
    p.drawString(50, y, f"{shop_name} - Collection Report")
    y -= 20
    p.setFont("Helvetica", 10)
    p.drawString(50, y, f"Email: {user['email']} | Phone: {user['number']}")
    y -= 30
    
    # --- Days Collections ---
    p.setFont("Helvetica-Bold", 11)
    p.drawString(50, y, "--- Days Collections ---")
    y -= 20
    
    p.setFont("Helvetica-Bold", 9)
    p.drawString(50, y, "Date")
    p.drawString(130, y, "Day")
    p.drawString(220, y, "Morning (Rs)")
    p.drawString(320, y, "Afternoon (Rs)")
    p.drawString(420, y, "Total (Rs)")
    y -= 15
    
    p.setFont("Helvetica", 9)
    grand_total = 0
    for row in all_records:
        if y < 50:
            p.showPage()
            y = 750
        p.drawString(50, y, str(row['date']))
        p.drawString(130, y, str(row['day_name']))
        p.drawString(220, y, str(row['morning_amount']))
        p.drawString(320, y, str(row['afternoon_amount']))
        p.drawString(420, y, str(row['total_amount']))
        grand_total += row['total_amount']
        y -= 15
        
    y -= 15
    if y < 80:
        p.showPage()
        y = 750

    # --- Weekly Collections ---
    p.setFont("Helvetica-Bold", 11)
    p.drawString(50, y, "--- Weekly Collections ---")
    y -= 20
    p.setFont("Helvetica-Bold", 9)
    p.drawString(50, y, "Week")
    p.drawString(200, y, "Total Amount (Rs)")
    y -= 15
    
    temp_weekly = {}
    for row in all_records:
        dt = datetime.strptime(row['date'], '%Y-%m-%d')
        year_week = dt.strftime('%Y-W%U')
        if year_week not in temp_weekly:
            temp_weekly[year_week] = 0
        temp_weekly[year_week] += row['total_amount']
        
    p.setFont("Helvetica", 9)
    week_idx = 1
    for wk, wval in temp_weekly.items():
        if y < 50:
            p.showPage()
            y = 750
        p.drawString(50, y, f"Week {week_idx}")
        p.drawString(200, y, str(wval))
        week_idx += 1
        y -= 15
        
    y -= 15
    if y < 80:
        p.showPage()
        y = 750

    # --- Yearly Collections ---
    p.setFont("Helvetica-Bold", 11)
    p.drawString(50, y, "--- Yearly Collections ---")
    y -= 20
    p.setFont("Helvetica-Bold", 9)
    p.drawString(50, y, "Year")
    p.drawString(200, y, "Total Amount (Rs)")
    y -= 15
    
    temp_yearly = {}
    for row in all_records:
        yr = row['date'][:4]
        if yr not in temp_yearly:
            temp_yearly[yr] = 0
        temp_yearly[yr] += row['total_amount']
        
    p.setFont("Helvetica", 9)
    for yr, yval in temp_yearly.items():
        if y < 50:
            p.showPage()
            y = 750
        p.drawString(50, y, str(yr))
        p.drawString(200, y, str(yval))
        y -= 15
        
    y -= 20
    if y < 50:
        p.showPage()
        y = 750
    p.setFont("Helvetica-Bold", 11)
    p.drawString(50, y, f"Grand Total Collection: Rs. {grand_total}")
    
    p.save()
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name='collection_report.pdf', mimetype='application/pdf')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)
