ALTER TABLE videos ADD COLUMN IF NOT EXISTS provider TEXT;
ALTER TABLE videos ADD COLUMN IF NOT EXISTS provider_video_id TEXT;
ALTER TABLE videos ADD COLUMN IF NOT EXISTS playback_url TEXT;
ALTER TABLE videos ADD COLUMN IF NOT EXISTS thumbnail_url TEXT;
ALTER TABLE videos ADD COLUMN IF NOT EXISTS duration_secs REAL;
ALTER TABLE videos ADD COLUMN IF NOT EXISTS upload_status TEXT NOT NULL DEFAULT 'pending';
ALTER TABLE videos ALTER COLUMN source_url DROP NOT NULL;
ALTER TABLE videos ALTER COLUMN provider SET DEFAULT 'cloudflare';

CREATE INDEX IF NOT EXISTS videos_provider_id_idx ON videos (provider_video_id);