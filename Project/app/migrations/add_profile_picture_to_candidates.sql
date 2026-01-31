-- Migration: Add profile_picture column to candidate_profiles table
-- Date: 2026-01-22
-- Description: Make profile picture mandatory for all candidates

-- Step 1: Add the column as nullable first (for existing records)
ALTER TABLE candidate_profiles 
ADD COLUMN profile_picture VARCHAR(500) DEFAULT 'default_avatar.png';

-- Step 2: Update existing records to have the default value
UPDATE candidate_profiles 
SET profile_picture = 'default_avatar.png' 
WHERE profile_picture IS NULL;

-- Step 3: Make the column NOT NULL
ALTER TABLE candidate_profiles 
MODIFY COLUMN profile_picture VARCHAR(500) NOT NULL DEFAULT 'default_avatar.png';

-- Note: New candidate registrations will require actual profile picture upload
-- The default is only for existing records that don't have one yet
