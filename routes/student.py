from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from models import Student, Order, OrderItem, DailyMenu, MenuItem, Notification, Settings, Feedback
from extensions import db
from utils.helpers import (generate_token, generate_qr_code, get_setting,
                           is_order_deadline_passed, is_cancel_deadline_passed,
                           get_tomorrow, send_notification, notify_all_admins)
from datetime import date, datetime
import os
import re

student_bp = Blueprint('student', __name__)


def student_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not isinstance(current_user._get_current_object(), Student):
            flash('এই পেজ শুধু শিক্ষার্থীদের জন্য।', 'danger')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


@student_bp.route('/dashboard')
@login_required
@student_required
def dashboard():
    student = current_user._get_current_object()
    today = date.today()
    tomorrow = get_tomorrow()
    today_order = Order.query.filter_by(student_id=student.id, order_date=today).first()
    tomorrow_order = Order.query.filter_by(student_id=student.id, order_date=tomorrow).first()
    tomorrow_menu = DailyMenu.query.filter_by(date=tomorrow).count()
    deadline_passed = is_order_deadline_passed()
    unread_count = Notification.query.filter_by(student_id=student.id, is_read=False).count()
    settings = {
        'college_name': get_setting('college_name'),
        'canteen_name': get_setting('canteen_name'),
        'order_deadline': get_setting('order_deadline', '22:00'),
        'cancel_deadline': get_setting('cancel_deadline', '08:00'),
    }
    return render_template('student/dashboard.html', student=student,
                           today_order=today_order, tomorrow_order=tomorrow_order,
                           tomorrow_menu=tomorrow_menu, deadline_passed=deadline_passed,
                           unread_count=unread_count, settings=settings)


@student_bp.route('/order', methods=['GET', 'POST'])
@login_required
@student_required
def order():
    student = current_user._get_current_object()
    tomorrow = get_tomorrow()
    deadline_passed = is_order_deadline_passed()
    existing = Order.query.filter_by(student_id=student.id, order_date=tomorrow
                                     ).filter(Order.status != 'cancelled').first()
    daily = DailyMenu.query.filter_by(date=tomorrow).all()
    menu_items = [d.menu_item for d in daily if d.menu_item.is_available]
    show_date = tomorrow
    if not menu_items:
        daily_today = DailyMenu.query.filter_by(date=date.today()).all()
        menu_items = [d.menu_item for d in daily_today if d.menu_item.is_available]
        show_date = date.today()
    if not menu_items:
        menu_items = MenuItem.query.filter_by(is_available=True).all()
        show_date = None
    can_order = (not deadline_passed and not existing and show_date == tomorrow)

    if request.method == 'POST':
        if not can_order:
            flash('এই মুহূর্তে অর্ডার দেওয়া সম্ভব নয়।', 'danger')
            return redirect(url_for('student.order'))
        selected_items = request.form.getlist('items')
        quantities = {}
        for item_id in selected_items:
            qty = int(request.form.get(f'qty_{item_id}', 1))
            quantities[int(item_id)] = max(1, min(qty, 10))
        if not selected_items:
            flash('অন্তত একটি আইটেম বাছাই করুন।', 'danger')
            return redirect(url_for('student.order'))
        token = generate_token()
        total = 0
        new_order = Order(token_number=token, student_id=student.id,
                          order_date=tomorrow, status='confirmed')
        db.session.add(new_order)
        db.session.flush()
        for item_id, qty in quantities.items():
            menu_item = MenuItem.query.get(item_id)
            if menu_item and menu_item.is_available:
                oi = OrderItem(order_id=new_order.id, menu_item_id=item_id,
                               quantity=qty, price=menu_item.price)
                db.session.add(oi)
                total += menu_item.price * qty
        new_order.total_price = total
        qr_data = f"CANTEEN|TOKEN:{token}|STUDENT:{student.roll}|DATE:{tomorrow}"
        new_order.qr_code = generate_qr_code(qr_data)
        db.session.commit()
        send_notification(student_id=student.id, title='অর্ডার নিশ্চিত হয়েছে!',
                          message=f'টোকেন: {token} — {tomorrow} তারিখের অর্ডার নিশ্চিত।',
                          notif_type='success')
        notify_all_admins(title='নতুন অর্ডার!',
                          message=f'{student.name} ({student.roll}) অর্ডার দিয়েছেন। টোকেন: {token}',
                          notif_type='info')
        flash(f'অর্ডার সফল! টোকেন: {token}', 'success')
        return redirect(url_for('student.order_detail', order_id=new_order.id))

    settings = {'college_name': get_setting('college_name'), 'canteen_name': get_setting('canteen_name'),
                'order_deadline': get_setting('order_deadline', '22:00')}
    return render_template('student/order.html', menu_items=menu_items, tomorrow=tomorrow,
                           show_date=show_date, can_order=can_order,
                           deadline_passed=deadline_passed, existing=existing, settings=settings)


