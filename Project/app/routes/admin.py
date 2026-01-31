from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify, send_file
from extensions import db
from models import (
    User, Notification, ActivityLog, JobPosting, JobApplication,
    Company, Skill, CandidateSkill, JobRequiredSkill, CandidateProfile,
    InterviewRoom, InterviewParticipant, InterviewFeedback, InterviewerRecommendation,
    InterviewerApplication, InterviewerProfile, InterviewerSkill, InterviewerIndustry,
    InterviewerCertification, InterviewerJobRole
)
from datetime import datetime, timedelta
from io import BytesIO
from sqlalchemy import func, text, and_, or_
from werkzeug.security import generate_password_hash
import csv
import json

bp = Blueprint('admin', __name__, url_prefix='/admin')

# --- ADMIN DASHBOARD ---
@bp.route('/dashboard')
def admin_dashboard():
    if 'user_id' not in session or session['user_type'] != 'admin':
        return redirect(url_for('auth.login'))
    
    # System statistics
    stats = {
        'total_users': User.query.count(),
        'total_candidates': User.query.filter_by(user_type='candidate').count(),
        'candidates': User.query.filter_by(user_type='candidate').count(),
        'total_employers': User.query.filter_by(user_type='employer').count(),
        'employers': User.query.filter_by(user_type='employer').count(),
        'total_interviewers': User.query.filter_by(user_type='interviewer').count(),
        'interviewers': User.query.filter_by(user_type='interviewer').count(),
        'pending_interviewer_apps': InterviewerApplication.query.filter_by(status='pending').count(),
        'total_jobs': JobPosting.query.count(),
        'active_jobs': JobPosting.query.filter_by(is_active=True).count(),
        'total_applications': JobApplication.query.count(),
        'total_skills': Skill.query.count(),
        'total_companies': Company.query.count(),
        'new_users_today': User.query.filter(func.date(User.created_at) == func.date(datetime.now())).count(),
        'new_applications_today': JobApplication.query.filter(func.date(JobApplication.applied_at) == func.date(datetime.now())).count()
    }
    
    # Recent activity
    recent_activities = ActivityLog.query.order_by(
        ActivityLog.timestamp.desc()
    ).limit(20).all()
    
    # User registration trends (last 30 days)
    thirty_days_ago = datetime.now() - timedelta(days=30)
    daily_registrations = db.session.query(
        func.date(User.created_at).label('date'),
        func.count(User.id).label('count')
    ).filter(
        User.created_at >= thirty_days_ago
    ).group_by(func.date(User.created_at)).all()
    
    return render_template('admin/admin_dashboard.html',
                         stats=stats,
                         recent_activities=recent_activities,
                         daily_registrations=daily_registrations)

# --- ADMIN USERS ---
@bp.route('/users')
def admin_users():
    if 'user_id' not in session or session['user_type'] != 'admin':
        return redirect(url_for('auth.login'))
    
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    user_type = request.args.get('user_type', '')
    
    query = User.query
    
    if search:
        query = query.filter(
            or_(
                User.first_name.contains(search),
                User.last_name.contains(search),
                User.email.contains(search)
            )
        )
    
    if user_type:
        query = query.filter(User.user_type == user_type)
    
    users = query.order_by(User.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False
    )
    
    return render_template('admin/admin_users.html',
                         users=users,
                         search=search,
                         user_type=user_type)

