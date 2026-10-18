-- Canary release support for existing PostgreSQL installations.
ALTER TABLE workflow_releases
  ADD COLUMN IF NOT EXISTS traffic_percent integer NOT NULL DEFAULT 100;
ALTER TABLE workflow_releases
  DROP CONSTRAINT IF EXISTS workflow_releases_traffic_percent_check;
ALTER TABLE workflow_releases
  ADD CONSTRAINT workflow_releases_traffic_percent_check CHECK (traffic_percent BETWEEN 1 AND 100);
