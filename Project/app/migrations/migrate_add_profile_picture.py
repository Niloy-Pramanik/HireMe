"""
Database migration script to add profile_picture field to candidate_profiles
Run this script to update existing database
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from extensions import db
from sqlalchemy import text

def migrate_add_profile_picture():
    """Add profile_picture column to candidate_profiles table"""
    
    try:
        # Check if column already exists
        result = db.session.execute(text("""
            SELECT COUNT(*) 
            FROM INFORMATION_SCHEMA.COLUMNS 
            WHERE TABLE_NAME = 'candidate_profiles' 
            AND COLUMN_NAME = 'profile_picture'
        """))
        
        exists = result.scalar() > 0
        
        if exists:
            print("✓ profile_picture column already exists")
            return True
        
        print("Adding profile_picture column to candidate_profiles...")
        
        # Step 1: Add column as nullable with default
        db.session.execute(text("""
            ALTER TABLE candidate_profiles 
            ADD COLUMN profile_picture VARCHAR(500) DEFAULT 'default_avatar.png'
        """))
        
        # Step 2: Update existing records
        db.session.execute(text("""
            UPDATE candidate_profiles 
            SET profile_picture = 'default_avatar.png' 
            WHERE profile_picture IS NULL
        """))
        
        # Step 3: Make column NOT NULL
        db.session.execute(text("""
            ALTER TABLE candidate_profiles 
            MODIFY COLUMN profile_picture VARCHAR(500) NOT NULL DEFAULT 'default_avatar.png'
        """))
        
        db.session.commit()
        print("✓ Migration completed successfully!")
        print("✓ All existing candidates now have default avatar")
        print("✓ New candidates will be required to upload profile picture")
        return True
        
    except Exception as e:
        db.session.rollback()
        print(f"✗ Migration failed: {str(e)}")
        return False

if __name__ == '__main__':
    from run import app
    
    with app.app_context():
        print("=" * 60)
        print("Database Migration: Add Profile Picture to Candidates")
        print("=" * 60)
        
        success = migrate_add_profile_picture()
        
        if success:
            print("\n" + "=" * 60)
            print("Migration completed successfully!")
            print("=" * 60)
        else:
            print("\n" + "=" * 60)
            print("Migration failed! Please check the error above.")
            print("=" * 60)
