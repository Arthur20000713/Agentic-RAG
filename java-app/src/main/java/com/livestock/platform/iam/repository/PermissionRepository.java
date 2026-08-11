package com.livestock.platform.iam.repository;

import com.livestock.platform.iam.domain.Permission;
import com.livestock.platform.iam.domain.PermissionCode;
import java.util.Collection;
import java.util.List;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface PermissionRepository extends JpaRepository<Permission, Long> {

    Optional<Permission> findByCode(PermissionCode code);

    List<Permission> findAllByCodeIn(Collection<PermissionCode> codes);
}
