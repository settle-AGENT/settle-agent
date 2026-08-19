package com.settle.backend.domain.document.client;

import com.settle.backend.domain.file.entity.DocumentType;
import java.util.Map;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.client.RestClient;

@Component
public class HttpAiDocumentClient implements AiDocumentClient {
    private final RestClient restClient;

    public HttpAiDocumentClient(@Qualifier("aiRestClient") RestClient restClient) {
        this.restClient = restClient;
    }

    @Override
    public Map<String, Object> extract(String sessionId, byte[] image, DocumentType documentType) {
        ByteArrayResource file = new ByteArrayResource(image) {
            @Override
            public String getFilename() {
                return documentType.name() + ".png";
            }
        };
        MultiValueMap<String, Object> body = new LinkedMultiValueMap<>();
        body.add("session_id", sessionId);
        body.add("doc_type", documentType.name());
        body.add("file", file);

        return restClient.post()
                .uri("/api/profile/extract-upload")
                .contentType(MediaType.MULTIPART_FORM_DATA)
                .body(body)
                .retrieve()
                .body(new ParameterizedTypeReference<>() {
                });
    }
}
