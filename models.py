from extensions import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timezone, timedelta

def bd_now():
    """Return current Bangladesh Standard Time (UTC+6)"""
    return datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=6)


class StudentRoll(db.Model):
    """Pre-loaded student rolls from CSV - for verification during registration"""
    __tablename__ = 'student_rolls'

    id = db.Column(db.Integer, primary_key=True)
    roll = db.Column(db.String(50), unique=True, nullable=False, index=True)
    name = db.Column(db.String(150), nullable=False)
    is_registered = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=bd_now)

    def __repr__(self):
        return f'<StudentRoll {self.roll}>'


class Student(UserMixin, db.Model):
    """Registered student"""
    __tablename__ = 'students'

    id = db.Column(db.Integer, primary_key=True)
    roll = db.Column(db.String(50), unique=True, nullable=False, index=True)
    name = db.Column(db.String(150), nullable=False)
    department = db.Column(db.String(100), nullable=False)
    session = db.Column(db.String(50), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    guardian_teacher = db.Column(db.String(150), nullable=False)
    photo = db.Column(db.String(255), default='default.png')
    password_hash = db.Column(db.String(256), nullable=False)
    is_blocked = db.Column(db.Boolean, default=False)
    warning_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=bd_now)

    orders = db.relationship('Order', backref='student', lazy='dynamic')
    notifications = db.relationship('Notification', backref='student', lazy='dynamic',
                                    foreign_keys='Notification.student_id')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def get_id(self):
        return f'student_{self.id}'

    def __repr__(self):
        return f'<Student {self.roll}>'


class Admin(UserMixin, db.Model):
    """Canteen admin"""
    __tablename__ = 'admins'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, default=bd_now)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def get_id(self):
        return f'admin_{self.id}'

    def __repr__(self):
        return f'<Admin {self.username}>'


class MenuItem(db.Model):
    """Canteen menu items"""
    __tablename__ = 'menu_items'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, default='')
    price = db.Column(db.Float, nullable=False)
    image = db.Column(db.String(255), default='food_default.png')
    is_available = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=bd_now)
    updated_at = db.Column(db.DateTime, default=bd_now, onupdate=datetime.utcnow)

    order_items = db.relationship('OrderItem', backref='menu_item', lazy='dynamic')

    def __repr__(self):
        return f'<MenuItem {self.name}>'


class DailyMenu(db.Model):
    """Which items are available on which date"""
    __tablename__ = 'daily_menus'

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, index=True)
    menu_item_id = db.Column(db.Integer, db.ForeignKey('menu_items.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=bd_now)

    menu_item = db.relationship('MenuItem', backref='daily_entries')

    __table_args__ = (db.UniqueConstraint('date', 'menu_item_id'),)

    def __repr__(self):
        return f'<DailyMenu {self.date}>'


class Order(db.Model):
    """Student orders"""
    __tablename__ = 'orders'

    id = db.Column(db.Integer, primary_key=True)
    token_number = db.Column(db.String(10), unique=True, nullable=False, index=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    order_date = db.Column(db.Date, nullable=False)  # date the food is for
    status = db.Column(db.String(20), default='pending')  # pending, confirmed, ready, delivered, cancelled
    total_price = db.Column(db.Float, default=0.0)
    qr_code = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=bd_now)
    updated_at = db.Column(db.DateTime, default=bd_now, onupdate=datetime.utcnow)

    items = db.relationship('OrderItem', backref='order', lazy='dynamic', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Order {self.token_number}>'


class OrderItem(db.Model):
    """Items within an order"""
    __tablename__ = 'order_items'

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    menu_item_id = db.Column(db.Integer, db.ForeignKey('menu_items.id'), nullable=False)
    quantity = db.Column(db.Integer, default=1)
    price = db.Column(db.Float, nullable=False)  # snapshot of price at order time

    def __repr__(self):
        return f'<OrderItem order={self.order_id} item={self.menu_item_id}>'


class Settings(db.Model):
    """Canteen settings"""
    __tablename__ = 'settings'

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.String(500), nullable=False)
    updated_at = db.Column(db.DateTime, default=bd_now, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<Settings {self.key}>'


class Feedback(db.Model):
    """Student feedback for delivered orders"""
    __tablename__ = 'feedbacks'

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), unique=True, nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    quantity_rating = db.Column(db.Integer, nullable=False)  # 1-5
    quality_rating = db.Column(db.Integer, nullable=False)   # 1-5
    comment = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=bd_now)

    order = db.relationship('Order', backref=db.backref('feedback', uselist=False))
    student = db.relationship('Student', backref='feedbacks')

    def __repr__(self):
        return f'<Feedback order={self.order_id}>'


class Notification(db.Model):
    """In-app notifications"""
    __tablename__ = 'notifications'

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=True)
    admin_id = db.Column(db.Integer, db.ForeignKey('admins.id'), nullable=True)
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    notif_type = db.Column(db.String(50), default='info')  # info, success, warning
    created_at = db.Column(db.DateTime, default=bd_now)

    def __repr__(self):
        return f'<Notification {self.title}>'


class SupportTicket(db.Model):
    """Student support tickets / suggestions"""
    __tablename__ = 'support_tickets'

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    ticket_type = db.Column(db.String(20), default='problem')  # problem, suggestion
    subject = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='open')  # open, in_progress, resolved
    admin_reply = db.Column(db.Text, default='')
    replied_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=bd_now)

    student = db.relationship('Student', backref='tickets')

    def __repr__(self):
        return f'<SupportTicket {self.id}>'
