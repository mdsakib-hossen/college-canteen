from models import Admin, Settings
from extensions import db


def seed_admin():
    """Create default admin and settings if not exist"""
    # Create default admin
    if not Admin.query.filter_by(username='canteen_admin').first():
        admin = Admin(username='canteen_admin')
        admin.set_password('Admin@1234')
        db.session.add(admin)

    # Default settings
    defaults = {
        'college_name': 'Your College Name',
        'canteen_name': 'College Canteen',
        'canteen_open': '08:00',
        'canteen_close': '16:00',
        'order_deadline': '22:00',   # time by which order must be placed (previous day)
        'cancel_deadline': '08:00',  # time by which order can be cancelled (same day)
        'developer': 'Sakib',
    }
    for key, value in defaults.items():
        if not Settings.query.filter_by(key=key).first():
            db.session.add(Settings(key=key, value=value))

    db.session.commit()


def get_setting(key, default=''):
    """Helper to get a setting value"""
    from models import Settings
    s = Settings.query.filter_by(key=key).first()
    return s.value if s else default
