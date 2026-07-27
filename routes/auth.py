from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from flask_login import login_user, logout_user, login_required, current_user
from models import Student, Admin, StudentRoll
from extensions import db, limiter
from utils.helpers import get_setting
import re

auth_bp = Blueprint('auth', __name__)


def validate_password(password):
    """Password must be 8+ chars, have uppercase, lowercase, digit"""
    if len(password) < 8:
        return False, 'পাসওয়ার্ড কমপক্ষে ৮ অক্ষরের হতে হবে।'
    if not re.search(r'[A-Z]', password):
        return False, 'পাসওয়ার্ডে অন্তত একটি বড় হাতের অক্ষর থাকতে হবে।'
    if not re.search(r'[a-z]', password):
        return False, 'পাসওয়ার্ডে অন্তত একটি ছোট হাতের অক্ষর থাকতে হবে।'
    if not re.search(r'\d', password):
        return False, 'পাসওয়ার্ডে অন্তত একটি সংখ্যা থাকতে হবে।'
    return True, ''


@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit("10 per minute")
def login():
    if current_user.is_authenticated:
        # Only redirect if already a student — admin should see login page normally
        if isinstance(current_user._get_current_object(), Student):
            return redirect(url_for('student.dashboard'))
        # Admin is logged in — logout first so student can login
        from flask_login import logout_user
        logout_user()

    if request.method == 'POST':
        roll = request.form.get('roll', '').strip()
        password = request.form.get('password', '')

        student = Student.query.filter_by(roll=roll).first()
        if student and student.check_password(password):
            if student.is_blocked:
                flash('আপনার একাউন্ট ব্লক করা হয়েছে। ক্যান্টিন অফিসে যোগাযোগ করুন।', 'danger')
                return redirect(url_for('auth.login'))
            login_user(student, remember=False)
            # Force password change if temp password was set
            try:
                if student.must_change_password:
                    return redirect(url_for('auth.change_password_forced'))
            except Exception:
                pass
            next_page = request.args.get('next')
            return redirect(next_page or url_for('student.dashboard'))
        else:
            flash('রোল নম্বর বা পাসওয়ার্ড ভুল হয়েছে।', 'danger')

    settings = {'college_name': get_setting('college_name'), 'canteen_name': get_setting('canteen_name')}
    return render_template('auth/login.html', settings=settings)


