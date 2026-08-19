package com.settleagent.backend.application;

import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface IntegratedApplicationRepository
    extends JpaRepository<IntegratedApplicationEntity, String> {

    List<IntegratedApplicationEntity> findAllByUser_IdOrderByCreatedAtDesc(String userId);
}
