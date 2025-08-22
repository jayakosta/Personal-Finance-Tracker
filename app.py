from dotenv import load_dotenv
load_dotenv()

from flask import Flask, render_template, request, redirect, url_for, session, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
import os, io, base64
import matplotlib.pyplot as plt
import requests
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

app = Flask(__name__)
app.config['SECRET_KEY'] = 'yoursecret'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)

# ---------------------- Database Models ----------------------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(50), nullable=False)
    type = db.Column(db.String(10), nullable=False)
    date = db.Column(db.Date, nullable=False)

# Initialize DB tables
with app.app_context():
    db.create_all()

# ---------------------- Routes ----------------------
@app.route('/')
def home():
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        email = request.form['email']
        password = bcrypt.generate_password_hash(request.form['password']).decode('utf-8')
        user = User(email=email, password=password)
        db.session.add(user)
        db.session.commit()
        return redirect(url_for('home'))
    return render_template('signup.html')

@app.route('/login', methods=['POST'])
def login():
    email = request.form['email']
    password = request.form['password']
    user = User.query.filter_by(email=email).first()
    if user and bcrypt.check_password_hash(user.password, password):
        session['user_id'] = user.id
        return redirect(url_for('dashboard'))
    return "Invalid credentials!"

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('home'))

    transactions = Transaction.query.filter_by(user_id=session['user_id']).all()
    categories = {}
    for t in transactions:
        if t.type == 'expense':
            categories[t.category] = categories.get(t.category, 0) + t.amount

    # Create a bigger, dark-themed chart
    plt.figure(figsize=(6, 6), facecolor='#121212')
    if categories:
        plt.pie(
            categories.values(),
            labels=categories.keys(),
            autopct='%1.1f%%',
            textprops={'color': 'white'}
        )
    else:
        plt.text(0.5, 0.5, 'No Data', color='white', ha='center')

    plt.gca().set_facecolor('#121212')  # Chart background dark
    plt.tight_layout()

    img = io.BytesIO()
    plt.savefig(img, format='png', transparent=True)  # Transparent background
    img.seek(0)
    chart_url = base64.b64encode(img.getvalue()).decode()
    plt.close()  # Free memory

    return render_template('dashboard.html', chart=chart_url, transactions=transactions)


@app.route('/add_transaction', methods=['POST'])
def add_transaction():
    if 'user_id' not in session:
        return redirect(url_for('home'))
    amount = float(request.form['amount'])
    category = request.form['category']
    type_ = request.form['type']
    date = datetime.strptime(request.form['date'], '%Y-%m-%d')
    t = Transaction(user_id=session['user_id'], amount=amount, category=category, type=type_, date=date)
    db.session.add(t)
    db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/chat', methods=['GET', 'POST'])
def chat():
    if 'user_id' not in session:
        return redirect(url_for('home'))

    response = ""
    if request.method == 'POST':
        question = request.form['question']
        transactions = Transaction.query.filter_by(user_id=session['user_id']).all()
        total_expense = sum(t.amount for t in transactions if t.type == 'expense')
        prompt = f"User spent {total_expense} this month. {question}"

        api_key = os.getenv("GROQ_API_KEY")
        headers = {"Authorization": f"Bearer {api_key}"}
        data = {
            "model": "llama3-8b-8192",
            "messages": [{"role": "user", "content": prompt}]
        }
        r = requests.post("https://api.groq.com/openai/v1/chat/completions", json=data, headers=headers)
        try:
            response = r.json()['choices'][0]['message']['content']
        except:
            response = "AI service unavailable."

    return render_template('chatbot.html', response=response)

@app.route('/export_pdf')
def export_pdf():
    if 'user_id' not in session:
        return redirect(url_for('home'))

    transactions = Transaction.query.filter_by(user_id=session['user_id']).all()

    pdf_path = "financial_report.pdf"
    c = canvas.Canvas(pdf_path, pagesize=letter)
    width, height = letter

    c.setFont("Helvetica-Bold", 16)
    c.drawString(200, 750, "Monthly Financial Report")

    c.setFont("Helvetica", 12)
    y = 700
    total_income = sum(t.amount for t in transactions if t.type == 'income')
    total_expense = sum(t.amount for t in transactions if t.type == 'expense')

    c.drawString(50, y, f"Total Income: {total_income}")
    y -= 20
    c.drawString(50, y, f"Total Expenses: {total_expense}")
    y -= 40

    c.drawString(50, y, "Transactions:")
    y -= 20

    for t in transactions:
        line = f"{t.date} - {t.category} - {t.amount} ({t.type})"
        c.drawString(50, y, line)
        y -= 20
        if y < 50:
            c.showPage()
            y = 750

    c.save()
    return send_file(pdf_path, as_attachment=True)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

if __name__ == '__main__':
    app.run(debug=True)
