from flask import Blueprint, render_template, request, redirect, url_for, flash, session, send_file
from sqlalchemy import and_, or_, func
from datetime import datetime
from extensions import db
from models import (
    User, JobPosting, Company, CandidateProfile, JobApplication, 
    JobRequiredSkill, Skill, ApplicationStatusHistory, InterviewRoom, CandidateSkill, MCQExam
)
from services import create_notification, log_activity, calculate_job_match_score
from services.email_service import send_application_confirmation_email

job_bp = Blueprint('job', __name__)

@job_bp.route('/jobs')
def browse_jobs():
    page = request.args.get('page', 1, type=int)
    search = request.args.get('q', '') or request.args.get('search', '')
    location = request.args.get('location', '')
    job_types = request.args.getlist('job_type')  # Support multiple job types
    experience_level = request.args.get('experience', '') or request.args.get('experience_level', '')
    salary_min = request.args.get('min_salary', type=int) or request.args.get('salary_min', type=int)
    skill_id = request.args.get('skill', type=int)
    work_mode = request.args.get('work_mode', '')
    sort = request.args.get('sort', 'newest')
    
    query = db.session.query(JobPosting, Company).join(Company).filter(
        JobPosting.is_active == True
    )
    
    if search:
        query = query.filter(
            or_(
                JobPosting.title.ilike(f'%{search}%'),
                JobPosting.description.ilike(f'%{search}%'),
                Company.company_name.ilike(f'%{search}%')
            )
        )
    
    if location:
        query = query.filter(JobPosting.location.ilike(f'%{location}%'))
    
    if job_types:
        # Filter by multiple job types
        query = query.filter(JobPosting.job_type.in_(job_types))
    
    # Filter by work mode (Remote, Onsite, Hybrid)
    if work_mode:
        query = query.filter(
            or_(
                JobPosting.location.ilike(f'%{work_mode}%'),
                JobPosting.description.ilike(f'%{work_mode}%')
            )
        )
    
    if experience_level:
        exp_ranges = {
            'entry': (0, 2),
            'mid': (2, 5),
            'senior': (5, 50),
            'executive': (10, 50)
        }
        if experience_level in exp_ranges:
            min_exp, max_exp = exp_ranges[experience_level]
            query = query.filter(
                or_(
                    JobPosting.experience_required.between(min_exp, max_exp),
                    JobPosting.experience_required == None
                )
            )
    
    if salary_min:
        query = query.filter(
            or_(
                JobPosting.salary_min >= salary_min,
                JobPosting.salary_max >= salary_min
            )
        )
    
    # Filter by skill
    if skill_id:
        job_ids_with_skill = db.session.query(JobRequiredSkill.job_id).filter(
            JobRequiredSkill.skill_id == skill_id
        ).subquery()
        query = query.filter(JobPosting.id.in_(job_ids_with_skill))
    
    # Sorting - Using CASE for MySQL compatibility (MySQL doesn't support NULLS LAST)
    if sort == 'salary_high':
        query = query.order_by(
            func.coalesce(JobPosting.salary_max, 0).desc(),
            JobPosting.created_at.desc()
        )
    elif sort == 'salary_low':
        # For ascending, use a large number for NULLs to push them to the end
        query = query.order_by(
            func.coalesce(JobPosting.salary_min, 999999999).asc(),
            JobPosting.created_at.desc()
        )
    else:  # newest
        query = query.order_by(JobPosting.created_at.desc())
    
    jobs = query.paginate(page=page, per_page=12, error_out=False)
    
    # Get total jobs count
    total_jobs = db.session.query(JobPosting).filter(JobPosting.is_active == True).count()
    
    # Get all skills for filter
    skills = Skill.query.order_by(Skill.skill_name).all()
    
    return render_template('job/browse_jobs.html',
                         jobs=jobs,
                         total_jobs=total_jobs,
                         skills=skills,
                         search=search,
                         location=location,
                         job_types=job_types,
                         experience_level=experience_level,
                         salary_min=salary_min,
                         skill_id=skill_id,
                         sort=sort)

