package com.livestock.platform.iam.repository;

import com.livestock.platform.iam.domain.UserAccount;
import java.util.Optional;
import jakarta.persistence.LockModeType;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import com.livestock.platform.iam.domain.RoleCode;
import com.livestock.platform.iam.domain.UserStatus;

public interface UserAccountRepository extends JpaRepository<UserAccount, Long> {

    @EntityGraph(attributePaths = {"roles", "roles.permissions"})
    Optional<UserAccount> findByUsernameIgnoreCase(String username);

    @EntityGraph(attributePaths = {"roles", "roles.permissions"})
    Optional<UserAccount> findOneById(Long id);

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select user from UserAccount user where user.id = :id")
    Optional<UserAccount> findByIdForUpdate(@Param("id") Long id);

    @Override
    @EntityGraph(attributePaths = {"roles", "roles.permissions"})
    Page<UserAccount> findAll(Pageable pageable);

    @Query("""
            select count(distinct user.id)
            from UserAccount user
            join user.roles role
            where user.status = :status and role.code = :roleCode
            """)
    long countByStatusAndRoleCode(
            @Param("status") UserStatus status,
            @Param("roleCode") RoleCode roleCode
    );

    boolean existsByUsernameIgnoreCase(String username);
}
