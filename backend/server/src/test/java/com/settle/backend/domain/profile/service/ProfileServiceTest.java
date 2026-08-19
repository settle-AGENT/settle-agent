package com.settle.backend.domain.profile.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.settle.backend.domain.profile.client.AiProfileClient;
import com.settle.backend.domain.profile.dto.ProfileConfirmRequest;
import com.settle.backend.domain.profile.exception.ProfileValidationException;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.http.ResponseEntity;

class ProfileServiceTest {
    private final AiProfileClient aiProfileClient = mock(AiProfileClient.class);
    private final ProfileService profileService = new ProfileService(
            aiProfileClient,
            new ObjectMapper()
    );

    @Test
    void forwardsAJsonObjectStringWithoutChangingTheResponse() {
        ProfileConfirmRequest request = new ProfileConfirmRequest(
                "demo-001",
                "{\"nationality\":\"VNM\"}"
        );
        ResponseEntity<Map<String, Object>> upstream = ResponseEntity.ok(Map.of(
                "state", Map.of("profile", Map.of("nationality", "VNM")),
                "ui", Map.of("type", "question"),
                "reply", "다음 질문입니다."
        ));
        when(aiProfileClient.confirm(request)).thenReturn(upstream);

        ResponseEntity<Map<String, Object>> result = profileService.confirm(request);

        assertThat(result).isSameAs(upstream);
        verify(aiProfileClient).confirm(request);
    }

    @Test
    void acceptsAnEmptyJsonObjectWhenNoFieldWasEdited() {
        ProfileConfirmRequest request = new ProfileConfirmRequest("demo-001", "{}");
        when(aiProfileClient.confirm(request)).thenReturn(ResponseEntity.ok(Map.of()));

        profileService.confirm(request);

        verify(aiProfileClient).confirm(request);
    }

    @Test
    void rejectsMessageThatIsNotAJsonObjectString() {
        ProfileConfirmRequest request = new ProfileConfirmRequest(
                "demo-001",
                "[\"nationality\"]"
        );

        assertThatThrownBy(() -> profileService.confirm(request))
                .isInstanceOf(ProfileValidationException.class)
                .satisfies(exception -> assertThat(
                        ((ProfileValidationException) exception).getDetails()
                ).containsExactly(Map.of(
                        "field", "message",
                        "reason", "invalid_json_object_string"
                )));
    }
}
