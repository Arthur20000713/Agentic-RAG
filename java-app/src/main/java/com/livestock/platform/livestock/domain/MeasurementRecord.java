package com.livestock.platform.livestock.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
import org.hibernate.annotations.CreationTimestamp;

@Entity
@Table(name = "measurement_record")
public class MeasurementRecord {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "owner_id", nullable = false)
    private Long ownerId;

    @Column(name = "animal_id", nullable = false)
    private Long animalId;

    @Column(name = "measure_date", nullable = false)
    private LocalDate measureDate;

    @Column(name = "body_height_cm", precision = 12, scale = 3)
    private BigDecimal bodyHeightCm;

    @Column(name = "body_length_cm", precision = 12, scale = 3)
    private BigDecimal bodyLengthCm;

    @Column(name = "chest_girth_cm", precision = 12, scale = 3)
    private BigDecimal chestGirthCm;

    @Column(name = "chest_depth_cm", precision = 12, scale = 3)
    private BigDecimal chestDepthCm;

    @Column(name = "chest_width_cm", precision = 12, scale = 3)
    private BigDecimal chestWidthCm;

    @Column(name = "weight_kg", precision = 12, scale = 3)
    private BigDecimal weightKg;

    @Column(length = 64)
    private String source;

    @Column(precision = 5, scale = 4)
    private BigDecimal confidence;

    @Column(name = "algorithm_version", length = 128)
    private String algorithmVersion;

    @Column(name = "measurement_batch_id", length = 128)
    private String measurementBatchId;

    @Column(length = 1000)
    private String note;

    @CreationTimestamp
    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    protected MeasurementRecord() {
    }

    public Long getId() { return id; }
    public Long getOwnerId() { return ownerId; }
    public Long getAnimalId() { return animalId; }
    public LocalDate getMeasureDate() { return measureDate; }
    public BigDecimal getBodyHeightCm() { return bodyHeightCm; }
    public BigDecimal getBodyLengthCm() { return bodyLengthCm; }
    public BigDecimal getChestGirthCm() { return chestGirthCm; }
    public BigDecimal getChestDepthCm() { return chestDepthCm; }
    public BigDecimal getChestWidthCm() { return chestWidthCm; }
    public BigDecimal getWeightKg() { return weightKg; }
    public String getSource() { return source; }
    public BigDecimal getConfidence() { return confidence; }
    public String getAlgorithmVersion() { return algorithmVersion; }
    public String getMeasurementBatchId() { return measurementBatchId; }
    public String getNote() { return note; }
    public Instant getCreatedAt() { return createdAt; }
}
