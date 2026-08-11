ALTER TABLE biz_task
    ADD CONSTRAINT uk_biz_task_operation UNIQUE (operation_id);

CREATE TABLE knowledge_document (
    id BIGINT NOT NULL AUTO_INCREMENT,
    document_id VARCHAR(128) NOT NULL,
    owner_id BIGINT NOT NULL,
    client_idempotency_key VARCHAR(128) NOT NULL,
    operation_id VARCHAR(128) NOT NULL,
    original_request_id VARCHAR(128) NOT NULL,
    collection_name VARCHAR(128) NOT NULL,
    object_key VARCHAR(512) NOT NULL,
    file_name VARCHAR(255) NOT NULL,
    media_type VARCHAR(128) NOT NULL,
    size_bytes BIGINT NOT NULL,
    sha256 VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL,
    index_task_id BIGINT NULL,
    rag_document_id VARCHAR(64) NULL,
    execution_mode VARCHAR(8) NULL,
    chunk_count INT NULL,
    index_deadline_at TIMESTAMP(6) NOT NULL,
    indexed_at TIMESTAMP(6) NULL,
    version BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6),
    CONSTRAINT pk_knowledge_document PRIMARY KEY (id),
    CONSTRAINT uk_knowledge_document_public_id UNIQUE (document_id),
    CONSTRAINT uk_knowledge_document_owner_client_key
        UNIQUE (owner_id, client_idempotency_key),
    CONSTRAINT uk_knowledge_document_operation UNIQUE (operation_id),
    CONSTRAINT uk_knowledge_document_object_key UNIQUE (object_key),
    CONSTRAINT uk_knowledge_document_task UNIQUE (index_task_id),
    CONSTRAINT fk_knowledge_document_owner FOREIGN KEY (owner_id)
        REFERENCES sys_user (id) ON DELETE RESTRICT,
    CONSTRAINT fk_knowledge_document_task FOREIGN KEY (index_task_id)
        REFERENCES biz_task (id) ON DELETE RESTRICT,
    CONSTRAINT chk_knowledge_document_status CHECK (
        status IN ('UPLOADED', 'INDEXING', 'VALIDATED', 'INDEXED', 'FAILED', 'TIMED_OUT', 'CANCELLED')
    ),
    CONSTRAINT chk_knowledge_document_size CHECK (size_bytes > 0),
    CONSTRAINT chk_knowledge_document_chunk_count CHECK (
        chunk_count IS NULL OR chunk_count >= 0
    ),
    INDEX idx_knowledge_document_owner_created (owner_id, created_at),
    INDEX idx_knowledge_document_status_updated (status, updated_at)
);
