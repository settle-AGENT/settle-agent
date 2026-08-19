package com.settle.backend.domain.application.repository;

import com.settle.backend.domain.application.entity.AccountOpeningApplication;
import java.util.List;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface AccountOpeningApplicationRepository
        extends JpaRepository<AccountOpeningApplication, UUID> {

    List<AccountOpeningApplication> findAllByMember_IdOrderByCreatedAtDesc(UUID memberId);
}
