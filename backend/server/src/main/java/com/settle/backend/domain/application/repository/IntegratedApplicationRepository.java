package com.settle.backend.domain.application.repository;

import com.settle.backend.domain.application.entity.IntegratedApplication;
import java.util.List;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface IntegratedApplicationRepository extends JpaRepository<IntegratedApplication, UUID> {

    List<IntegratedApplication> findAllByMember_IdOrderByCreatedAtDesc(UUID memberId);
}
