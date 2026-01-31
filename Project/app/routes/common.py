from flask import Blueprint, render_template, request, redirect, url_for, flash, session, send_file
from extensions import db
from models import User, Notification, CandidateProfile
from datetime import datetime, timedelta
from sqlalchemy import func, or_
import io

bp = Blueprint('common', __name__)

# --- NOTIFICATIONS ROUTES ---

@bp.route('/notifications')
def notifications():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    # --- filtering & pagination -------------------------------
    page        = request.args.get('page', 1, type=int)
    base_q      = Notification.query.filter_by(user_id=session['user_id'])
    if request.args.get('filter') == 'unread':
        base_q = base_q.filter_by(is_read=False)
    if request.args.get('type'):
        base_q = base_q.filter_by(notification_type=request.args['type'])

    notifications_data = base_q.order_by(Notification.created_at.desc()) \
                          .paginate(page=page, per_page=20, error_out=False)

    # --- date cut-offs that the template will use --------------
    now            = datetime.utcnow()
    today_start    = now.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_start= today_start - timedelta(days=1)
    week_ago       = today_start - timedelta(days=7)

    return render_template(
        'common/notifications.html',
        notifications   = notifications_data,
        today_start     = today_start,
        yesterday_start = yesterday_start,
        week_ago        = week_ago
    )

@bp.route('/notifications/mark_read/<int:notification_id>')
def mark_notification_read(notification_id):
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    notification = Notification.query.filter_by(
        id=notification_id, user_id=session['user_id']
    ).first()
    
    if notification:
        notification.is_read = True
        db.session.commit()
        
        if notification.action_url:
            return redirect(notification.action_url)
    
    return redirect(url_for('common.notifications'))

# --- HELPER FUNCTIONS ---

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


# --- PROFILE PICTURE ROUTE (Accessible to all roles) ---

@bp.route('/profile_picture/<int:candidate_id>')
def get_candidate_profile_picture(candidate_id):
    """Serve candidate profile picture from database - accessible to employers and interviewers"""
    profile = CandidateProfile.query.get_or_404(candidate_id)
    
    if not profile.profile_picture:
        # Return default avatar SVG if no picture
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
