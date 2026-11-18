BEGIN;
SET LOCAL search_path TO soclite, public;
SELECT pg_advisory_xact_lock(hashtextextended('soclite:03-access-monitoring', 0));

CREATE TABLE IF NOT EXISTS access_logs (
    id BIGSERIAL PRIMARY KEY,
    source VARCHAR(64) NOT NULL,
    event_id VARCHAR(160) NOT NULL,
    account VARCHAR(160) NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    outcome VARCHAR(12) NOT NULL CHECK (outcome IN ('success', 'failure')),
    source_ip INET,
    device_id VARCHAR(160),
    network VARCHAR(12) NOT NULL CHECK (network IN ('direct', 'vpn', 'proxy', 'unknown')),
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    accuracy_km DOUBLE PRECISION,
    fingerprint CHAR(64) NOT NULL,
    score SMALLINT NOT NULL CHECK (score BETWEEN 0 AND 100),
    signals JSONB NOT NULL,
    baseline_size SMALLINT NOT NULL,
    CONSTRAINT uq_access_logs_source_event UNIQUE (source, event_id)
);
CREATE INDEX IF NOT EXISTS idx_access_logs_profile
    ON access_logs (source, account, outcome, occurred_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_access_logs_recent ON access_logs (occurred_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS access_anomalies (
    access_log_id BIGINT PRIMARY KEY REFERENCES access_logs(id) ON DELETE CASCADE,
    alert_id BIGINT UNIQUE REFERENCES alerts(id) ON DELETE SET NULL,
    detected_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS access_iocs (
    id BIGSERIAL PRIMARY KEY,
    ip_address INET NOT NULL UNIQUE,
    reference VARCHAR(240) NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ
);

WITH new_permissions AS (
    INSERT INTO permissions (code, module, action, description) VALUES
        ('access:read', 'access', 'read', 'Consultar accesos, perfiles, anomalías e indicadores IP'),
        ('access:write', 'access', 'write', 'Importar eventos de acceso y cargar la demostración'),
        ('access:ioc', 'access', 'ioc', 'Gestionar indicadores IP y su vigencia')
    ON CONFLICT (code) DO NOTHING
    RETURNING id, code
)
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles r CROSS JOIN new_permissions p
WHERE r.code IN ('admin', 'soc_manager')
   OR (r.code = 'analyst' AND p.code IN ('access:read', 'access:write'))
ON CONFLICT DO NOTHING;

COMMIT;
