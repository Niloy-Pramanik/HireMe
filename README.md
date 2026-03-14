# HireMe - Comprehensive Job Matching Platform

A full-stack web application built with Flask that connects job seekers with employers through an intelligent matching system featuring real-time interviews, skill assessments, and comprehensive user management.

## 🎯 Who Is This Product For?

### Primary Users
- **Job Seekers & Candidates**: Professionals looking for career opportunities with advanced skill matching and comprehensive interview preparation tools
- **Companies & Employers**: Organizations seeking to streamline their hiring process with intelligent candidate matching and professional interview management
- **Professional Interviewers**: Certified experts who conduct technical interviews and provide candidate assessments as freelance services

### Industry Applications
- **Tech Companies**: Startups to enterprises looking for developers, engineers, and technical talent
- **Recruitment Agencies**: Organizations that need scalable interview and assessment tools
- **Educational Institutions**: Career services departments helping students and graduates find employment
- **HR Departments**: Internal teams managing large-scale hiring processes with technical roles

### Use Cases
- **Remote Hiring**: Companies conducting interviews with distributed teams and candidates
- **Technical Assessment**: Organizations requiring comprehensive skill evaluation and coding interviews  
- **Freelance Interview Services**: Independent interviewers offering professional assessment services
- **Career Development**: Job seekers wanting structured skill analysis and career guidance

## 🚀 Features

### Core Functionality
- **Multi-role System**: Candidates, Employers, Interviewers
- **Intelligent Job Matching**: Algorithm-based job recommendations using skill analysis
- **Real-time Interview Rooms**: Live video calls, code editor and chat
- **Examination System**: Technical assessments for preliminary screening
- **Expert Application System for interviewers onboarding**: Professional interviewer application process
- **Comprehensive Notifications**: Email and in-app notification system

### User Roles & Capabilities

#### 👨‍💼 Candidates
- Profile management with skill tracking
- Job browsing with advanced filters
- Application management and tracking
- Interview scheduling and participation
- Real-time skill analysis and recommendations
- Technical exam completion
- Interview history and feedback

#### 🏢 Employers
- Company profile management
- Job posting with detailed requirements
- Application review and candidate filtering
- Interview scheduling and management
- In-house interviewer management
- External interviewer hiring
- Comprehensive reporting and analytics

#### 👩‍💻 Interviewers
- Professional profile with certifications
- Availability management
- Earnings tracking and payment history
- Interview room tools (code editor, whiteboard)
- Candidate evaluation and feedback
- Expert application process
- Review and rating system

#### 🛡️ Administrators
- Onboarding of Interviewers who are applying


### 🔧 Technical Features
- **Real-time Communication**: WebSocket integration with Flask-SocketIO
- **Secure Authentication**: Role-based access control
- **File Management**: Profile picture uploads and document handling
- **Code Execution**: Sandboxed environment for technical interviews
- **Email Integration**: Automated notifications and confirmations
- **Database Migrations**: Structured schema evolution
- **Responsive Design**: Mobile-friendly interface

## 🛠️ Tech Stack

### Backend
- **Framework**: Flask 2.3.2
- **Database**: MySQL with SQLAlchemy ORM
- **Real-time**: Flask-SocketIO, python-socketio
- **Email**: Flask-Mail with SMTP
- **Migrations**: Flask-Migrate
- **Authentication**: Flask session management

## Frontend
- **Templates:** Jinja2 with server-side rendering  
- **Dynamic Interactions:** HTMX for partial page updates without full reloads  
- **JavaScript:** Alpine.js for lightweight client-side interactivity  
- **Styling:** Tailwind CSS with custom utility-based styling  
- **Real-time UI:** HTMX-powered asynchronous requests for responsive and dynamic interface updates

### Development Tools
- **Database**: PyMySQL connector
- **Environment**: python-dotenv
- **Package Management**: pip with requirements.txt

## 📋 Prerequisites

- Python 3.8+
- MySQL 5.7+ or 8.0+
- Git
- Gmail account for SMTP (or other email service)

## ⚙️ Installation & Setup

### 1. Clone the Repository
```bash
git clone https://github.com/Knocktern/HireMe.git
cd HireMe/Project/app
```

### 2. Create Virtual Environment
```bash
python -m venv env
source env/bin/activate  # On Windows: env\Scripts\activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Database Setup
```sql
-- Create MySQL database
CREATE DATABASE job_matching_system;
CREATE USER 'hireme_user'@'localhost' IDENTIFIED BY 'secure_password';
GRANT ALL PRIVILEGES ON job_matching_system.* TO 'hireme_user'@'localhost';
FLUSH PRIVILEGES;
```

### 5. Environment Configuration
```bash
# Copy environment template
cp .env.example .env

# Edit .env with your configurations
# Copy sample config
cp config.sample.py config.py
```




### 7. Run the Application
```bash
python run.py
```

The application will be available at `http://localhost:5000`

## 📁 Project Structure

```
Project/app/
├── models/                 # Database models
│   ├── user.py            # User management
│   ├── job.py             # Job postings
│   ├── candidate.py       # Candidate profiles
│   ├── interviewer.py     # Interviewer management
│   ├── interview.py       # Interview sessions
│   ├── exam.py            # Examination system
│   └── ...
├── routes/                # URL routing and controllers
│   ├── auth.py            # Authentication
│   ├── candidate.py       # Candidate operations
│   ├── employer.py        # Employer functions
│   ├── interviewer.py     # Interviewer management
│   ├── admin.py           # Admin panel
│   └── ...
├── services/              # Business logic
│   ├── email_service.py   # Email notifications
│   ├── job_matching_service.py # Matching algorithm
│   └── notification_service.py # Notifications
├── templates/             # HTML templates
│   ├── admin/             # Admin interface
│   ├── candidate/         # Candidate portal
│   ├── employer/          # Employer dashboard
│   ├── interviewer/       # Interviewer platform
│   ├── emails/            # Email templates
│   └── ...
├── static/                # Static assets
│   ├── js/               # JavaScript files
│   ├── css/              # Stylesheets
│   └── uploads/          # File uploads
├── migrations/           # Database migrations
├── utils/                # Utility functions
├── config.py            # Configuration (not in repo)
├── extensions.py        # Flask extensions
├── realtime.py         # Socket.IO handlers
└── run.py              # Application entry point
```










## 📖 API Documentation

### Real-time Events (Socket.IO)

#### Interview Room Events
- `join_interview`: Join an interview room
- `leave_interview`: Leave the room
- `code_change`: Share code changes
- `chat_message`: Send chat messages

### REST Endpoints

#### Authentication
- `POST /auth/login` - User login
- `POST /auth/register` - User registration
- `GET /auth/logout` - User logout

#### Jobs
- `GET /jobs` - Browse jobs
- `POST /jobs` - Create job posting
- `GET /jobs/<id>` - Job details
- `POST /jobs/<id>/apply` - Apply to job



## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.








**Built with ❤️ for connecting talent with opportunity**
