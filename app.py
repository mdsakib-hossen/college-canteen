import os
from flask import Flask
from extensions import db, login_manager, csrf, limiter
from dotenv import load_dotenv

load_dotenv()


def create_app():
    app = Flask(__name__)

    # Security config
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production-xK9mP2qL')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///canteen.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['WTF_CSRF_ENABLED'] = True
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # 5MB max upload

    # Init extensions with app
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)

    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'এই পেজ দেখতে আগে লগইন করুন।'
    login_manager.login_message_category = 'warning'

    # Register user loader (must be done inside create_app after login_manager.init_app)
    from models import Student, Admin

    @login_manager.user_loader
    def load_user(user_id):
        if user_id.startswith('student_'):
            return Student.query.get(int(user_id.split('_')[1]))
        elif user_id.startswith('admin_'):
            return Admin.query.get(int(user_id.split('_')[1]))
        return None

    # Register Bangladesh timezone filter
    from datetime import timedelta

    @app.template_filter('bdtime')
    def bdtime_filter(dt):
        """Display datetime as Bangladesh Standard Time (already stored as BST)"""
        if dt is None:
            return ''
        return dt.strftime('%d %b %Y, %I:%M %p')

    @app.template_filter('bdtime_short')
    def bdtime_short_filter(dt):
        if dt is None:
            return ''
        return dt.strftime('%d %b, %I:%M %p')

    # Register blueprints
    from routes.main import main_bp
    from routes.auth import auth_bp
    from routes.student import student_bp
    from routes.admin import admin_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(student_bp, url_prefix='/student')
    app.register_blueprint(admin_bp, url_prefix='/canteen-panel-x7k2')

    # Create tables and seed initial data (inside app context)
    with app.app_context():
        db.create_all()
        from utils.seed import seed_admin
        seed_admin()

    return app


if __name__ == '__main__':
    app = create_app()
    app.run(debug=False, host='0.0.0.0', port=5000)
