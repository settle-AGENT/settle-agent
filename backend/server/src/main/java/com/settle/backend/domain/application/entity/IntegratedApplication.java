package com.settle.backend.domain.application.entity;

import com.settle.backend.domain.member.entity.Member;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.PrePersist;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "integrated_applications")
public class IntegratedApplication {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "user_id", nullable = false)
    private Member member;

    @Column(name = "s3_url", nullable = false, columnDefinition = "TEXT")
    private String s3Url;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    protected IntegratedApplication() {
    }

    public IntegratedApplication(Member member, String s3Url) {
        this.member = member;
        this.s3Url = s3Url;
    }

    @PrePersist
    void initializeCreatedAt() {
        createdAt = Instant.now();
    }
}
