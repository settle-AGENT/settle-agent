package com.settleagent.backend.card;

import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;

public interface CardRepository extends JpaRepository<CardEntity, String> {

    Optional<CardEntity> findByUser_Id(String userId);
}
