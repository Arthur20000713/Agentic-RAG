ALTER TABLE conversation_message
    DROP INDEX uk_conversation_message_request_role,
    ADD INDEX idx_conversation_message_request_id (request_id);
