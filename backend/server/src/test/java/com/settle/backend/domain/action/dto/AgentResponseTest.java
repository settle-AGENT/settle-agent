package com.settle.backend.domain.action.dto;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.settle.backend.domain.document.dto.DocumentPreviewPayload;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class AgentResponseTest {
    private final ObjectMapper objectMapper = new ObjectMapper();

    @Test
    void serializesDocPreviewAccordingToContract() {
        UUID documentId = UUID.fromString("47b7c5aa-4b10-4e10-93ec-c52d913cc2cd");
        DocumentPreviewPayload payload = new DocumentPreviewPayload(
                documentId,
                "계좌개설신청서",
                "/api/documents/%s/preview".formatted(documentId),
                "/api/documents/%s/download".formatted(documentId),
                List.of()
        );
        AgentResponse response = new AgentResponse(
                "1",
                "PDF를 생성했습니다.",
                new AgentResponse.Ui("doc_preview", payload),
                Map.of("session_id", "demo-001")
        );

        JsonNode json = objectMapper.valueToTree(response);

        assertThat(json.path("schema_version").asText()).isEqualTo("1");
        assertThat(json.path("ui").path("type").asText()).isEqualTo("doc_preview");
        assertThat(json.path("ui").path("payload").path("document_id").asText())
                .isEqualTo(documentId.toString());
        assertThat(json.path("ui").path("payload").path("warnings").isArray()).isTrue();
    }
}
