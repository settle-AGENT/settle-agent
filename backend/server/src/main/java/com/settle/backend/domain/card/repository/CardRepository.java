package com.settle.backend.domain.card.repository;

import com.settle.backend.domain.card.entity.Card;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CardRepository extends JpaRepository<Card, UUID> {

    Optional<Card> findByMember_Id(UUID memberId);

    boolean existsByMember_Id(UUID memberId);
}
