CREATE TABLE legacy_import_run (
    id BIGINT NOT NULL AUTO_INCREMENT,
    run_id CHAR(36) NOT NULL,
    domain VARCHAR(32) NOT NULL,
    source_name VARCHAR(255) NOT NULL,
    source_sha256 CHAR(64) NOT NULL,
    backup_sha256 CHAR(64) NOT NULL,
    source_size_bytes BIGINT NOT NULL,
    status VARCHAR(16) NOT NULL,
    expected_counts_json JSON NOT NULL,
    imported_counts_json JSON NOT NULL,
    reconciliation_json JSON NOT NULL,
    started_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    finished_at TIMESTAMP(6) NULL,
    CONSTRAINT pk_legacy_import_run PRIMARY KEY (id),
    CONSTRAINT uk_legacy_import_run_run_id UNIQUE (run_id),
    CONSTRAINT uk_legacy_import_run_domain_source UNIQUE (domain, source_sha256),
    CONSTRAINT chk_legacy_import_run_status
        CHECK (status IN ('RUNNING', 'SUCCEEDED')),
    CONSTRAINT chk_legacy_import_run_source_size CHECK (source_size_bytes >= 0),
    INDEX idx_legacy_import_run_domain_started_at (domain, started_at)
);

CREATE TABLE legacy_import_owner_map (
    run_id BIGINT NOT NULL,
    source_owner_id VARCHAR(255) NOT NULL,
    target_user_id BIGINT NOT NULL,
    target_username VARCHAR(64) NOT NULL,
    mapping_kind VARCHAR(16) NOT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT pk_legacy_import_owner_map
        PRIMARY KEY (run_id, source_owner_id),
    CONSTRAINT uk_legacy_import_owner_map_target
        UNIQUE (run_id, target_user_id),
    CONSTRAINT fk_legacy_import_owner_map_run FOREIGN KEY (run_id)
        REFERENCES legacy_import_run (id) ON DELETE RESTRICT,
    CONSTRAINT fk_legacy_import_owner_map_user FOREIGN KEY (target_user_id)
        REFERENCES sys_user (id) ON DELETE RESTRICT,
    CONSTRAINT chk_legacy_import_owner_map_kind
        CHECK (mapping_kind = 'SHADOW')
);

CREATE TABLE legacy_import_id_map (
    run_id BIGINT NOT NULL,
    entity_type VARCHAR(32) NOT NULL,
    source_id VARCHAR(255) NOT NULL,
    target_id BIGINT NOT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT pk_legacy_import_id_map
        PRIMARY KEY (run_id, entity_type, source_id),
    CONSTRAINT uk_legacy_import_id_map_target
        UNIQUE (run_id, entity_type, target_id),
    CONSTRAINT fk_legacy_import_id_map_run FOREIGN KEY (run_id)
        REFERENCES legacy_import_run (id) ON DELETE RESTRICT,
    INDEX idx_legacy_import_id_map_source (entity_type, source_id)
);