@student_bp.route('/orders')
@login_required
@student_required
def my_orders():
    student = current_user._get_current_object()
    orders = Order.query.filter_by(student_id=student.id).order_by(Order.created_at.desc()).all()
    unread_count = Notification.query.filter_by(student_id=student.id, is_read=False).count()
    settings = {'college_name': get_setting('college_name'), 'canteen_name': get_setting('canteen_name')}
    return render_template('student/my_orders.html', orders=orders,
                           unread_count=unread_count, settings=settings)


@student_bp.route('/order/<int:order_id>')
@login_required
@student_required
def order_detail(order_id):
    student = current_user._get_current_object()
    order = Order.query.filter_by(id=order_id, student_id=student.id).first_or_404()
    can_cancel = (order.status not in ['cancelled', 'delivered'] and not is_cancel_deadline_passed())
    unread_count = Notification.query.filter_by(student_id=student.id, is_read=False).count()
    settings = {'college_name': get_setting('college_name'), 'canteen_name': get_setting('canteen_name'),
                'cancel_deadline': get_setting('cancel_deadline', '08:00')}
    return render_template('student/order_detail.html', order=order, can_cancel=can_cancel,
                           unread_count=unread_count, settings=settings)


@student_bp.route('/order/<int:order_id>/cancel', methods=['POST'])
@login_required
@student_required
def cancel_order(order_id):
    student = current_user._get_current_object()
    order = Order.query.filter_by(id=order_id, student_id=student.id).first_or_404()
    if order.status in ['cancelled', 'delivered']:
        flash('এই অর্ডার বাতিল করা সম্ভব নয়।', 'danger')
        return redirect(url_for('student.order_detail', order_id=order_id))
    if is_cancel_deadline_passed():
        flash(f'বাতিলের সময় পার হয়ে গেছে।', 'danger')
        return redirect(url_for('student.order_detail', order_id=order_id))
    order.status = 'cancelled'
    student.warning_count += 1
    db.session.commit()
    send_notification(student_id=student.id, title='অর্ডার বাতিল হয়েছে',
                      message=f'টোকেন {order.token_number} বাতিল করা হয়েছে।',
                      notif_type='warning')
    flash('অর্ডার বাতিল হয়েছে।', 'info')
    return redirect(url_for('student.my_orders'))


@student_bp.route('/notifications')
@login_required
@student_required
def notifications():
    student = current_user._get_current_object()
    notifs = Notification.query.filter_by(student_id=student.id).order_by(
        Notification.created_at.desc()).limit(50).all()
    Notification.query.filter_by(student_id=student.id, is_read=False).update({'is_read': True})
    db.session.commit()
    settings = {'college_name': get_setting('college_name'), 'canteen_name': get_setting('canteen_name')}
    return render_template('student/notifications.html', notifications=notifs, settings=settings)


@student_bp.route('/notifications/count')
@student_required
def notification_count():
    if not current_user.is_authenticated or not isinstance(current_user._get_current_object(), Student):
        return jsonify({'count': 0})
    student = current_user._get_current_object()
    count = Notification.query.filter_by(student_id=student.id, is_read=False).count()
    return jsonify({'count': count})


