package com.livestock.platform.livestock.repository;

import com.livestock.platform.livestock.domain.Animal;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface AnimalRepository extends JpaRepository<Animal, Long> {
    Optional<Animal> findByIdAndOwnerId(Long id, Long ownerId);
}
