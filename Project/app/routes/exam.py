from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from datetime import datetime

from extensions import db
from models import User, CandidateProfile, JobPosting, JobApplication, MCQExam, MCQQuestion, ExamAttempt, CandidateAnswer, Company

bp = Blueprint('exam', __name__, url_prefix='/exam')


@bp.route('/<int:exam_id>')
def take_exam(exam_id):
    if 'user_id' not in session or session['user_type'] != 'candidate':
        return redirect(url_for('auth.login'))
    
    user = User.query.get(session['user_id'])
    profile = user.candidate_profile
    
    exam = MCQExam.query.get_or_404(exam_id)
    
    # Check if already completed
    existing_attempt = ExamAttempt.query.filter_by(
        candidate_id=profile.id, exam_id=exam_id, status='completed'
    ).first()
    
    if existing_attempt:
        flash('You have already completed this exam', 'info')
        return redirect(url_for('exam.exam_result', attempt_id=existing_attempt.id))
    
    # Get or create in-progress attempt
    attempt = ExamAttempt.query.filter_by(
        candidate_id=profile.id, exam_id=exam_id, status='in_progress'
    ).first()
    
    if not attempt:
        attempt = ExamAttempt(
            candidate_id=profile.id,
            exam_id=exam_id,
            total_questions=exam.total_questions
        )
        db.session.add(attempt)
        db.session.commit()
    
    # Get questions
    questions = MCQQuestion.query.filter_by(exam_id=exam_id).all()
    
    # Get job and company info
    job = JobPosting.query.get(exam.job_id)
    company = job.company if job else None
    
    # Get already answered questions
    answered = db.session.query(CandidateAnswer.question_id).filter_by(
        attempt_id=attempt.id
    ).all()
    answered_ids = [q[0] for q in answered]
    
    return render_template('exam/take_exam.html',
                         exam=exam,
                         attempt=attempt,
                         questions=questions,
                         answered_ids=answered_ids,
                         job=job,
                         company=company)


@bp.route('/submit/<int:attempt_id>', methods=['POST'])
def submit_exam(attempt_id):
    if 'user_id' not in session or session['user_type'] != 'candidate':
        return redirect(url_for('auth.login'))
    
    attempt = ExamAttempt.query.get_or_404(attempt_id)
    
    if attempt.status == 'completed':
        flash('Exam already submitted', 'info')
        return redirect(url_for('exam.exam_result', attempt_id=attempt_id))
    
    try:
        # Process answers
        questions = MCQQuestion.query.filter_by(exam_id=attempt.exam_id).all()
        correct_answers = 0
        
        for question in questions:
            selected_answer = request.form.get(f'q{question.id}')
            if selected_answer:
                is_correct = selected_answer == question.correct_answer
                if is_correct:
                    correct_answers += 1
                
                # Save answer
                answer = CandidateAnswer(
                    attempt_id=attempt.id,
                    question_id=question.id,
                    selected_answer=selected_answer,
                    is_correct=is_correct
                )
                db.session.add(answer)
        
        # Calculate score
        score = (correct_answers / len(questions)) * 100 if questions else 0
        
        # Update attempt
        attempt.completed_at = datetime.utcnow()
        attempt.status = 'completed'
        attempt.correct_answers = correct_answers
        attempt.score = score
        attempt.time_spent = (datetime.utcnow() - attempt.started_at).total_seconds()
        
        # Get exam to find job_id
        exam = MCQExam.query.get(attempt.exam_id)
        
        # Update job application with exam score
        application = JobApplication.query.filter_by(
            candidate_id=attempt.candidate_id
        ).join(JobPosting).filter(
            JobPosting.id == exam.job_id
        ).first()
        
        if application:
            application.exam_score = score
        
        db.session.commit()
        
        flash('Exam submitted successfully!', 'success')
        return redirect(url_for('exam.exam_result', attempt_id=attempt_id))
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error submitting exam: {str(e)}', 'error')
        return redirect(url_for('exam.take_exam', exam_id=attempt.exam_id))


@bp.route('/result/<int:attempt_id>')
def exam_result(attempt_id):
    if 'user_id' not in session or session['user_type'] != 'candidate':
        return redirect(url_for('auth.login'))
    
    attempt = ExamAttempt.query.get_or_404(attempt_id)
    exam = MCQExam.query.get(attempt.exam_id)
    
    # Get job and company info
    job = JobPosting.query.get(exam.job_id)
    company = job.company if job else None
    
    # Calculate if passed
    passed = attempt.score >= exam.passing_score
    
    # Get detailed results
    answers = db.session.query(CandidateAnswer, MCQQuestion).join(MCQQuestion).filter(
        CandidateAnswer.attempt_id == attempt_id
    ).all()
    
    return render_template('exam/exam_result.html',
                         attempt=attempt,
                         exam=exam,
                         job=job,
                         company=company,
                         passed=passed,
                         score=attempt.score,
                         correct_count=attempt.correct_answers,
                         total_questions=attempt.total_questions,
                         answers=answers)