@student_bp.route('/profile', methods=['GET', 'POST'])
@login_required
@student_required
def profile():
    student = current_user._get_current_object()
    unread_count = Notification.query.filter_by(student_id=student.id, is_read=False).count()
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'change_password':
            old_pw = request.form.get('old_password', '')
            new_pw = request.form.get('new_password', '')
            confirm_pw = request.form.get('confirm_password', '')
            if not student.check_password(old_pw):
                flash('পুরানো পাসওয়ার্ড ভুল।', 'danger')
            elif new_pw != confirm_pw:
                flash('নতুন পাসওয়ার্ড মিলছে না।', 'danger')
            else:
                from routes.auth import validate_password
                valid, msg = validate_password(new_pw)
                if not valid:
                    flash(msg, 'danger')
                else:
                    student.set_password(new_pw)
                    db.session.commit()
                    flash('পাসওয়ার্ড পরিবর্তন হয়েছে।', 'success')
        elif action == 'update_photo':
            if 'photo' in request.files:
                photo = request.files['photo']
                if photo and photo.filename:
                    allowed = {'png', 'jpg', 'jpeg'}
                    ext = photo.filename.rsplit('.', 1)[-1].lower()
                    if ext in allowed:
                        photo_filename = f"{student.roll}.{ext}"
                        upload_path = os.path.join('static', 'uploads', 'profiles')
                        os.makedirs(upload_path, exist_ok=True)
                        photo.save(os.path.join(upload_path, photo_filename))
                        student.photo = photo_filename
                        db.session.commit()
                        flash('ছবি আপডেট হয়েছে।', 'success')
                    else:
                        flash('শুধু PNG, JPG ফাইল আপলোড করুন।', 'danger')
        return redirect(url_for('student.profile'))
    settings = {'college_name': get_setting('college_name'), 'canteen_name': get_setting('canteen_name')}
    return render_template('student/profile.html', student=student,
                           unread_count=unread_count, settings=settings)


@student_bp.route('/order/<int:order_id>/feedback', methods=['GET', 'POST'])
@login_required
@student_required
def give_feedback(order_id):
    student = current_user._get_current_object()
    order = Order.query.filter_by(id=order_id, student_id=student.id).first_or_404()
    if order.status != 'delivered':
        flash('শুধুমাত্র সম্পন্ন অর্ডারে ফিডব্যাক দেওয়া যাবে।', 'warning')
        return redirect(url_for('student.order_detail', order_id=order_id))
    if order.feedback:
        flash('এই অর্ডারে আগেই ফিডব্যাক দেওয়া হয়েছে।', 'info')
        return redirect(url_for('student.order_detail', order_id=order_id))
    if request.method == 'POST':
        try:
            qty_r = int(request.form.get('quantity_rating', 0))
            qlt_r = int(request.form.get('quality_rating', 0))
        except ValueError:
            flash('সঠিক রেটিং দিন।', 'danger')
            return redirect(url_for('student.give_feedback', order_id=order_id))
        if not (1 <= qty_r <= 5) or not (1 <= qlt_r <= 5):
            flash('রেটিং ১ থেকে ৫ এর মধ্যে হতে হবে।', 'danger')
            return redirect(url_for('student.give_feedback', order_id=order_id))
        comment = request.form.get('comment', '').strip()[:500]
        fb = Feedback(order_id=order.id, student_id=student.id,
                      quantity_rating=qty_r, quality_rating=qlt_r, comment=comment)
        db.session.add(fb)
        db.session.commit()
        flash('ফিডব্যাক দেওয়ার জন্য ধন্যবাদ! 🙏', 'success')
        return redirect(url_for('student.order_detail', order_id=order_id))
    unread_count = Notification.query.filter_by(student_id=student.id, is_read=False).count()
    settings = {'college_name': get_setting('college_name'), 'canteen_name': get_setting('canteen_name')}
    return render_template('student/feedback.html', order=order,
                           unread_count=unread_count, settings=settings)
