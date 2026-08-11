CREATE TABLE sys_user (
    id BIGINT NOT NULL AUTO_INCREMENT,
    username VARCHAR(64) NOT NULL,
    password_hash VARCHAR(100) NOT NULL,
    status VARCHAR(16) NOT NULL,
    security_version BIGINT NOT NULL DEFAULT 0,
    version BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6),
    CONSTRAINT pk_sys_user PRIMARY KEY (id),
    CONSTRAINT uk_sys_user_username UNIQUE (username),
    CONSTRAINT chk_sys_user_status CHECK (status IN ('ENABLED', 'DISABLED'))
);

CREATE TABLE sys_role (
    id BIGINT NOT NULL AUTO_INCREMENT,
    code VARCHAR(32) NOT NULL,
    name VARCHAR(64) NOT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT pk_sys_role PRIMARY KEY (id),
    CONSTRAINT uk_sys_role_code UNIQUE (code)
);

CREATE TABLE sys_permission (
    id BIGINT NOT NULL AUTO_INCREMENT,
    code VARCHAR(64) NOT NULL,
    description VARCHAR(255) NOT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT pk_sys_permission PRIMARY KEY (id),
    CONSTRAINT uk_sys_permission_code UNIQUE (code)
);

CREATE TABLE sys_user_role (
    user_id BIGINT NOT NULL,
    role_id BIGINT NOT NULL,
    granted_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT pk_sys_user_role PRIMARY KEY (user_id, role_id),
    CONSTRAINT fk_sys_user_role_user FOREIGN KEY (user_id)
        REFERENCES sys_user (id) ON DELETE RESTRICT,
    CONSTRAINT fk_sys_user_role_role FOREIGN KEY (role_id)
        REFERENCES sys_role (id) ON DELETE RESTRICT
);

CREATE TABLE sys_role_permission (
    role_id BIGINT NOT NULL,
    permission_id BIGINT NOT NULL,
    CONSTRAINT pk_sys_role_permission PRIMARY KEY (role_id, permission_id),
    CONSTRAINT fk_sys_role_permission_role FOREIGN KEY (role_id)
        REFERENCES sys_role (id) ON DELETE RESTRICT,
    CONSTRAINT fk_sys_role_permission_permission FOREIGN KEY (permission_id)
        REFERENCES sys_permission (id) ON DELETE RESTRICT
);

CREATE TABLE audit_log (
    id BIGINT NOT NULL AUTO_INCREMENT,
    actor_id BIGINT NULL,
    action VARCHAR(64) NOT NULL,
    resource_type VARCHAR(64) NOT NULL,
    resource_id VARCHAR(128) NULL,
    request_id VARCHAR(128) NOT NULL,
    result VARCHAR(16) NOT NULL,
    client_ip VARCHAR(45) NULL,
    user_agent VARCHAR(512) NULL,
    detail_json JSON NOT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT pk_audit_log PRIMARY KEY (id),
    CONSTRAINT fk_audit_log_actor FOREIGN KEY (actor_id)
        REFERENCES sys_user (id) ON DELETE RESTRICT,
    INDEX idx_audit_log_request_id (request_id),
    INDEX idx_audit_log_actor_created_at (actor_id, created_at),
    INDEX idx_audit_log_action_created_at (action, created_at)
);

INSERT INTO sys_role (id, code, name)
VALUES
    (1, 'ADMIN', 'Administrator'),
    (2, 'VET', 'Veterinarian'),
    (3, 'AUDITOR', 'Auditor'),
    (4, 'USER', 'User');

INSERT INTO sys_permission (id, code, description)
VALUES
    (1, 'USER_MANAGE', 'Manage users, status, and role assignments'),
    (2, 'AI_CHAT', 'Use the AI chat service'),
    (3, 'MEASUREMENT_ANALYZE', 'Analyze livestock measurements'),
    (4, 'CONVERSATION_READ_OWN', 'Read conversations owned by the caller'),
    (5, 'CONVERSATION_READ_ALL', 'Read all conversations'),
    (6, 'DOCUMENT_UPLOAD', 'Upload knowledge documents'),
    (7, 'TASK_READ_OWN', 'Read tasks owned by the caller'),
    (8, 'TASK_MANAGE', 'Manage all tasks'),
    (9, 'TRACE_READ', 'Read AI execution traces'),
    (10, 'AUDIT_READ', 'Read enterprise audit records');

INSERT INTO sys_role_permission (role_id, permission_id)
SELECT 1, id FROM sys_permission;

INSERT INTO sys_role_permission (role_id, permission_id)
VALUES
    (2, 2),
    (2, 3),
    (2, 4),
    (2, 6),
    (2, 7),
    (3, 9),
    (3, 10),
    (4, 2),
    (4, 4),
    (4, 7);