@auth_bp.route('/register', methods=['GET', 'POST'])
@limiter.limit("20 per minute")
def register():
    if current_user.is_authenticated:
        return redirect(url_for('student.dashboard'))

    step = request.args.get('step', '1')

    if request.method == 'POST':
        step = request.form.get('step', '1')

        if step == '1':
            # Step 1: Verify roll number
            roll = request.form.get('roll', '').strip().upper()
            roll_record = StudentRoll.query.filter_by(roll=roll).first()

            if not roll_record:
                flash('এই রোল নম্বর আমাদের তালিকায় নেই। ক্যান্টিন অফিসে যোগাযোগ করুন।', 'danger')
                return render_template('auth/register_step1.html',
                                       settings={'college_name': get_setting('college_name')})

            if roll_record.is_registered:
                flash('এই রোল নম্বর দিয়ে ইতিমধ্যে রেজিস্ট্রেশন হয়েছে।', 'danger')
                return render_template('auth/register_step1.html',
                                       settings={'college_name': get_setting('college_name')})

            # Store in session for step 2
            session['reg_roll'] = roll
            session['reg_name'] = roll_record.name
            return redirect(url_for('auth.register', step='2'))

        elif step == '2':
            roll = session.get('reg_roll')
            if not roll:
                return redirect(url_for('auth.register', step='1'))

            department = request.form.get('department', '').strip()
            sess = request.form.get('session', '').strip()
            phone = request.form.get('phone', '').strip()
            guardian_teacher = request.form.get('guardian_teacher', '').strip()
            password = request.form.get('password', '')
            confirm_password = request.form.get('confirm_password', '')

            # Validation
            errors = []
            if not department:
                errors.append('ডিপার্টমেন্ট দিতে হবে।')
            if not sess:
                errors.append('সেশন দিতে হবে।')
            if not phone or not re.match(r'^01[0-9]\d{8}$', phone):
                errors.append('সঠিক মোবাইল নম্বর দিন (যেমন: 01712345678)।')
            if not guardian_teacher:
                errors.append('গার্ডিয়ান/শিক্ষকের নাম দিতে হবে।')
            if password != confirm_password:
                errors.append('পাসওয়ার্ড মিলছে না।')

            valid_pw, pw_msg = validate_password(password)
            if not valid_pw:
                errors.append(pw_msg)

            if errors:
                for e in errors:
                    flash(e, 'danger')
                return render_template('auth/register_step2.html',
                                       roll=roll, name=session.get('reg_name'),
                                       settings={'college_name': get_setting('college_name')})

            # Handle photo upload
            photo_filename = 'default.png'
            if 'photo' in request.files:
                photo = request.files['photo']
                if photo and photo.filename:
                    import os
                    from werkzeug.utils import secure_filename
                    allowed = {'png', 'jpg', 'jpeg'}
                    ext = photo.filename.rsplit('.', 1)[-1].lower()
                    if ext in allowed:
                        photo_filename = f"{roll}.{ext}"
                        upload_path = os.path.join('static', 'uploads', 'profiles')
                        os.makedirs(upload_path, exist_ok=True)
                        photo.save(os.path.join(upload_path, photo_filename))

            # Create student
            roll_record = StudentRoll.query.filter_by(roll=roll).first()
            student = Student(
                roll=roll,
                name=roll_record.name,
                department=department,
                session=sess,
                phone=phone,
                guardian_teacher=guardian_teacher,
                photo=photo_filename
            )
            student.set_password(password)
            roll_record.is_registered = True
            db.session.add(student)
            db.session.commit()

            session.pop('reg_roll', None)
            session.pop('reg_name', None)

            # Logout any existing session (e.g. admin) before going to login
            from flask_login import logout_user
            logout_user()

            flash('রেজিস্ট্রেশন সফল হয়েছে! এখন লগইন করুন।', 'success')
            return redirect(url_for('auth.login'))

    settings = {'college_name': get_setting('college_name'), 'canteen_name': get_setting('canteen_name')}
    if step == '2':
        roll = session.get('reg_roll')
        if not roll:
            return redirect(url_for('auth.register', step='1'))
        return render_template('auth/register_step2.html',
                               roll=roll, name=session.get('reg_name'), settings=settings)

    return render_template('auth/register_step1.html', settings=settings)


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('সফলভাবে লগআউট হয়েছেন।', 'info')
    return redirect(url_for('main.index'))


@auth_bp.route('/forgot-password')
def forgot_password():
    settings = {'college_name': get_setting('college_name'), 'canteen_name': get_setting('canteen_name')}
    return render_template('auth/forgot_password.html', settings=settings)


@auth_bp.route('/change-password-forced', methods=['GET', 'POST'])
@login_required
def change_password_forced():
    student = current_user._get_current_object()
    if not isinstance(student, Student):
        return redirect(url_for('main.index'))

    if not student.must_change_password:
        return redirect(url_for('student.dashboard'))

    if request.method == 'POST':
        new_pw = request.form.get('new_password', '')
        confirm_pw = request.form.get('confirm_password', '')

        if new_pw != confirm_pw:
            flash('পাসওয়ার্ড মিলছে না।', 'danger')
        else:
            valid, msg = validate_password(new_pw)
            if not valid:
                flash(msg, 'danger')
            else:
                student.set_password(new_pw)
                student.must_change_password = False
                db.session.commit()
                flash('পাসওয়ার্ড পরিবর্তন হয়েছে! এখন লগইন করুন।', 'success')
                from flask_login import logout_user
                logout_user()
                return redirect(url_for('auth.login'))

    settings = {'college_name': get_setting('college_name'), 'canteen_name': get_setting('canteen_name')}
    return render_template('auth/change_password_forced.html', settings=settings)


# Admin login (hidden URL)
@auth_bp.route('/canteen-admin-login', methods=['GET', 'POST'])
@limiter.limit("5 per minute")
def admin_login():
    if current_user.is_authenticated and isinstance(current_user._get_current_object(), Admin):
        return redirect(url_for('admin.dashboard'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        admin = Admin.query.filter_by(username=username).first()
        if admin and admin.check_password(password):
            login_user(admin, remember=False)
            return redirect(url_for('admin.dashboard'))
        else:
            flash('ব্যবহারকারীর নাম বা পাসওয়ার্ড ভুল।', 'danger')

    settings = {'college_name': get_setting('college_name'), 'canteen_name': get_setting('canteen_name')}
    return render_template('auth/admin_login.html', settings=settings)
