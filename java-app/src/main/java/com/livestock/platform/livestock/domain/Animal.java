package com.livestock.platform.livestock.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;
import java.time.Instant;
import java.time.LocalDate;
import org.hibernate.annotations.CreationTimestamp;
import org.hibernate.annotations.UpdateTimestamp;

@Entity
@Table(name = "animal")
public class Animal {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "owner_id", nullable = false)
    private Long ownerId;

    @Column(name = "farm_id")
    private Long farmId;

    @Column(name = "animal_code", nullable = false, length = 128)
    private String animalCode;

    @Column(length = 64)
    private String species;

    @Column(length = 128)
    private String breed;

    @Column(length = 32)
    private String sex;

    @Column(name = "birth_date")
    private LocalDate birthDate;

    @Column(length = 1000)
    private String note;

    @Version
    @Column(nullable = false)
    private long version;

    @CreationTimestamp
    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    @UpdateTimestamp
    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    protected Animal() {
    }

    public Long getId() { return id; }
    public Long getOwnerId() { return ownerId; }
    public Long getFarmId() { return farmId; }
    public String getAnimalCode() { return animalCode; }
    public String getSpecies() { return species; }
    public String getBreed() { return breed; }
    public String getSex() { return sex; }
    public LocalDate getBirthDate() { return birthDate; }
    public String getNote() { return note; }
    public long getVersion() { return version; }
    public Instant getCreatedAt() { return createdAt; }
    public Instant getUpdatedAt() { return updatedAt; }
}
