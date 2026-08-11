package com.livestock.platform.authorization;

import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.Set;
import java.util.stream.Stream;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;
import org.springframework.security.access.AccessDeniedException;

class OwnershipGuardTest {

    private final OwnershipGuard ownershipGuard = new OwnershipGuard();

    @ParameterizedTest(name = "{0} owner policy")
    @MethodSource("ownedResourcePolicies")
    void ownerWithOwnPermissionCanAccess(
            String resourceType,
            String ownAuthority,
            String allAuthority
    ) {
        assertThatCode(
                () -> ownershipGuard.requireOwnerOrAuthority(
                        "user-a",
                        "user-a",
                        Set.of(ownAuthority),
                        ownAuthority,
                        allAuthority
                )
        ).doesNotThrowAnyException();
    }

    @ParameterizedTest(name = "{0} cross-user policy")
    @MethodSource("ownedResourcePolicies")
    void crossUserWithoutAllPermissionIsDenied(
            String resourceType,
            String ownAuthority,
            String allAuthority
    ) {
        assertThatThrownBy(
                () -> ownershipGuard.requireOwnerOrAuthority(
                        "user-a",
                        "user-b",
                        Set.of(ownAuthority),
                        ownAuthority,
                        allAuthority
                )
        ).isInstanceOf(AccessDeniedException.class);
    }

    @Test
    void explicitAllPermissionCanReadAnotherUsersResource() {
        assertThatCode(
                () -> ownershipGuard.requireOwnerOrAuthority(
                        "auditor",
                        "user-b",
                        Set.of("CONVERSATION_READ_ALL"),
                        "CONVERSATION_READ_OWN",
                        "CONVERSATION_READ_ALL"
                )
        ).doesNotThrowAnyException();
    }

    @Test
    void ownershipAloneDoesNotReplaceTheOwnPermission() {
        assertThatThrownBy(
                () -> ownershipGuard.requireOwnerOrAuthority(
                        "user-a",
                        "user-a",
                        Set.of(),
                        "TASK_READ_OWN",
                        "TASK_MANAGE"
                )
        ).isInstanceOf(AccessDeniedException.class);
    }

    private static Stream<Arguments> ownedResourcePolicies() {
        return Stream.of(
                Arguments.of(
                        "conversation",
                        "CONVERSATION_READ_OWN",
                        "CONVERSATION_READ_ALL"
                ),
                Arguments.of("task", "TASK_READ_OWN", "TASK_MANAGE"),
                Arguments.of("document", "DOCUMENT_READ_OWN", "DOCUMENT_READ_ALL"),
                Arguments.of("animal", "ANIMAL_READ_OWN", "ANIMAL_READ_ALL")
        );
    }
}
