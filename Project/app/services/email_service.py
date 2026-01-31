from flask import render_template, current_app
from flask_mail import Message
from extensions import mail
from threading import Thread
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


def send_async_email(app, msg):
    """Send email asynchronously"""
    with app.app_context():
        try:
            mail.send(msg)
        except Exception as e:
            print(f"Error sending email: {str(e)}")


def send_email(subject, recipients, text_body, html_body):
    """Send email with both text and HTML versions"""
    # Create message with proper encoding
    msg = Message(
        subject=subject,
        recipients=recipients,
        sender=current_app.config['MAIL_DEFAULT_SENDER']
    )
    
    # Ensure UTF-8 encoding for both text and HTML parts
    msg.body = text_body
    msg.html = html_body
    
    # Send email asynchronously to avoid blocking
    app = current_app._get_current_object()
    Thread(target=send_async_email, args=(app, msg)).start()


def send_application_confirmation_email(candidate, job, company, has_exam=False):
    """
    Send application confirmation email to candidate
    
    Args:
        candidate: CandidateProfile object
        job: JobPosting object
        company: Company object
        has_exam: Boolean indicating if job has MCQ exam
    """
    user_email = candidate.user.email
    candidate_name = f"{candidate.user.first_name} {candidate.user.last_name}"
    
    subject = f"Application Received - {job.title} at {company.company_name}"
    
    # Render email templates
    text_body = render_template('emails/application_confirmation.txt',
                                candidate_name=candidate_name,
                                job_title=job.title,
                                company_name=company.company_name,
                                has_exam=has_exam)
    
    html_body = render_template('emails/application_confirmation.html',
                                candidate_name=candidate_name,
                                job_title=job.title,
                                company_name=company.company_name,
                                has_exam=has_exam)
    
    send_email(subject, [user_email], text_body, html_body)


def send_interview_scheduled_email(candidate, job, company, interview_room):
    """
    Send interview scheduled email to candidate
    
    Args:
        candidate: CandidateProfile object
        job: JobPosting object
        company: Company object
        interview_room: InterviewRoom object
    """
    user_email = candidate.user.email
    candidate_name = f"{candidate.user.first_name} {candidate.user.last_name}"
    
    subject = f"Interview Scheduled - {job.title} at {company.company_name}"
    
    # Render email templates
    text_body = render_template('emails/interview_scheduled.txt',
                                candidate_name=candidate_name,
                                job_title=job.title,
                                company_name=company.company_name,
                                interview_date=interview_room.scheduled_time.strftime('%B %d, %Y'),
                                interview_time=interview_room.scheduled_time.strftime('%I:%M %p'),
                                interview_duration=interview_room.duration_minutes,
                                room_code=interview_room.room_code)
    
    html_body = render_template('emails/interview_scheduled.html',
                                candidate_name=candidate_name,
                                job_title=job.title,
                                company_name=company.company_name,
                                interview_date=interview_room.scheduled_time.strftime('%B %d, %Y'),
                                interview_time=interview_room.scheduled_time.strftime('%I:%M %p'),
                                interview_duration=interview_room.duration_minutes,
                                room_code=interview_room.room_code)
    
    send_email(subject, [user_email], text_body, html_body)


def send_exam_reminder_email(candidate, job, company, exam):
    """
    Send exam reminder email to candidate
    
    Args:
        candidate: CandidateProfile object
        job: JobPosting object
        company: Company object
        exam: MCQExam object
    """
    user_email = candidate.user.email
    candidate_name = f"{candidate.user.first_name} {candidate.user.last_name}"
    
    subject = f"Complete Your Assessment - {job.title} at {company.company_name}"
    
    # Render email templates
    text_body = render_template('emails/exam_reminder.txt',
                                candidate_name=candidate_name,
                                job_title=job.title,
                                company_name=company.company_name,
                                exam_title=exam.exam_title,
                                exam_duration=exam.duration_minutes)
    
    html_body = render_template('emails/exam_reminder.html',
                                candidate_name=candidate_name,
                                job_title=job.title,
                                company_name=company.company_name,
                                exam_title=exam.exam_title,
                                exam_duration=exam.duration_minutes)
    
    send_email(subject, [user_email], text_body, html_body)
