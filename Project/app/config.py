import os

class Config:
    """Base configuration"""
    SECRET_KEY = 'your-secret-key-change-this'
    
    # SQLAlchemy Database configuration
    SQLALCHEMY_DATABASE_URI = 'mysql+pymysql://root:sakibonlockdown@localhost:3306/job_matching_system'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    
    # Mail configuration
    MAIL_SERVER = 'smtp.gmail.com'
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USERNAME = 'hiremeautomatedmail@gmail.com'
    MAIL_PASSWORD = 'esoq ymko jrpx uynz'
    MAIL_DEFAULT_SENDER = ('HireMe', 'hiremeautomatedmail@gmail.com')
    MAIL_MAX_EMAILS = None
    MAIL_ASCII_ATTACHMENTS = False

class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True

class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False

class TestingConfig(Config):
    """Testing configuration"""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
