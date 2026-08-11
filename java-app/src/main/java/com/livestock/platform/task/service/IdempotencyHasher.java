package com.livestock.platform.task.service;

import com.livestock.platform.task.domain.TaskType;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import org.springframework.stereotype.Component;

@Component
public final class IdempotencyHasher {

    public String requestHash(
            long conversationId,
            TaskType taskType,
            long contextVersion,
            String content
    ) {
        MessageDigest digest = sha256();
        updateLong(digest, conversationId);
        updateText(digest, taskType.name());
        updateLong(digest, contextVersion);
        updateText(digest, content);
        return HexFormat.of().formatHex(digest.digest());
    }

    public String keyDigest(String idempotencyKey) {
        MessageDigest digest = sha256();
        digest.update(idempotencyKey.getBytes(StandardCharsets.UTF_8));
        return HexFormat.of().formatHex(digest.digest(), 0, 12);
    }

    public String documentRequestHash(
            String collection,
            String fileName,
            String mediaType,
            long sizeBytes,
            String sha256
    ) {
        MessageDigest digest = sha256();
        updateText(digest, TaskType.DOCUMENT_INDEX.name());
        updateText(digest, collection);
        updateText(digest, fileName);
        updateText(digest, mediaType);
        updateLong(digest, sizeBytes);
        updateText(digest, sha256);
        return HexFormat.of().formatHex(digest.digest());
    }

    private static void updateLong(MessageDigest digest, long value) {
        digest.update(ByteBuffer.allocate(Long.BYTES).putLong(value).array());
    }

    private static void updateText(MessageDigest digest, String value) {
        byte[] bytes = value.getBytes(StandardCharsets.UTF_8);
        digest.update(ByteBuffer.allocate(Integer.BYTES).putInt(bytes.length).array());
        digest.update(bytes);
    }

    private static MessageDigest sha256() {
        try {
            return MessageDigest.getInstance("SHA-256");
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("SHA-256 is unavailable", exception);
        }
    }
}
