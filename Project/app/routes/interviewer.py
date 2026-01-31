from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify, send_file
from extensions import db
from models import (
    User, InterviewRoom, InterviewParticipant, Skill,
    InterviewerProfile, InterviewerSkill, InterviewerIndustry, InterviewerCertification,
    InterviewerAvailability, InterviewerEarning, InterviewerReview, InterviewerJobRole,
    InterviewerApplication, JobApplication, JobPosting, Company, CandidateProfile, CandidateSkill,
    JobRequiredSkill, ExamAttempt
)
from datetime import datetime, time
import io

bp = Blueprint('interviewer', __name__, url_prefix='/interviewer')


# =====================================================
# INTERVIEWER DASHBOARD
# =====================================================
@bp.route('/dashboard')
def interviewer_dashboard():
    if 'user_id' not in session or session['user_type'] != 'interviewer':
        return redirect(url_for('auth.login'))
    
    user = User.query.get(session['user_id'])
    profile = InterviewerProfile.query.filter_by(user_id=user.id).first()
    
    # Check if profile exists and application status
    if not profile:
        # No profile - redirect to apply
        flash('Please complete your expert application to get started.', 'info')
        return redirect(url_for('interviewer.apply_expert'))
    
    # Check approval status
    if profile.approval_status == 'pending':
        # Check if they have submitted an application
        application = InterviewerApplication.query.filter_by(
            email=user.email
        ).order_by(InterviewerApplication.created_at.desc()).first()
        
        if not application:
            # No application submitted yet
            flash('Please complete your expert application.', 'info')
            return redirect(url_for('interviewer.apply_expert'))
        
        # Show pending application status page
        return render_template('interviewer/application_status.html',
                             user=user,
                             profile=profile,
                             application=application)
    
    if profile.approval_status == 'rejected':
        application = InterviewerApplication.query.filter_by(
            email=user.email
        ).order_by(InterviewerApplication.created_at.desc()).first()
        return render_template('interviewer/application_status.html',
                             user=user,
                             profile=profile,
                             application=application)
    
    # Profile is approved - show normal dashboard
    # Get upcoming interviews
    from models.job import JobApplication, JobPosting
    from models.company import Company
    
    upcoming_interviews = db.session.query(InterviewRoom, JobApplication, JobPosting, Company).join(
        JobApplication, InterviewRoom.job_application_id == JobApplication.id
    ).join(
        JobPosting, JobApplication.job_id == JobPosting.id
    ).join(
        Company, JobPosting.company_id == Company.id
    ).join(
        InterviewParticipant, InterviewRoom.id == InterviewParticipant.room_id
    ).filter(
        InterviewParticipant.user_id == session['user_id'],
        InterviewRoom.status.in_(['scheduled', 'active']),
        InterviewRoom.scheduled_time >= datetime.utcnow()
    ).order_by(InterviewRoom.scheduled_time.asc()).all()
    
    # Get completed interviews
    completed_interviews = db.session.query(InterviewRoom, JobApplication, JobPosting, Company).join(
        JobApplication, InterviewRoom.job_application_id == JobApplication.id
    ).join(
        JobPosting, JobApplication.job_id == JobPosting.id
    ).join(
        Company, JobPosting.company_id == Company.id
    ).join(
        InterviewParticipant, InterviewRoom.id == InterviewParticipant.room_id
    ).filter(
        InterviewParticipant.user_id == session['user_id'],
        InterviewRoom.status == 'completed'
    ).order_by(InterviewRoom.ended_at.desc()).limit(5).all()
    
    # Get earnings stats
    total_earnings = 0
    pending_earnings = 0
    if profile:
        total_earnings = profile.total_earnings or 0
        pending_earnings_query = InterviewerEarning.query.filter_by(
            interviewer_id=profile.id, status='pending'
        ).with_entities(db.func.sum(InterviewerEarning.amount_earned)).scalar()
        pending_earnings = pending_earnings_query or 0
    
    return render_template('interviewer/interviewer_dashboard.html',
                         user=user,
                         profile=profile,
                         upcoming_interviews=upcoming_interviews,
                         completed_interviews=completed_interviews,
                         total_earnings=total_earnings,
                         pending_earnings=pending_earnings)


