from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, make_response
from flask_login import login_required, current_user
from models import Admin, Student, StudentRoll, MenuItem, DailyMenu, Order, OrderItem, Settings, Notification, Feedback
from extensions import db
from utils.helpers import get_setting, send_notification
from datetime import date, datetime
import csv
import io
import json

admin_bp = Blueprint('admin', __name__)


def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.admin_login'))
        if not isinstance(current_user._get_current_object(), Admin):
            return redirect(url_for('auth.admin_login'))
        return f(*args, **kwargs)
    return decorated


def get_unread_count():
    admin = current_user._get_current_object()
    return Notification.query.filter_by(admin_id=admin.id, is_read=False).count()


@admin_bp.route('/dashboard')
@login_required
@admin_required
def dashboard():
    today = date.today()
    total_orders_today = Order.query.filter_by(order_date=today).filter(
        Order.status != 'cancelled').count()
    pending = Order.query.filter_by(order_date=today, status='confirmed').count()
    ready = Order.query.filter_by(order_date=today, status='ready').count()
    delivered = Order.query.filter_by(order_date=today, status='delivered').count()
    total_students = Student.query.filter_by(is_blocked=False).count()
    unread = get_unread_count()
    recent_orders = Order.query.filter_by(order_date=today).filter(
        Order.status != 'cancelled').order_by(Order.created_at.desc()).limit(10).all()
    settings = {'college_name': get_setting('college_name'), 'canteen_name': get_setting('canteen_name')}
    return render_template('admin/dashboard.html',
                           total_orders_today=total_orders_today,
                           pending=pending, ready=ready, delivered=delivered,
                           total_students=total_students, unread=unread,
                           recent_orders=recent_orders, today=today, settings=settings)


# ── MENU MANAGEMENT ──────────────────────────────────────────────────────────

@admin_bp.route('/menu')
@login_required
@admin_required
def menu():
    items = MenuItem.query.order_by(MenuItem.name).all()
    unread = get_unread_count()
    settings = {'college_name': get_setting('college_name'), 'canteen_name': get_setting('canteen_name')}
    return render_template('admin/menu.html', items=items, unread=unread, settings=settings)


