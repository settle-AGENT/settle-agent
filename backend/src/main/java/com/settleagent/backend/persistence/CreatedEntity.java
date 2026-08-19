package com.settleagent.backend.persistence;

import jakarta.persistence.Column;
import jakarta.persistence.MappedSuperclass;
import jakarta.persistence.PrePersist;

import java.time.Instant;

@MappedSuperclass
public abstract class CreatedEntity extends UuidEntity {

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    @PrePersist
    protected void assignCreatedAt() {
        if (createdAt == null) {
            createdAt = Instant.now();
        }
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
