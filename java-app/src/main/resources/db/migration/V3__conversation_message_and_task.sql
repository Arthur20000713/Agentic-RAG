CREATE TABLE conversation (
    id BIGINT NOT NULL AUTO_INCREMENT,
    owner_id BIGINT NOT NULL,
    title VARCHAR(255) NOT NULL,
    status VARCHAR(16) NOT NULL,
    context_version BIGINT NOT NULL DEFAULT 0,
    active_operation_id VARCHAR(128) NULL,
    version BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6),
    last_message_at TIMESTAMP(6) NULL,
    CONSTRAINT pk_conversation PRIMARY KEY (id),
    CONSTRAINT fk_conversation_owner FOREIGN KEY (owner_id)
        REFERENCES sys_user (id) ON DELETE RESTRICT,
    CONSTRAINT chk_conversation_status
        CHECK (status IN ('ACTIVE', 'ARCHIVED', 'DELETED')),
    CONSTRAINT chk_conversation_context_version CHECK (context_version >= 0),
    INDEX idx_conversation_owner_updated_at (owner_id, updated_at),
    INDEX idx_conversation_status_updated_at (status, updated_at)
);

CREATE TABLE conversation_message (
    id BIGINT NOT NULL AUTO_INCREMENT,
    conversation_id BIGINT NOT NULL,
    turn_id VARCHAR(128) NOT NULL,
    role VARCHAR(16) NOT NULL,
    content MEDIUMTEXT NOT NULL,
    request_id VARCHAR(128) NOT NULL,
    status VARCHAR(16) NOT NULL,
    intent VARCHAR(128) NULL,
    risk_level VARCHAR(16) NULL,
    evidence_status VARCHAR(32) NULL,
    metadata_json JSON NOT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT pk_conversation_message PRIMARY KEY (id),
    CONSTRAINT fk_conversation_message_conversation FOREIGN KEY (conversation_id)
        REFERENCES conversation (id) ON DELETE RESTRICT,
    CONSTRAINT uk_conversation_message_turn_role
        UNIQUE (conversation_id, turn_id, role),
    CONSTRAINT uk_conversation_message_request_role UNIQUE (request_id, role),
    CONSTRAINT chk_conversation_message_role
        CHECK (role IN ('USER', 'ASSISTANT')),
    CONSTRAINT chk_conversation_message_status
        CHECK (status IN ('PENDING', 'COMPLETED', 'FAILED')),
    INDEX idx_conversation_message_conversation_created_at
        (conversation_id, created_at)
);

CREATE TABLE biz_task (
    id BIGINT NOT NULL AUTO_INCREMENT,
    owner_id BIGINT NOT NULL,
    conversation_id BIGINT NULL,
    type VARCHAR(32) NOT NULL,
    operation_id VARCHAR(128) NOT NULL,
    request_hash VARCHAR(64) NOT NULL,
    executor_job_id VARCHAR(128) NULL,
    status VARCHAR(32) NOT NULL,
    progress INT NOT NULL DEFAULT 0,
    result_ref VARCHAR(512) NULL,
    error_code VARCHAR(128) NULL,
    retry_count INT NOT NULL DEFAULT 0,
    version BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    started_at TIMESTAMP(6) NULL,
    finished_at TIMESTAMP(6) NULL,
    CONSTRAINT pk_biz_task PRIMARY KEY (id),
    CONSTRAINT fk_biz_task_owner FOREIGN KEY (owner_id)
        REFERENCES sys_user (id) ON DELETE RESTRICT,
    CONSTRAINT fk_biz_task_conversation FOREIGN KEY (conversation_id)
        REFERENCES conversation (id) ON DELETE RESTRICT,
    CONSTRAINT uk_biz_task_owner_operation UNIQUE (owner_id, operation_id),
    CONSTRAINT chk_biz_task_type
        CHECK (type IN ('AI_QUERY', 'MEASUREMENT_ANALYSIS', 'DOCUMENT_INDEX')),
    CONSTRAINT chk_biz_task_status
        CHECK (
            status IN (
                'CREATED',
                'RUNNING',
                'SUCCEEDED',
                'FAILED',
                'TIMED_OUT',
                'CANCELLED',
                'SUBMIT_UNKNOWN'
            )
        ),
    CONSTRAINT chk_biz_task_progress CHECK (progress BETWEEN 0 AND 100),
    CONSTRAINT chk_biz_task_retry_count CHECK (retry_count >= 0),
    INDEX idx_biz_task_status_created_at (status, created_at),
    INDEX idx_biz_task_owner_created_at (owner_id, created_at),
    INDEX idx_biz_task_conversation_created_at (conversation_id, created_at)
);
