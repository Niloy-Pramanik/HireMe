from extensions import db
from datetime import datetime

class Notification(db.Model):
    __tablename__ = 'notifications'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    message = db.Column(db.Text, nullable=False)
    notification_type = db.Column(db.Enum('application', 'message', 'exam', 'job_match', 'system', 'interview'), default='system')
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    action_url = db.Column(db.String(500))
    
    # Calendar event fields
    event_datetime = db.Column(db.DateTime)  # Event date/time for interviews
    event_title = db.Column(db.String(255))  # Event title (e.g., "Interview at TechCorp")
    can_add_to_calendar = db.Column(db.Boolean, default=False)  # Whether user can add to calendar
    room_code = db.Column(db.String(50))  # Interview room code for calendar events

