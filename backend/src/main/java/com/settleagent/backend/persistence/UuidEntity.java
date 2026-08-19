package com.settleagent.backend.persistence;

import jakarta.persistence.Column;
import jakarta.persistence.Id;
import jakarta.persistence.MappedSuperclass;
import jakarta.persistence.PrePersist;

import java.util.UUID;

@MappedSuperclass
public abstract class UuidEntity {

    @Id
    @Column(name = "id", nullable = false, length = 36)
    private String id;

    @PrePersist
    protected void assignId() {
        if (id == null) {
            id = UUID.randomUUID().toString();
        }
    }

    public String getId() {
        return id;
    }
}
