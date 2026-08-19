package com.settleagent.backend.persistence;

import jakarta.persistence.Column;
import jakarta.persistence.MappedSuperclass;
import jakarta.persistence.PrePersist;
import jakarta.persistence.PreUpdate;

import java.time.Instant;

@MappedSuperclass
public abstract class AuditedEntity extends CreatedEntity {

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    @PrePersist
    protected void assignUpdatedAt() {
        updatedAt = Instant.now();
    }

    @PreUpdate
    protected void updateTimestamp() {
        updatedAt = Instant.now();
    }

    public Instant getUpdatedAt() {
        return updatedAt;
    }
}
