package com.settleagent.backend.user;

import com.settleagent.backend.persistence.AuditedEntity;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Table;

@Entity
@Table(name = "users")
public class UserEntity extends AuditedEntity {

    @Column(name = "email", nullable = false, unique = true, length = 320)
    private String email;

    @Column(name = "nickname", nullable = false, unique = true, length = 100)
    private String nickname;

    @Column(name = "password_hash", nullable = false, columnDefinition = "TEXT")
    private String passwordHash;

    @Column(name = "language", nullable = false, length = 20)
    private String language;

    @Column(name = "visa_type", nullable = false, length = 50)
    private String visaType;

    @Column(name = "nationality", nullable = false, length = 100)
    private String nationality;

    protected UserEntity() {
    }

    public UserEntity(
        String email,
        String nickname,
        String passwordHash,
        String language,
        String visaType,
        String nationality
    ) {
        this.email = email;
        this.nickname = nickname;
        this.passwordHash = passwordHash;
        this.language = language;
        this.visaType = visaType;
        this.nationality = nationality;
    }

    public String getEmail() {
        return email;
    }

    public String getNickname() {
        return nickname;
    }

    public String getPasswordHash() {
        return passwordHash;
    }

    public String getLanguage() {
        return language;
    }

    public String getVisaType() {
        return visaType;
    }

    public String getNationality() {
        return nationality;
    }

    public void updateProfile(String nickname, String language, String visaType, String nationality) {
        this.nickname = nickname;
        this.language = language;
        this.visaType = visaType;
        this.nationality = nationality;
    }

    public void changePasswordHash(String passwordHash) {
        this.passwordHash = passwordHash;
    }
}
