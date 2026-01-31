from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from extensions import db
from models import User, CandidateProfile, Company, Notification, InterviewerProfile
from services import create_notification, log_activity

auth_bp = Blueprint('auth', __name__)


# =====================================================
# INTERVIEWER REGISTRATION
# =====================================================
@auth_bp.route('/register/interviewer', methods=['GET', 'POST'])
def register_interviewer():
    """Registration page for expert interviewers"""
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        phone = request.form.get('phone', '').strip()
        
        # Validation
        if not all([email, password, first_name, last_name]):
            flash('Please fill in all required fields.', 'error')
            return render_template('auth/register_interviewer.html')
        
        if password != confirm_password:
            flash('Passwords do not match.', 'error')
            return render_template('auth/register_interviewer.html')
        
        if len(password) < 8:
            flash('Password must be at least 8 characters long.', 'error')
            return render_template('auth/register_interviewer.html')
        
        # Check if email exists
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            flash('This email is already registered. Please login or use a different email.', 'error')
            return render_template('auth/register_interviewer.html')
        
        try:
            # Create user account
            new_user = User(
                email=email,
                password_hash=generate_password_hash(password),
                user_type='interviewer',
                first_name=first_name,
                last_name=last_name,
                phone=phone,
                is_active=True
            )
            db.session.add(new_user)
            db.session.flush()
            
            # Create pending interviewer profile
            profile = InterviewerProfile(
                user_id=new_user.id,
                interviewer_type='independent',
                approval_status='pending',  # Needs to complete application
                is_verified=False,
                is_active=False,  # Not active until application approved
                is_available=False
            )
            db.session.add(profile)
            db.session.commit()
            
            # Log activity
            log_activity('users', 'INSERT', new_user.id, 
                        new_values={'email': email, 'user_type': 'interviewer'})
            
            # Create welcome notification
            create_notification(
                new_user.id, 
                'Welcome to HireMe!', 
                'Your interviewer account has been created. Please complete your expert application to start conducting interviews.',
                'system'
            )
            
            flash('Registration successful! Please login and complete your expert application.', 'success')
            return redirect(url_for('auth.login'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Registration failed: {str(e)}', 'error')
    
    return render_template('auth/register_interviewer.html')

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user_type = request.form['user_type']
        first_name = request.form['first_name']
        last_name = request.form['last_name']
        phone = request.form.get('phone', '')
        
        # Validate profile picture for candidates
        if user_type == 'candidate':
            profile_picture = request.files.get('profile_picture')
            if not profile_picture or not profile_picture.filename:
                flash('Profile picture is required for candidates.', 'error')
                return render_template('auth/register.html')
            
            allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
            file_ext = profile_picture.filename.rsplit('.', 1)[1].lower() if '.' in profile_picture.filename else ''
            if file_ext not in allowed_extensions:
                flash('Invalid image format. Please upload PNG, JPG, JPEG, GIF, or WEBP.', 'error')
                return render_template('auth/register.html')
        
        password_hash = generate_password_hash(password)
        
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            flash('Email already registered. Please use a different email.', 'error')
            return render_template('auth/register.html')
        
        try:
            new_user = User(
                email=email,
                password_hash=password_hash,
                user_type=user_type,
                first_name=first_name,
                last_name=last_name,
                phone=phone
            )
            db.session.add(new_user)
            db.session.flush()
            
            if user_type == 'candidate':
                # Save profile picture to database as binary
                profile_picture = request.files['profile_picture']
                picture_binary = profile_picture.read()
                picture_mimetype = profile_picture.mimetype
                
                # Create candidate profile with profile picture in database
                candidate_profile = CandidateProfile(
                    user_id=new_user.id,
                    profile_picture=picture_binary,
                    profile_picture_mimetype=picture_mimetype
                )
                db.session.add(candidate_profile)
            elif user_type == 'employer':
                company_name = request.form.get('company_name', '')
                company = Company(user_id=new_user.id, company_name=company_name)
                db.session.add(company)
            
            db.session.commit()
            
            # Log activity
            log_activity('users', 'INSERT', new_user.id, 
                        new_values={'email': email, 'user_type': user_type})
            
            # Create welcome notification
            create_notification(new_user.id, 'Welcome!', 
                              f'Welcome to our job matching platform, {first_name}!')
            
            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('auth.login'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Registration failed: {str(e)}', 'error')
    
    return render_template('auth/register.html')

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        user = User.query.filter_by(email=email, is_active=True).first()
        
        if user and check_password_hash(user.password_hash, password):
            # Update last login
            user.last_login = datetime.utcnow()
            db.session.commit()
            
            session['user_id'] = user.id
            session['user_type'] = user.user_type
            session['user_name'] = f"{user.first_name} {user.last_name}"
            
            # Log activity
            log_activity('users', 'UPDATE', user.id,
                        old_values={'last_login': None},
                        new_values={'last_login': user.last_login.isoformat()},
                        user_id=user.id)
            
            # Updated redirect logic for all user types
            if user.user_type == 'candidate':
                return redirect(url_for('candidate.candidate_dashboard'))
            elif user.user_type == 'admin':
                return redirect(url_for('admin.admin_dashboard'))
            elif user.user_type == 'interviewer':
                return redirect(url_for('interviewer.interviewer_dashboard'))
            elif user.user_type == 'manager':
                return redirect(url_for('manager.manager_dashboard'))
            else:  # employer
                return redirect(url_for('employer.employer_dashboard'))
        else:
            flash('Invalid email or password', 'error')
    
    return render_template('auth/login.html')


@auth_bp.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out successfully', 'info')
    return redirect(url_for('main.index'))
