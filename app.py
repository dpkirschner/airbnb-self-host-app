import os
import logging
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, login_user, login_required, logout_user, current_user

logging.basicConfig(level=logging.DEBUG)

class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)
app = Flask(__name__)

app.secret_key = os.environ.get("FLASK_SECRET_KEY") or "your-secret-key-here"
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}

db.init_app(app)

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'admin_login'

from models import Admin, LeadEmail, PropertyImage

@login_manager.user_loader
def load_user(user_id):
    return Admin.query.get(int(user_id))

@app.route('/')
def index():
    images = PropertyImage.query.all()
    return render_template('index.html', images=images)

@app.route('/submit_email', methods=['POST'])
def submit_email():
    email = request.form.get('email')
    if email:
        existing_email = LeadEmail.query.filter_by(email=email).first()
        if not existing_email:
            new_lead = LeadEmail(email=email)
            db.session.add(new_lead)
            db.session.commit()
            flash('Thank you for your interest! We\'ll be in touch soon.', 'success')
        else:
            flash('You\'re already subscribed!', 'info')
    return redirect(url_for('index'))

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        app.logger.debug(f"Login attempt for username: {username}")
        admin = Admin.query.filter_by(username=username).first()
        
        if admin and check_password_hash(admin.password_hash, password):
            app.logger.debug("Password verified successfully")
            login_user(admin)
            app.logger.debug(f"User logged in successfully: {current_user.is_authenticated}")
            return redirect(url_for('admin_dashboard'))
        else:
            app.logger.debug("Login failed")
            flash('Invalid credentials', 'error')
    return render_template('admin_login.html')

@app.route('/admin')
@login_required
def admin_dashboard():
    app.logger.debug(f"Accessing admin dashboard. User authenticated: {current_user.is_authenticated}")
    leads = LeadEmail.query.all()
    images = PropertyImage.query.all()
    return render_template('admin.html', leads=leads, images=images)

@app.route('/admin/add_image', methods=['POST'])
def add_image():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    
    image_url = request.form.get('image_url')
    caption = request.form.get('caption')
    
    if image_url:
        new_image = PropertyImage(url=image_url, caption=caption)
        db.session.add(new_image)
        db.session.commit()
        flash('Image added successfully!', 'success')
    return redirect(url_for('admin_dashboard'))

with app.app_context():
    app.logger.debug("Creating database tables...")
    db.create_all()
    # Create default admin if none exists
    if not Admin.query.first():
        app.logger.debug("No admin user found, creating default admin account...")
        admin = Admin(
            username='admin',
            password_hash=generate_password_hash('admin123')
        )
        db.session.add(admin)
        try:
            db.session.commit()
            app.logger.debug("Default admin account created successfully")
        except Exception as e:
            app.logger.error(f"Error creating admin account: {str(e)}")
            db.session.rollback()
    else:
        app.logger.debug("Admin account already exists")