@admin_bp.route('/menu/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_menu_item():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        price_str = request.form.get('price', '0')
        is_available = request.form.get('is_available') == 'on'

        try:
            price = float(price_str)
            if price < 0:
                raise ValueError
        except ValueError:
            flash('সঠিক মূল্য দিন।', 'danger')
            return redirect(url_for('admin.add_menu_item'))

        if not name:
            flash('আইটেমের নাম দিতে হবে।', 'danger')
            return redirect(url_for('admin.add_menu_item'))

        image_filename = 'food_default.png'
        if 'image' in request.files:
            img = request.files['image']
            if img and img.filename:
                import os
                from werkzeug.utils import secure_filename
                allowed = {'png', 'jpg', 'jpeg', 'webp'}
                ext = img.filename.rsplit('.', 1)[-1].lower()
                if ext in allowed:
                    image_filename = f"food_{secure_filename(name.replace(' ', '_'))}.{ext}"
                    upload_path = os.path.join('static', 'uploads', 'food')
                    os.makedirs(upload_path, exist_ok=True)
                    img.save(os.path.join(upload_path, image_filename))

        item = MenuItem(name=name, description=description, price=price,
                        image=image_filename, is_available=is_available)
        db.session.add(item)
        db.session.commit()
        flash(f'"{name}" মেনুতে যোগ হয়েছে।', 'success')
        return redirect(url_for('admin.menu'))

    unread = get_unread_count()
    settings = {'college_name': get_setting('college_name'), 'canteen_name': get_setting('canteen_name')}
    return render_template('admin/add_menu_item.html', unread=unread, settings=settings)


@admin_bp.route('/menu/edit/<int:item_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_menu_item(item_id):
    item = MenuItem.query.get_or_404(item_id)
    if request.method == 'POST':
        item.name = request.form.get('name', item.name).strip()
        item.description = request.form.get('description', '').strip()
        try:
            item.price = float(request.form.get('price', item.price))
        except ValueError:
            flash('সঠিক মূল্য দিন।', 'danger')
            return redirect(url_for('admin.edit_menu_item', item_id=item_id))
        item.is_available = request.form.get('is_available') == 'on'
        db.session.commit()
        flash('আইটেম আপডেট হয়েছে।', 'success')
        return redirect(url_for('admin.menu'))

    unread = get_unread_count()
    settings = {'college_name': get_setting('college_name'), 'canteen_name': get_setting('canteen_name')}
    return render_template('admin/edit_menu_item.html', item=item, unread=unread, settings=settings)


@admin_bp.route('/menu/delete/<int:item_id>', methods=['POST'])
@login_required
@admin_required
def delete_menu_item(item_id):
    item = MenuItem.query.get_or_404(item_id)
    db.session.delete(item)
    db.session.commit()
    flash('আইটেম মুছে ফেলা হয়েছে।', 'info')
    return redirect(url_for('admin.menu'))


@admin_bp.route('/menu/toggle/<int:item_id>', methods=['POST'])
@login_required
@admin_required
def toggle_menu_item(item_id):
    item = MenuItem.query.get_or_404(item_id)
    item.is_available = not item.is_available
    db.session.commit()
    return jsonify({'available': item.is_available})


@admin_bp.route('/daily-menu', methods=['GET', 'POST'])
@login_required
@admin_required
def daily_menu():
    selected_date_str = request.args.get('date', str(date.today()))
    try:
        selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
    except ValueError:
        selected_date = date.today()

    if request.method == 'POST':
        selected_date_str = request.form.get('date')
        try:
            selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
        except ValueError:
            flash('সঠিক তারিখ দিন।', 'danger')
            return redirect(url_for('admin.daily_menu'))

        # Remove existing daily menu for this date
        DailyMenu.query.filter_by(date=selected_date).delete()
        db.session.commit()

        selected_items = request.form.getlist('items')
        for item_id in selected_items:
            dm = DailyMenu(date=selected_date, menu_item_id=int(item_id))
            db.session.add(dm)
        db.session.commit()
        flash(f'{selected_date} তারিখের মেনু সেট হয়েছে।', 'success')
        return redirect(url_for('admin.daily_menu', date=selected_date_str))

    all_items = MenuItem.query.filter_by(is_available=True).all()
    current_daily = [dm.menu_item_id for dm in DailyMenu.query.filter_by(date=selected_date).all()]
    unread = get_unread_count()
    settings = {'college_name': get_setting('college_name'), 'canteen_name': get_setting('canteen_name')}
    return render_template('admin/daily_menu.html', all_items=all_items,
                           current_daily=current_daily, selected_date=selected_date,
                           unread=unread, settings=settings)


# ── ORDER MANAGEMENT ─────────────────────────────────────────────────────────

@admin_bp.route('/orders')
@login_required
@admin_required
def orders():
    selected_date_str = request.args.get('date', str(date.today()))
    try:
        selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
    except ValueError:
        selected_date = date.today()

    order_list = Order.query.filter_by(order_date=selected_date).filter(
        Order.status != 'cancelled').order_by(Order.created_at.asc()).all()
    unread = get_unread_count()
    settings = {'college_name': get_setting('college_name'), 'canteen_name': get_setting('canteen_name')}
    return render_template('admin/orders.html', orders=order_list,
                           selected_date=selected_date, unread=unread, settings=settings)


@admin_bp.route('/orders/update-status/<int:order_id>', methods=['POST'])
@login_required
@admin_required
def update_order_status(order_id):
    order = Order.query.get_or_404(order_id)
    new_status = request.form.get('status')
    allowed = ['confirmed', 'ready', 'delivered', 'cancelled']
    if new_status not in allowed:
        flash('অবৈধ স্ট্যাটাস।', 'danger')
        return redirect(url_for('admin.orders'))

    old_status = order.status
    order.status = new_status
    db.session.commit()

    # Notify student on ready
    if new_status == 'ready' and old_status != 'ready':
        send_notification(
            student_id=order.student_id,
            title='আপনার খাবার প্রস্তুত!',
            message=f'টোকেন {order.token_number} এর অর্ডার প্রস্তুত। ক্যান্টিনে এসে নিয়ে যান।',
            notif_type='success'
        )
    flash('স্ট্যাটাস আপডেট হয়েছে।', 'success')
    return redirect(url_for('admin.orders', date=str(order.order_date)))


@admin_bp.route('/orders/print')
@login_required
@admin_required
def print_orders():
    selected_date_str = request.args.get('date', str(date.today()))
    try:
        selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
    except ValueError:
        selected_date = date.today()
    order_list = Order.query.filter_by(order_date=selected_date).filter(
        Order.status != 'cancelled').order_by(Order.created_at.asc()).all()
    settings = {'college_name': get_setting('college_name'), 'canteen_name': get_setting('canteen_name')}
    return render_template('admin/print_orders.html', orders=order_list,
                           selected_date=selected_date, settings=settings)


@admin_bp.route('/orders/download-csv')
@login_required
@admin_required
def download_orders_csv():
    selected_date_str = request.args.get('date', str(date.today()))
    try:
        selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
    except ValueError:
        selected_date = date.today()

    order_list = Order.query.filter_by(order_date=selected_date).filter(
        Order.status != 'cancelled').all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Token', 'Student Name', 'Roll', 'Department', 'Session', 'Items', 'Total', 'Status'])
    for o in order_list:
        items_str = ', '.join([f"{oi.menu_item.name} x{oi.quantity}" for oi in o.items])
        writer.writerow([o.token_number, o.student.name, o.student.roll,
                         o.student.department, o.student.session, items_str,
                         f"{o.total_price:.2f} BDT", o.status])

    response = make_response(output.getvalue())
    response.headers['Content-Disposition'] = f'attachment; filename=orders_{selected_date}.csv'
    response.headers['Content-type'] = 'text/csv'
    return response


# ── STUDENT MANAGEMENT ───────────────────────────────────────────────────────

@admin_bp.route('/students')
@login_required
@admin_required
def students():
    # Show all rolls (registered and unregistered)
    all_rolls = StudentRoll.query.order_by(StudentRoll.roll).all()
    registered = {s.roll: s for s in Student.query.all()}
    unread = get_unread_count()
    settings = {'college_name': get_setting('college_name'), 'canteen_name': get_setting('canteen_name')}
    return render_template('admin/students.html', all_rolls=all_rolls,
                           registered=registered, unread=unread, settings=settings)


@admin_bp.route('/students/add-manual', methods=['POST'])
@login_required
@admin_required
def add_student_manual():
    roll = request.form.get('roll', '').strip().upper()
    name = request.form.get('name', '').strip()

    if not roll or not name:
        flash('রোল নম্বর এবং নাম দিতে হবে।', 'danger')
        return redirect(url_for('admin.upload_csv'))

    if StudentRoll.query.filter_by(roll=roll).first():
        flash(f'"{roll}" রোল নম্বর আগে থেকেই আছে।', 'warning')
        return redirect(url_for('admin.upload_csv'))

    db.session.add(StudentRoll(roll=roll, name=name))
    db.session.commit()
    flash(f'✅ {name} ({roll}) সফলভাবে যোগ হয়েছে।', 'success')
    return redirect(url_for('admin.students'))


@admin_bp.route('/students/upload-csv', methods=['GET', 'POST'])
@login_required
@admin_required
def upload_csv():
    if request.method == 'POST':
        if 'csv_file' not in request.files:
            flash('কোনো ফাইল বাছাই করা হয়নি।', 'danger')
            return redirect(url_for('admin.upload_csv'))

        f = request.files['csv_file']
        if not f.filename.endswith('.csv'):
            flash('শুধু CSV ফাইল আপলোড করুন।', 'danger')
            return redirect(url_for('admin.upload_csv'))

        stream = io.StringIO(f.stream.read().decode('UTF-8-SIG'))
        reader = csv.DictReader(stream)
        added = 0
        skipped = 0
        errors = []

        for i, row in enumerate(reader, start=2):
            roll = str(row.get('roll', row.get('Roll', row.get('ROLL', '')))).strip().upper()
            name = str(row.get('name', row.get('Name', row.get('NAME', '')))).strip()
            if not roll or not name:
                errors.append(f'লাইন {i}: roll বা name খালি।')
                continue
            if StudentRoll.query.filter_by(roll=roll).first():
                skipped += 1
                continue
            db.session.add(StudentRoll(roll=roll, name=name))
            added += 1

        db.session.commit()
        flash(f'{added}টি নতুন রোল যোগ হয়েছে। {skipped}টি আগে থেকেই ছিল।', 'success')
        if errors:
            for e in errors[:5]:
                flash(e, 'warning')
        return redirect(url_for('admin.students'))

    unread = get_unread_count()
    settings = {'college_name': get_setting('college_name'), 'canteen_name': get_setting('canteen_name')}
    return render_template('admin/upload_csv.html', unread=unread, settings=settings)


@admin_bp.route('/students/delete-roll/<int:roll_id>', methods=['POST'])
@login_required
@admin_required
def delete_roll(roll_id):
    roll_record = StudentRoll.query.get_or_404(roll_id)
    # Block deletion if already registered
    if roll_record.is_registered:
        flash('নিবন্ধিত শিক্ষার্থীর রোল মুছে ফেলা যাবে না।', 'danger')
        return redirect(url_for('admin.students'))
    db.session.delete(roll_record)
    db.session.commit()
    flash(f'"{roll_record.roll}" মুছে ফেলা হয়েছে।', 'info')
    return redirect(url_for('admin.students'))


@admin_bp.route('/students/toggle-block/<int:student_id>', methods=['POST'])
@login_required
@admin_required
def toggle_block(student_id):
    student = Student.query.get_or_404(student_id)
    student.is_blocked = not student.is_blocked
    db.session.commit()
    status = 'ব্লক' if student.is_blocked else 'আনব্লক'
    flash(f'{student.name} কে {status} করা হয়েছে।', 'info')
    return redirect(url_for('admin.students'))


# ── FEEDBACK ─────────────────────────────────────────────────────────────────

@admin_bp.route('/feedback')
@admin_required
def feedback():
    from sqlalchemy import func
    feedbacks = Feedback.query.order_by(Feedback.created_at.desc()).all()
    # Averages
    avg = db.session.query(
        func.avg(Feedback.quantity_rating).label('avg_qty'),
        func.avg(Feedback.quality_rating).label('avg_qlt'),
        func.count(Feedback.id).label('total')
    ).first()
    unread = get_unread_count()
    settings = {'college_name': get_setting('college_name'), 'canteen_name': get_setting('canteen_name')}
    return render_template('admin/feedback.html', feedbacks=feedbacks,
                           avg=avg, unread=unread, settings=settings)


# ── NOTIFICATIONS ─────────────────────────────────────────────────────────────
@admin_bp.route('/notifications', methods=['GET', 'POST'])
@admin_required
def notifications():
    admin = current_user._get_current_object()

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        message = request.form.get('message', '').strip()
        target = request.form.get('target', 'all')
        notif_type = request.form.get('notif_type', 'info')

        if not title or not message:
            flash('শিরোনাম এবং বার্তা দিতে হবে।', 'danger')
            return redirect(url_for('admin.notifications'))

        if target == 'all':
            students = Student.query.filter_by(is_blocked=False).all()
            for s in students:
                send_notification(student_id=s.id, title=title,
                                  message=message, notif_type=notif_type)
            flash(f'✅ {len(students)} জন শিক্ষার্থীকে notification পাঠানো হয়েছে।', 'success')
        else:
            roll = target.strip().upper()
            student = Student.query.filter_by(roll=roll).first()
            if not student:
                flash(f'"{roll}" রোল নম্বরের শিক্ষার্থী পাওয়া যায়নি।', 'danger')
                return redirect(url_for('admin.notifications'))
            send_notification(student_id=student.id, title=title,
                              message=message, notif_type=notif_type)
            flash(f'✅ {student.name} কে notification পাঠানো হয়েছে।', 'success')

        return redirect(url_for('admin.notifications'))

    # GET
    notifs = Notification.query.filter_by(admin_id=admin.id).order_by(
        Notification.created_at.desc()).limit(50).all()
    Notification.query.filter_by(admin_id=admin.id, is_read=False).update({'is_read': True})
    db.session.commit()
    students = Student.query.filter_by(is_blocked=False).order_by(Student.roll).all()
    unread = 0
    settings = {'college_name': get_setting('college_name'), 'canteen_name': get_setting('canteen_name')}
    return render_template('admin/notifications.html', notifications=notifs,
                           students=students, unread=unread, settings=settings)


@admin_bp.route('/notifications/count')
@admin_required
def notification_count():
    if not current_user.is_authenticated or not isinstance(current_user._get_current_object(), Admin):
        return jsonify({'count': 0})
    count = get_unread_count()
    return jsonify({'count': count})


# ── SETTINGS ─────────────────────────────────────────────────────────────────

@admin_bp.route('/settings', methods=['GET', 'POST'])
@login_required
@admin_required
def settings_page():
    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'update_general':
            keys = ['college_name', 'canteen_name', 'canteen_open', 'canteen_close',
                    'order_deadline', 'cancel_deadline']
            for key in keys:
                val = request.form.get(key, '').strip()
                if val:
                    s = Settings.query.filter_by(key=key).first()
                    if s:
                        s.value = val
                    else:
                        db.session.add(Settings(key=key, value=val))
            db.session.commit()
            flash('সেটিংস সেভ হয়েছে।', 'success')

        elif action == 'change_password':
            admin = current_user._get_current_object()
            old_pw = request.form.get('old_password', '')
            new_pw = request.form.get('new_password', '')
            confirm_pw = request.form.get('confirm_password', '')
            if not admin.check_password(old_pw):
                flash('পুরানো পাসওয়ার্ড ভুল।', 'danger')
            elif new_pw != confirm_pw:
                flash('নতুন পাসওয়ার্ড মিলছে না।', 'danger')
            elif len(new_pw) < 8:
                flash('পাসওয়ার্ড কমপক্ষে ৮ অক্ষরের হতে হবে।', 'danger')
            else:
                admin.set_password(new_pw)
                db.session.commit()
                flash('পাসওয়ার্ড পরিবর্তন হয়েছে।', 'success')

        elif action == 'backup':
            # Download all data as JSON
            students_data = [{'roll': s.roll, 'name': s.name, 'department': s.department,
                               'session': s.session, 'phone': s.phone} for s in Student.query.all()]
            orders_data = [{'token': o.token_number, 'student_roll': o.student.roll,
                            'date': str(o.order_date), 'status': o.status,
                            'total': o.total_price} for o in Order.query.all()]
            backup = {'exported_at': str(datetime.utcnow()), 'students': students_data, 'orders': orders_data}
            response = make_response(json.dumps(backup, ensure_ascii=False, indent=2))
            response.headers['Content-Disposition'] = 'attachment; filename=canteen_backup.json'
            response.headers['Content-Type'] = 'application/json'
            return response

        return redirect(url_for('admin.settings_page'))

    current_settings = {s.key: s.value for s in Settings.query.all()}
    unread = get_unread_count()
    return render_template('admin/settings.html', current_settings=current_settings,
                           unread=unread, settings={'college_name': get_setting('college_name'),
                                                    'canteen_name': get_setting('canteen_name')})


# ── VERIFY & SERVE ────────────────────────────────────────────────────────────
@admin_bp.route('/verify', methods=['GET', 'POST'])
@admin_required
def verify():
    order = None
    error = None
    token = request.args.get('token', '').strip().upper()

    if request.method == 'POST':
        token = request.form.get('token', '').strip().upper()
        return redirect(url_for('admin.verify', token=token))

    if token:
        # Support both "#0047" and "0047"
        if not token.startswith('#'):
            token = '#' + token
        order = Order.query.filter_by(token_number=token).first()
        if not order:
            error = f'"{token}" টোকেন পাওয়া যায়নি।'
        elif order.status == 'cancelled':
            error = f'এই অর্ডার ({token}) বাতিল করা হয়েছে।'
        elif order.status == 'delivered':
            error = f'এই অর্ডার ({token}) আগেই দেওয়া হয়েছে।'

    settings = {'college_name': get_setting('college_name'), 'canteen_name': get_setting('canteen_name')}
    unread = get_unread_count()
    return render_template('admin/verify.html', order=order, error=error,
                           token=token, unread=unread, settings=settings)


@admin_bp.route('/verify/serve/<int:order_id>', methods=['POST'])
@admin_required
def serve_order(order_id):
    order = Order.query.get_or_404(order_id)
    if order.status not in ['cancelled', 'delivered']:
        order.status = 'delivered'
        db.session.commit()
        # Notify student
        send_notification(
            student_id=order.student_id,
            title='খাবার দেওয়া হয়েছে ✓',
            message=f'টোকেন {order.token_number} এর অর্ডার সম্পন্ন হয়েছে। ফিডব্যাক দিতে ভুলবেন না!',
            notif_type='success'
        )
        flash(f'✅ {order.token_number} — খাবার দেওয়া সম্পন্ন!', 'success')
    else:
        flash('এই অর্ডার আগেই সম্পন্ন বা বাতিল।', 'warning')
    return redirect(url_for('admin.verify'))
