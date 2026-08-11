package com.livestock.platform.iam.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.JoinTable;
import jakarta.persistence.ManyToMany;
import jakarta.persistence.Table;
import jakarta.persistence.Version;
import java.time.Instant;
import java.util.Collection;
import java.util.Collections;
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;
import org.hibernate.annotations.CreationTimestamp;
import org.hibernate.annotations.UpdateTimestamp;

@Entity
@Table(name = "sys_user")
public class UserAccount {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "username", nullable = false, unique = true, length = 64)
    private String username;

    @Column(name = "password_hash", nullable = false, length = 100)
    private String passwordHash;

    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false, length = 16)
    private UserStatus status;

    @Column(name = "security_version", nullable = false)
    private long securityVersion;

    @Version
    @Column(name = "version", nullable = false)
    private long version;

    @ManyToMany(fetch = FetchType.LAZY)
    @JoinTable(
            name = "sys_user_role",
            joinColumns = @JoinColumn(name = "user_id"),
            inverseJoinColumns = @JoinColumn(name = "role_id")
    )
    private Set<Role> roles = new HashSet<>();

    @CreationTimestamp
    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    @UpdateTimestamp
    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    protected UserAccount() {
    }

    public UserAccount(String username, String passwordHash) {
        this.username = Objects.requireNonNull(username, "username");
        this.passwordHash = Objects.requireNonNull(passwordHash, "passwordHash");
        this.status = UserStatus.ENABLED;
    }

    public void changeStatus(UserStatus nextStatus) {
        UserStatus requiredStatus = Objects.requireNonNull(nextStatus, "nextStatus");
        if (status != requiredStatus) {
            status = requiredStatus;
            securityVersion++;
        }
    }

    public void replaceRoles(Collection<Role> nextRoles) {
        Set<Role> requiredRoles = new HashSet<>(
                Objects.requireNonNull(nextRoles, "nextRoles")
        );
        if (!roles.equals(requiredRoles)) {
            roles.clear();
            roles.addAll(requiredRoles);
            securityVersion++;
        }
    }

    public Long getId() {
        return id;
    }

    public String getUsername() {
        return username;
    }

    public String getPasswordHash() {
        return passwordHash;
    }

    public UserStatus getStatus() {
        return status;
    }

    public long getSecurityVersion() {
        return securityVersion;
    }

    public long getVersion() {
        return version;
    }

    public Set<Role> getRoles() {
        return Collections.unmodifiableSet(roles);
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public Instant getUpdatedAt() {
        return updatedAt;
    }
}
