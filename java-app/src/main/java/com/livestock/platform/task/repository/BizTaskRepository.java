package com.livestock.platform.task.repository;

import com.livestock.platform.task.domain.BizTask;
import com.livestock.platform.task.domain.TaskStatus;
import com.livestock.platform.task.domain.TaskType;
import java.util.Collection;
import java.util.Optional;
import jakarta.persistence.LockModeType;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface BizTaskRepository extends JpaRepository<BizTask, Long> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select task from BizTask task where task.id = :id")
    Optional<BizTask> findByIdForUpdate(@Param("id") Long id);

    Optional<BizTask> findByIdAndOwnerId(Long id, Long ownerId);

    Optional<BizTask> findByOwnerIdAndOperationId(Long ownerId, String operationId);

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("""
            select task
            from BizTask task
            where task.ownerId = :ownerId and task.operationId = :operationId
            """)
    Optional<BizTask> findByOwnerIdAndOperationIdForUpdate(
            @Param("ownerId") Long ownerId,
            @Param("operationId") String operationId
    );

    Page<BizTask> findAllByOwnerId(Long ownerId, Pageable pageable);

    Page<BizTask> findAllByStatusIn(
            Collection<TaskStatus> statuses,
            Pageable pageable
    );

    Page<BizTask> findAllByTypeAndStatusIn(
            TaskType type,
            Collection<TaskStatus> statuses,
            Pageable pageable
    );
}