# =====================================================
# EXPERT APPLICATION (for logged-in interviewers)
# =====================================================
@bp.route('/apply', methods=['GET', 'POST'])
def apply_expert():
    """Expert application form for logged-in interviewers"""
    if 'user_id' not in session or session['user_type'] != 'interviewer':
        return redirect(url_for('auth.login'))
    
    user = User.query.get(session['user_id'])
    profile = InterviewerProfile.query.filter_by(user_id=user.id).first()
    
    # Check if already approved
    if profile and profile.approval_status == 'approved':
        flash('Your application has already been approved!', 'info')
        return redirect(url_for('interviewer.interviewer_dashboard'))
    
    # Check for existing pending application
    existing_application = InterviewerApplication.query.filter_by(
        email=user.email, status='pending'
    ).first()
    
    if existing_application:
        flash('You already have a pending application. Please wait for admin review.', 'info')
        return redirect(url_for('interviewer.interviewer_dashboard'))
    
    skills = Skill.query.order_by(Skill.skill_name).all()
    industries = [
        'Technology', 'Finance & Banking', 'Healthcare', 'E-commerce',
        'Education', 'Manufacturing', 'Telecommunications', 'Media & Entertainment',
        'Real Estate', 'Consulting', 'Automotive', 'Energy', 'Retail',
        'Logistics & Supply Chain', 'Insurance', 'Government', 'Non-Profit'
    ]
    
    if request.method == 'POST':
        try:
            import json
            from services import create_notification
            
            # Parse experience years safely
            exp_years_str = request.form.get('experience_years', '0')
            try:
                experience_years = int(exp_years_str) if exp_years_str else 0
            except (ValueError, TypeError):
                experience_years = 0
            
            # Parse hourly rate safely
            hourly_rate_str = request.form.get('hourly_rate', '0')
            try:
                hourly_rate = float(hourly_rate_str) if hourly_rate_str else 0.0
            except (ValueError, TypeError):
                hourly_rate = 0.0
            
            # Process skills
            selected_skills = request.form.getlist('skills')
            skills_data = []
            for skill_id in selected_skills:
                try:
                    skill = Skill.query.get(int(skill_id))
                    if skill:
                        proficiency = request.form.get(f'skill_proficiency_{skill_id}', 'Expert')
                        skills_data.append({
                            'id': skill.id,
                            'name': skill.skill_name,
                            'proficiency': proficiency
                        })
                except (ValueError, TypeError):
                    continue
            
            # Process industries
            selected_industries = request.form.getlist('industries')
            
            # Process certifications
            cert_names = request.form.getlist('cert_name[]')
            cert_orgs = request.form.getlist('cert_org[]')
            cert_urls = request.form.getlist('cert_url[]')
            certifications_data = []
            for i, name in enumerate(cert_names):
                if name and name.strip():
                    certifications_data.append({
                        'name': name.strip(),
                        'organization': cert_orgs[i].strip() if i < len(cert_orgs) else '',
                        'url': cert_urls[i].strip() if i < len(cert_urls) else ''
                    })
            
            # Handle file uploads
            cv_file = request.files.get('cv')
            cv_content = None
            cv_filename = None
            cv_mimetype = None
            if cv_file and cv_file.filename:
                cv_content = cv_file.read()
                cv_filename = cv_file.filename
                cv_mimetype = cv_file.mimetype
            
            exp_proof_file = request.files.get('experience_proof')
            exp_content = None
            exp_filename = None
            exp_mimetype = None
            if exp_proof_file and exp_proof_file.filename:
                exp_content = exp_proof_file.read()
                exp_filename = exp_proof_file.filename
                exp_mimetype = exp_proof_file.mimetype
            
            # Create application (linked to logged-in user)
            application = InterviewerApplication(
                email=user.email,
                first_name=user.first_name,
                last_name=user.last_name,
                phone=user.phone,
                headline=request.form.get('headline', '').strip(),
                bio=request.form.get('bio', '').strip(),
                experience_years=experience_years,
                linkedin_url=request.form.get('linkedin_url', '').strip(),
                hourly_rate=hourly_rate,
                currency=request.form.get('currency', 'USD'),
                skills_json=json.dumps(skills_data),
                industries_json=json.dumps(selected_industries),
                certifications_json=json.dumps(certifications_data),
                cv_content=cv_content,
                cv_filename=cv_filename,
                cv_mimetype=cv_mimetype,
                experience_proof_content=exp_content,
                experience_proof_filename=exp_filename,
                experience_proof_mimetype=exp_mimetype,
                status='pending',
                created_user_id=user.id  # Link to existing user
            )
            
            db.session.add(application)
            db.session.commit()
            
            # Notify admins
            admins = User.query.filter_by(user_type='admin', is_active=True).all()
            for admin in admins:
                create_notification(
                    admin.id,
                    'New Expert Interviewer Application',
                    f'{user.first_name} {user.last_name} ({user.email}) has submitted an expert interviewer application.',
                    'application'
                )
            
            flash('Your application has been submitted successfully! We will review it shortly.', 'success')
            return redirect(url_for('interviewer.interviewer_dashboard'))
            
        except Exception as e:
            db.session.rollback()
            import traceback
            traceback.print_exc()
            flash(f'Error submitting application: {str(e)}', 'error')
    
    return render_template('interviewer/apply_expert.html',
                         user=user,
                         profile=profile,
                         skills=skills,
                         industries=industries)


