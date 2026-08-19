package com.settleagent.backend.application;

import com.settleagent.backend.persistence.CreatedEntity;
import com.settleagent.backend.user.UserEntity;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import org.hibernate.annotations.OnDelete;
import org.hibernate.annotations.OnDeleteAction;

@Entity
@Table(name = "integrated_applications")
public class IntegratedApplicationEntity extends CreatedEntity {

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "user_id", nullable = false)
    @OnDelete(action = OnDeleteAction.CASCADE)
    private UserEntity user;

    @Column(name = "s3_url", nullable = false, columnDefinition = "TEXT")
    private String s3Url;

    protected IntegratedApplicationEntity() {
    }

    public IntegratedApplicationEntity(UserEntity user, String s3Url) {
        this.user = user;
        this.s3Url = s3Url;
    }

    public UserEntity getUser() {
        return user;
    }

    public String getS3Url() {
        return s3Url;
    }
}
