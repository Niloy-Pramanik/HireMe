from flask import Flask
from flask_migrate import Migrate
from config import DevelopmentConfig
from extensions import db, mail, socketio
from models import *
import realtime  # Import to register Socket.IO event handlers

migrate = Migrate()

def create_app(config_class=DevelopmentConfig):
    """Application factory function"""
    app = Flask(__name__, 
                template_folder='templates',
                static_folder='static')
    
    # Load configuration
    app.config.from_object(config_class)
    
    # Initialize extensions
    db.init_app(app)
    mail.init_app(app)
    socketio.init_app(app)
    migrate.init_app(app, db)
    
    # Register context processor
    @app.context_processor
    def inject_datetime():
        from datetime import datetime, timedelta
        from flask import session
        from models import Notification
        
        unread_count = 0
        if 'user_id' in session:
            unread_count = Notification.query.filter_by(
                user_id=session['user_id'],
                is_read=False
            ).count()
        
        return {
            'datetime': datetime,
            'timedelta': timedelta,
            'now': datetime.now(),
            'unread_notification_count': unread_count
        }
    
    # Register blueprints
    from routes.main import main_bp
    from routes.auth import auth_bp
    from routes.job import job_bp
    from routes.candidate import candidate_bp
    from routes.employer import bp as employer_bp
    from routes.admin import bp as admin_bp
    from routes.interviewer import bp as interviewer_bp
    from routes.exam import bp as exam_bp
    from routes.notification import bp as notification_bp
    from routes.interview import bp as interview_bp
    from routes.common import bp as common_bp
    from routes.expert_application import bp as expert_application_bp
    
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(job_bp)
    app.register_blueprint(candidate_bp)
    app.register_blueprint(employer_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(interviewer_bp)
    app.register_blueprint(exam_bp)
    app.register_blueprint(notification_bp)
    app.register_blueprint(interview_bp)
    app.register_blueprint(common_bp)
    app.register_blueprint(expert_application_bp)
    
    # Create database tables
    with app.app_context():
        db.create_all()
    
    return app
