-- =====================================================
-- SQL Migration Script for Interviewer Feature
-- HireMe Platform - Expert Interviewer System
-- Generated: December 2025
-- =====================================================

-- Run this script on your MySQL database to add the new tables
-- Make sure to backup your database before running this script

-- =====================================================
-- 1. INTERVIEWER PROFILES TABLE
-- Main profile table for all interviewers (independent & in-house)
-- =====================================================
CREATE TABLE IF NOT EXISTS interviewer_profiles (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL UNIQUE,
    
    -- Profile Information
    headline VARCHAR(255),
    bio TEXT,
    experience_years INT DEFAULT 0,
    linkedin_url VARCHAR(500),
    
    -- CV/Resume
    cv_file_path VARCHAR(500),
    cv_content LONGBLOB,
    cv_filename VARCHAR(255),
    cv_mimetype VARCHAR(100),
    
    -- Experience Proof Document
    experience_proof_path VARCHAR(500),
    experience_proof_content LONGBLOB,
    experience_proof_filename VARCHAR(255),
    experience_proof_mimetype VARCHAR(100),
    
    -- Interviewer Type
    interviewer_type ENUM('independent', 'in_house') DEFAULT 'independent',
    company_id INT NULL,
    
    -- Payment
    hourly_rate DECIMAL(10, 2) DEFAULT 0,
    currency VARCHAR(10) DEFAULT 'USD',
    
    -- Status & Verification
    approval_status ENUM('pending', 'approved', 'rejected') DEFAULT 'pending',
    rejection_reason TEXT,
    is_verified BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,
    is_available BOOLEAN DEFAULT TRUE,
    
    -- Stats
    total_interviews INT DEFAULT 0,
    total_earnings DECIMAL(12, 2) DEFAULT 0,
    average_rating DECIMAL(3, 2) DEFAULT 0,
    
    -- Timestamps
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    approved_at DATETIME,
    
    -- Foreign Keys
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE SET NULL,
    
    -- Indexes
    INDEX idx_interviewer_type (interviewer_type),
    INDEX idx_approval_status (approval_status),
    INDEX idx_is_active (is_active),
    INDEX idx_is_available (is_available),
    INDEX idx_company_id (company_id),
    INDEX idx_hourly_rate (hourly_rate),
    INDEX idx_average_rating (average_rating)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- =====================================================
-- 2. INTERVIEWER SKILLS TABLE
-- Skills that interviewer can conduct interviews for
-- =====================================================
CREATE TABLE IF NOT EXISTS interviewer_skills (
    id INT AUTO_INCREMENT PRIMARY KEY,
    interviewer_id INT NOT NULL,
    skill_id INT NOT NULL,
    proficiency_level ENUM('Intermediate', 'Advanced', 'Expert') DEFAULT 'Advanced',
    years_experience INT DEFAULT 0,
    can_interview BOOLEAN DEFAULT TRUE,
    
    -- Foreign Keys
    FOREIGN KEY (interviewer_id) REFERENCES interviewer_profiles(id) ON DELETE CASCADE,
    FOREIGN KEY (skill_id) REFERENCES skills(id) ON DELETE CASCADE,
    
    -- Unique constraint
    UNIQUE KEY unique_interviewer_skill (interviewer_id, skill_id),
    
    -- Indexes
    INDEX idx_skill_id (skill_id),
    INDEX idx_proficiency (proficiency_level)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- =====================================================
-- 3. INTERVIEWER INDUSTRIES TABLE
-- Industries the interviewer has experience in
-- =====================================================
CREATE TABLE IF NOT EXISTS interviewer_industries (
    id INT AUTO_INCREMENT PRIMARY KEY,
    interviewer_id INT NOT NULL,
    industry_name VARCHAR(100) NOT NULL,
    years_experience INT DEFAULT 0,
    
    -- Foreign Keys
    FOREIGN KEY (interviewer_id) REFERENCES interviewer_profiles(id) ON DELETE CASCADE,
    
    -- Unique constraint
    UNIQUE KEY unique_interviewer_industry (interviewer_id, industry_name),
    
    -- Indexes
    INDEX idx_industry_name (industry_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- =====================================================
-- 4. INTERVIEWER CERTIFICATIONS TABLE
-- Certifications and credentials
-- =====================================================
CREATE TABLE IF NOT EXISTS interviewer_certifications (
    id INT AUTO_INCREMENT PRIMARY KEY,
    interviewer_id INT NOT NULL,
    
    certification_name VARCHAR(255) NOT NULL,
    issuing_organization VARCHAR(255),
    issue_date DATE,
    expiry_date DATE,
    credential_id VARCHAR(255),
    credential_url VARCHAR(500),
    
    -- Certificate file
    certificate_file_path VARCHAR(500),
    certificate_content LONGBLOB,
    certificate_filename VARCHAR(255),
    certificate_mimetype VARCHAR(100),
    
    is_verified BOOLEAN DEFAULT FALSE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    
    -- Foreign Keys
    FOREIGN KEY (interviewer_id) REFERENCES interviewer_profiles(id) ON DELETE CASCADE,
    
    -- Indexes
    INDEX idx_certification_name (certification_name),
    INDEX idx_issuing_org (issuing_organization)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- =====================================================
-- 5. INTERVIEWER AVAILABILITY TABLE
-- Weekly availability slots
-- =====================================================
CREATE TABLE IF NOT EXISTS interviewer_availabilities (
    id INT AUTO_INCREMENT PRIMARY KEY,
    interviewer_id INT NOT NULL,
    
    day_of_week INT NOT NULL CHECK (day_of_week >= 0 AND day_of_week <= 6),  -- 0=Monday, 6=Sunday
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    timezone VARCHAR(50) DEFAULT 'UTC',
    is_active BOOLEAN DEFAULT TRUE,
    
    -- Foreign Keys
    FOREIGN KEY (interviewer_id) REFERENCES interviewer_profiles(id) ON DELETE CASCADE,
    
    -- Indexes
    INDEX idx_day_of_week (day_of_week),
    INDEX idx_is_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- =====================================================
-- 6. INTERVIEWER EARNINGS TABLE
-- Track earnings for each completed interview
-- =====================================================
CREATE TABLE IF NOT EXISTS interviewer_earnings (
    id INT AUTO_INCREMENT PRIMARY KEY,
    interviewer_id INT NOT NULL,
    interview_room_id INT NOT NULL,
    
    duration_minutes INT DEFAULT 0,
    hourly_rate DECIMAL(10, 2) NOT NULL,
    amount_earned DECIMAL(10, 2) NOT NULL,
    currency VARCHAR(10) DEFAULT 'USD',
    
    status ENUM('pending', 'confirmed', 'paid') DEFAULT 'pending',
    
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    confirmed_at DATETIME,
    paid_at DATETIME,
    
    -- Foreign Keys
    FOREIGN KEY (interviewer_id) REFERENCES interviewer_profiles(id) ON DELETE CASCADE,
    FOREIGN KEY (interview_room_id) REFERENCES interview_rooms(id) ON DELETE CASCADE,
    
    -- Indexes
    INDEX idx_status (status),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- =====================================================
-- 7. INTERVIEWER REVIEWS TABLE
-- Reviews/ratings from employers
-- =====================================================
CREATE TABLE IF NOT EXISTS interviewer_reviews (
    id INT AUTO_INCREMENT PRIMARY KEY,
    interviewer_id INT NOT NULL,
    reviewer_id INT NOT NULL,
    interview_room_id INT,
    
    -- Ratings (1-5)
    professionalism_rating INT CHECK (professionalism_rating >= 1 AND professionalism_rating <= 5),
    technical_accuracy_rating INT CHECK (technical_accuracy_rating >= 1 AND technical_accuracy_rating <= 5),
    communication_rating INT CHECK (communication_rating >= 1 AND communication_rating <= 5),
    punctuality_rating INT CHECK (punctuality_rating >= 1 AND punctuality_rating <= 5),
    overall_rating INT CHECK (overall_rating >= 1 AND overall_rating <= 5),
    
    review_text TEXT,
    would_hire_again BOOLEAN DEFAULT TRUE,
    
    is_public BOOLEAN DEFAULT TRUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    
    -- Foreign Keys
    FOREIGN KEY (interviewer_id) REFERENCES interviewer_profiles(id) ON DELETE CASCADE,
    FOREIGN KEY (reviewer_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (interview_room_id) REFERENCES interview_rooms(id) ON DELETE SET NULL,
    
    -- Indexes
    INDEX idx_overall_rating (overall_rating),
    INDEX idx_created_at (created_at),
    INDEX idx_is_public (is_public)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- =====================================================
-- 8. INTERVIEWER APPLICATIONS TABLE
-- Applications to become expert interviewer (admin review)
-- =====================================================
CREATE TABLE IF NOT EXISTS interviewer_applications (
    id INT AUTO_INCREMENT PRIMARY KEY,
    
    -- Applicant info
    email VARCHAR(255) NOT NULL,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    phone VARCHAR(20),
    
    -- Professional info
    headline VARCHAR(255),
    bio TEXT,
    experience_years INT DEFAULT 0,
    linkedin_url VARCHAR(500),
    hourly_rate DECIMAL(10, 2),
    currency VARCHAR(10) DEFAULT 'USD',
    
    -- Skills & Industries (JSON)
    skills_json TEXT,
    industries_json TEXT,
    
    -- Documents
    cv_content LONGBLOB,
    cv_filename VARCHAR(255),
    cv_mimetype VARCHAR(100),
    
    experience_proof_content LONGBLOB,
    experience_proof_filename VARCHAR(255),
    experience_proof_mimetype VARCHAR(100),
    
    certifications_json TEXT,
    
    -- Application status
    status ENUM('pending', 'under_review', 'approved', 'rejected') DEFAULT 'pending',
    rejection_reason TEXT,
    reviewed_by INT,
    created_user_id INT,
    
    -- Timestamps
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    reviewed_at DATETIME,
    
    -- Foreign Keys
    FOREIGN KEY (reviewed_by) REFERENCES users(id) ON DELETE SET NULL,
    FOREIGN KEY (created_user_id) REFERENCES users(id) ON DELETE SET NULL,
    
    -- Indexes
    INDEX idx_email (email),
    INDEX idx_status (status),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- =====================================================
-- 9. INTERVIEWER JOB ROLES TABLE
-- Job roles interviewer can conduct interviews for
-- =====================================================
CREATE TABLE IF NOT EXISTS interviewer_job_roles (
    id INT AUTO_INCREMENT PRIMARY KEY,
    interviewer_id INT NOT NULL,
    
    role_name VARCHAR(255) NOT NULL,
    experience_level ENUM('Junior', 'Mid', 'Senior', 'Lead', 'Principal', 'All Levels') DEFAULT 'All Levels',
    interviews_conducted INT DEFAULT 0,
    
    -- Foreign Keys
    FOREIGN KEY (interviewer_id) REFERENCES interviewer_profiles(id) ON DELETE CASCADE,
    
    -- Unique constraint
    UNIQUE KEY unique_interviewer_role (interviewer_id, role_name),
    
    -- Indexes
    INDEX idx_role_name (role_name),
    INDEX idx_experience_level (experience_level)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- =====================================================
-- SAMPLE DATA (Optional - for testing)
-- =====================================================

-- Add some common industries
-- INSERT INTO interviewer_industries (interviewer_id, industry_name, years_experience) VALUES
-- You can add sample data after creating interviewer profiles

-- =====================================================
-- USEFUL QUERIES
-- =====================================================

-- Get all approved independent interviewers with their skills
-- SELECT ip.*, u.first_name, u.last_name, u.email,
--        GROUP_CONCAT(s.skill_name) as skills
-- FROM interviewer_profiles ip
-- JOIN users u ON ip.user_id = u.id
-- LEFT JOIN interviewer_skills isk ON ip.id = isk.interviewer_id
-- LEFT JOIN skills s ON isk.skill_id = s.id
-- WHERE ip.interviewer_type = 'independent' 
--   AND ip.approval_status = 'approved'
--   AND ip.is_active = TRUE
-- GROUP BY ip.id;

-- Get interviewer earnings summary
-- SELECT ip.id, u.first_name, u.last_name,
--        COUNT(ie.id) as total_paid_interviews,
--        SUM(ie.amount_earned) as total_earnings
-- FROM interviewer_profiles ip
-- JOIN users u ON ip.user_id = u.id
-- LEFT JOIN interviewer_earnings ie ON ip.id = ie.interviewer_id
-- GROUP BY ip.id;

-- Get pending applications for admin review
-- SELECT * FROM interviewer_applications 
-- WHERE status = 'pending' 
-- ORDER BY created_at ASC;

-- =====================================================
-- END OF MIGRATION SCRIPT
-- =====================================================
