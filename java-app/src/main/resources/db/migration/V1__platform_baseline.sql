CREATE TABLE platform_schema_marker (
    id SMALLINT NOT NULL,
    schema_version VARCHAR(32) NOT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT pk_platform_schema_marker PRIMARY KEY (id)
);

INSERT INTO platform_schema_marker (id, schema_version)
VALUES (1, 'P2_BASELINE');
