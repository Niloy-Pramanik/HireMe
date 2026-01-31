from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from extensions import db
from models import (
    User, ActivityLog, Notification, InterviewRoom, InterviewParticipant, 
    InterviewFeedback, CodeSession, InterviewerRecommendation,
    JobApplication, JobPosting, Company, CandidateProfile,
    InterviewerEarning, InterviewerProfile
)
from datetime import datetime
import json
import time

bp = Blueprint('interview', __name__)

# --- INTERVIEW ROOM ROUTES ---

@bp.route('/interview/<room_code>')
def join_interview(room_code):
    """Join interview room - simplified approach"""
    try:
        # Get interview room from database using existing models
        room = InterviewRoom.query.filter_by(room_code=room_code).first_or_404()
        
        # Check if user is authorized to join
        if 'user_id' not in session:
            return redirect(url_for('auth.login'))
        
        participant = InterviewParticipant.query.filter_by(
            room_id=room.id,
            user_id=session['user_id']
        ).first()
        
        if not participant:
            flash('You are not authorized to join this interview', 'error')
            return redirect(url_for('main.index'))
        
        # Get all participants with user info
        participants = db.session.query(InterviewParticipant, User).join(User).filter(
            InterviewParticipant.room_id == room.id
        ).all()
        
        # Get current user
        current_user = User.query.get(session['user_id'])
        
        # Get job and company info from application
        job = room.application.job
        company = job.company
        
        # Get candidate info
        candidate = room.application.candidate
        candidate_user = candidate.user
        candidate_name = f"{candidate_user.first_name} {candidate_user.last_name}"
        
        # Get interviewer names (all interviewers in this room)
        interviewer_names = []
        for p, u in participants:
            if p.role == 'interviewer':
                interviewer_names.append(f"{u.first_name} {u.last_name}")
        interviewer_name = ", ".join(interviewer_names) if interviewer_names else "Interviewer"
        
        # Update room status if interview is starting
        if room.status == 'scheduled':
            room.status = 'active'
            room.started_at = datetime.utcnow()
            participant.joined_at = datetime.utcnow()
            participant.is_active = True
            db.session.commit()
        
        return render_template('interviewer/interview_room.html', 
                             room=room,
                             interview=room,  # Alias for template compatibility
                             job=job,
                             company=company,
                             candidate_name=candidate_name,
                             interviewer_name=interviewer_name,
                             participants=participants,
                             current_user=current_user,
                             current_user_role=participant.role,
                             interview_questions=[]  # TODO: Add preset questions feature
                            )
        
    except Exception as e:
        flash(f'Error loading interview room: {e}', 'error')
        return redirect(url_for('main.index'))