@job_bp.route('/job/<int:job_id>')
def job_details(job_id):
    job_data = db.session.query(JobPosting, Company).join(Company).filter(
        JobPosting.id == job_id
    ).first()
    
    if not job_data:
        flash('Job not found', 'error')
        return redirect(url_for('job.browse_jobs'))
    
    job, company = job_data
    
    # Get required skills for this job
    required_skills = db.session.query(JobRequiredSkill, Skill).join(Skill).filter(
        JobRequiredSkill.job_id == job_id
    ).all()
    
    # Check if user has applied
    has_applied = False
    match_score = 0
    if 'user_id' in session and session['user_type'] == 'candidate':
        user = User.query.get(session['user_id'])
        if user.candidate_profile:
            application = JobApplication.query.filter_by(
                job_id=job_id, candidate_id=user.candidate_profile.id
            ).first()
            has_applied = application is not None
            match_score = calculate_job_match_score(user.candidate_profile.id, job_id)
    
    # Get related jobs from same company
    related_jobs = JobPosting.query.filter(
        JobPosting.company_id == company.id,
        JobPosting.id != job_id,
        JobPosting.is_active == True
    ).limit(3).all()
    
    return render_template('job/job_details.html',
                         job=job,
                         company=company,
                         required_skills=required_skills,
                         has_applied=has_applied,
                         match_score=match_score,
                         related_jobs=related_jobs)


@job_bp.route('/apply/<int:job_id>', methods=['GET', 'POST'])
def apply_job(job_id):
    if 'user_id' not in session or session['user_type'] != 'candidate':
        flash('Please login as a candidate to apply', 'error')
        return redirect(url_for('auth.login'))
    
    user = User.query.get(session['user_id'])
    profile = user.candidate_profile
    
    if not profile:
        flash('Please complete your profile first', 'error')
        return redirect(url_for('candidate.candidate_profile'))
    
    job = JobPosting.query.get_or_404(job_id)
    company = Company.query.get(job.company_id)
    
    # Get candidate skills
    candidate_skills = db.session.query(CandidateSkill, Skill).join(Skill).filter(
        CandidateSkill.candidate_id == profile.id
    ).all()
    
    # Check if already applied
    existing_application = JobApplication.query.filter_by(
        job_id=job_id, candidate_id=profile.id
    ).first()
    
    if existing_application:
        flash('You have already applied for this job', 'info')
        return redirect(url_for('job.job_details', job_id=job_id))
    
    if request.method == 'POST':
        try:
            application = JobApplication(
                job_id=job_id,
                candidate_id=profile.id,
                cover_letter=request.form.get('cover_letter', '')
            )
            
            db.session.add(application)
            db.session.flush()
            
            # Log activity
            log_activity('job_applications', 'INSERT', application.id,
                        new_values={'job_id': job_id, 'candidate_id': profile.id},
                        user_id=session['user_id'])
            
            # Create status history
            status_history = ApplicationStatusHistory(
                application_id=application.id,
                old_status=None,
                new_status='applied',
                changed_by=session['user_id'],
                notes='Initial application submitted'
            )
            db.session.add(status_history)
            
            # Notify employer
            company = job.company
            create_notification(
                company.user_id,
                'New Job Application',
                f'New application received for {job.title} from {user.first_name} {user.last_name}',
                'application',
                url_for('employer.employer_view_application', application_id=application.id)
            )
            
            db.session.commit()
            
            # Send confirmation email
            try:
                # Check if job has MCQ exam
                has_exam = MCQExam.query.filter_by(job_id=job_id, is_active=True).first() is not None
                send_application_confirmation_email(profile, job, company, has_exam=has_exam)
            except Exception as e:
                print(f"Error sending confirmation email: {str(e)}")
            
            flash('Application submitted successfully!', 'success')
            return redirect(url_for('candidate.candidate_applications'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error submitting application: {str(e)}', 'error')
    
    return render_template('job/apply_job.html', job=job, company=company, profile=profile, user=user, candidate_skills=candidate_skills)
