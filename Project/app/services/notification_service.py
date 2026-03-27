from extensions import db
from models import Notification, ActivityLog
from datetime import datetime
import json

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


def create_interview_notification(user_id, title, message, event_datetime, event_title, room_code=None):
    """
    Create an interview notification with calendar event option
    
    Args:
        user_id: User ID to notify
        title: Notification title
        message: Notification message
        event_datetime: datetime object of the interview
        event_title: Title for the calendar event
        room_code: Interview room code (optional)
    """
    notification = Notification(
        user_id=user_id,
        title=title,
        message=message,
        notification_type='interview',
        event_datetime=event_datetime,
        event_title=event_title,
        can_add_to_calendar=True,
        room_code=room_code,
        action_url=f"/interview/{room_code}" if room_code else None
    )
    db.session.add(notification)
    db.session.commit()
    return notification


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