@bp.route('/interview/<room_code>/feedback', methods=['GET', 'POST'])
def interview_feedback(room_code):
    if 'user_id' not in session or session['user_type'] != 'interviewer':
        return redirect(url_for('auth.login'))
        
    room = InterviewRoom.query.filter_by(room_code=room_code).first_or_404()
    
    # Verify this interviewer was part of this interview
    participant = InterviewParticipant.query.filter_by(
        room_id=room.id,
        user_id=session['user_id'],
        role='interviewer'
    ).first()
    
    if not participant:
        flash('You are not authorized to submit feedback for this interview', 'error')
        return redirect(url_for('interviewer.interviewer_dashboard'))
    
    # Check if feedback already submitted
    existing_feedback = InterviewFeedback.query.filter_by(
        room_id=room.id,
        interviewer_id=session['user_id']
    ).first()
    
    if existing_feedback:
        flash('You have already submitted feedback for this interview', 'info')
        return redirect(url_for('interviewer.interviewer_dashboard'))
    
    # Get job and candidate info
    job = room.application.job
    company = job.company
    candidate = room.application.candidate
    candidate_user = candidate.user
    candidate_name = f"{candidate_user.first_name} {candidate_user.last_name}"
    
    # Skill categories for assessment
    skill_categories = {
        'Technical Skills': ['Problem Solving', 'Code Quality', 'System Design', 'Technical Knowledge'],
        'Soft Skills': ['Communication', 'Teamwork', 'Adaptability', 'Critical Thinking']
    }
    
    if request.method == 'POST':
        try:
            # Get scores
            technical_score = int(request.form.get('technical_score', 0) or 0)
            communication_score = int(request.form.get('communication_score', 0) or 0)
            problem_solving_score = int(request.form.get('problem_solving_score', 0) or 0)
            
            # Map overall_rating from number to enum value
            rating_num = int(request.form.get('overall_rating', 3) or 3)
            rating_map = {1: 'poor', 2: 'average', 3: 'average', 4: 'good', 5: 'excellent'}
            overall_rating = rating_map.get(rating_num, 'average')
            
            # Get recommendation
            recommendation = request.form.get('recommendation', '')
            rec_map = {'strong_yes': 'hire', 'yes': 'hire', 'no': 'reject', 'strong_no': 'reject'}
            recommendation_enum = rec_map.get(recommendation, 'maybe')
            
            # Compile feedback text from various fields
            strengths = request.form.get('strengths', '')
            improvements = request.form.get('improvements', '')
            technical_notes = request.form.get('technical_notes', '')
            additional_comments = request.form.get('additional_comments', '')
            recommendation_reason = request.form.get('recommendation_reason', '')
            
            feedback_text = f"""
Strengths: {strengths}

Areas for Improvement: {improvements}

Technical Notes: {technical_notes}

Additional Comments: {additional_comments}

Recommendation Reason: {recommendation_reason}
            """.strip()
            
            feedback = InterviewFeedback(
                room_id=room.id,
                interviewer_id=session['user_id'],
                candidate_id=candidate_user.id,
                technical_score=technical_score,
                communication_score=communication_score,
                problem_solving_score=problem_solving_score,
                overall_rating=overall_rating,
                feedback_text=feedback_text,
                recommendation=recommendation_enum
            )
            db.session.add(feedback)
            
            # Update interview room status if not already completed
            if room.status != 'completed':
                room.status = 'completed'
                room.ended_at = datetime.utcnow()
                
                # Calculate interview duration and create earnings for all interviewers
                if room.started_at:
                    duration_minutes = int((room.ended_at - room.started_at).total_seconds() / 60)
                    
                    # Get all interviewers who participated
                    interviewer_participants = InterviewParticipant.query.filter_by(
                        room_id=room.id,
                        role='interviewer'
                    ).all()
                    
                    for interviewer_participant in interviewer_participants:
                        # Get interviewer profile
                        interviewer_profile = InterviewerProfile.query.filter_by(
                            user_id=interviewer_participant.user_id
                        ).first()
                        
                        if interviewer_profile and interviewer_profile.hourly_rate:
                            # Calculate earnings based on duration and hourly rate
                            hourly_rate = float(interviewer_profile.hourly_rate)
                            amount_earned = (duration_minutes / 60.0) * hourly_rate
                            
                            # Create earnings record
                            earning = InterviewerEarning(
                                interviewer_id=interviewer_profile.id,
                                interview_room_id=room.id,
                                duration_minutes=duration_minutes,
                                hourly_rate=hourly_rate,
                                amount_earned=amount_earned,
                                currency='BDT',
                                status='pending'
                            )
                            db.session.add(earning)
                            
                            # Update interviewer's total interviews count
                            interviewer_profile.total_interviews = (interviewer_profile.total_interviews or 0) + 1
            
            db.session.commit()
            
            # Notify employer about submitted feedback
            create_notification(
                room.application.job.company.user_id,
                'Interview Feedback Submitted',
                f'Feedback has been submitted for {candidate_name}\'s interview for {job.title}.',
                'system',
                url_for('employer.employer_view_application', application_id=room.application.id)
            )
            
            flash('Feedback submitted successfully!', 'success')
            return redirect(url_for('interviewer.interviewer_dashboard'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error submitting feedback: {str(e)}', 'error')
        
    return render_template('interviewer/interview_feedback.html', 
                          room=room,
                          interview=room,
                          job=job,
                          company=company,
                          candidate_name=candidate_name,
                          skill_categories=skill_categories)

@bp.route('/interview/<room_code>/code-editor')
def code_editor(room_code):
    """Code editor for interview room - opens in separate tab"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
        
    try:
        # Get interview room from database
        room = InterviewRoom.query.filter_by(room_code=room_code).first_or_404()
        
        # Check if user is authorized to join
        participant = InterviewParticipant.query.filter_by(
            room_id=room.id,
            user_id=session['user_id']
        ).first()
        
        if not participant:
            flash('You are not authorized to access this code editor', 'error')
            return redirect(url_for('main.index'))
        
        # Get all participants for context
        participants = db.session.query(InterviewParticipant, User).join(User).filter(
            InterviewParticipant.room_id == room.id
        ).all()
        
        return render_template('interviewer/code_editor.html', 
                             room=room, 
                             participants=participants,
                             current_user_role=participant.role)
        
    except Exception as e:
        flash(f'Error loading code editor: {e}', 'error')
        return redirect(url_for('main.index'))

# --- API ENDPOINTS ---

@bp.route('/api/execute_code', methods=['POST'])
def api_execute_code():
    """API endpoint for code execution in interview rooms"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
        
    data = request.get_json()
    code = data.get('code', '')
    language = data.get('language', 'javascript')
    
    if not code:
        return jsonify({'error': 'No code provided'}), 400
        
    try:
        start_time = time.time()
        output = execute_code(code, language)
        execution_time = time.time() - start_time
        
        return jsonify({
            'output': output,
            'execution_time': round(execution_time, 3),
            'language': language
        })
    except Exception as e:
        return jsonify({'error': f'Execution failed: {str(e)}'}), 500

# --- ADMIN/MANAGER INTERVIEW MANAGEMENT ROUTES ---

@bp.route('/admin/interviewers', methods=['GET', 'POST'])
def manage_interviewers():
    if 'user_id' not in session or session['user_type'] not in ['admin', 'manager']:
        return redirect(url_for('auth.login'))
        
    if request.method == 'POST':
        # Add new interviewer
        from werkzeug.security import generate_password_hash
        
        email = request.form['email']
        password = request.form['password']
        first_name = request.form['first_name']
        last_name = request.form['last_name']
        phone = request.form.get('phone', '')
        
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            flash('Email already exists', 'error')
        else:
            password_hash = generate_password_hash(password)
            new_interviewer = User(
                email=email,
                password_hash=password_hash,
                user_type='interviewer',
                first_name=first_name,
                last_name=last_name,
                phone=phone
            )
            db.session.add(new_interviewer)
            db.session.commit()
            flash('Interviewer added successfully', 'success')
            
    interviewers = User.query.filter_by(user_type='interviewer').all()
    return render_template('admin/manage_interviewers.html', interviewers=interviewers)

@bp.route('/admin/schedule_interview/<int:application_id>', methods=['GET', 'POST'])
def schedule_interview(application_id):
    if 'user_id' not in session or session['user_type'] not in ['admin', 'manager']:
        return redirect(url_for('auth.login'))

    application = JobApplication.query.get_or_404(application_id)

    if request.method == 'POST':
        try:
            # Parse datetime without any time restrictions
            scheduled_time_str = request.form['scheduled_time']
            scheduled_time = datetime.strptime(scheduled_time_str, '%Y-%m-%dT%H:%M')

            # Generate unique room code
            room_code = f"INT{application_id}{int(datetime.now().timestamp())}"

            # Create interview room with any datetime
            interview_room = InterviewRoom(
                room_name=f"Interview - {application.job.title}",
                room_code=room_code,
                job_application_id=application_id,
                scheduled_time=scheduled_time,
                duration_minutes=int(request.form.get('duration_minutes', 60)),
                created_by=session['user_id']
            )

            db.session.add(interview_room)
            db.session.flush()

            # Add candidate as participant
            candidate_participant = InterviewParticipant(
                room_id=interview_room.id,
                user_id=application.candidate.user_id,
                role='candidate'
            )
            db.session.add(candidate_participant)

            # Add selected interviewers
            interviewer_ids = request.form.getlist('interviewer_ids[]')
            for interviewer_id in interviewer_ids:
                interviewer_participant = InterviewParticipant(
                    room_id=interview_room.id,
                    user_id=int(interviewer_id),
                    role='interviewer'
                )
                db.session.add(interviewer_participant)

            # UPDATE RECOMMENDATION STATUS
            # Mark selected recommendations as 'accepted' and non-selected as 'not_selected'
            recommendations = InterviewerRecommendation.query.filter_by(
                application_id=application_id, 
                status='pending'
            ).all()

            for rec in recommendations:
                if str(rec.interviewer_id) in interviewer_ids:
                    rec.status = 'accepted'
                else:
                    rec.status = 'not_selected'

            db.session.commit()

            # Send notifications
            create_notification(
                application.candidate.user_id,
                'Interview Scheduled',
                f'Your interview for {application.job.title} has been scheduled for {scheduled_time.strftime("%B %d, %Y at %I:%M %p")}',
                'system',
                url_for('interview.join_interview', room_code=room_code)
            )

            for interviewer_id in interviewer_ids:
                create_notification(
                    int(interviewer_id),
                    'Interview Assignment',
                    f'You have been assigned to interview for {application.job.title} on {scheduled_time.strftime("%B %d, %Y at %I:%M %p")}',
                    'system',
                    url_for('interview.join_interview', room_code=room_code)
                )

            flash('Interview scheduled successfully for 24/7 availability!', 'success')
            return redirect(url_for('admin.admin_dashboard'))

        except ValueError as e:
            flash('Invalid date/time format. Please try again.', 'error')
        except Exception as e:
            db.session.rollback()
            flash(f'Error scheduling interview: {str(e)}', 'error')

    # GET REQUEST: Fetch data for the template
    interviewers = User.query.filter_by(user_type='interviewer').all()
    
    # FETCH RECOMMENDATIONS FOR THIS APPLICATION
    recommended_interviewers = db.session.query(InterviewerRecommendation).join(
        User, InterviewerRecommendation.interviewer_id == User.id
    ).filter(
        InterviewerRecommendation.application_id == application_id,
        InterviewerRecommendation.status == 'pending'
    ).all()

    return render_template('admin/schedule_interview.html',
                         application=application,
                         interviewers=interviewers,
                         recommended_interviewers=recommended_interviewers)

@bp.route('/admin/edit_interview/<int:interview_id>', methods=['GET', 'POST'])
def edit_interview(interview_id):
    if 'user_id' not in session or session['user_type'] not in ['admin', 'manager']:
        return redirect(url_for('auth.login'))

    interview_room = InterviewRoom.query.get_or_404(interview_id)
    
    # Get all participants for this interview
    participants = db.session.query(InterviewParticipant, User).join(User).filter(
        InterviewParticipant.room_id == interview_room.id
    ).all()
    
    if request.method == 'POST':
        try:
            # Parse the updated datetime
            scheduled_time_str = request.form['scheduled_time']
            scheduled_time = datetime.strptime(scheduled_time_str, '%Y-%m-%dT%H:%M')
            
            # Store old values for logging
            old_values = {
                'scheduled_time': interview_room.scheduled_time.isoformat(),
                'duration_minutes': interview_room.duration_minutes,
                'status': interview_room.status
            }
            
            # Update interview room details - NO TIME RESTRICTIONS for 24/7 scheduling
            interview_room.scheduled_time = scheduled_time
            interview_room.duration_minutes = int(request.form.get('duration_minutes', 60))
            interview_room.status = request.form.get('status', 'scheduled')
            
            # Handle interviewer updates
            new_interviewer_ids = request.form.getlist('interviewer_ids[]')
            
            # Remove existing interviewers (keep candidate)
            InterviewParticipant.query.filter_by(
                room_id=interview_room.id,
                role='interviewer'
            ).delete()
            
            # Add new interviewers
            for interviewer_id in new_interviewer_ids:
                interviewer_participant = InterviewParticipant(
                    room_id=interview_room.id,
                    user_id=int(interviewer_id),
                    role='interviewer'
                )
                db.session.add(interviewer_participant)
            
            db.session.commit()
            
            # Log activity
            new_values = {
                'scheduled_time': interview_room.scheduled_time.isoformat(),
                'duration_minutes': interview_room.duration_minutes,
                'status': interview_room.status
            }
            
            log_activity('interview_rooms', 'UPDATE', interview_room.id,
                        old_values=old_values, new_values=new_values, 
                        user_id=session['user_id'])
            
            # Send update notifications to all participants
            candidate_participant = next((p for p, u in participants if p.role == 'candidate'), None)
            if candidate_participant:
                create_notification(
                    candidate_participant.user_id,
                    'Interview Updated',
                    f'Your interview for {interview_room.application.job.title} has been rescheduled to {scheduled_time.strftime("%B %d, %Y at %I:%M %p")}',
                    'system',
                    url_for('interview.join_interview', room_code=interview_room.room_code)
                )
            
            # Notify new interviewers
            for interviewer_id in new_interviewer_ids:
                create_notification(
                    int(interviewer_id),
                    'Interview Updated',
                    f'Interview assignment updated for {interview_room.application.job.title} - {scheduled_time.strftime("%B %d, %Y at %I:%M %p")}',
                    'system',
                    url_for('interview.join_interview', room_code=interview_room.room_code)
                )
            
            flash('Interview updated successfully!', 'success')
            return redirect(url_for('interview.manage_interviews'))
            
        except ValueError as e:
            flash('Invalid date/time format. Please try again.', 'error')
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating interview: {str(e)}', 'error')
    
    # Get all interviewers for selection
    all_interviewers = User.query.filter_by(user_type='interviewer').all()
    
    # Get current interviewer IDs
    current_interviewer_ids = [p.user_id for p, u in participants if p.role == 'interviewer']
    
    return render_template('admin/edit_interview.html',
                          interview_room=interview_room,
                          participants=participants,
                          all_interviewers=all_interviewers,
                          current_interviewer_ids=current_interviewer_ids)

@bp.route('/admin/delete_interview/<int:interview_id>', methods=['POST'])
def delete_interview(interview_id):
    if 'user_id' not in session or session['user_type'] not in ['admin', 'manager']:
        return redirect(url_for('auth.login'))

    interview_room = InterviewRoom.query.get_or_404(interview_id)
    
    # Check if interview can be deleted (only if not completed)
    if interview_room.status == 'completed':
        flash('Cannot delete completed interviews. Contact system administrator.', 'error')
        return redirect(url_for('interview.manage_interviews'))
    
    try:
        # Get participants before deletion for notifications
        participants = db.session.query(InterviewParticipant, User).join(User).filter(
            InterviewParticipant.room_id == interview_room.id
        ).all()
        
        job_title = interview_room.application.job.title
        room_code = interview_room.room_code
        
        # Delete related records in correct order
        # 1. Delete interview feedback (if any)
        InterviewFeedback.query.filter_by(room_id=interview_room.id).delete()
        
        # 2. Delete code sessions (if any)
        CodeSession.query.filter_by(room_id=interview_room.id).delete()
        
        # 3. Delete interview participants
        InterviewParticipant.query.filter_by(room_id=interview_room.id).delete()
        
        # 4. Delete the interview room
        db.session.delete(interview_room)
        
        # Log activity before committing
        log_activity('interview_rooms', 'DELETE', interview_id,
                    old_values={'room_code': room_code, 'job_title': job_title},
                    user_id=session['user_id'])
        
        db.session.commit()
        
        # Notify all participants about cancellation
        for participant, user in participants:
            create_notification(
                participant.user_id,
                'Interview Cancelled',
                f'The interview for {job_title} scheduled in room {room_code} has been cancelled.',
                'system'
            )
        
        flash('Interview deleted successfully and participants notified.', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting interview: {str(e)}', 'error')
    
    return redirect(url_for('interview.manage_interviews'))

@bp.route('/admin/manage_interviews')
def manage_interviews():
    if 'user_id' not in session or session['user_type'] not in ['admin', 'manager']:
        return redirect(url_for('auth.login'))
    
    # Get all interviews with related data
    page = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', '')
    
    query = db.session.query(
        InterviewRoom, JobApplication, JobPosting, Company, CandidateProfile, User
    ).join(
        JobApplication, InterviewRoom.job_application_id == JobApplication.id
    ).join(
        JobPosting, JobApplication.job_id == JobPosting.id
    ).join(
        Company, JobPosting.company_id == Company.id
    ).join(
        CandidateProfile, JobApplication.candidate_id == CandidateProfile.id
    ).join(
        User, CandidateProfile.user_id == User.id
    )
    
    if status_filter:
        query = query.filter(InterviewRoom.status == status_filter)
    
    interviews = query.order_by(InterviewRoom.scheduled_time.desc()).paginate(
        page=page, per_page=20, error_out=False
    )
    
    return render_template('admin/manage_interviews.html',
                          interviews=interviews,
                          status_filter=status_filter)

@bp.route('/admin/cancel_interview/<int:interview_id>', methods=['POST'])
def cancel_interview(interview_id):
    if 'user_id' not in session or session['user_type'] not in ['admin', 'manager']:
        return redirect(url_for('auth.login'))

    interview_room = InterviewRoom.query.get_or_404(interview_id)
    
    if interview_room.status == 'completed':
        flash('Cannot cancel completed interviews.', 'error')
        return redirect(url_for('interview.manage_interviews'))
    
    try:
        # Get participants for notifications
        participants = db.session.query(InterviewParticipant, User).join(User).filter(
            InterviewParticipant.room_id == interview_room.id
        ).all()
        
        # Update status to cancelled
        old_status = interview_room.status
        interview_room.status = 'cancelled'
        
        # Log activity
        log_activity('interview_rooms', 'UPDATE', interview_room.id,
                    old_values={'status': old_status},
                    new_values={'status': 'cancelled'},
                    user_id=session['user_id'])
        
        db.session.commit()
        
        # Notify participants
        job_title = interview_room.application.job.title
        for participant, user in participants:
            create_notification(
                participant.user_id,
                'Interview Cancelled',
                f'The interview for {job_title} has been cancelled. You will be notified if it gets rescheduled.',
                'system'
            )
        
        flash('Interview cancelled successfully and participants notified.', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error cancelling interview: {str(e)}', 'error')
    
    return redirect(url_for('interview.manage_interviews'))

# --- HELPER FUNCTIONS ---

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

# --- CODE EXECUTION FUNCTIONS ---

import requests
import subprocess

ONLINE_EXECUTION_ENABLED = True
PISTON_API_URL = "https://emkc.org/api/v2/piston"

PISTON_LANGUAGE_MAP = {
    'javascript': {'language': 'javascript', 'version': '*'},
    'python': {'language': 'python', 'version': '*'},
    'java': {'language': 'java', 'version': '*'},
    'cpp': {'language': 'cpp', 'version': '*'},
    'c': {'language': 'c', 'version': '*'},
    'csharp': {'language': 'csharp', 'version': '*'},
    'php': {'language': 'php', 'version': '*'},
    'ruby': {'language': 'ruby', 'version': '*'},
    'rust': {'language': 'rust', 'version': '*'},
    'swift': {'language': 'swift', 'version': '*'},
}

def execute_code_online(code, language):
    """Execute code using the Piston API"""
    try:
        if not ONLINE_EXECUTION_ENABLED:
            return "Online code execution is disabled."
            
        language_info = PISTON_LANGUAGE_MAP.get(language)
        if not language_info:
            return f"Language '{language}' is not supported."
            
        # Get available runtimes
        runtimes_response = requests.get(f"{PISTON_API_URL}/runtimes")
        if runtimes_response.status_code != 200:
            return "API Error: Failed to get available runtimes"
            
        runtimes = runtimes_response.json()
        
        # Find the latest version
        lang_name = language_info['language']
        version = None
        for runtime in runtimes:
            if runtime['language'] == lang_name:
                version = runtime['version']
                break
                
        if not version:
            return f"Language '{language}' is not available."
            
        # Execute code
        payload = {
            "language": lang_name,
            "version": version,
            "files": [{"content": code}],
            "stdin": "",
            "args": [],
            "compile_timeout": 10000,
            "run_timeout": 3000,
            "compile_memory_limit": -1,
            "run_memory_limit": -1
        }
        
        response = requests.post(f"{PISTON_API_URL}/execute", json=payload)
        if response.status_code != 200:
            return f"API Error: {response.text}"
            
        result = response.json()
        
        # Check for compilation errors
        if 'compile' in result and result['compile']['code'] != 0:
            return f"Compilation Error: {result['compile']['stderr']}"
            
        # Get run results
        run_result = result.get('run', {})
        stdout = run_result.get('stdout', '')
        stderr = run_result.get('stderr', '')
        exit_code = run_result.get('code', 0)
        
        if exit_code == 0:
            return stdout
        else:
            return f"Execution Error (code {exit_code}): {stderr}"
            
    except Exception as e:
        return f"Online execution error: {str(e)}"

def execute_code(code, language):
    """Execute code via online Piston API only."""
    return execute_code_online(code, language)
