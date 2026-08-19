package com.settle.backend.domain.member.entity;

import java.time.Instant;
import java.util.UUID;

public record Member(
        UUID id,
        String email,
        String passwordHash,
        Instant createdAt
) {
}