# --- ADMIN SKILLS ---
@bp.route('/skills', methods=['GET', 'POST'])
def admin_skills():
    if 'user_id' not in session or session['user_type'] != 'admin':
        return redirect(url_for('auth.login'))
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'add_skill':
            skill_name = request.form['skill_name']
            category = request.form['category']
            description = request.form.get('description', '')
            
            existing_skill = Skill.query.filter_by(skill_name=skill_name).first()
            if existing_skill:
                flash('Skill already exists', 'error')
            else:
                new_skill = Skill(
                    skill_name=skill_name,
                    category=category,
                    description=description
                )
                db.session.add(new_skill)
                db.session.commit()
                
                log_activity('skills', 'INSERT', new_skill.id,
                           new_values={'skill_name': skill_name, 'category': category},
                           user_id=session['user_id'])
                
                flash('Skill added successfully', 'success')
        
        elif action == 'bulk_import':
            # Handle CSV upload for bulk skill import
            if 'csv_file' in request.files:
                file = request.files['csv_file']
                if file and file.filename.endswith('.csv'):
                    try:
                        # Process CSV file
                        csv_data = file.read().decode('utf-8')
                        csv_reader = csv.DictReader(csv_data.splitlines())
                        
                        added_count = 0
                        for row in csv_reader:
                            if 'skill_name' in row and row['skill_name']:
                                existing = Skill.query.filter_by(
                                    skill_name=row['skill_name']
                                ).first()
                                
                                if not existing:
                                    new_skill = Skill(
                                        skill_name=row['skill_name'],
                                        category=row.get('category', 'General'),
                                        description=row.get('description', '')
                                    )
                                    db.session.add(new_skill)
                                    added_count += 1
                        
                        db.session.commit()
                        flash(f'Successfully imported {added_count} skills', 'success')
                        
                    except Exception as e:
                        db.session.rollback()
                        flash(f'Error importing skills: {str(e)}', 'error')
    
    # Get skills with pagination
    page = request.args.get('page', 1, type=int)
    category_filter = request.args.get('category', '')
    
    query = Skill.query
    if category_filter:
        query = query.filter(Skill.category == category_filter)
    
    skills = query.order_by(Skill.category, Skill.skill_name).paginate(
        page=page, per_page=50, error_out=False
    )
    
    # Get unique categories
    categories = db.session.query(Skill.category).distinct().all()
    categories = [cat[0] for cat in categories if cat[0]]
    
    return render_template('admin/admin_skills.html',
                         skills=skills,
                         categories=categories,
                         category_filter=category_filter)

