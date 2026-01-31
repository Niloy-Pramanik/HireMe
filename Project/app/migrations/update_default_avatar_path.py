"""
Quick script to update default avatar path for existing candidates
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from extensions import db
from sqlalchemy import text

def update_default_avatars():
    try:
        result = db.session.execute(text("""
            UPDATE candidate_profiles 
            SET profile_picture = 'uploads/profile_pictures/default_avatar.svg'
            WHERE profile_picture = 'default_avatar.png'
        """))
        
        db.session.commit()
        print(f"✓ Updated {result.rowcount} candidate profiles with correct default avatar path")
        return True
    except Exception as e:
        db.session.rollback()
        print(f"✗ Error: {str(e)}")
        return False

if __name__ == '__main__':
    from run import app
    with app.app_context():
        update_default_avatars()
