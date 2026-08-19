package com.settle.backend.domain.profile.client;

import com.settle.backend.domain.profile.dto.ProfileConfirmRequest;
import java.util.Map;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class HttpAiProfileClient implements AiProfileClient {
    private final RestClient restClient;

    public HttpAiProfileClient(
            RestClient.Builder builder,
            @Value("${settle.ai.base-url}") String baseUrl
    ) {
        this.restClient = builder.baseUrl(baseUrl).build();
    }

    @Override
    public ResponseEntity<Map<String, Object>> confirm(ProfileConfirmRequest request) {
        return restClient.post()
                .uri("/api/profile/confirm")
                .body(request)
                .exchange((upstreamRequest, upstreamResponse) -> {
                    Map<String, Object> body = upstreamResponse.bodyTo(
                            new ParameterizedTypeReference<>() {
                            }
                    );
                    return ResponseEntity.status(upstreamResponse.getStatusCode()).body(body);
                });
    }
}
