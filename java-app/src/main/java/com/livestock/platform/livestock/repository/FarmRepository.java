package com.livestock.platform.livestock.repository;

import com.livestock.platform.livestock.domain.Farm;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface FarmRepository extends JpaRepository<Farm, Long> {
    Optional<Farm> findByIdAndOwnerId(Long id, Long ownerId);
}
