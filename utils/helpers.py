import qrcode
import io
import base64
import random
import string
from datetime import datetime, date, time
from models import Order, Settings
from extensions import db


def generate_token():
    """Generate a unique order token like #0047"""
    while True:
        number = random.randint(1, 9999)
        token = f'#{number:04d}'
        if not Order.query.filter_by(token_number=token).first():
            return token


def generate_qr_code(data: str) -> str:
    """Generate a QR code and return as base64 string"""
    qr = qrcode.QRCode(version=1, box_size=6, border=2)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color='black', back_color='white')
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    return base64.b64encode(buffer.getvalue()).decode('utf-8')


def get_setting(key, default=''):
    """Get setting value by key"""
    s = Settings.query.filter_by(key=key).first()
    return s.value if s else default


def is_order_deadline_passed():
    """Check if today's order deadline has passed (for ordering next day's food)"""
    deadline_str = get_setting('order_deadline', '22:00')
    h, m = map(int, deadline_str.split(':'))
    deadline = time(h, m)
    now = datetime.now().time()
    return now > deadline


def is_cancel_deadline_passed():
    """Check if cancel deadline has passed for today's orders"""
    cancel_str = get_setting('cancel_deadline', '08:00')
    h, m = map(int, cancel_str.split(':'))
    deadline = time(h, m)
    now = datetime.now().time()
    return now > deadline


def get_tomorrow():
    """Get tomorrow's date"""
    from datetime import timedelta
    return date.today() + timedelta(days=1)


def send_notification(student_id=None, admin_id=None, title='', message='', notif_type='info'):
    """Create an in-app notification"""
    from models import Notification
    notif = Notification(
        student_id=student_id,
        admin_id=admin_id,
        title=title,
        message=message,
        notif_type=notif_type
    )
    db.session.add(notif)
    db.session.commit()


def notify_all_admins(title, message, notif_type='info'):
    """Send notification to all admins"""
    from models import Admin
    admins = Admin.query.all()
    for admin in admins:
        send_notification(admin_id=admin.id, title=title, message=message, notif_type=notif_type)
