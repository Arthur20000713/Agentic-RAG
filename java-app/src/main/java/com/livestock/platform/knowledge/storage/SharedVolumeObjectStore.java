package com.livestock.platform.knowledge.storage;

import com.livestock.platform.common.error.ApiException;
import com.livestock.platform.knowledge.KnowledgeProperties;
import java.io.BufferedInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.security.DigestInputStream;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.Map;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.multipart.MultipartFile;

@Component
public class SharedVolumeObjectStore {

    private static final Map<String, String> MEDIA_TYPES = Map.of(
            ".pdf", "application/pdf",
            ".txt", "text/plain"
    );

    private final KnowledgeProperties properties;

    public SharedVolumeObjectStore(KnowledgeProperties properties) {
        this.properties = properties;
    }

    public StoredObject store(Long ownerId, MultipartFile file) {
        String fileName = validateMetadata(file);
        String extension = extension(fileName);
        Path ownerDirectory = properties.sharedRoot()
                .resolve("users")
                .resolve(String.valueOf(ownerId))
                .resolve("documents");
        String objectName = UUID.randomUUID() + extension;
        Path target = ownerDirectory.resolve(objectName).normalize();
        Path temporary = ownerDirectory.resolve("." + objectName + ".uploading");
        if (!target.startsWith(properties.sharedRoot())) {
            throw invalid("INVALID_OBJECT_KEY", "The generated object key is invalid");
        }
        try {
            Files.createDirectories(ownerDirectory);
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            try (InputStream source = new BufferedInputStream(file.getInputStream());
                 DigestInputStream hashing = new DigestInputStream(source, digest)) {
                Files.copy(hashing, temporary, StandardCopyOption.REPLACE_EXISTING);
            }
            long actualSize = Files.size(temporary);
            if (actualSize != file.getSize() || actualSize <= 0
                    || actualSize > properties.maxFileBytes()) {
                throw invalid("INVALID_DOCUMENT_SIZE", "The uploaded document size is invalid");
            }
            validateContent(temporary, extension);
            Files.move(temporary, target, StandardCopyOption.ATOMIC_MOVE);
            String objectKey = properties.sharedRoot().relativize(target)
                    .toString()
                    .replace('\\', '/');
            return new StoredObject(
                    objectKey,
                    fileName,
                    file.getContentType(),
                    actualSize,
                    HexFormat.of().formatHex(digest.digest()),
                    target
            );
        } catch (ApiException exception) {
            deleteQuietly(temporary);
            throw exception;
        } catch (IOException | NoSuchAlgorithmException exception) {
            deleteQuietly(temporary);
            throw new ApiException(
                    HttpStatus.SERVICE_UNAVAILABLE,
                    "DOCUMENT_STORAGE_UNAVAILABLE",
                    "Document storage is temporarily unavailable"
            );
        }
    }

    public void deleteQuietly(Path path) {
        try {
            Files.deleteIfExists(path);
        } catch (IOException ignored) {
            // Orphan cleanup is performed separately; never hide the business outcome.
        }
    }

    private String validateMetadata(MultipartFile file) {
        String fileName = file.getOriginalFilename();
        if (fileName == null || fileName.isBlank() || fileName.length() > 255
                || fileName.contains("/") || fileName.contains("\\")) {
            throw invalid("INVALID_FILE_NAME", "The document file name is invalid");
        }
        if (file.isEmpty() || file.getSize() > properties.maxFileBytes()) {
            throw invalid("INVALID_DOCUMENT_SIZE", "The uploaded document size is invalid");
        }
        String expectedMediaType = MEDIA_TYPES.get(extension(fileName));
        if (expectedMediaType == null || !expectedMediaType.equals(file.getContentType())) {
            throw invalid("UNSUPPORTED_MEDIA_TYPE", "Only PDF and UTF-8 text documents are supported");
        }
        return fileName;
    }

    private static void validateContent(Path path, String extension) throws IOException {
        if (".pdf".equals(extension)) {
            try (InputStream stream = Files.newInputStream(path)) {
                if (!java.util.Arrays.equals(stream.readNBytes(5), "%PDF-".getBytes(StandardCharsets.US_ASCII))) {
                    throw invalid("INVALID_PDF", "The PDF signature is invalid");
                }
            }
            return;
        }
        try {
            StandardCharsets.UTF_8.newDecoder().decode(java.nio.ByteBuffer.wrap(Files.readAllBytes(path)));
        } catch (CharacterCodingException exception) {
            throw invalid("INVALID_TEXT_ENCODING", "Text documents must use UTF-8");
        }
    }

    private static String extension(String fileName) {
        int index = fileName.lastIndexOf('.');
        return index < 0 ? "" : fileName.substring(index).toLowerCase(java.util.Locale.ROOT);
    }

    private static ApiException invalid(String code, String message) {
        return new ApiException(HttpStatus.BAD_REQUEST, code, message);
    }

    public record StoredObject(
            String objectKey,
            String fileName,
            String mediaType,
            long sizeBytes,
            String sha256,
            Path absolutePath
    ) {
    }
}
