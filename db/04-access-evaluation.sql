BEGIN;
SET LOCAL search_path TO soclite, public;
SELECT pg_advisory_xact_lock(hashtextextended('soclite:04-access-evaluation', 0));

CREATE TABLE IF NOT EXISTS access_reviews (
    access_log_id BIGINT PRIMARY KEY REFERENCES access_logs(id) ON DELETE CASCADE,
    label VARCHAR(12) NOT NULL CHECK (label IN ('expected', 'anomalous')),
    note VARCHAR(300),
    reviewed_by BIGINT REFERENCES users(id) ON DELETE SET NULL,
    reviewed_at TIMESTAMPTZ NOT NULL
);

WITH new_permission AS (
    INSERT INTO permissions (code, module, action, description)
    VALUES ('access:review', 'access', 'review', 'Validar eventos de acceso para medir la detección')
    ON CONFLICT (code) DO NOTHING
    RETURNING id
)
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM roles r CROSS JOIN new_permission p
WHERE r.code IN ('admin', 'soc_manager', 'analyst')
ON CONFLICT DO NOTHING;

COMMIT;
