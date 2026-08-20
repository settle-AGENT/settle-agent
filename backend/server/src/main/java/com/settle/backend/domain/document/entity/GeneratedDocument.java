package com.settle.backend.domain.document.entity;

import com.settle.backend.domain.member.entity.Member;
import jakarta.persistence.Column;
import jakarta.persistence.Convert;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.PrePersist;
import jakarta.persistence.PreUpdate;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import java.time.Instant;
import java.util.List;
import java.util.UUID;

@Entity
@Table(
        name = "generated_documents",
        uniqueConstraints = @UniqueConstraint(
                name = "uk_generated_document_object_key",
                columnNames = "object_key"
        )
)
public class GeneratedDocument {

    @Id
    private UUID id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "user_id", nullable = false)
    private Member member;

    @Column(name = "session_id", nullable = false, length = 100)
    private String sessionId;

    @Column(name = "action_id", nullable = false, length = 100)
    private String actionId;

    @Column(nullable = false, length = 200)
    private String title;

    @Column(name = "object_key", nullable = false, length = 1024)
    private String objectKey;

    @Convert(converter = StringListJsonConverter.class)
    @Column(name = "warnings_json", nullable = false, columnDefinition = "TEXT")
    private List<String> warnings = List.of();

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private GeneratedDocumentStatus status;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    protected GeneratedDocument() {
    }

    public GeneratedDocument(
            UUID id,
            Member member,
            String sessionId,
            String actionId,
            String title,
            String objectKey
    ) {
        this.id = id;
        this.member = member;
        this.sessionId = sessionId;
        this.actionId = actionId;
        this.title = title;
        this.objectKey = objectKey;
        this.status = GeneratedDocumentStatus.GENERATING;
    }

    public void markReady(List<String> warnings) {
        this.warnings = List.copyOf(warnings == null ? List.of() : warnings);
        this.status = GeneratedDocumentStatus.READY;
    }

    public void markFailed() {
        this.status = GeneratedDocumentStatus.FAILED;
    }

    public void markIssued() {
        this.status = GeneratedDocumentStatus.ISSUED;
    }

    @PrePersist
    void initializeTimestamps() {
        Instant now = Instant.now();
        createdAt = now;
        updatedAt = now;
    }

    @PreUpdate
    void updateTimestamp() {
        updatedAt = Instant.now();
    }

    public UUID getId() {
        return id;
    }

    public Member getMember() {
        return member;
    }

    public String getSessionId() {
        return sessionId;
    }

    public String getActionId() {
        return actionId;
    }

    public String getTitle() {
        return title;
    }

    public String getObjectKey() {
        return objectKey;
    }

    public List<String> getWarnings() {
        return List.copyOf(warnings);
    }

    public GeneratedDocumentStatus getStatus() {
        return status;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public Instant getUpdatedAt() {
        return updatedAt;
    }

}