# =====================================================
# INTERVIEWER PROFILE
# =====================================================
@bp.route('/profile')
def profile():
    if 'user_id' not in session or session['user_type'] != 'interviewer':
        return redirect(url_for('auth.login'))
    
    user = User.query.get(session['user_id'])
    profile = InterviewerProfile.query.filter_by(user_id=user.id).first()
    
    if not profile:
        # Create a profile if doesn't exist
        profile = InterviewerProfile(user_id=user.id)
        db.session.add(profile)
        db.session.commit()
    
    all_skills = Skill.query.order_by(Skill.skill_name).all()
    reviews = InterviewerReview.query.filter_by(interviewer_id=profile.id, is_public=True).order_by(
        InterviewerReview.created_at.desc()
    ).limit(10).all()
    
    return render_template('interviewer/interviewer_profile.html',
                         user=user,
                         profile=profile,
                         all_skills=all_skills,
                         reviews=reviews)


@bp.route('/profile/edit', methods=['GET', 'POST'])
def edit_profile():
    if 'user_id' not in session or session['user_type'] != 'interviewer':
        return redirect(url_for('auth.login'))
    
    user = User.query.get(session['user_id'])
    profile = InterviewerProfile.query.filter_by(user_id=user.id).first()
    
    if not profile:
        profile = InterviewerProfile(user_id=user.id)
        db.session.add(profile)
        db.session.commit()
    
    if request.method == 'POST':
        try:
            # Update basic info
            profile.headline = request.form.get('headline', '')
            profile.bio = request.form.get('bio', '')
            profile.experience_years = int(request.form.get('experience_years', 0))
            profile.linkedin_url = request.form.get('linkedin_url', '')
            profile.hourly_rate = float(request.form.get('hourly_rate', 0))
            profile.currency = request.form.get('currency', 'USD')
            profile.is_available = request.form.get('is_available') == 'on'
            
            # Handle CV upload
            cv_file = request.files.get('cv_file')
            if cv_file and cv_file.filename:
                profile.cv_content = cv_file.read()
                profile.cv_filename = cv_file.filename
                profile.cv_mimetype = cv_file.mimetype
            
            # Handle experience proof upload
            exp_file = request.files.get('experience_proof')
            if exp_file and exp_file.filename:
                profile.experience_proof_content = exp_file.read()
                profile.experience_proof_filename = exp_file.filename
                profile.experience_proof_mimetype = exp_file.mimetype
            
            # Update skills
            skill_ids = request.form.getlist('skills')
            # Remove old skills
            InterviewerSkill.query.filter_by(interviewer_id=profile.id).delete()
            # Add new skills
            for skill_id in skill_ids:
                interviewer_skill = InterviewerSkill(
                    interviewer_id=profile.id,
                    skill_id=int(skill_id),
                    proficiency_level='Expert'
                )
                db.session.add(interviewer_skill)
            
            # Update industries
            industries = request.form.get('industries', '').split(',')
            InterviewerIndustry.query.filter_by(interviewer_id=profile.id).delete()
            for industry in industries:
                industry = industry.strip()
                if industry:
                    interviewer_industry = InterviewerIndustry(
                        interviewer_id=profile.id,
                        industry_name=industry
                    )
                    db.session.add(interviewer_industry)
            
            # Update job roles
            job_roles = request.form.get('job_roles', '').split(',')
            InterviewerJobRole.query.filter_by(interviewer_id=profile.id).delete()
            for role in job_roles:
                role = role.strip()
                if role:
                    job_role = InterviewerJobRole(
                        interviewer_id=profile.id,
                        role_name=role
                    )
                    db.session.add(job_role)
            
            db.session.commit()
            flash('Profile updated successfully!', 'success')
            return redirect(url_for('interviewer.profile'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating profile: {str(e)}', 'error')
    
    all_skills = Skill.query.order_by(Skill.skill_name).all()
    
    return render_template('interviewer/edit_profile.html',
                         user=user,
                         profile=profile,
                         all_skills=all_skills)


# =====================================================
# AVAILABILITY MANAGEMENT
# =====================================================
@bp.route('/availability')
def availability():
    if 'user_id' not in session or session['user_type'] != 'interviewer':
        return redirect(url_for('auth.login'))
    
    user = User.query.get(session['user_id'])
    profile = InterviewerProfile.query.filter_by(user_id=user.id).first()
    
    if not profile:
        flash('Please complete your profile first.', 'warning')
        return redirect(url_for('interviewer.edit_profile'))
    
    availabilities = InterviewerAvailability.query.filter_by(
        interviewer_id=profile.id
    ).order_by(InterviewerAvailability.day_of_week, InterviewerAvailability.start_time).all()
    
    days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    
    return render_template('interviewer/availability.html',
                         user=user,
                         profile=profile,
                         availabilities=availabilities,
                         days=days)


@bp.route('/availability/add', methods=['POST'])
def add_availability():
    if 'user_id' not in session or session['user_type'] != 'interviewer':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    profile = InterviewerProfile.query.filter_by(user_id=session['user_id']).first()
    if not profile:
        return jsonify({'success': False, 'message': 'Profile not found'}), 404
    
    try:
        day_of_week = int(request.form.get('day_of_week'))
        start_time_str = request.form.get('start_time')
        end_time_str = request.form.get('end_time')
        timezone = request.form.get('timezone', 'UTC')
        
        start_time = datetime.strptime(start_time_str, '%H:%M').time()
        end_time = datetime.strptime(end_time_str, '%H:%M').time()
        
        availability = InterviewerAvailability(
            interviewer_id=profile.id,
            day_of_week=day_of_week,
            start_time=start_time,
            end_time=end_time,
            timezone=timezone
        )
        db.session.add(availability)
        db.session.commit()
        
        flash('Availability added successfully!', 'success')
        return redirect(url_for('interviewer.availability'))
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error adding availability: {str(e)}', 'error')
        return redirect(url_for('interviewer.availability'))


@bp.route('/availability/delete/<int:availability_id>', methods=['POST'])
def delete_availability(availability_id):
    if 'user_id' not in session or session['user_type'] != 'interviewer':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    profile = InterviewerProfile.query.filter_by(user_id=session['user_id']).first()
    availability = InterviewerAvailability.query.filter_by(
        id=availability_id, interviewer_id=profile.id
    ).first()
    
    if availability:
        db.session.delete(availability)
        db.session.commit()
        flash('Availability slot removed.', 'success')
    else:
        flash('Availability slot not found.', 'error')
    
    return redirect(url_for('interviewer.availability'))


# =====================================================
# EARNINGS
# =====================================================
@bp.route('/earnings')
def earnings():
    if 'user_id' not in session or session['user_type'] != 'interviewer':
        return redirect(url_for('auth.login'))
    
    user = User.query.get(session['user_id'])
    profile = InterviewerProfile.query.filter_by(user_id=user.id).first()
    
    if not profile:
        flash('Please complete your profile first.', 'warning')
        return redirect(url_for('interviewer.edit_profile'))
    
    # Get earnings with pagination
    page = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', '')
    
    earnings_query = InterviewerEarning.query.filter_by(interviewer_id=profile.id)
    
    if status_filter:
        earnings_query = earnings_query.filter_by(status=status_filter)
    
    earnings_paginated = earnings_query.order_by(
        InterviewerEarning.created_at.desc()
    ).paginate(page=page, per_page=20, error_out=False)
    
    # Calculate totals
    total_earnings = db.session.query(db.func.sum(InterviewerEarning.amount_earned)).filter(
        InterviewerEarning.interviewer_id == profile.id
    ).scalar() or 0
    
    pending_earnings = db.session.query(db.func.sum(InterviewerEarning.amount_earned)).filter(
        InterviewerEarning.interviewer_id == profile.id,
        InterviewerEarning.status == 'pending'
    ).scalar() or 0
    
    confirmed_amount = db.session.query(db.func.sum(InterviewerEarning.amount_earned)).filter(
        InterviewerEarning.interviewer_id == profile.id,
        InterviewerEarning.status == 'confirmed'
    ).scalar() or 0
    
    # Calculate monthly earnings (current month)
    from datetime import datetime
    current_month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    monthly_earnings = db.session.query(db.func.sum(InterviewerEarning.amount_earned)).filter(
        InterviewerEarning.interviewer_id == profile.id,
        InterviewerEarning.created_at >= current_month_start
    ).scalar() or 0
    
    return render_template('interviewer/earnings.html',
                         user=user,
                         profile=profile,
                         earnings=earnings_paginated,
                         total_earnings=total_earnings,
                         pending_earnings=pending_earnings,
                         monthly_earnings=monthly_earnings,
                         confirmed_amount=confirmed_amount)


# =====================================================
# CERTIFICATIONS
# =====================================================
@bp.route('/certifications')
def certifications():
    if 'user_id' not in session or session['user_type'] != 'interviewer':
        return redirect(url_for('auth.login'))
    
    user = User.query.get(session['user_id'])
    profile = InterviewerProfile.query.filter_by(user_id=user.id).first()
    
    if not profile:
        flash('Please complete your profile first.', 'warning')
        return redirect(url_for('interviewer.edit_profile'))
    
    certs = InterviewerCertification.query.filter_by(interviewer_id=profile.id).all()
    
    return render_template('interviewer/certifications.html',
                         user=user,
                         profile=profile,
                         certifications=certs)


@bp.route('/certifications/add', methods=['POST'])
def add_certification():
    if 'user_id' not in session or session['user_type'] != 'interviewer':
        return redirect(url_for('auth.login'))
    
    profile = InterviewerProfile.query.filter_by(user_id=session['user_id']).first()
    if not profile:
        flash('Profile not found.', 'error')
        return redirect(url_for('interviewer.certifications'))
    
    try:
        cert = InterviewerCertification(
            interviewer_id=profile.id,
            certification_name=request.form.get('certification_name'),
            issuing_organization=request.form.get('issuing_organization'),
            credential_id=request.form.get('credential_id'),
            credential_url=request.form.get('credential_url')
        )
        
        issue_date = request.form.get('issue_date')
        if issue_date:
            cert.issue_date = datetime.strptime(issue_date, '%Y-%m-%d').date()
        
        expiry_date = request.form.get('expiry_date')
        if expiry_date:
            cert.expiry_date = datetime.strptime(expiry_date, '%Y-%m-%d').date()
        
        # Handle certificate file upload
        cert_file = request.files.get('certificate_file')
        if cert_file and cert_file.filename:
            cert.certificate_content = cert_file.read()
            cert.certificate_filename = cert_file.filename
            cert.certificate_mimetype = cert_file.mimetype
        
        db.session.add(cert)
        db.session.commit()
        flash('Certification added successfully!', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error adding certification: {str(e)}', 'error')
    
    return redirect(url_for('interviewer.certifications'))


@bp.route('/certifications/delete/<int:cert_id>', methods=['POST'])
def delete_certification(cert_id):
    if 'user_id' not in session or session['user_type'] != 'interviewer':
        return redirect(url_for('auth.login'))
    
    profile = InterviewerProfile.query.filter_by(user_id=session['user_id']).first()
    cert = InterviewerCertification.query.filter_by(
        id=cert_id, interviewer_id=profile.id
    ).first()
    
    if cert:
        db.session.delete(cert)
        db.session.commit()
        flash('Certification removed.', 'success')
    else:
        flash('Certification not found.', 'error')
    
    return redirect(url_for('interviewer.certifications'))


# =====================================================
# REVIEWS
# =====================================================
@bp.route('/reviews')
def reviews():
    if 'user_id' not in session or session['user_type'] != 'interviewer':
        return redirect(url_for('auth.login'))
    
    user = User.query.get(session['user_id'])
    profile = InterviewerProfile.query.filter_by(user_id=user.id).first()
    
    if not profile:
        flash('Please complete your profile first.', 'warning')
        return redirect(url_for('interviewer.edit_profile'))
    
    page = request.args.get('page', 1, type=int)
    reviews_paginated = InterviewerReview.query.filter_by(
        interviewer_id=profile.id
    ).order_by(InterviewerReview.created_at.desc()).paginate(page=page, per_page=10, error_out=False)
    
    # Calculate rating stats
    rating_stats = db.session.query(
        db.func.avg(InterviewerReview.overall_rating).label('avg_rating'),
        db.func.count(InterviewerReview.id).label('total_reviews')
    ).filter(InterviewerReview.interviewer_id == profile.id).first()
    
    return render_template('interviewer/reviews.html',
                         user=user,
                         profile=profile,
                         reviews=reviews_paginated,
                         avg_rating=rating_stats.avg_rating or 0,
                         total_reviews=rating_stats.total_reviews or 0)


# =====================================================
# FILE DOWNLOADS
# =====================================================
# VIEW CANDIDATE PROFILE BEFORE INTERVIEW
# =====================================================
@bp.route('/interview/<int:room_id>/candidate')
def view_candidate_profile(room_id):
    """View candidate profile and details before interview"""
    if 'user_id' not in session or session['user_type'] != 'interviewer':
        return redirect(url_for('auth.login'))
    
    user = User.query.get(session['user_id'])
    
    # Get interview room
    room = InterviewRoom.query.get_or_404(room_id)
    
    # Verify interviewer is part of this interview
    participant = InterviewParticipant.query.filter_by(
        room_id=room.id,
        user_id=session['user_id']
    ).first()
    
    if not participant:
        flash('You are not authorized to view this candidate.', 'error')
        return redirect(url_for('interviewer.interviewer_dashboard'))
    
    # Get job application and related data
    application = JobApplication.query.get(room.job_application_id)
    job = JobPosting.query.get(application.job_id)
    company = Company.query.get(job.company_id)
    candidate = CandidateProfile.query.get(application.candidate_id)
    candidate_user = User.query.get(candidate.user_id)
    
    # Get candidate skills
    from models.skill import CandidateSkill, Skill
    candidate_skills = db.session.query(CandidateSkill, Skill).join(Skill).filter(
        CandidateSkill.candidate_id == candidate.id
    ).all()
    
    # Get job required skills
    from models.job import JobRequiredSkill
    required_skills = db.session.query(JobRequiredSkill, Skill).join(Skill).filter(
        JobRequiredSkill.job_id == job.id
    ).all()
    
    # Categorize skills
    candidate_skill_ids = {skill.id for _, skill in candidate_skills}
    required_skill_ids = {skill.id for _, skill in required_skills}
    
    # Matched skills (candidate has AND job requires)
    matched_skills = [(cs, skill) for cs, skill in candidate_skills if skill.id in required_skill_ids]
    
    # Lacked skills (job requires but candidate doesn't have)
    lacked_skills = [(rs, skill) for rs, skill in required_skills if skill.id not in candidate_skill_ids]
    
    # Extra skills (candidate has but job doesn't require)
    extra_skills = [(cs, skill) for cs, skill in candidate_skills if skill.id not in required_skill_ids]
    
    # Get exam result if exists
    from models.exam import MCQExam, ExamAttempt
    exam = MCQExam.query.filter_by(job_id=job.id).first()
    exam_attempt = None
    if exam:
        exam_attempt = ExamAttempt.query.filter_by(
            candidate_id=candidate.id,
            exam_id=exam.id,
            status='completed'
        ).order_by(ExamAttempt.completed_at.desc()).first()
    
    return render_template('interviewer/view_candidate.html',
                         room=room,
                         application=application,
                         job=job,
                         company=company,
                         candidate=candidate,
                         candidate_user=candidate_user,
                         matched_skills=matched_skills,
                         lacked_skills=lacked_skills,
                         extra_skills=extra_skills,
                         exam_attempt=exam_attempt)


# =====================================================
def download_cv(profile_id):
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    profile = InterviewerProfile.query.get_or_404(profile_id)
    
    # Allow download if it's the owner or an employer
    if session['user_id'] != profile.user_id and session['user_type'] not in ['employer', 'admin']:
        flash('Unauthorized access.', 'error')
        return redirect(url_for('main.index'))
    
    if not profile.cv_content:
        flash('CV not found.', 'error')
        return redirect(url_for('interviewer.profile'))
    
    return send_file(
        io.BytesIO(profile.cv_content),
        mimetype=profile.cv_mimetype,
        as_attachment=True,
        download_name=profile.cv_filename
    )

