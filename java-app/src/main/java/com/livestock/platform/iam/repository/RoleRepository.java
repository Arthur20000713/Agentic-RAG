package com.livestock.platform.iam.repository;

import com.livestock.platform.iam.domain.Role;
import com.livestock.platform.iam.domain.RoleCode;
import java.util.Collection;
import java.util.List;
import java.util.Optional;
import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;

public interface RoleRepository extends JpaRepository<Role, Long> {

    @EntityGraph(attributePaths = "permissions")
    Optional<Role> findByCode(RoleCode code);

    @EntityGraph(attributePaths = "permissions")
    List<Role> findAllByCodeIn(Collection<RoleCode> codes);
}
