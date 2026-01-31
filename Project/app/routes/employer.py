from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify, Response
from sqlalchemy import func, and_, or_
from datetime import datetime, timedelta
from io import BytesIO
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash

from extensions import db
from models import (
    User, Company, JobPosting, JobApplication, JobRequiredSkill,
    CandidateProfile, CandidateSkill, Skill, MCQExam, MCQQuestion,
    InterviewerRecommendation, ActivityLog, Notification, ApplicationStatusHistory, InterviewRoom,
    InterviewerProfile, InterviewerSkill, InterviewerIndustry, InterviewerAvailability,
    InterviewerReview, InterviewerJobRole, InterviewFeedback, InterviewParticipant
)
from services.email_service import send_interview_scheduled_email
from services import log_activity, create_notification
from services.job_matching_service import calculate_job_match_score
from utils.file_utils import allowed_file
from flask import send_file
import json

bp = Blueprint('employer', __name__, url_prefix='/employer')


@bp.route('/company/profile', methods=['GET', 'POST'])
def company_profile():
    """View and edit company profile"""
    if 'user_id' not in session or session['user_type'] != 'employer':
        return redirect(url_for('auth.login'))
    
    user = User.query.get(session['user_id'])
    company = user.company
    
    if not company:
        flash('Company not found. Please contact support.', 'error')
        return redirect(url_for('employer.employer_dashboard'))
    
    if request.method == 'POST':
        try:
            company.company_name = request.form.get('company_name', company.company_name)
            company.industry = request.form.get('industry', '')
            company.company_size = request.form.get('company_size', '')
            company.location = request.form.get('location', '')
            company.description = request.form.get('description', '')
            company.website = request.form.get('website', '')
            
            # Handle logo upload if provided
            if 'logo' in request.files:
                logo_file = request.files['logo']
                if logo_file and logo_file.filename:
                    # Check allowed image extensions
                    allowed_image_ext = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
                    ext = logo_file.filename.rsplit('.', 1)[1].lower() if '.' in logo_file.filename else ''
                    if ext in allowed_image_ext:
                        company.logo = logo_file.read()
                        company.logo_filename = secure_filename(logo_file.filename)
            
            db.session.commit()
            
            log_activity('companies', 'UPDATE', company.id,
                        new_values={'company_name': company.company_name, 'industry': company.industry})
            
            flash('Company profile updated successfully!', 'success')
            return redirect(url_for('employer.company_profile'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating profile: {str(e)}', 'error')
    
    # Industry options
    industries = [
        'Technology', 'Healthcare', 'Finance', 'Education', 'Manufacturing',
        'Retail', 'Consulting', 'Media & Entertainment', 'Telecommunications',
        'Real Estate', 'Transportation', 'Energy', 'Agriculture', 'Hospitality',
        'Legal', 'Non-Profit', 'Government', 'Automotive', 'Aerospace', 'Other'
    ]
    
    return render_template('employer/company_profile.html',
                         user=user,
                         company=company,
                         industries=industries)


@bp.route('/company/logo')
def company_logo():
    """Serve the company logo for logged-in employer"""
    if 'user_id' not in session or session['user_type'] != 'employer':
        return redirect(url_for('auth.login'))
    
    user = User.query.get(session['user_id'])
    company = user.company
    
    if company and company.logo:
        return send_file(
            BytesIO(company.logo),
            mimetype='image/png',
            download_name=company.logo_filename or 'logo.png'
        )
    
    # Return a placeholder or 404
    return '', 404


@bp.route('/company/<int:company_id>/logo')
def get_company_logo(company_id):
    """Serve company logo by company ID (public)"""
    company = Company.query.get(company_id)
    
    if company and company.logo:
        return send_file(
            BytesIO(company.logo),
            mimetype='image/png',
            download_name=company.logo_filename or 'logo.png'
        )
    
    # Return empty for no logo
    return '', 404


def get_employer_analytics(company_id):
    """Get analytics data for employer dashboard"""
    # Total applications this month
    current_month = datetime.now().replace(day=1)
    total_applications = db.session.query(JobApplication).join(JobPosting).filter(
        JobPosting.company_id == company_id,
        JobApplication.applied_at >= current_month
    ).count()
    
    # Applications by status
    status_counts = db.session.query(
        JobApplication.application_status,
        func.count(JobApplication.id)
    ).join(JobPosting).filter(
        JobPosting.company_id == company_id
    ).group_by(JobApplication.application_status).all()
    
    # Top performing jobs (by application count)
    top_jobs = db.session.query(
        JobPosting.title,
        func.count(JobApplication.id).label('app_count')
    ).outerjoin(JobApplication).filter(
        JobPosting.company_id == company_id
    ).group_by(JobPosting.id).order_by(func.count(JobApplication.id).desc()).limit(5).all()
    
    return {
        'total_applications': total_applications,
        'status_counts': dict(status_counts),
        'top_jobs': top_jobs
    }


@bp.route('/dashboard')
def employer_dashboard():
    if 'user_id' not in session or session['user_type'] != 'employer':
        return redirect(url_for('auth.login'))
    
    user = User.query.get(session['user_id'])
    company = user.company
    
    # Get job postings with application counts
    job_postings = db.session.query(
        JobPosting,
        func.count(JobApplication.id).label('application_count')
    ).outerjoin(JobApplication).filter(
        JobPosting.company_id == company.id
    ).group_by(JobPosting.id).order_by(JobPosting.created_at.desc()).all()
    
    # Get recent applications
    applications = db.session.query(JobApplication, JobPosting, CandidateProfile, User).join(
        JobPosting, JobApplication.job_id == JobPosting.id
    ).join(
        CandidateProfile, JobApplication.candidate_id == CandidateProfile.id
    ).join(
        User, CandidateProfile.user_id == User.id
    ).filter(
        JobPosting.company_id == company.id
    ).order_by(JobApplication.applied_at.desc()).limit(10).all()
    
    # Get notifications
    notifications = Notification.query.filter_by(
        user_id=session['user_id'], is_read=False
    ).order_by(Notification.created_at.desc()).limit(5).all()
    
    # Get analytics data
    analytics = get_employer_analytics(company.id)
    
    # Calculate additional dashboard metrics
    active_jobs_count = db.session.query(JobPosting).filter(
        JobPosting.company_id == company.id,
        JobPosting.is_active == True
    ).count()
    
    # Get new applications (this week)
    one_week_ago = datetime.now() - timedelta(days=7)
    new_applications = db.session.query(JobApplication).join(JobPosting).filter(
        JobPosting.company_id == company.id,
        JobApplication.applied_at >= one_week_ago
    ).count()
    
    # Get scheduled interviews
    scheduled_interviews = db.session.query(InterviewRoom).join(
        JobApplication, InterviewRoom.job_application_id == JobApplication.id
    ).join(
        JobPosting, JobApplication.job_id == JobPosting.id
    ).filter(
        JobPosting.company_id == company.id,
        InterviewRoom.status == 'scheduled',
        InterviewRoom.scheduled_time >= datetime.now()
    ).count()
    
    # Get active exams
    active_exams = db.session.query(MCQExam).join(JobPosting).filter(
        JobPosting.company_id == company.id,
        MCQExam.is_active == True
    ).count()
    
    return render_template('employer/employer_dashboard.html',
                         user=user,
                         company=company,
                         job_postings=job_postings,
                         applications=applications,
                         notifications=notifications,
                         analytics=analytics,
                         active_jobs_count=active_jobs_count,
                         new_applications=new_applications,
                         scheduled_interviews=scheduled_interviews,
                         active_exams=active_exams)


@bp.route('/jobs')
def employer_jobs():
    if 'user_id' not in session or session['user_type'] != 'employer':
        return redirect(url_for('auth.login'))
    
    user = User.query.get(session['user_id'])
    company = user.company
    
    job_postings = db.session.query(
        JobPosting,
        func.count(JobApplication.id).label('application_count')
    ).outerjoin(JobApplication).filter(
        JobPosting.company_id == company.id
    ).group_by(JobPosting.id).order_by(JobPosting.created_at.desc()).all()
    
    return render_template('employer/employer_jobs.html',
                         job_postings=job_postings,
                         user=user,
                         company=company)

@bp.route('/job/create', methods=['GET', 'POST'])
def create_job():
    if 'user_id' not in session or session['user_type'] != 'employer':
        return redirect(url_for('auth.login'))
    
    user = User.query.get(session['user_id'])
    company = user.company
    
    if request.method == 'POST':
        try:
            # Create new job posting
            job = JobPosting(
                company_id=company.id,
                title=request.form['title'],
                description=request.form['description'],
                requirements=request.form.get('requirements', ''),
                location=request.form.get('location', ''),
                job_type=request.form.get('job_type', 'Full-time'),
                experience_required=int(request.form.get('experience_required', 0)),
                salary_min=float(request.form.get('salary_min')) if request.form.get('salary_min') else None,
                salary_max=float(request.form.get('salary_max')) if request.form.get('salary_max') else None,
                is_active=True
            )
            
            db.session.add(job)
            db.session.flush()  # Get job.id
            
            # Add selected skills
            skill_ids = request.form.getlist('skills')
            for skill_id in skill_ids:
                try:
                    job_skill = JobRequiredSkill(
                        job_id=job.id,
                        skill_id=int(skill_id),
                        importance='Required'
                    )
                    db.session.add(job_skill)
                except (ValueError, TypeError):
                    continue
            
            db.session.commit()
            
            flash('Job posting created successfully!', 'success')
            return redirect(url_for('employer.employer_jobs'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating job posting: {str(e)}', 'error')
    
    # Get all skills for the form
    skills = Skill.query.order_by(Skill.skill_name).all()
    
    return render_template('employer/create_job.html', user=user, company=company, skills=skills)


@bp.route('/job/<int:job_id>/exam', methods=['GET', 'POST'])
def manage_job_exam(job_id):
    if 'user_id' not in session or session['user_type'] != 'employer':
        return redirect(url_for('auth.login'))
    
    user = User.query.get(session['user_id'])
    company = user.company
    
    # Verify job belongs to this employer
    job = JobPosting.query.filter_by(id=job_id, company_id=company.id).first()
    if not job:
        flash('Job not found.', 'error')
        return redirect(url_for('employer.employer_dashboard'))
    
    # Get existing exam
    exam = MCQExam.query.filter_by(job_id=job_id).first()
    
    if request.method == 'POST':
        if not exam:
            # Create new exam
            exam = MCQExam(
                job_id=job_id,
                exam_title=request.form.get('title'),
                description=request.form.get('description'),
                duration_minutes=int(request.form.get('time_limit', 60)),
                passing_score=float(request.form.get('passing_score', 60.0))
            )
            db.session.add(exam)
        else:
            # Update existing exam
            exam.exam_title = request.form.get('title')
            exam.description = request.form.get('description')
            exam.duration_minutes = int(request.form.get('time_limit', 60))
            exam.passing_score = float(request.form.get('passing_score', 60.0))
        
        db.session.commit()
        flash('Exam details saved successfully!', 'success')
        return redirect(url_for('employer.manage_exam_questions', exam_id=exam.id))
    
    return render_template('exam/manage_job_exam.html', job=job, exam=exam)


@bp.route('/exam/<int:exam_id>/questions')
def manage_exam_questions(exam_id):
    if 'user_id' not in session or session['user_type'] != 'employer':
        return redirect(url_for('auth.login'))
    
    user = User.query.get(session['user_id'])
    company = user.company
    
    # Verify exam belongs to this employer
    exam = db.session.query(MCQExam).join(JobPosting).filter(
        MCQExam.id == exam_id,
        JobPosting.company_id == company.id
    ).first()
    
    if not exam:
        flash('Exam not found.', 'error')
        return redirect(url_for('employer.employer_dashboard'))
    
    questions = MCQQuestion.query.filter_by(exam_id=exam_id).all()
    return render_template('exam/manage_exam_questions.html', exam=exam, questions=questions)


@bp.route('/exam/<int:exam_id>/add_question', methods=['GET', 'POST'])
def add_exam_question(exam_id):
    if 'user_id' not in session or session['user_type'] != 'employer':
        return redirect(url_for('auth.login'))
    
    if request.method == 'POST':
        # Get the number of options
        options_count = int(request.form.get('options_count', 4))
        
        # Collect options and find correct answer
        options = []
        correct_answer = None
        correct_option_index = int(request.form.get('correct_option', 0))
        
        for i in range(options_count):
            option_text = request.form.get(f'option_{i}', '').strip()
            if option_text:
                options.append(option_text)
                if i == correct_option_index:
                    # Map to A, B, C, D
                    correct_answer = chr(65 + len(options) - 1)  # A=65 in ASCII
        
        # Ensure we have exactly 4 options (pad if necessary)
        while len(options) < 4:
            options.append('')
        
        question = MCQQuestion(
            exam_id=exam_id,
            question_text=request.form.get('question_text'),
            option_a=options[0] if len(options) > 0 else '',
            option_b=options[1] if len(options) > 1 else '',
            option_c=options[2] if len(options) > 2 else '',
            option_d=options[3] if len(options) > 3 else '',
            correct_answer=correct_answer,
            points=int(request.form.get('points', 1)),
            difficulty_level=request.form.get('difficulty', 'Medium').capitalize(),
            category=request.form.get('category', '')
        )
        db.session.add(question)
        
        # Update exam total_questions
        exam = MCQExam.query.get(exam_id)
        exam.total_questions = MCQQuestion.query.filter_by(exam_id=exam_id).count() + 1
        
        db.session.commit()
        flash('Question added successfully!', 'success')
        return redirect(url_for('employer.manage_exam_questions', exam_id=exam_id))
    
    exam = MCQExam.query.get_or_404(exam_id)
    return render_template('exam/add_exam_question.html', exam=exam)


@bp.route('/applications')
def employer_applications():
    if 'user_id' not in session or session['user_type'] != 'employer':
        return redirect(url_for('auth.login'))
    
    user = User.query.get(session['user_id'])
    company = user.company
    
    # Check if company exists
    if not company:
        flash('Company profile not found. Please complete your company profile first.', 'error')
        return redirect(url_for('employer.employer_dashboard'))
    
    # Get applications with filters
    status_filter = request.args.get('status', '')
    job_filter = request.args.get('job_id', '')
    
    query = db.session.query(JobApplication, JobPosting, CandidateProfile, User).join(
        JobPosting, JobApplication.job_id == JobPosting.id
    ).join(
        CandidateProfile, JobApplication.candidate_id == CandidateProfile.id
    ).join(
        User, CandidateProfile.user_id == User.id
    ).filter(
        JobPosting.company_id == company.id
    )

    if status_filter:
        query = query.filter(JobApplication.application_status == status_filter)
    
    if job_filter:
        query = query.filter(JobPosting.id == int(job_filter))
    
    applications_raw = query.order_by(JobApplication.applied_at.desc()).all()
    
    # Calculate match scores for each application
    applications = []
    for app, job, candidate, candidate_user in applications_raw:
        match_score = calculate_job_match_score(candidate.id, job.id)
        applications.append((app, job, candidate, candidate_user, match_score))
    
    # Get company jobs for filter
    company_jobs = JobPosting.query.filter_by(company_id=company.id).all()
    
    return render_template('employer/employer_applications.html',
        applications=applications,
        company_jobs=company_jobs,
        company=company,
        user=user,
        status_filter=status_filter,
        job_filter=job_filter)


@bp.route('/application/<int:application_id>')
def employer_view_application(application_id):
    if 'user_id' not in session or session['user_type'] != 'employer':
        return redirect(url_for('auth.login'))
    
    application_data = db.session.query(
        JobApplication, JobPosting, CandidateProfile, User
    ).join(
        JobPosting, JobApplication.job_id == JobPosting.id
    ).join(
        CandidateProfile, JobApplication.candidate_id == CandidateProfile.id
    ).join(
        User, CandidateProfile.user_id == User.id
    ).filter(
        JobApplication.id == application_id
    ).first()
    
    if not application_data:
        flash('Application not found', 'error')
        return redirect(url_for('employer.employer_applications'))
    
    application, job, candidate, user = application_data
    
    # Verify this application belongs to employer's company
    employer = User.query.get(session['user_id'])
    if job.company_id != employer.company.id:
        flash('Unauthorized access', 'error')
        return redirect(url_for('employer.employer_applications'))
    
    # Get candidate skills
    candidate_skills_data = db.session.query(CandidateSkill, Skill).join(Skill).filter(
        CandidateSkill.candidate_id == candidate.id
    ).all()
    
    # Get job required skills
    required_skills_data = db.session.query(JobRequiredSkill, Skill).join(Skill).filter(
        JobRequiredSkill.job_id == job.id
    ).all()
    
    # Categorize skills
    candidate_skill_ids = {skill.id for _, skill in candidate_skills_data}
    required_skill_ids = {skill.id for _, skill in required_skills_data}
    
    # Matched skills (candidate has AND job requires)
    matched_skills = [(cs, skill) for cs, skill in candidate_skills_data if skill.id in required_skill_ids]
    
    # Lacked skills (job requires but candidate doesn't have)
    lacked_skills = [(rs, skill) for rs, skill in required_skills_data if skill.id not in candidate_skill_ids]
    
    # Extra skills (candidate has but job doesn't require)
    extra_skills = [(cs, skill) for cs, skill in candidate_skills_data if skill.id not in required_skill_ids]
    
    # Get application status history
    status_history = ApplicationStatusHistory.query.filter_by(
        application_id=application_id
    ).order_by(ApplicationStatusHistory.changed_at.desc()).all()
    
    # Calculate match score
    match_score = calculate_job_match_score(candidate.id, job.id)
    
    # Get available interviewers for recommendation
    available_interviewers = User.query.filter_by(
        user_type='interviewer', is_active=True
    ).all()
    
    # Get existing interviewer recommendations
    interviewer_recommendations = InterviewerRecommendation.query.filter_by(
        application_id=application_id
    ).all()
    
    # Get scheduled interview (if any)
    interview_room = InterviewRoom.query.filter_by(
        job_application_id=application_id
    ).first()
    
    # Get interview feedback (if interview completed)
    interview_feedbacks = []
    if interview_room:
        feedbacks = db.session.query(InterviewFeedback, User).join(
            User, InterviewFeedback.interviewer_id == User.id
        ).filter(
            InterviewFeedback.room_id == interview_room.id
        ).all()
        interview_feedbacks = feedbacks
    
    return render_template('employer/employer_view_application.html',
                         application=application,
                         job=job,
                         candidate=candidate,
                         user=user,
                         matched_skills=matched_skills,
                         lacked_skills=lacked_skills,
                         extra_skills=extra_skills,
                         status_history=status_history,
                         match_score=match_score,
                         available_interviewers=available_interviewers,
                         interviewer_recommendations=interviewer_recommendations,
                         interview_room=interview_room,
                         interview_feedbacks=interview_feedbacks)


@bp.route('/application/<int:application_id>/update_status', methods=['POST'])
def update_application_status(application_id):
    if 'user_id' not in session or session['user_type'] != 'employer':
        return redirect(url_for('auth.login'))
    
    application = JobApplication.query.get_or_404(application_id)
    
    # Verify ownership
    employer = User.query.get(session['user_id'])
    if application.job.company_id != employer.company.id:
        flash('Unauthorized access', 'error')
        return redirect(url_for('employer.employer_applications'))
    
    old_status = application.application_status
    new_status = request.form['status']
    notes = request.form.get('notes', '')
    
    try:
        # Update application status
        application.application_status = new_status
        
        # Create status history
        status_history = ApplicationStatusHistory(
            application_id=application_id,
            old_status=old_status,
            new_status=new_status,
            changed_by=session['user_id'],
            notes=notes
        )
        db.session.add(status_history)
        
        # Log activity
        log_activity('job_applications', 'UPDATE', application_id,
                    old_values={'application_status': old_status},
                    new_values={'application_status': new_status},
                    user_id=session['user_id'])
        
        # Notify candidate
        candidate_user = application.candidate.user
        create_notification(
            candidate_user.id,
            'Application Status Updated',
            f'Your application for {application.job.title} has been updated to: {new_status}',
            'application',
            url_for('candidate.candidate_applications')
        )
        
        db.session.commit()
        
        flash('Application status updated successfully', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating status: {str(e)}', 'error')
    
    return redirect(url_for('employer.employer_view_application', application_id=application_id))


@bp.route('/download_cv/<int:candidate_id>')
def download_cv(candidate_id):
    if 'user_id' not in session or session['user_type'] != 'employer':
        return redirect(url_for('auth.login'))
    
    # Get candidate profile
    candidate = CandidateProfile.query.get_or_404(candidate_id)
    
    # Verify employer has access to this candidate's CV (through applications)
    employer = User.query.get(session['user_id'])
    company = employer.company
    
    # Check if there's an application from this candidate to any of the employer's jobs
    application_exists = db.session.query(JobApplication).join(
        JobPosting, JobApplication.job_id == JobPosting.id
    ).filter(
        JobApplication.candidate_id == candidate_id,
        JobPosting.company_id == company.id
    ).first()
    
    if not application_exists:
        flash('You do not have permission to download this CV', 'error')
        return redirect(url_for('employer.employer_applications'))
    
    # Check if CV exists
    if not candidate.cv_content or not candidate.cv_filename:
        flash('CV not found for this candidate', 'error')
        return redirect(url_for('employer.employer_applications'))
    
    try:
        # Log the download activity
        log_activity('candidate_profiles', 'DOWNLOAD_CV', candidate_id,
                    new_values={'downloaded_by': session['user_id']},
                    user_id=session['user_id'])
        
        # Return the file with proper headers to force download
        response = Response(
            candidate.cv_content,
            mimetype=candidate.cv_mimetype or 'application/octet-stream'
        )
        response.headers['Content-Disposition'] = f'attachment; filename="{candidate.cv_filename}"'
        response.headers['Content-Length'] = len(candidate.cv_content)
        return response
    except Exception as e:
        flash(f'Error downloading CV: {str(e)}', 'error')
        return redirect(url_for('employer.employer_applications'))


@bp.route('/recommend_interviewer/<int:application_id>', methods=['POST'])
def recommend_interviewer(application_id):
    if 'user_id' not in session or session['user_type'] != 'employer':
        return redirect(url_for('auth.login'))
    
    # Verify application belongs to employer
    application = db.session.query(JobApplication).join(
        JobPosting, JobApplication.job_id == JobPosting.id
    ).filter(
        JobApplication.id == application_id,
        JobPosting.company_id == User.query.get(session['user_id']).company.id
    ).first()
    
    if not application:
        flash('Application not found or unauthorized access', 'error')
        return redirect(url_for('employer.employer_applications'))
    
    interviewer_id = request.form.get('interviewer_id')
    recommendation_notes = request.form.get('recommendation_notes', '')
    
    if not interviewer_id:
        flash('Please select an interviewer', 'error')
        return redirect(url_for('employer.employer_view_application', application_id=application_id))
    
    # Check if recommendation already exists
    existing_recommendation = InterviewerRecommendation.query.filter_by(
        application_id=application_id,
        interviewer_id=interviewer_id,
        status='pending'
    ).first()
    
    if existing_recommendation:
        flash('Recommendation already sent to this interviewer', 'warning')
        return redirect(url_for('employer.employer_view_application', application_id=application_id))
    
    try:
        # Create recommendation (pending)
        recommendation = InterviewerRecommendation(
            application_id=application_id,
            recommended_by=session['user_id'],
            interviewer_id=int(interviewer_id),
            recommendation_notes=recommendation_notes,
            status='pending'
        )
        
        db.session.add(recommendation)
        db.session.flush()
        
        # Log activity
        log_activity('interviewer_recommendations', 'INSERT', recommendation.id,
            new_values={
                'application_id': application_id,
                'interviewer_id': interviewer_id,
                'recommended_by': session['user_id']
            },
            user_id=session['user_id'])

        # Notify ADMIN/MANAGER (not interviewer)
        interviewer = User.query.get(interviewer_id)
        employer = User.query.get(session['user_id'])
        admins = User.query.filter(User.user_type.in_(['admin', 'manager'])).all()
        for admin in admins:
            create_notification(
                admin.id,
                'New Interviewer Recommendation',
                f'Employer {employer.first_name} {employer.last_name} has recommended {interviewer.first_name} {interviewer.last_name} for interviewing candidate {application.candidate.user.first_name} {application.candidate.user.last_name} (Job: {application.job.title}).',
                'system',
                url_for('admin.schedule_interview', application_id=application_id)
            )
        db.session.commit()
        flash('Interviewer recommendation submitted to manager for approval and scheduling.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error sending recommendation: {str(e)}', 'error')
    return redirect(url_for('employer.employer_view_application', application_id=application_id))


@bp.route('/exam/question/<int:question_id>/edit', methods=['GET', 'POST'])
def edit_exam_question(question_id):
    if 'user_id' not in session or session['user_type'] != 'employer':
        return redirect(url_for('auth.login'))
    
    question = MCQQuestion.query.get_or_404(question_id)
    exam = question.exam
    
    # Verify this question belongs to this employer
    user = User.query.get(session['user_id'])
    company = user.company
    
    exam_check = db.session.query(MCQExam).join(JobPosting).filter(
        MCQExam.id == exam.id,
        JobPosting.company_id == company.id
    ).first()
    
    if not exam_check:
        flash('Unauthorized access.', 'error')
        return redirect(url_for('employer.employer_dashboard'))
    
    if request.method == 'POST':
        # Get the number of options
        options_count = int(request.form.get('options_count', 4))
        
        # Collect options and find correct answer
        options = []
        correct_answer = None
        correct_option_index = int(request.form.get('correct_option', 0))
        
        for i in range(options_count):
            option_text = request.form.get(f'option_{i}', '').strip()
            if option_text:
                options.append(option_text)
                if i == correct_option_index:
                    # Map to A, B, C, D
                    correct_answer = chr(65 + len(options) - 1)  # A=65 in ASCII
        
        # Ensure we have exactly 4 options (pad if necessary)
        while len(options) < 4:
            options.append('')
        
        question.question_text = request.form.get('question_text')
        question.option_a = options[0] if len(options) > 0 else ''
        question.option_b = options[1] if len(options) > 1 else ''
        question.option_c = options[2] if len(options) > 2 else ''
        question.option_d = options[3] if len(options) > 3 else ''
        question.correct_answer = correct_answer
        question.points = int(request.form.get('points', 1))
        question.difficulty_level = request.form.get('difficulty', 'Medium').capitalize()
        question.category = request.form.get('category', '')
        
        db.session.commit()
        flash('Question updated successfully!', 'success')
        return redirect(url_for('employer.manage_exam_questions', exam_id=exam.id))
    
    return render_template('exam/add_exam_question.html', question=question, exam=exam)


@bp.route('/exam/question/<int:question_id>/delete', methods=['POST'])
def delete_exam_question(question_id):
    if 'user_id' not in session or session['user_type'] != 'employer':
        return redirect(url_for('auth.login'))
    
    question = MCQQuestion.query.get_or_404(question_id)
    exam = question.exam
    
    # Verify this question belongs to this employer
    user = User.query.get(session['user_id'])
    company = user.company
    
    exam_check = db.session.query(MCQExam).join(JobPosting).filter(
        MCQExam.id == exam.id,
        JobPosting.company_id == company.id
    ).first()
    
    if not exam_check:
        flash('Unauthorized access.', 'error')
        return redirect(url_for('employer.employer_dashboard'))
    
    try:
        db.session.delete(question)
        db.session.commit()
        
        # Log activity
        log_activity('mcq_questions', 'DELETE', question_id,
                    old_values={'question_text': question.question_text},
                    user_id=session['user_id'])
        
        flash('Question deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting question: {str(e)}', 'error')
    
    return redirect(url_for('employer.manage_exam_questions', exam_id=exam.id))


# =====================================================
# INTERVIEWER MANAGEMENT - EMPLOYER
# =====================================================

@bp.route('/interviewers')
def employer_interviewers():
    """View all interviewers available to employer (in-house + browse marketplace)"""
    if 'user_id' not in session or session['user_type'] != 'employer':
        return redirect(url_for('auth.login'))
    
    user = User.query.get(session['user_id'])
    company = user.company
    
    # Get in-house interviewers
    in_house_interviewers = db.session.query(InterviewerProfile, User).join(
        User, InterviewerProfile.user_id == User.id
    ).filter(
        InterviewerProfile.company_id == company.id,
        InterviewerProfile.interviewer_type == 'in_house'
    ).all()
    
    return render_template('employer/employer_interviewers.html',
                         user=user,
                         company=company,
                         in_house_interviewers=in_house_interviewers)


@bp.route('/interviewers/browse')
def browse_expert_interviewers():
    """Browse marketplace of approved independent expert interviewers"""
    if 'user_id' not in session or session['user_type'] != 'employer':
        return redirect(url_for('auth.login'))
    
    user = User.query.get(session['user_id'])
    company = user.company
    
    page = request.args.get('page', 1, type=int)
    skill_filter = request.args.get('skill', '')
    industry_filter = request.args.get('industry', '')
    min_rate = request.args.get('min_rate', type=float)
    max_rate = request.args.get('max_rate', type=float)
    search = request.args.get('search', '')
    
    # Base query for approved, active independent interviewers
    query = db.session.query(InterviewerProfile, User).join(
        User, InterviewerProfile.user_id == User.id
    ).filter(
        InterviewerProfile.interviewer_type == 'independent',
        InterviewerProfile.approval_status == 'approved',
        InterviewerProfile.is_active == True
    )
    
    # Apply filters
    if skill_filter:
        query = query.join(
            InterviewerSkill, InterviewerProfile.id == InterviewerSkill.interviewer_id
        ).filter(InterviewerSkill.skill_id == int(skill_filter))
    
    if industry_filter:
        query = query.join(
            InterviewerIndustry, InterviewerProfile.id == InterviewerIndustry.interviewer_id
        ).filter(InterviewerIndustry.industry_name == industry_filter)
    
    if min_rate:
        query = query.filter(InterviewerProfile.hourly_rate >= min_rate)
    
    if max_rate:
        query = query.filter(InterviewerProfile.hourly_rate <= max_rate)
    
    if search:
        query = query.filter(
            or_(
                User.first_name.contains(search),
                User.last_name.contains(search),
                InterviewerProfile.headline.contains(search)
            )
        )
    
    interviewers = query.order_by(
        InterviewerProfile.is_verified.desc(),
        InterviewerProfile.average_rating.desc()
    ).paginate(page=page, per_page=12, error_out=False)
    
    # Get filter options
    all_skills = Skill.query.order_by(Skill.skill_name).all()
    all_industries = db.session.query(InterviewerIndustry.industry_name).distinct().all()
    all_industries = [i[0] for i in all_industries]
    
    return render_template('employer/browse_interviewers.html',
                         user=user,
                         company=company,
                         interviewers=interviewers,
                         all_skills=all_skills,
                         all_industries=all_industries,
                         skill_filter=skill_filter,
                         industry_filter=industry_filter,
                         min_rate=min_rate,
                         max_rate=max_rate,
                         search=search)


@bp.route('/interviewers/view/<int:profile_id>')
def view_interviewer_profile(profile_id):
    """View detailed interviewer profile"""
    if 'user_id' not in session or session['user_type'] != 'employer':
        return redirect(url_for('auth.login'))
    
    user = User.query.get(session['user_id'])
    company = user.company
    
    profile = InterviewerProfile.query.get_or_404(profile_id)
    interviewer_user = User.query.get(profile.user_id)
    
    # Check if employer can view this profile
    # Can view if: in-house interviewer of their company OR approved independent
    can_view = (
        (profile.interviewer_type == 'in_house' and profile.company_id == company.id) or
        (profile.interviewer_type == 'independent' and profile.approval_status == 'approved')
    )
    
    if not can_view:
        flash('You do not have permission to view this profile.', 'error')
        return redirect(url_for('employer.employer_interviewers'))
    
    # Get reviews
    reviews = InterviewerReview.query.filter_by(
        interviewer_id=profile.id, is_public=True
    ).order_by(InterviewerReview.created_at.desc()).limit(5).all()
    
    # Get availability
    availabilities = InterviewerAvailability.query.filter_by(
        interviewer_id=profile.id, is_active=True
    ).order_by(InterviewerAvailability.day_of_week).all()
    
    days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    
    return render_template('employer/view_interviewer.html',
                         user=user,
                         company=company,
                         profile=profile,
                         interviewer_user=interviewer_user,
                         reviews=reviews,
                         availabilities=availabilities,
                         days=days)


@bp.route('/interviewers/add-inhouse', methods=['GET', 'POST'])
def add_inhouse_interviewer():
    """Add in-house interviewer from company"""
    if 'user_id' not in session or session['user_type'] != 'employer':
        return redirect(url_for('auth.login'))
    
    user = User.query.get(session['user_id'])
    company = user.company
    
    if request.method == 'POST':
        try:
            email = request.form.get('email')
            
            # Check if user already exists
            existing_user = User.query.filter_by(email=email).first()
            
            if existing_user:
                # Check if already an interviewer with a profile
                existing_profile = InterviewerProfile.query.filter_by(user_id=existing_user.id).first()
                if existing_profile:
                    flash('This user is already registered as an interviewer.', 'error')
                    return redirect(url_for('employer.add_inhouse_interviewer'))
                
                # Update existing user to interviewer type and create profile
                existing_user.user_type = 'interviewer'
                
                profile = InterviewerProfile(
                    user_id=existing_user.id,
                    headline=request.form.get('headline', ''),
                    experience_years=int(request.form.get('experience_years', 0)),
                    interviewer_type='in_house',
                    company_id=company.id,
                    approval_status='approved',  # In-house = auto-approved
                    is_active=True,
                    is_available=True,
                    approved_at=datetime.utcnow()
                )
                db.session.add(profile)
                
            else:
                # Create new user as interviewer
                import secrets
                temp_password = secrets.token_urlsafe(12)
                
                new_user = User(
                    email=email,
                    password_hash=generate_password_hash(temp_password),
                    user_type='interviewer',
                    first_name=request.form.get('first_name'),
                    last_name=request.form.get('last_name'),
                    phone=request.form.get('phone', ''),
                    is_active=True
                )
                db.session.add(new_user)
                db.session.flush()
                
                profile = InterviewerProfile(
                    user_id=new_user.id,
                    headline=request.form.get('headline', ''),
                    experience_years=int(request.form.get('experience_years', 0)),
                    interviewer_type='in_house',
                    company_id=company.id,
                    approval_status='approved',
                    is_active=True,
                    is_available=True,
                    approved_at=datetime.utcnow()
                )
                db.session.add(profile)
                db.session.flush()
                
                # Create notification for new user
                create_notification(
                    new_user.id,
                    f'Welcome to {company.company_name}!',
                    f'You have been added as an in-house interviewer. Your temporary password is: {temp_password}',
                    'system'
                )
                
                flash(f'Interviewer added! Temporary password sent: {temp_password}', 'success')
            
            # Add skills
            skill_ids = request.form.getlist('skills')
            for skill_id in skill_ids:
                interviewer_skill = InterviewerSkill(
                    interviewer_id=profile.id,
                    skill_id=int(skill_id),
                    proficiency_level='Expert'
                )
                db.session.add(interviewer_skill)
            
            db.session.commit()
            
            log_activity('interviewer_profiles', 'INSERT', profile.id,
                        new_values={'email': email, 'company_id': company.id, 'type': 'in_house'},
                        user_id=session['user_id'])
            
            flash('In-house interviewer added successfully!', 'success')
            return redirect(url_for('employer.employer_interviewers'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding interviewer: {str(e)}', 'error')
    
    all_skills = Skill.query.order_by(Skill.skill_name).all()
    
    return render_template('employer/add_inhouse_interviewer.html',
                         user=user,
                         company=company,
                         all_skills=all_skills)


@bp.route('/interviewers/remove/<int:profile_id>', methods=['POST'])
def remove_inhouse_interviewer(profile_id):
    """Remove in-house interviewer (only from company, not delete account)"""
    if 'user_id' not in session or session['user_type'] != 'employer':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    user = User.query.get(session['user_id'])
    company = user.company
    
    profile = InterviewerProfile.query.filter_by(
        id=profile_id,
        company_id=company.id,
        interviewer_type='in_house'
    ).first()
    
    if not profile:
        flash('Interviewer not found or not part of your company.', 'error')
        return redirect(url_for('employer.employer_interviewers'))
    
    # Don't delete, just remove company association
    profile.company_id = None
    profile.interviewer_type = 'independent'
    profile.approval_status = 'pending'  # Need admin approval to be independent
    
    db.session.commit()
    
    flash('Interviewer removed from your company.', 'success')
    return redirect(url_for('employer.employer_interviewers'))


@bp.route('/interviewers/select-for-interview', methods=['POST'])
def select_interviewer_for_interview():
    """Select interviewer for a scheduled interview"""
    if 'user_id' not in session or session['user_type'] != 'employer':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    interview_room_id = request.form.get('interview_room_id')
    interviewer_profile_id = request.form.get('interviewer_profile_id')
    
    user = User.query.get(session['user_id'])
    company = user.company
    
    # Verify the interview belongs to this company
    interview_room = InterviewRoom.query.get_or_404(interview_room_id)
    job_app = JobApplication.query.get(interview_room.job_application_id)
    job = JobPosting.query.get(job_app.job_id)
    
    if job.company_id != company.id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    profile = InterviewerProfile.query.get_or_404(interviewer_profile_id)
    
    # Add interviewer as participant
    from models import InterviewParticipant
    
    participant = InterviewParticipant(
        room_id=interview_room.id,
        user_id=profile.user_id,
        role='interviewer'
    )
    db.session.add(participant)
    db.session.commit()
    
    # Notify the interviewer
    create_notification(
        profile.user_id,
        'New Interview Assignment',
        f'You have been assigned to conduct an interview for {job.title} at {company.company_name}.',
        'interview',
        url_for('interviewer.interviewer_dashboard')
    )
    
    flash('Interviewer assigned to the interview successfully!', 'success')
    return redirect(request.referrer or url_for('employer.employer_dashboard'))


@bp.route('/interviewers/<int:profile_id>/review', methods=['GET', 'POST'])
def review_interviewer(profile_id):
    """Leave a review for an interviewer after interview"""
    if 'user_id' not in session or session['user_type'] != 'employer':
        return redirect(url_for('auth.login'))
    
    user = User.query.get(session['user_id'])
    company = user.company
    profile = InterviewerProfile.query.get_or_404(profile_id)
    
    if request.method == 'POST':
        try:
            review = InterviewerReview(
                interviewer_id=profile.id,
                reviewer_id=user.id,
                interview_room_id=request.form.get('interview_room_id'),
                professionalism_rating=int(request.form.get('professionalism_rating', 0)),
                technical_accuracy_rating=int(request.form.get('technical_accuracy_rating', 0)),
                communication_rating=int(request.form.get('communication_rating', 0)),
                punctuality_rating=int(request.form.get('punctuality_rating', 0)),
                overall_rating=int(request.form.get('overall_rating', 0)),
                review_text=request.form.get('review_text', ''),
                would_hire_again=request.form.get('would_hire_again') == 'yes'
            )
            db.session.add(review)
            
            # Update average rating
            avg_rating = db.session.query(func.avg(InterviewerReview.overall_rating)).filter(
                InterviewerReview.interviewer_id == profile.id
            ).scalar()
            profile.average_rating = round(avg_rating, 2) if avg_rating else 0
            
            db.session.commit()
            
            flash('Thank you for your review!', 'success')
            return redirect(url_for('employer.view_interviewer_profile', profile_id=profile_id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error submitting review: {str(e)}', 'error')
    
    # Get completed interviews with this interviewer
    from models import InterviewParticipant
    completed_interviews = db.session.query(InterviewRoom).join(
        InterviewParticipant, InterviewRoom.id == InterviewParticipant.room_id
    ).join(
        JobApplication, InterviewRoom.job_application_id == JobApplication.id
    ).join(
        JobPosting, JobApplication.job_id == JobPosting.id
    ).filter(
        InterviewParticipant.user_id == profile.user_id,
        JobPosting.company_id == company.id,
        InterviewRoom.status == 'completed'
    ).all()
    
    return render_template('employer/review_interviewer.html',
                         user=user,
                         company=company,
                         profile=profile,
                         completed_interviews=completed_interviews)


@bp.route('/application/<int:application_id>/schedule_interview', methods=['GET', 'POST'])
def schedule_interview(application_id):
    """Schedule an interview for a shortlisted candidate"""
    if 'user_id' not in session or session['user_type'] != 'employer':
        return redirect(url_for('auth.login'))
    
    user = User.query.get(session['user_id'])
    company = user.company
    
    # Verify application belongs to this employer's company
    application = db.session.query(JobApplication).join(
        JobPosting, JobApplication.job_id == JobPosting.id
    ).filter(
        JobApplication.id == application_id,
        JobPosting.company_id == company.id
    ).first()
    
    if not application:
        flash('Application not found or unauthorized access', 'error')
        return redirect(url_for('employer.employer_applications'))
    
    # Check if interview already scheduled
    existing_interview = InterviewRoom.query.filter_by(
        job_application_id=application_id
    ).filter(InterviewRoom.status.in_(['scheduled', 'active'])).first()
    
    if existing_interview:
        flash('An interview is already scheduled for this application', 'warning')
        return redirect(url_for('employer.employer_view_application', application_id=application_id))
    
    if request.method == 'POST':
        try:
            # Parse datetime
            scheduled_date = request.form.get('date')
            scheduled_time = request.form.get('time')
            scheduled_datetime = datetime.strptime(f"{scheduled_date} {scheduled_time}", '%Y-%m-%d %H:%M')
            
            # Validate that scheduled time is in the future
            if scheduled_datetime < datetime.now():
                flash('Please select a future date and time for the interview', 'error')
                return redirect(url_for('employer.schedule_interview', application_id=application_id))
            
            duration = int(request.form.get('duration', 60))
            interview_type = request.form.get('interview_type', 'video')
            notes = request.form.get('notes', '')
            
            # Generate unique room code
            import uuid
            room_code = f"INT{application_id}{uuid.uuid4().hex[:8].upper()}"
            
            # Create interview room
            interview_room = InterviewRoom(
                room_name=f"Interview - {application.job.title}",
                room_code=room_code,
                job_application_id=application_id,
                scheduled_time=scheduled_datetime,
                duration_minutes=duration,
                status='scheduled',
                created_by=session['user_id']
            )
            
            db.session.add(interview_room)
            db.session.flush()
            
            # Add candidate as participant
            from models import InterviewParticipant
            candidate_participant = InterviewParticipant(
                room_id=interview_room.id,
                user_id=application.candidate.user_id,
                role='candidate'
            )
            db.session.add(candidate_participant)
            
            # Add selected interviewers
            interviewer_ids = request.form.getlist('interviewer_ids')
            for interviewer_id in interviewer_ids:
                interviewer_participant = InterviewParticipant(
                    room_id=interview_room.id,
                    user_id=int(interviewer_id),
                    role='interviewer'
                )
                db.session.add(interviewer_participant)
            
            # Update application status to interview_scheduled
            old_status = application.application_status
            application.application_status = 'interview_scheduled'
            
            # Create status history
            status_history = ApplicationStatusHistory(
                application_id=application_id,
                old_status=old_status,
                new_status='interview_scheduled',
                changed_by=session['user_id'],
                notes=f'Interview scheduled for {scheduled_datetime.strftime("%B %d, %Y at %I:%M %p")}'
            )
            db.session.add(status_history)
            
            # Log activity
            log_activity('interview_rooms', 'INSERT', interview_room.id,
                        new_values={
                            'application_id': application_id,
                            'scheduled_time': scheduled_datetime.isoformat(),
                            'interviewer_ids': interviewer_ids
                        },
                        user_id=session['user_id'])
            
            db.session.commit()
            
            # Send email notification to candidate
            try:
                send_interview_scheduled_email(
                    application.candidate,
                    application.job,
                    company,
                    interview_room
                )
            except Exception as e:
                print(f"Error sending interview email: {str(e)}")
            
            # Send notifications
            candidate_user = application.candidate.user
            create_notification(
                candidate_user.id,
                'Interview Scheduled',
                f'Your interview for {application.job.title} at {company.company_name} has been scheduled for {scheduled_datetime.strftime("%B %d, %Y at %I:%M %p")}.',
                'system',
                url_for('interview.join_interview', room_code=room_code)
            )
            
            # Notify interviewers
            for interviewer_id in interviewer_ids:
                create_notification(
                    int(interviewer_id),
                    'Interview Assignment',
                    f'You have been assigned to interview {candidate_user.first_name} {candidate_user.last_name} for {application.job.title} on {scheduled_datetime.strftime("%B %d, %Y at %I:%M %p")}.',
                    'system',
                    url_for('interview.join_interview', room_code=room_code)
                )
            
            flash('Interview scheduled successfully!', 'success')
            return redirect(url_for('employer.employer_view_application', application_id=application_id))
            
        except ValueError as e:
            flash('Invalid date/time format. Please try again.', 'error')
        except Exception as e:
            db.session.rollback()
            flash(f'Error scheduling interview: {str(e)}', 'error')
    
    # GET request - show the form
    # Get available interviewers (company's in-house + platform interviewers)
    # In-house interviewers assigned to this company
    inhouse_interviewers = db.session.query(User, InterviewerProfile).join(
        InterviewerProfile, User.id == InterviewerProfile.user_id
    ).filter(
        User.user_type == 'interviewer',
        InterviewerProfile.company_id == company.id,
        InterviewerProfile.is_available == True
    ).all()
    
    # Platform interviewers (freelancers - verified)
    platform_interviewers = db.session.query(User, InterviewerProfile).join(
        InterviewerProfile, User.id == InterviewerProfile.user_id
    ).filter(
        User.user_type == 'interviewer',
        InterviewerProfile.company_id.is_(None),
        InterviewerProfile.is_available == True,
        InterviewerProfile.is_verified == True
    ).all()
    
    # All other interviewers (fallback if no in-house or platform interviewers)
    all_interviewers = db.session.query(User, InterviewerProfile).join(
        InterviewerProfile, User.id == InterviewerProfile.user_id
    ).filter(
        User.user_type == 'interviewer'
    ).all()
    
    return render_template('employer/schedule_interview.html',
                         user=user,
                         company=company,
                         application=application,
                         job=application.job,
                         candidate=application.candidate,
                         inhouse_interviewers=inhouse_interviewers,
                         platform_interviewers=platform_interviewers,
                         all_interviewers=all_interviewers,
                         today=datetime.now().strftime('%Y-%m-%d'))