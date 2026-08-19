package com.settleagent.backend;

import com.settleagent.backend.application.AccountOpeningApplicationEntity;
import com.settleagent.backend.application.AccountOpeningApplicationRepository;
import com.settleagent.backend.application.IntegratedApplicationEntity;
import com.settleagent.backend.application.IntegratedApplicationRepository;
import com.settleagent.backend.card.CardEntity;
import com.settleagent.backend.card.CardRepository;
import com.settleagent.backend.user.UserEntity;
import com.settleagent.backend.user.UserRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.dao.DataIntegrityViolationException;

import java.time.LocalDate;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@DataJpaTest(properties = {
    "spring.flyway.enabled=false",
    "spring.jpa.hibernate.ddl-auto=create-drop",
    "spring.jpa.properties.hibernate.default_schema=PUBLIC"
})
class PersistenceIntegrationTest {

    @Autowired
    private UserRepository userRepository;

    @Autowired
    private CardRepository cardRepository;

    @Autowired
    private AccountOpeningApplicationRepository accountOpeningApplicationRepository;

    @Autowired
    private IntegratedApplicationRepository integratedApplicationRepository;

    @Test
    void repositoriesPersistAllFourModelsAndJsonPurposes() {
        UserEntity user = userRepository.saveAndFlush(new UserEntity(
            "student@example.com",
            "settler",
            "$2a$12$hashed-password",
            "ko",
            "D-2",
            "VN"
        ));

        CardEntity card = cardRepository.saveAndFlush(new CardEntity(
            user,
            "NGUYEN VAN A",
            "D-2-2",
            "encrypted-registration-number",
            "Seoul",
            LocalDate.of(2026, 3, 1),
            LocalDate.of(2027, 2, 28),
            "encrypted-passport-number",
            LocalDate.of(2030, 12, 31),
            "s3://documents/arc-front.enc",
            "s3://documents/arc-back.enc",
            "s3://documents/passport.enc",
            List.of("TUITION", "LIVING")
        ));

        accountOpeningApplicationRepository.saveAndFlush(
            new AccountOpeningApplicationEntity(user, "s3://applications/account-opening.pdf")
        );
        integratedApplicationRepository.saveAndFlush(
            new IntegratedApplicationEntity(user, "s3://applications/integrated.pdf")
        );

        assertThat(card.getId()).isNotNull();
        assertThat(cardRepository.findByUser_Id(user.getId()).orElseThrow().getAccountPurposes())
            .containsExactly("TUITION", "LIVING");
        assertThat(accountOpeningApplicationRepository.findAllByUser_IdOrderByCreatedAtDesc(user.getId()))
            .hasSize(1);
        assertThat(integratedApplicationRepository.findAllByUser_IdOrderByCreatedAtDesc(user.getId()))
            .hasSize(1);
    }

    @Test
    void emailAndNicknameAreUnique() {
        userRepository.saveAndFlush(new UserEntity(
            "unique@example.com", "unique-nickname", "hash", "en", "D-4", "US"
        ));

        assertThatThrownBy(() -> userRepository.saveAndFlush(new UserEntity(
            "unique@example.com", "different-nickname", "hash", "en", "D-4", "US"
        ))).isInstanceOf(DataIntegrityViolationException.class);
    }
}
