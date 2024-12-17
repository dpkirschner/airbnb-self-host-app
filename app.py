import os
import logging
from datetime import timedelta
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

app.secret_key = os.environ.get("FLASK_SECRET_KEY", "your-secret-key-here")
# app.config['SECRET_KEY'] = os.environ.get("FLASK_SECRET_KEY","your-secret-key-here")
# At the top of your app.py, after creating the Flask app
app.config.update(SESSION_COOKIE_SECURE=True,
                  SESSION_COOKIE_HTTPONLY=True,
                  SESSION_COOKIE_SAMESITE='Lax',
                  PERMANENT_SESSION_LIFETIME=timedelta(minutes=30),
                  REMEMBER_COOKIE_SECURE=True,
                  REMEMBER_COOKIE_HTTPONLY=True,
                  REMEMBER_COOKIE_DURATION=timedelta(days=14),
                  SESSION_TYPE='sqlalchemy')


# Make sessions permanent by default
@app.before_request
def make_session_permanent():
    session.permanent = True


# Fix the database URL for SQLAlchemy
database_url = os.environ.get("DATABASE_URL")
if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}

db.init_app(app)

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'admin_login'
login_manager.debug = True

if not app.config['SECRET_KEY']:
    raise RuntimeError(
        "FLASK_SECRET_KEY is not set and no default key is provided!")

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
    app.logger.debug(f"Submitting Email address: {email}")
    if email:
        existing_email = LeadEmail.query.filter_by(email=email).first()
        if not existing_email:
            new_lead = LeadEmail(email=email)
            db.session.add(new_lead)
            db.session.commit()
            flash('Thank you for your interest! We\'ll be in touch soon.',
                  'success')
        else:
            flash('You\'re already subscribed!', 'info')
    return redirect(url_for('index'))


@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if current_user.is_authenticated:
        return redirect(url_for('admin_dashboard'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        try:
            admin = Admin.query.filter_by(username=username).first()
            app.logger.debug(f"Login attempt for username: {username}")

            if admin and check_password_hash(admin.password_hash, password):
                # Try to log in the user
                login_user(admin, remember=True)

                # Explicitly set session data
                session['user_id'] = admin.id
                session['_fresh'] = True
                session.modified = True

                app.logger.debug(
                    f"Login successful for user: {admin.username}")
                app.logger.debug(f"Session after login: {dict(session)}")

                # Force session save
                db.session.commit()

                return redirect(url_for('admin'))

            app.logger.error("Invalid login credentials")
            flash('Invalid username or password', 'error')
            return render_template('admin_login.html')

        except Exception as e:
            app.logger.error(f"Login error: {str(e)}")
            flash('An error occurred during login', 'error')
            return render_template('admin_login.html')

    return render_template('admin_login.html')


@app.route('/test')
def test():
    app.logger.debug(f"Raw session: {request.cookies.get('session')}")
    app.logger.debug(f"Session contents: {dict(session)}")
    app.logger.debug(f"Current user type: {type(current_user)}")
    app.logger.debug(
        f"Current user authenticated: {current_user.is_authenticated}")
    app.logger.debug(f"Current user ID: {session.get('user_id')}")
    app.logger.debug(
        f"Remember cookie: {request.cookies.get('remember_token')}")
    return f"Authenticated: {current_user.is_authenticated}"


@app.route('/admin')
@login_required
def admin_dashboard():
    app.logger.debug(
        f"Accessing admin dashboard. User authenticated: {current_user.is_authenticated}"
    )
    leads = LeadEmail.query.all()
    images = PropertyImage.query.all()
    return render_template('admin.html', leads=leads, images=images)


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('admin_login'))


@app.route('/admin/add_image', methods=['POST'])
@login_required
def add_image():
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
        app.logger.debug(
            "No admin user found, creating default admin account...")
        admin = Admin(username='admin',
                      password_hash=generate_password_hash('admin123'))
        db.session.add(admin)
        try:
            db.session.commit()
            app.logger.debug("Default admin account created successfully")
        except Exception as e:
            app.logger.error(f"Error creating admin account: {str(e)}")
            db.session.rollback()
    else:
        app.logger.debug("Admin account already exists")
