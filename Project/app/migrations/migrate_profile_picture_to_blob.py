"""
Database migration: Convert profile_picture from VARCHAR to BLOB
This migration converts the profile picture storage from file paths to binary data in database
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from extensions import db
from sqlalchemy import text
from models import CandidateProfile

def migrate_profile_picture_to_blob():
    """Convert profile_picture column from VARCHAR to BLOB"""
    
    try:
        print("Step 1: Checking current table structure...")
        
        # Check if profile_picture_mimetype column exists
        result = db.session.execute(text("""
            SELECT COUNT(*) 
            FROM INFORMATION_SCHEMA.COLUMNS 
            WHERE TABLE_NAME = 'candidate_profiles' 
            AND COLUMN_NAME = 'profile_picture_mimetype'
        """))
        
        mimetype_exists = result.scalar() > 0
        
        if not mimetype_exists:
            print("Step 2: Adding profile_picture_mimetype column...")
            db.session.execute(text("""
                ALTER TABLE candidate_profiles 
                ADD COLUMN profile_picture_mimetype VARCHAR(50) DEFAULT 'image/svg+xml'
            """))
            db.session.commit()
            print("✓ Added profile_picture_mimetype column")
        else:
            print("✓ profile_picture_mimetype column already exists")
        
        print("\nStep 3: Reading default SVG avatar...")
        # Default avatar SVG
        default_svg = '''<svg width="200" height="200" xmlns="http://www.w3.org/2000/svg">
  <circle cx="100" cy="100" r="100" fill="#E5E7EB"/>
  <g fill="#9CA3AF">
    <circle cx="100" cy="75" r="30"/>
    <path d="M 100 105 Q 60 105 40 145 L 160 145 Q 140 105 100 105 Z"/>
  </g>
</svg>'''
        default_binary = default_svg.encode('utf-8')
        
        print("Step 4: Creating temporary column for binary data...")
        db.session.execute(text("""
            ALTER TABLE candidate_profiles 
            ADD COLUMN profile_picture_new LONGBLOB
        """))
        db.session.commit()
        print("✓ Created temporary column")
        
        print("\nStep 5: Converting existing data to binary...")
        # Get all candidates
        candidates = CandidateProfile.query.all()
        converted_count = 0
        
        for candidate in candidates:
            # Set default avatar for all (since we're moving from file paths)
            db.session.execute(
                text("UPDATE candidate_profiles SET profile_picture_new = :data, profile_picture_mimetype = 'image/svg+xml' WHERE id = :id"),
                {'data': default_binary, 'id': candidate.id}
            )
            converted_count += 1
        
        db.session.commit()
        print(f"✓ Converted {converted_count} candidate profiles to binary storage")
        
        print("\nStep 6: Dropping old column and renaming new column...")
        db.session.execute(text("""
            ALTER TABLE candidate_profiles 
            DROP COLUMN profile_picture
        """))
        db.session.execute(text("""
            ALTER TABLE candidate_profiles 
            CHANGE COLUMN profile_picture_new profile_picture LONGBLOB NOT NULL
        """))
        db.session.commit()
        print("✓ Replaced old column with new binary column")
        
        print("\n" + "=" * 70)
        print("✓ MIGRATION COMPLETED SUCCESSFULLY!")
        print("=" * 70)
        print(f"✓ Converted {converted_count} profiles to database storage")
        print("✓ All candidates now have default avatar (binary in database)")
        print("✓ Candidates can now upload new pictures via profile edit")
        print("✓ Pictures will be visible to employers and interviewers")
        print("=" * 70)
        return True
        
    except Exception as e:
        db.session.rollback()
        print(f"\n✗ Migration failed: {str(e)}")
        print("\nAttempting rollback...")
        try:
            db.session.execute(text("ALTER TABLE candidate_profiles DROP COLUMN IF EXISTS profile_picture_new"))
            db.session.execute(text("ALTER TABLE candidate_profiles DROP COLUMN IF EXISTS profile_picture_mimetype"))
            db.session.commit()
            print("✓ Rollback completed")
        except:
            print("✗ Rollback failed - manual intervention required")
        return False

if __name__ == '__main__':
    from run import app
    
    with app.app_context():
        print("=" * 70)
        print("DATABASE MIGRATION: Profile Picture to Binary Storage")
        print("=" * 70)
        print("This will convert profile pictures from file paths to database storage")
        print("All existing candidates will get default avatar (can be updated later)")
        print("=" * 70)
        
        response = input("\nProceed with migration? (yes/no): ")
        
        if response.lower() in ['yes', 'y']:
            print("\nStarting migration...\n")
            migrate_profile_picture_to_blob()
        else:
            print("\nMigration cancelled.")
