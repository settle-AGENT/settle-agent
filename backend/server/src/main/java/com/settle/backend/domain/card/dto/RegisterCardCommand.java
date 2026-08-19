package com.settle.backend.domain.card.dto;

import com.settle.backend.domain.card.entity.AccountPurpose;
import java.time.LocalDate;
import java.util.Set;

public record RegisterCardCommand(
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
}
