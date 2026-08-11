package com.livestock.platform.livestock.repository;

import com.livestock.platform.livestock.domain.MeasurementRecord;
import java.util.List;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

public interface MeasurementRecordRepository extends JpaRepository<MeasurementRecord, Long> {
    List<MeasurementRecord> findByAnimalIdAndOwnerIdOrderByMeasureDateDescIdDesc(
            Long animalId,
            Long ownerId,
            Pageable pageable
    );
}
