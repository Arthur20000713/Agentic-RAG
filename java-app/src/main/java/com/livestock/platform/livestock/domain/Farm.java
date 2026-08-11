package com.livestock.platform.livestock.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;
import java.time.Instant;
import org.hibernate.annotations.CreationTimestamp;
import org.hibernate.annotations.UpdateTimestamp;

@Entity
@Table(name = "farm")
public class Farm {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "owner_id", nullable = false)
    private Long ownerId;

    @Column(name = "farm_code", nullable = false, length = 128)
    private String farmCode;

    @Column(length = 255)
    private String name;

    @Column(length = 255)
    private String location;

    @Version
    @Column(nullable = false)
    private long version;

    @CreationTimestamp
    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    @UpdateTimestamp
    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    protected Farm() {
    }

    public Long getId() { return id; }
    public Long getOwnerId() { return ownerId; }
    public String getFarmCode() { return farmCode; }
    public String getName() { return name; }
    public String getLocation() { return location; }
    public long getVersion() { return version; }
    public Instant getCreatedAt() { return createdAt; }
    public Instant getUpdatedAt() { return updatedAt; }
}
