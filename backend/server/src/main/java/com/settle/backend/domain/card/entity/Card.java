package com.settle.backend.domain.card.entity;

import com.settle.backend.domain.member.entity.Member;
import jakarta.persistence.CollectionTable;
import jakarta.persistence.Column;
import jakarta.persistence.ElementCollection;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.OneToOne;
import jakarta.persistence.PrePersist;
import jakarta.persistence.PreUpdate;
import jakarta.persistence.Table;
import java.time.Instant;
import java.time.LocalDate;
import java.util.HashSet;
import java.util.Set;
import java.util.UUID;

@Entity
@Table(name = "cards")
public class Card {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    @OneToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "user_id", nullable = false, unique = true)
    private Member member;

    @Column(nullable = false)
    private String name;

    @Column(name = "stay_qualification", nullable = false, length = 100)
    private String stayQualification;

    @Column(name = "registration_number_encrypted", nullable = false, columnDefinition = "TEXT")
    private String registrationNumberEncrypted;

    @Column(name = "stay_address", nullable = false, columnDefinition = "TEXT")
    private String stayAddress;

    @Column(name = "stay_start_date", nullable = false)
    private LocalDate stayStartDate;

    @Column(name = "stay_end_date", nullable = false)
    private LocalDate stayEndDate;

    @Column(name = "passport_number_encrypted", nullable = false, columnDefinition = "TEXT")
    private String passportNumberEncrypted;

    @Column(name = "passport_expires_on", nullable = false)
    private LocalDate passportExpiresOn;

    @Column(name = "registration_front_image_url", nullable = false, columnDefinition = "TEXT")
    private String registrationFrontImageUrl;

    @Column(name = "registration_back_image_url", nullable = false, columnDefinition = "TEXT")
    private String registrationBackImageUrl;

    @Column(name = "passport_image_url", nullable = false, columnDefinition = "TEXT")
    private String passportImageUrl;

    @ElementCollection(fetch = FetchType.EAGER)
    @CollectionTable(name = "card_account_purposes", joinColumns = @JoinColumn(name = "card_id"))
    @Enumerated(EnumType.STRING)
    @Column(name = "purpose", nullable = false, length = 50)
    private Set<AccountPurpose> accountPurposes = new HashSet<>();

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    protected Card() {
    }

    public Card(
            Member member,
            String name,
            String stayQualification,
            String registrationNumberEncrypted,
            String stayAddress,
            LocalDate stayStartDate,
            LocalDate stayEndDate,
            String passportNumberEncrypted,
            LocalDate passportExpiresOn,
            String registrationFrontImageUrl,
            String registrationBackImageUrl,
            String passportImageUrl,
            Set<AccountPurpose> accountPurposes
    ) {
        this.member = member;
        this.name = name;
        this.stayQualification = stayQualification;
        this.registrationNumberEncrypted = registrationNumberEncrypted;
        this.stayAddress = stayAddress;
        this.stayStartDate = stayStartDate;
        this.stayEndDate = stayEndDate;
        this.passportNumberEncrypted = passportNumberEncrypted;
        this.passportExpiresOn = passportExpiresOn;
        this.registrationFrontImageUrl = registrationFrontImageUrl;
        this.registrationBackImageUrl = registrationBackImageUrl;
        this.passportImageUrl = passportImageUrl;
        this.accountPurposes = new HashSet<>(accountPurposes);
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

    public String getStayQualification() {
        return stayQualification;
    }

    public Set<AccountPurpose> getAccountPurposes() {
        return Set.copyOf(accountPurposes);
    }
}
