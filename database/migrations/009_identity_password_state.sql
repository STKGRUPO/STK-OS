-- Existing users predate password_set_at. A non-null compatible hash means
-- their password was already defined before the identity migration existed.
UPDATE users
SET password_set_at = COALESCE(updated_at, created_at, now())
WHERE password_hash IS NOT NULL
  AND password_set_at IS NULL;
