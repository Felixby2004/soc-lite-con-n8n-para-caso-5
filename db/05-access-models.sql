BEGIN;
SET LOCAL search_path TO soclite, public;
SELECT pg_advisory_xact_lock(hashtextextended('soclite:05-access-models', 0));

CREATE TABLE IF NOT EXISTS access_model_runs (
    id BIGSERIAL PRIMARY KEY,
    requested_by BIGINT REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    status VARCHAR(12) NOT NULL CHECK (status IN ('queued', 'running', 'completed', 'failed')),
    configuration JSONB NOT NULL,
    progress JSONB NOT NULL DEFAULT '{}'::jsonb,
    result JSONB,
    artifact JSONB,
    error TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_access_model_active_run
    ON access_model_runs ((1)) WHERE status IN ('queued', 'running');

WITH new_permission AS (
    INSERT INTO permissions (code, module, action, description)
    VALUES ('access:train', 'access', 'train', 'Entrenar modelos y ejecutar estudios de Optuna')
    ON CONFLICT (code) DO NOTHING
    RETURNING id
)
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM roles r CROSS JOIN new_permission p
WHERE r.code IN ('admin', 'soc_manager')
ON CONFLICT DO NOTHING;

COMMIT;