# --- ADMIN ACTIVITY LOGS ---
@bp.route('/activity_logs')
def admin_activity_logs():
    if 'user_id' not in session or session['user_type'] != 'admin':
        return redirect(url_for('auth.login'))
    
    from datetime import datetime
    
    page = request.args.get('page', 1, type=int)
    table_filter = request.args.get('table', '')
    operation_filter = request.args.get('operation', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    
    query = ActivityLog.query
    
    if table_filter:
        query = query.filter(ActivityLog.table_name == table_filter)
    
    if operation_filter:
        query = query.filter(ActivityLog.operation_type == operation_filter)
    
    if date_from:
        try:
            from_date = datetime.strptime(date_from, '%Y-%m-%d')
            query = query.filter(ActivityLog.timestamp >= from_date)
        except ValueError:
            pass
    
    if date_to:
        try:
            to_date = datetime.strptime(date_to, '%Y-%m-%d')
            # Add 1 day to include the entire end date
            to_date = to_date.replace(hour=23, minute=59, second=59)
            query = query.filter(ActivityLog.timestamp <= to_date)
        except ValueError:
            pass
    
    logs = query.order_by(ActivityLog.timestamp.desc()).paginate(
        page=page, per_page=50, error_out=False
    )
    
    # Get unique table names and operations
    tables = db.session.query(ActivityLog.table_name).distinct().all()
    tables = [table[0] for table in tables if table[0]]
    
    operations = ['INSERT', 'UPDATE', 'DELETE', 'DOWNLOAD_CV']
    
    return render_template('admin/admin_activity_logs.html',
                         logs=logs,
                         tables=tables,
                         operations=operations,
                         table_filter=table_filter,
                         operation_filter=operation_filter,
                         date_from=date_from,
                         date_to=date_to)

# --- ADMIN REPORTS ---
@bp.route('/reports')
def admin_reports():
    if 'user_id' not in session or session['user_type'] != 'admin':
        return redirect(url_for('auth.login'))
    
    # Generate various reports
    reports = {
        'user_growth': get_user_growth_report(),
        'job_statistics': get_job_statistics_report(),
        'application_trends': get_application_trends_report(),
        'skill_demand': get_skill_demand_report()
    }
    
    return render_template('admin/admin_reports.html', reports=reports)

# --- REPORT GENERATION FUNCTIONS ---

def get_user_growth_report():
    """Generate user growth report"""
    thirty_days_ago = datetime.now() - timedelta(days=30)
    
    growth_data = db.session.query(
        func.date(User.created_at).label('date'),
        User.user_type,
        func.count(User.id).label('count')
    ).filter(
        User.created_at >= thirty_days_ago
    ).group_by(
        func.date(User.created_at), User.user_type
    ).order_by(func.date(User.created_at)).all()
    
    return growth_data

def get_job_statistics_report():
    """Generate job statistics report"""
    stats = {
        'by_type': db.session.query(
            JobPosting.job_type,
            func.count(JobPosting.id)
        ).group_by(JobPosting.job_type).all(),
        
        'by_location': db.session.query(
            JobPosting.location,
            func.count(JobPosting.id)
        ).group_by(JobPosting.location).order_by(
            func.count(JobPosting.id).desc()
        ).limit(10).all(),
        
        'by_company': db.session.query(
            Company.company_name,
            func.count(JobPosting.id)
        ).join(JobPosting).group_by(Company.id).order_by(
            func.count(JobPosting.id).desc()
        ).limit(10).all()
    }
    
    return stats

def get_application_trends_report():
    """Generate application trends report"""
    thirty_days_ago = datetime.now() - timedelta(days=30)
    
    trends = {
        'daily_applications': db.session.query(
            func.date(JobApplication.applied_at).label('date'),
            func.count(JobApplication.id).label('count')
        ).filter(
            JobApplication.applied_at >= thirty_days_ago
        ).group_by(func.date(JobApplication.applied_at)).all(),
        
        'status_distribution': db.session.query(
            JobApplication.application_status,
            func.count(JobApplication.id)
        ).group_by(JobApplication.application_status).all()
    }
    
    return trends

def get_skill_demand_report():
    """Generate skill demand report"""
    skill_demand = db.session.query(
        Skill.skill_name,
        Skill.category,
        func.count(JobRequiredSkill.id).label('demand_count')
    ).join(JobRequiredSkill).group_by(Skill.id).order_by(
        func.count(JobRequiredSkill.id).desc()
    ).limit(20).all()
    
    return skill_demand

# --- EXPORT ROUTES ---

@bp.route('/export/<data_type>')
def admin_export_data(data_type):
    if 'user_id' not in session or session['user_type'] != 'admin':
        return redirect(url_for('auth.login'))
    
    try:
        if data_type == 'users':
            return export_users_csv()
        elif data_type == 'jobs':
            return export_jobs_csv()
        elif data_type == 'applications':
            return export_applications_csv()
        elif data_type == 'skills':
            return export_skills_csv()
        else:
            flash('Invalid export type', 'error')
            return redirect(url_for('admin.admin_reports'))
    
    except Exception as e:
        flash(f'Export failed: {str(e)}', 'error')
        return redirect(url_for('admin.admin_reports'))

# --- EXPORT FUNCTIONS ---

def export_users_csv():
    """Export users data to CSV"""
    users = db.session.query(User, CandidateProfile, Company).outerjoin(
        CandidateProfile, User.id == CandidateProfile.user_id
    ).outerjoin(
        Company, User.id == Company.user_id
    ).all()
    
    output = BytesIO()
    output.write('ID,Email,User Type,First Name,Last Name,Phone,Created At,Last Login,Is Active,Experience Years,Education Level,Company Name,Industry\n'.encode())
    
    for user, candidate, company in users:
        row = [
            str(user.id),
            user.email,
            user.user_type,
            user.first_name,
            user.last_name,
            user.phone or '',
            user.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            user.last_login.strftime('%Y-%m-%d %H:%M:%S') if user.last_login else '',
            str(user.is_active),
            str(candidate.experience_years) if candidate else '',
            candidate.education_level or '' if candidate else '',
            company.company_name or '' if company else '',
            company.industry or '' if company else ''
        ]
        output.write(','.join([f'"{field}"' for field in row]).encode() + b'\n')
    
    output.seek(0)
    
    return send_file(
        output,
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'users_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
    )

def export_jobs_csv():
    """Export jobs data to CSV"""
    jobs = db.session.query(JobPosting, Company).join(Company).all()
    
    output = BytesIO()
    output.write('Job ID,Title,Company,Location,Job Type,Experience Required,Salary Min,Salary Max,Created At,Is Active,Applications Count\n'.encode())
    
    for job, company in jobs:
        app_count = JobApplication.query.filter_by(job_id=job.id).count()
        
        row = [
            str(job.id),
            job.title,
            company.company_name,
            job.location or '',
            job.job_type or '',
            str(job.experience_required),
            str(job.salary_min) if job.salary_min else '',
            str(job.salary_max) if job.salary_max else '',
            job.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            str(job.is_active),
            str(app_count)
        ]
        output.write(','.join([f'"{field}"' for field in row]).encode() + b'\n')
    
    output.seek(0)
    
    return send_file(
        output,
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'jobs_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
    )

def export_applications_csv():
    """Export applications data to CSV"""
    applications = db.session.query(
        JobApplication, JobPosting, Company, CandidateProfile, User
    ).join(
        JobPosting, JobApplication.job_id == JobPosting.id
    ).join(
        Company, JobPosting.company_id == Company.id
    ).join(
        CandidateProfile, JobApplication.candidate_id == CandidateProfile.id
    ).join(
        User, CandidateProfile.user_id == User.id
    ).all()
    
    output = BytesIO()
    output.write('Application ID,Job Title,Company,Candidate Name,Candidate Email,Status,Applied At,Exam Score\n'.encode())
    
    for app, job, company, candidate, user in applications:
        row = [
            str(app.id),
            job.title,
            company.company_name,
            f"{user.first_name} {user.last_name}",
            user.email,
            app.application_status,
            app.applied_at.strftime('%Y-%m-%d %H:%M:%S'),
            str(app.exam_score) if app.exam_score else ''
        ]
        output.write(','.join([f'"{field}"' for field in row]).encode() + b'\n')
    
    output.seek(0)
    
    return send_file(
        output,
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'applications_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
    )

def export_skills_csv():
    """Export skills data to CSV"""
    skills = Skill.query.order_by(Skill.category, Skill.skill_name).all()
    
    output = BytesIO()
    output.write('Skill ID,Skill Name,Category,Description,Usage Count\n'.encode())
    
    for skill in skills:
        usage_count = CandidateSkill.query.filter_by(skill_id=skill.id).count()
        usage_count += JobRequiredSkill.query.filter_by(skill_id=skill.id).count()
        
        row = [
            str(skill.id),
            skill.skill_name,
            skill.category or '',
            skill.description or '',
            str(usage_count)
        ]
        output.write(','.join([f'"{field}"' for field in row]).encode() + b'\n')
    
    output.seek(0)
    
    return send_file(
        output,
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'skills_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
    )


# =====================================================
# INTERVIEWER APPLICATION MANAGEMENT
# =====================================================

@bp.route('/interviewer-applications')
def interviewer_applications():
    """List all interviewer applications"""
    if 'user_id' not in session or session['user_type'] != 'admin':
        return redirect(url_for('auth.login'))
    
    page = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', '')
    
    query = InterviewerApplication.query
    
    if status_filter:
        query = query.filter(InterviewerApplication.status == status_filter)
    
    applications = query.order_by(
        InterviewerApplication.created_at.desc()
    ).paginate(page=page, per_page=20, error_out=False)
    
    # Get counts for each status
    status_counts = {
        'pending': InterviewerApplication.query.filter_by(status='pending').count(),
        'under_review': InterviewerApplication.query.filter_by(status='under_review').count(),
        'approved': InterviewerApplication.query.filter_by(status='approved').count(),
        'rejected': InterviewerApplication.query.filter_by(status='rejected').count()
    }
    
    return render_template('admin/interviewer_applications.html',
                         applications=applications,
                         status_filter=status_filter,
                         status_counts=status_counts)


@bp.route('/interviewer-applications/<int:app_id>')
def view_interviewer_application(app_id):
    """View detailed interviewer application"""
    if 'user_id' not in session or session['user_type'] != 'admin':
        return redirect(url_for('auth.login'))
    
    application = InterviewerApplication.query.get_or_404(app_id)
    
    # Parse JSON fields
    skills_data = json.loads(application.skills_json) if application.skills_json else []
    industries_data = json.loads(application.industries_json) if application.industries_json else []
    certifications_data = json.loads(application.certifications_json) if application.certifications_json else []
    
    return render_template('admin/view_interviewer_application.html',
                         application=application,
                         skills_data=skills_data,
                         industries_data=industries_data,
                         certifications_data=certifications_data)


@bp.route('/interviewer-applications/<int:app_id>/download-cv')
def download_application_cv(app_id):
    """Download CV from application"""
    if 'user_id' not in session or session['user_type'] != 'admin':
        return redirect(url_for('auth.login'))
    
    application = InterviewerApplication.query.get_or_404(app_id)
    
    if not application.cv_content:
        flash('CV not found.', 'error')
        return redirect(url_for('admin.view_interviewer_application', app_id=app_id))
    
    from flask import Response
    response = Response(
        application.cv_content,
        mimetype=application.cv_mimetype or 'application/octet-stream',
        headers={
            'Content-Disposition': f'attachment; filename="{application.cv_filename}"',
            'Content-Length': len(application.cv_content)
        }
    )
    return response


@bp.route('/interviewer-applications/<int:app_id>/download-exp-proof')
def download_application_exp_proof(app_id):
    """Download experience proof from application"""
    if 'user_id' not in session or session['user_type'] != 'admin':
        return redirect(url_for('auth.login'))
    
    application = InterviewerApplication.query.get_or_404(app_id)
    
    if not application.experience_proof_content:
        flash('Experience proof document not found.', 'error')
        return redirect(url_for('admin.view_interviewer_application', app_id=app_id))
    
    from flask import Response
    response = Response(
        application.experience_proof_content,
        mimetype=application.experience_proof_mimetype or 'application/octet-stream',
        headers={
            'Content-Disposition': f'attachment; filename="{application.experience_proof_filename}"',
            'Content-Length': len(application.experience_proof_content)
        }
    )
    return response


@bp.route('/interviewer-applications/<int:app_id>/review', methods=['POST'])
def review_interviewer_application(app_id):
    """Mark application as under review"""
    if 'user_id' not in session or session['user_type'] != 'admin':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    application = InterviewerApplication.query.get_or_404(app_id)
    application.status = 'under_review'
    application.reviewed_by = session['user_id']
    db.session.commit()
    
    flash('Application marked as under review.', 'info')
    return redirect(url_for('admin.view_interviewer_application', app_id=app_id))


@bp.route('/interviewer-applications/<int:app_id>/approve', methods=['POST'])
def approve_interviewer_application(app_id):
    """Approve interviewer application - updates existing profile or creates new user"""
    if 'user_id' not in session or session['user_type'] != 'admin':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    application = InterviewerApplication.query.get_or_404(app_id)
    
    if application.status == 'approved':
        flash('This application has already been approved.', 'warning')
        return redirect(url_for('admin.view_interviewer_application', app_id=app_id))
    
    try:
        # Check if user already exists with this email (new flow - registered interviewer)
        existing_user = User.query.filter_by(email=application.email).first()
        
        if existing_user:
            # User exists - update their existing profile
            user = existing_user
            profile = InterviewerProfile.query.filter_by(user_id=user.id).first()
            
            if profile:
                # Update existing profile
                profile.headline = application.headline
                profile.bio = application.bio
                profile.experience_years = application.experience_years
                profile.linkedin_url = application.linkedin_url
                profile.hourly_rate = application.hourly_rate
                profile.currency = application.currency
                profile.approval_status = 'approved'
                profile.is_active = True
                profile.is_available = True
                profile.approved_at = datetime.utcnow()
                profile.cv_content = application.cv_content
                profile.cv_filename = application.cv_filename
                profile.cv_mimetype = application.cv_mimetype
                profile.experience_proof_content = application.experience_proof_content
                profile.experience_proof_filename = application.experience_proof_filename
                profile.experience_proof_mimetype = application.experience_proof_mimetype
            else:
                # Create new profile for existing user
                profile = InterviewerProfile(
                    user_id=user.id,
                    headline=application.headline,
                    bio=application.bio,
                    experience_years=application.experience_years,
                    linkedin_url=application.linkedin_url,
                    hourly_rate=application.hourly_rate,
                    currency=application.currency,
                    interviewer_type='independent',
                    approval_status='approved',
                    is_verified=False,
                    is_active=True,
                    is_available=True,
                    approved_at=datetime.utcnow(),
                    cv_content=application.cv_content,
                    cv_filename=application.cv_filename,
                    cv_mimetype=application.cv_mimetype,
                    experience_proof_content=application.experience_proof_content,
                    experience_proof_filename=application.experience_proof_filename,
                    experience_proof_mimetype=application.experience_proof_mimetype
                )
                db.session.add(profile)
            
            db.session.flush()
            
            # Notification for existing user
            create_notification(
                user.id,
                'Your Expert Application is Approved!',
                'Congratulations! Your expert interviewer application has been approved. You can now conduct interviews and earn money!',
                'system'
            )
            
            flash(f'Application approved! {user.first_name} {user.last_name} is now an active interviewer.', 'success')
        else:
            # Old flow - Create new user account (for applications from landing page)
            import secrets
            temp_password = secrets.token_urlsafe(12)
            
            user = User(
                email=application.email,
                password_hash=generate_password_hash(temp_password),
                user_type='interviewer',
                first_name=application.first_name,
                last_name=application.last_name,
                phone=application.phone,
                is_active=True
            )
            db.session.add(user)
            db.session.flush()
            
            # Create interviewer profile
            profile = InterviewerProfile(
                user_id=user.id,
                headline=application.headline,
                bio=application.bio,
                experience_years=application.experience_years,
                linkedin_url=application.linkedin_url,
                hourly_rate=application.hourly_rate,
                currency=application.currency,
                interviewer_type='independent',
                approval_status='approved',
                is_verified=False,
                is_active=True,
                is_available=True,
                approved_at=datetime.utcnow(),
                cv_content=application.cv_content,
                cv_filename=application.cv_filename,
                cv_mimetype=application.cv_mimetype,
                experience_proof_content=application.experience_proof_content,
                experience_proof_filename=application.experience_proof_filename,
                experience_proof_mimetype=application.experience_proof_mimetype
            )
            db.session.add(profile)
            db.session.flush()
            
            # Notification with temp password
            create_notification(
                user.id,
                'Welcome to HireMe as Expert Interviewer!',
                f'Congratulations! Your application has been approved. Your temporary password is: {temp_password}. Please change it after your first login.',
                'system'
            )
            
            flash(f'Application approved! User account created with temporary password: {temp_password}', 'success')
        
        # Add skills from application
        skills_data = json.loads(application.skills_json) if application.skills_json else []
        # Clear existing skills first (for updates)
        InterviewerSkill.query.filter_by(interviewer_id=profile.id).delete()
        for skill_info in skills_data:
            interviewer_skill = InterviewerSkill(
                interviewer_id=profile.id,
                skill_id=skill_info.get('id'),
                proficiency_level=skill_info.get('proficiency', 'Expert')
            )
            db.session.add(interviewer_skill)
        
        # Add industries from application
        industries_data = json.loads(application.industries_json) if application.industries_json else []
        # Clear existing industries first (for updates)
        InterviewerIndustry.query.filter_by(interviewer_id=profile.id).delete()
        for industry_name in industries_data:
            interviewer_industry = InterviewerIndustry(
                interviewer_id=profile.id,
                industry_name=industry_name
            )
            db.session.add(interviewer_industry)
        
        # Add certifications from application
        certifications_data = json.loads(application.certifications_json) if application.certifications_json else []
        # Clear existing certifications first (for updates)
        InterviewerCertification.query.filter_by(interviewer_id=profile.id).delete()
        for cert_info in certifications_data:
            certification = InterviewerCertification(
                interviewer_id=profile.id,
                certification_name=cert_info.get('name', ''),
                issuing_organization=cert_info.get('organization', ''),
                credential_url=cert_info.get('url', '')
            )
            db.session.add(certification)
        
        # Update application status
        application.status = 'approved'
        application.reviewed_by = session['user_id']
        application.reviewed_at = datetime.utcnow()
        application.created_user_id = user.id
        
        db.session.commit()
        
        # Log activity
        log_activity('interviewer_applications', 'UPDATE', application.id,
                    old_values={'status': 'pending'},
                    new_values={'status': 'approved', 'created_user_id': user.id},
                    user_id=session['user_id'])
        
        return redirect(url_for('admin.interviewer_applications'))
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error approving application: {str(e)}', 'error')
        return redirect(url_for('admin.view_interviewer_application', app_id=app_id))


@bp.route('/interviewer-applications/<int:app_id>/reject', methods=['POST'])
def reject_interviewer_application(app_id):
    """Reject interviewer application"""
    if 'user_id' not in session or session['user_type'] != 'admin':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    application = InterviewerApplication.query.get_or_404(app_id)
    rejection_reason = request.form.get('rejection_reason', '')
    
    application.status = 'rejected'
    application.rejection_reason = rejection_reason
    application.reviewed_by = session['user_id']
    application.reviewed_at = datetime.utcnow()
    
    db.session.commit()
    
    # Log activity
    log_activity('interviewer_applications', 'UPDATE', application.id,
                old_values={'status': application.status},
                new_values={'status': 'rejected', 'rejection_reason': rejection_reason},
                user_id=session['user_id'])
    
    flash('Application has been rejected.', 'info')
    return redirect(url_for('admin.interviewer_applications'))


@bp.route('/interviewers')
def manage_interviewers():
    """Manage all interviewer profiles"""
    if 'user_id' not in session or session['user_type'] != 'admin':
        return redirect(url_for('auth.login'))
    
    page = request.args.get('page', 1, type=int)
    type_filter = request.args.get('type', '')
    status_filter = request.args.get('status', '')
    search = request.args.get('search', '')
    
    query = db.session.query(InterviewerProfile, User).join(
        User, InterviewerProfile.user_id == User.id
    )
    
    if type_filter:
        query = query.filter(InterviewerProfile.interviewer_type == type_filter)
    
    if status_filter:
        query = query.filter(InterviewerProfile.approval_status == status_filter)
    
    if search:
        query = query.filter(
            or_(
                User.first_name.contains(search),
                User.last_name.contains(search),
                User.email.contains(search)
            )
        )
    
    interviewers = query.order_by(InterviewerProfile.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False
    )
    
    return render_template('admin/manage_interviewers.html',
                         interviewers=interviewers,
                         type_filter=type_filter,
                         status_filter=status_filter,
                         search=search)


@bp.route('/interviewers/<int:profile_id>/verify', methods=['POST'])
def verify_interviewer(profile_id):
    """Toggle verification badge for interviewer"""
    if 'user_id' not in session or session['user_type'] != 'admin':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    profile = InterviewerProfile.query.get_or_404(profile_id)
    profile.is_verified = not profile.is_verified
    db.session.commit()
    
    status = 'verified' if profile.is_verified else 'unverified'
    flash(f'Interviewer has been {status}.', 'success')
    return redirect(url_for('admin.manage_interviewers'))


@bp.route('/interviewers/<int:profile_id>/toggle-active', methods=['POST'])
def toggle_interviewer_active(profile_id):
    """Toggle active status for interviewer"""
    if 'user_id' not in session or session['user_type'] != 'admin':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    profile = InterviewerProfile.query.get_or_404(profile_id)
    profile.is_active = not profile.is_active
    db.session.commit()
    
    status = 'activated' if profile.is_active else 'deactivated'
    flash(f'Interviewer has been {status}.', 'success')
    return redirect(url_for('admin.manage_interviewers'))


# --- ADMIN HELPER FUNCTIONS ---

def log_activity(table_name, operation_type, record_id, old_values=None, new_values=None, user_id=None):
    """Log activity for audit trail"""
    activity = ActivityLog(
        table_name=table_name,
        operation_type=operation_type,
        record_id=record_id,
        old_values=json.dumps(old_values) if old_values else None,
        new_values=json.dumps(new_values) if new_values else None,
        user_id=user_id
    )
    db.session.add(activity)
    db.session.commit()

def create_notification(user_id, title, message, notification_type='system', action_url=None):
    """Create a new notification for a user"""
    notification = Notification(
        user_id=user_id,
        title=title,
        message=message,
        notification_type=notification_type,
        action_url=action_url
    )
    db.session.add(notification)
    db.session.commit()
