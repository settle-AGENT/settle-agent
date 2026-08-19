package com.settleagent.backend.card;

import com.settleagent.backend.persistence.AuditedEntity;
import com.settleagent.backend.persistence.StringListJsonConverter;
import com.settleagent.backend.user.UserEntity;
import jakarta.persistence.Column;
import jakarta.persistence.Convert;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.OneToOne;
import jakarta.persistence.Table;
import org.hibernate.annotations.OnDelete;
import org.hibernate.annotations.OnDeleteAction;

import java.time.LocalDate;
import java.util.List;

@Entity
@Table(name = "cards")
public class CardEntity extends AuditedEntity {

    @OneToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "user_id", nullable = false, unique = true)
    @OnDelete(action = OnDeleteAction.CASCADE)
    private UserEntity user;

    @Column(name = "name", nullable = false)
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

    @Convert(converter = StringListJsonConverter.class)
    @Column(name = "account_purposes", nullable = false, columnDefinition = "TEXT")
    private List<String> accountPurposes;

    protected CardEntity() {
    }

    public CardEntity(
        UserEntity user,
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
        List<String> accountPurposes
    ) {
        this.user = user;
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
        this.accountPurposes = List.copyOf(accountPurposes);
    }

    public UserEntity getUser() {
        return user;
    }

    public String getName() {
        return name;
    }

    public String getStayQualification() {
        return stayQualification;
    }

    public String getRegistrationNumberEncrypted() {
        return registrationNumberEncrypted;
    }

    public String getStayAddress() {
        return stayAddress;
    }

    public LocalDate getStayStartDate() {
        return stayStartDate;
    }

    public LocalDate getStayEndDate() {
        return stayEndDate;
    }

    public String getPassportNumberEncrypted() {
        return passportNumberEncrypted;
    }

    public LocalDate getPassportExpiresOn() {
        return passportExpiresOn;
    }

    public String getRegistrationFrontImageUrl() {
        return registrationFrontImageUrl;
    }

    public String getRegistrationBackImageUrl() {
        return registrationBackImageUrl;
    }

    public String getPassportImageUrl() {
        return passportImageUrl;
    }

    public List<String> getAccountPurposes() {
        return List.copyOf(accountPurposes);
    }
}
