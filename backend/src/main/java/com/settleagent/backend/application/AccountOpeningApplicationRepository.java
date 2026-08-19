package com.settleagent.backend.application;

import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface AccountOpeningApplicationRepository
    extends JpaRepository<AccountOpeningApplicationEntity, String> {

    List<AccountOpeningApplicationEntity> findAllByUser_IdOrderByCreatedAtDesc(String userId);
}
