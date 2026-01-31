from extensions import db
from datetime import datetime

class CandidateProfile(db.Model):
    __tablename__ = 'candidate_profiles'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    profile_picture = db.Column(db.LargeBinary, nullable=False)  # Store image binary data
    profile_picture_mimetype = db.Column(db.String(50), nullable=False, default='image/svg+xml')  # Store MIME type
    experience_years = db.Column(db.Integer, default=0)
    education_level = db.Column(db.Enum('High School', 'Bachelor', 'Master', 'PhD', 'Other'))
    current_position = db.Column(db.String(255))
    location = db.Column(db.String(255))
    salary_expectation = db.Column(db.Numeric(10, 2))
    cv_file_path = db.Column(db.String(500))
    cv_content = db.Column(db.LargeBinary)
    cv_filename = db.Column(db.String(255))
    cv_mimetype = db.Column(db.String(100))
    summary = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    applications = db.relationship('JobApplication', backref='candidate', lazy=True)
