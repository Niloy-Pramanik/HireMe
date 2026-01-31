from flask import Blueprint, render_template, request, redirect, url_for, flash, session, send_file
from sqlalchemy import and_, or_
from datetime import datetime
from werkzeug.utils import secure_filename
import os
import io
from extensions import db
from models import (
    User, CandidateProfile, JobPosting, JobApplication, Company, 
    MCQExam, ExamAttempt, Skill, CandidateSkill, JobRequiredSkill, 
    Notification, InterviewRoom
)
from services import create_notification, log_activity, calculate_job_match_score
from utils import allowed_file

candidate_bp = Blueprint('candidate', __name__)

def get_job_recommendations(candidate_id):
    """Get personalized job recommendations for a candidate"""
    candidate = CandidateProfile.query.get(candidate_id)
    if not candidate:
        return []
    
    # Get jobs the candidate hasn't applied to
    applied_job_ids = db.session.query(JobApplication.job_id).filter_by(
        candidate_id=candidate_id
    ).subquery()
    
    available_jobs = db.session.query(JobPosting, Company).join(
        Company, JobPosting.company_id == Company.id
    ).filter(
        JobPosting.is_active == True,
        ~JobPosting.id.in_(applied_job_ids)
    ).all()
    
    # Calculate match scores and sort
    job_matches = []
    for job, company in available_jobs:
        match_score = calculate_job_match_score(candidate_id, job.id)
        if match_score > 30:  # Only show jobs with decent match
            job_matches.append({
                'job': job,
                'company': company,
                'match_score': match_score
            })
    
    # Sort by match score
    job_matches.sort(key=lambda x: x['match_score'], reverse=True)
    
    return job_matches[:10]  # Return top 10 matches

@candidate_bp.route('/candidate/dashboard')
def candidate_dashboard():
    if 'user_id' not in session or session['user_type'] != 'candidate':
        return redirect(url_for('auth.login'))

    user = User.query.get(session['user_id'])
    profile = user.candidate_profile

    # Get recent applications
    applications = db.session.query(JobApplication, JobPosting, Company).join(
        JobPosting, JobApplication.job_id == JobPosting.id
    ).join(
        Company, JobPosting.company_id == Company.id
    ).filter(
        JobApplication.candidate_id == profile.id
    ).order_by(JobApplication.applied_at.desc()).limit(5).all()

    # Get smart recommendations based on skills and experience
    recommendations = get_job_recommendations(profile.id)

    # Get notifications
    notifications = Notification.query.filter_by(
        user_id=session['user_id'], is_read=False
    ).order_by(Notification.created_at.desc()).limit(5).all()

    # Get exam invitations
    exam_invitations = db.session.query(MCQExam, JobPosting, Company).join(
        JobPosting, MCQExam.job_id == JobPosting.id
    ).join(
        Company, JobPosting.company_id == Company.id
    ).join(
        JobApplication, JobApplication.job_id == JobPosting.id
    ).filter(
        JobApplication.candidate_id == profile.id,
        MCQExam.is_active == True,
        ~MCQExam.id.in_(
            db.session.query(ExamAttempt.exam_id).filter_by(
                candidate_id=profile.id, status='completed'
            )
        )
    ).all()

    # Get total applications count
    applications_count = JobApplication.query.filter_by(candidate_id=profile.id).count()
    
    # Get upcoming interviews count
    interviews_count = db.session.query(InterviewRoom).join(
        JobApplication, InterviewRoom.job_application_id == JobApplication.id
    ).filter(
        JobApplication.candidate_id == profile.id,
        InterviewRoom.status.in_(['scheduled', 'active']),
        InterviewRoom.scheduled_time >= datetime.utcnow()
    ).count()
    
    # Get exams count
    exams_count = db.session.query(ExamAttempt).filter_by(candidate_id=profile.id).count()
    
    # Calculate profile strength (simplified calculation)
    profile_strength = 0
    if profile:
        fields = [profile.experience_years, profile.education_level, profile.current_position, 
                  profile.location, profile.summary, profile.cv_file_path]
        filled_fields = sum(1 for field in fields if field)
        profile_strength = int((filled_fields / len(fields)) * 100)
    
    # Get upcoming interviews for candidate
    upcoming_interviews = db.session.query(InterviewRoom, JobApplication, JobPosting, Company).join(
        JobApplication, InterviewRoom.job_application_id == JobApplication.id
    ).join(
        JobPosting, JobApplication.job_id == JobPosting.id
    ).join(
        Company, JobPosting.company_id == Company.id
    ).filter(
        JobApplication.candidate_id == profile.id,
        InterviewRoom.status.in_(['scheduled', 'active']),
        InterviewRoom.scheduled_time >= datetime.utcnow()
    ).order_by(InterviewRoom.scheduled_time.asc()).all()

    return render_template('candidate/candidate_dashboard.html',
                          user=user,
                          profile=profile,
                          applications=applications,
                          recommendations=recommendations,
                          notifications=notifications,
                          exam_invitations=exam_invitations,
                          upcoming_interviews=upcoming_interviews,
                          applications_count=applications_count,
                          interviews_count=interviews_count,
                          exams_count=exams_count,
                          profile_strength=profile_strength)


