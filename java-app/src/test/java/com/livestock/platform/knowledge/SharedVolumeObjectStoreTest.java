package com.livestock.platform.knowledge;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.livestock.platform.common.error.ApiException;
import com.livestock.platform.knowledge.storage.SharedVolumeObjectStore;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.mock.web.MockMultipartFile;

class SharedVolumeObjectStoreTest {

    @TempDir
    Path temporaryDirectory;

    @Test
    void storesValidatedTextBelowFixedRootWithOpaqueObjectKey() throws Exception {
        KnowledgeProperties properties = properties();
        SharedVolumeObjectStore store = new SharedVolumeObjectStore(properties);
        byte[] content = "livestock feeding guidance\n".getBytes(StandardCharsets.UTF_8);

        SharedVolumeObjectStore.StoredObject result = store.store(
                42L,
                new MockMultipartFile(
                        "file",
                        "guide.txt",
                        "text/plain",
                        content
                )
        );

        assertThat(result.objectKey()).startsWith("users/42/documents/");
        assertThat(result.objectKey()).endsWith(".txt").doesNotContain("\\");
        assertThat(result.absolutePath()).startsWith(temporaryDirectory);
        assertThat(Files.readAllBytes(result.absolutePath())).isEqualTo(content);
        assertThat(result.sha256()).hasSize(64);
    }

    @Test
    void rejectsClientPathsAndMismatchedContentTypes() {
        SharedVolumeObjectStore store = new SharedVolumeObjectStore(properties());

        assertThatThrownBy(() -> store.store(
                1L,
                new MockMultipartFile(
                        "file",
                        "../secret.txt",
                        "text/plain",
                        "safe".getBytes(StandardCharsets.UTF_8)
                )
        )).isInstanceOf(ApiException.class)
                .extracting("code")
                .isEqualTo("INVALID_FILE_NAME");

        assertThatThrownBy(() -> store.store(
                1L,
                new MockMultipartFile(
                        "file",
                        "guide.pdf",
                        "application/pdf",
                        "not a pdf".getBytes(StandardCharsets.UTF_8)
                )
        )).isInstanceOf(ApiException.class)
                .extracting("code")
                .isEqualTo("INVALID_PDF");
    }

    private KnowledgeProperties properties() {
        KnowledgeProperties properties = new KnowledgeProperties();
        properties.setSharedRoot(temporaryDirectory.toString());
        return properties;
    }
}
