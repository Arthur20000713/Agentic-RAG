package com.livestock.platform.livestock.service;

import com.livestock.platform.common.error.ApiException;
import com.livestock.platform.livestock.domain.Animal;
import com.livestock.platform.livestock.domain.MeasurementRecord;
import com.livestock.platform.livestock.repository.AnimalRepository;
import com.livestock.platform.livestock.repository.MeasurementRecordRepository;
import com.livestock.platform.security.UserPrincipal;
import java.time.Clock;
import java.time.LocalDate;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.regex.Pattern;
import org.springframework.data.domain.PageRequest;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class LivestockSnapshotService {

    private static final Pattern BUSINESS_ID = Pattern.compile("^[A-Za-z0-9._:-]+$");
    private final AnimalRepository animalRepository;
    private final MeasurementRecordRepository measurementRepository;
    private final Clock clock;

    public LivestockSnapshotService(
            AnimalRepository animalRepository,
            MeasurementRecordRepository measurementRepository,
            Clock clock
    ) {
        this.animalRepository = animalRepository;
        this.measurementRepository = measurementRepository;
        this.clock = clock;
    }

    @Transactional(readOnly = true)
    public AuthorizedMeasurementSnapshot load(Long animalId, UserPrincipal actor) {
        Long actorId = Long.valueOf(actor.userId());
        Animal animal = actor.authorities().contains("TASK_MANAGE")
                ? animalRepository.findById(animalId).orElseThrow(LivestockSnapshotService::notFound)
                : animalRepository.findByIdAndOwnerId(animalId, actorId)
                        .orElseThrow(LivestockSnapshotService::notFound);
        validateProfile(animal);

        List<MeasurementRecord> newestFirst = measurementRepository
                .findByAnimalIdAndOwnerIdOrderByMeasureDateDescIdDesc(
                        animal.getId(),
                        animal.getOwnerId(),
                        PageRequest.of(0, 100)
                );
        List<MeasurementRecord> oldestFirst = new ArrayList<>(newestFirst);
        Collections.reverse(oldestFirst);
        List<AuthorizedMeasurementSnapshot.HistoryItem> history = oldestFirst.stream()
                .map(LivestockSnapshotService::toHistory)
                .toList();

        return new AuthorizedMeasurementSnapshot(
                animal.getId(),
                animal.getOwnerId(),
                animal.getAnimalCode(),
                animal.getSpecies().trim(),
                animal.getBreed(),
                animal.getSex(),
                animal.getBirthDate(),
                animal.getFarmId(),
                ageMonth(animal.getBirthDate()),
                history
        );
    }

    private void validateProfile(Animal animal) {
        if (animal.getAnimalCode() == null
                || !BUSINESS_ID.matcher(animal.getAnimalCode()).matches()
                || animal.getSpecies() == null
                || animal.getSpecies().isBlank()) {
            throw incompleteProfile();
        }
        if (animal.getBirthDate() != null
                && animal.getBirthDate().isAfter(LocalDate.now(clock))) {
            throw incompleteProfile();
        }
    }

    private Integer ageMonth(LocalDate birthDate) {
        if (birthDate == null) {
            return null;
        }
        return Math.toIntExact(ChronoUnit.MONTHS.between(birthDate, LocalDate.now(clock)));
    }

    private static AuthorizedMeasurementSnapshot.HistoryItem toHistory(
            MeasurementRecord record
    ) {
        return new AuthorizedMeasurementSnapshot.HistoryItem(
                record.getMeasureDate(),
                record.getBodyHeightCm(),
                record.getBodyLengthCm(),
                record.getChestGirthCm(),
                record.getChestDepthCm(),
                record.getChestWidthCm(),
                record.getWeightKg()
        );
    }

    private static ApiException notFound() {
        return new ApiException(
                HttpStatus.NOT_FOUND,
                "ANIMAL_NOT_FOUND",
                "The animal was not found"
        );
    }

    private static ApiException incompleteProfile() {
        return new ApiException(
                HttpStatus.CONFLICT,
                "ANIMAL_PROFILE_INCOMPLETE",
                "The animal profile is incomplete for AI analysis"
        );
    }
}