@candidate_bp.route('/candidate/profile', methods=['GET', 'POST'])
def candidate_profile():
    if 'user_id' not in session or session['user_type'] != 'candidate':
        return redirect(url_for('auth.login'))
    
    user = User.query.get(session['user_id'])
    profile = user.candidate_profile
    
    # Get available skills and candidate's current skills
    available_skills = Skill.query.order_by(Skill.category, Skill.skill_name).all()
    candidate_skills = db.session.query(CandidateSkill, Skill).join(Skill).filter(
        CandidateSkill.candidate_id == profile.id
    ).all()
    
    if request.method == 'POST':
        try:
            # Store old values for logging
            old_values = {
                'experience_years': profile.experience_years,
                'education_level': profile.education_level,
                'current_position': profile.current_position,
                'location': profile.location,
                'salary_expectation': float(profile.salary_expectation) if profile.salary_expectation else None,
                'summary': profile.summary
            }
            
            # Update user info
            user.first_name = request.form['first_name']
            user.last_name = request.form['last_name']
            user.phone = request.form.get('phone', '')
            
            # Update candidate profile
            profile.experience_years = int(request.form.get('experience_years', 0))
            profile.education_level = request.form.get('education_level') if request.form.get('education_level') else None
            profile.current_position = request.form.get('current_position', '')
            profile.location = request.form.get('location', '')
            profile.salary_expectation = float(request.form['salary_expectation']) if request.form.get('salary_expectation') else None
            profile.summary = request.form.get('summary', '')
            
            # Handle profile picture upload
            profile_picture = request.files.get('profile_picture')
            if profile_picture and profile_picture.filename:
                allowed_img_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
                file_ext = profile_picture.filename.rsplit('.', 1)[1].lower() if '.' in profile_picture.filename else ''
                if file_ext in allowed_img_extensions:
                    try:
                        # Save new profile picture to database as binary
                        picture_binary = profile_picture.read()
                        picture_mimetype = profile_picture.mimetype
                        
                        profile.profile_picture = picture_binary
                        profile.profile_picture_mimetype = picture_mimetype
                        flash('Profile picture updated successfully!', 'success')
                    except Exception as e:
                        flash(f'Error uploading profile picture: {str(e)}', 'warning')
                else:
                    flash('Invalid image format. Please upload PNG, JPG, JPEG, GIF, or WEBP.', 'warning')
            
            # Handle CV file upload
            cv_file = request.files.get('cv_file')
            if cv_file and cv_file.filename and allowed_file(cv_file.filename):
                try:
                    # Read file content as binary
                    file_content = cv_file.read()
                    
                    # Save CV to database
                    profile.cv_content = file_content
                    profile.cv_filename = secure_filename(cv_file.filename)
                    profile.cv_mimetype = cv_file.mimetype
                    
                    flash('CV uploaded successfully!', 'success')
                except Exception as e:
                    flash(f'Error uploading CV: {str(e)}', 'warning')
            
            # Handle skills
            selected_skills = request.form.getlist('skills[]')
            
            # Remove old skills
            CandidateSkill.query.filter_by(candidate_id=profile.id).delete()
            
            # Add new skills
            for skill_id in selected_skills:
                proficiency = request.form.get(f'proficiency_{skill_id}', 'Intermediate')
                years_exp = int(request.form.get(f'years_{skill_id}', 0))
                
                candidate_skill = CandidateSkill(
                    candidate_id=profile.id,
                    skill_id=int(skill_id),
                    proficiency_level=proficiency,
                    years_experience=years_exp
                )
                db.session.add(candidate_skill)
            
            db.session.commit()
            
            # Log activity
            new_values = {
                'experience_years': profile.experience_years,
                'education_level': profile.education_level,
                'current_position': profile.current_position,
                'location': profile.location,
                'salary_expectation': float(profile.salary_expectation) if profile.salary_expectation else None,
                'summary': profile.summary
            }
            
            log_activity('candidate_profiles', 'UPDATE', profile.id,
                        old_values=old_values, new_values=new_values, user_id=session['user_id'])
            
            # Create notification for profile update
            create_notification(session['user_id'], 'Profile Updated',
                              'Your profile has been successfully updated. Check your new job recommendations!',
                              'system', url_for('candidate.candidate_recommendations'))
            
            flash('Profile updated successfully! Check your job recommendations.', 'success')
            return redirect(url_for('candidate.candidate_recommendations'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating profile: {str(e)}', 'error')
    
    return render_template('candidate/candidate_profile_edit.html',
                         user=user,
                         profile=profile,
                         available_skills=available_skills,
                         candidate_skills=candidate_skills)



@candidate_bp.route('/candidate/applications')
def candidate_applications():
    if 'user_id' not in session or session['user_type'] != 'candidate':
        return redirect(url_for('auth.login'))
    
    user = User.query.get(session['user_id'])
    profile = user.candidate_profile
    
    # Get applications with status history
    applications = db.session.query(JobApplication, JobPosting, Company).join(
        JobPosting, JobApplication.job_id == JobPosting.id
    ).join(
        Company, JobPosting.company_id == Company.id
    ).filter(
        JobApplication.candidate_id == profile.id
    ).order_by(JobApplication.applied_at.desc()).all()
    
    # Get status history for each application
    from models import ApplicationStatusHistory
    application_histories = {}
    for app, job, company in applications:
        history = ApplicationStatusHistory.query.filter_by(
            application_id=app.id
        ).order_by(ApplicationStatusHistory.changed_at.desc()).all()
        application_histories[app.id] = history
    
    return render_template('candidate/candidate_applications.html',
                         applications=applications,
                         application_histories=application_histories,
                         user=user,
                         profile=profile)

@candidate_bp.route('/candidate/recommendations')
def candidate_recommendations():
    if 'user_id' not in session or session['user_type'] != 'candidate':
        return redirect(url_for('auth.login'))
    
    user = User.query.get(session['user_id'])
    profile = user.candidate_profile
    
    recommendations = get_job_recommendations(profile.id)
    
    return render_template('candidate/candidate_recommendations.html',
                         recommendations=recommendations,
                         user=user,
                         profile=profile)

@candidate_bp.route('/candidate/skill_analysis')
def candidate_skill_analysis():
    if 'user_id' not in session or session['user_type'] != 'candidate':
        return redirect(url_for('auth.login'))
    
    user = User.query.get(session['user_id'])
    profile = user.candidate_profile
    
    # Get candidate's skills
    candidate_skills = db.session.query(CandidateSkill, Skill).join(Skill).filter(
        CandidateSkill.candidate_id == profile.id
    ).all()
    
    # Get detailed job analysis
    recommendations = get_job_recommendations(profile.id)
    
    # Analyze skill gaps
    skill_gap_analysis = []
    for rec in recommendations[:5]:  # Top 5 recommendations
        job = rec['job']
        required_skills = db.session.query(JobRequiredSkill, Skill).join(Skill).filter(
            JobRequiredSkill.job_id == job.id
        ).all()
        
        candidate_skill_ids = [cs.skill_id for cs, _ in candidate_skills]
        missing_skills = []
        matching_skills = []
        
        for req_skill, skill in required_skills:
            if skill.id in candidate_skill_ids:
                matching_skills.append({
                    'skill': skill,
                    'importance': req_skill.importance
                })
            else:
                missing_skills.append({
                    'skill': skill,
                    'importance': req_skill.importance
                })
        
        skill_gap_analysis.append({
            'job': job,
            'company': rec['company'],
            'match_score': rec['match_score'],
            'matching_skills': matching_skills,
            'missing_skills': missing_skills
        })
    
    return render_template('candidate/candidate_skill_analysis.html',
                         skill_gap_analysis=skill_gap_analysis,
                         candidate_skills=candidate_skills,
                         user=user,
                         profile=profile)


@candidate_bp.route('/candidate/interviews')
def candidate_interviews():
    if 'user_id' not in session or session['user_type'] != 'candidate':
        return redirect(url_for('auth.login'))

    user = User.query.get(session['user_id'])
    profile = user.candidate_profile

    # Get upcoming interviews
    upcoming_interviews = db.session.query(InterviewRoom, JobApplication, JobPosting, Company).join(
        JobApplication, InterviewRoom.job_application_id == JobApplication.id
    ).join(
        JobPosting, JobApplication.job_id == JobPosting.id
    ).join(
        Company, JobPosting.company_id == Company.id
    ).filter(
        JobApplication.candidate_id == profile.id,
        InterviewRoom.status.in_(['scheduled', 'active']),
        InterviewRoom.scheduled_time >= datetime.utcnow()
    ).order_by(InterviewRoom.scheduled_time.asc()).all()

    # Get past interviews
    past_interviews = db.session.query(InterviewRoom, JobApplication, JobPosting, Company).join(
        JobApplication, InterviewRoom.job_application_id == JobApplication.id
    ).join(
        JobPosting, JobApplication.job_id == JobPosting.id
    ).join(
        Company, JobPosting.company_id == Company.id
    ).filter(
        JobApplication.candidate_id == profile.id,
        InterviewRoom.status == 'completed'
    ).order_by(InterviewRoom.ended_at.desc()).limit(10).all()

    return render_template('candidate/candidate_interviews.html',
                          user=user,
                          profile=profile,
                          upcoming_interviews=upcoming_interviews,
                          past_interviews=past_interviews)


@candidate_bp.route('/candidate/profile_picture/<int:candidate_id>')
def get_profile_picture(candidate_id):
    """Serve candidate profile picture from database"""
    profile = CandidateProfile.query.get_or_404(candidate_id)
    
    if not profile.profile_picture:
        # Return default avatar if no picture
        default_svg = '''<svg width="200" height="200" xmlns="http://www.w3.org/2000/svg">
            <circle cx="100" cy="100" r="100" fill="#E5E7EB"/>
            <g fill="#9CA3AF">
                <circle cx="100" cy="75" r="30"/>
                <path d="M 100 105 Q 60 105 40 145 L 160 145 Q 140 105 100 105 Z"/>
            </g>
        </svg>'''
        return default_svg, 200, {'Content-Type': 'image/svg+xml'}
    
    # Return the image from database
    return send_file(
        io.BytesIO(profile.profile_picture),
        mimetype=profile.profile_picture_mimetype,
        as_attachment=False
    )
