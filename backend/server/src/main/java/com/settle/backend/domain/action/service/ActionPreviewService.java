package com.settle.backend.domain.action.service;

import com.settle.backend.common.auth.SessionOwnership;
import com.settle.backend.domain.action.client.AiActionClient;
import com.settle.backend.domain.action.dto.AgentResponse;
import com.settle.backend.domain.document.dto.DocumentPreviewPayload;
import com.settle.backend.domain.document.entity.GeneratedDocument;
import com.settle.backend.domain.document.service.GeneratedDocumentService;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;
import org.springframework.stereotype.Service;

@Service
public class ActionPreviewService {
    private final AiActionClient aiActionClient;
    private final GeneratedDocumentService documentService;

    public ActionPreviewService(
            AiActionClient aiActionClient,
            GeneratedDocumentService documentService
    ) {
        this.aiActionClient = aiActionClient;
        this.documentService = documentService;
    }

    public AgentResponse preview(UUID memberId, String actionId, String sessionId) {
        SessionOwnership.require(memberId, sessionId);
        AgentResponse aiResponse = aiActionClient.preview(actionId, sessionId);
        if (aiResponse.ui() == null || !"doc_preview".equals(aiResponse.ui().type())) {
            return withStoredDocuments(aiResponse, memberId, sessionId);
        }

        Map<String, Object> aiPayload = payloadMap(aiResponse.ui().payload());
        requiredText(aiPayload, "document_id");
        String title = requiredText(aiPayload, "title");
        byte[] pdf = aiActionClient.downloadPdf(requiredText(aiPayload, "pdf_url"));
        List<String> warnings = warnings(aiPayload.get("warnings"));
        GeneratedDocument document = documentService.storePdf(
                memberId,
                sessionId,
                actionId,
                title,
                pdf,
                warnings
        );

        UUID documentId = document.getId();
        DocumentPreviewPayload payload = new DocumentPreviewPayload(
                documentId,
                title,
                previewUrl(documentId),
                downloadUrl(documentId),
                warnings
        );
        Map<String, Object> state = documentState(aiResponse.state(), documentService.listReady(memberId, sessionId));
        return new AgentResponse(
                aiResponse.schemaVersion(),
                aiResponse.reply(),
                new AgentResponse.Ui("doc_preview", payload),
                state
        );
    }

    public synchronized AgentResponse approve(
            UUID memberId,
            String actionId,
            String sessionId,
            boolean approved
    ) {
        SessionOwnership.require(memberId, sessionId);
        AgentResponse current = aiActionClient.state(sessionId);
        Map<String, Object> pending = pendingApproval(current.state());
        if (pending == null) {
            if (alreadyExecuted(actionId, aiActionClient.ledger(sessionId)) || !approved) {
                return withStoredDocuments(current, memberId, sessionId);
            }
            throw new IllegalArgumentException("pending_approval_not_found");
        }
        Object pendingActionId = pending.get("action_id");
        if (!(pendingActionId instanceof String pendingAction) || pendingAction.isBlank()) {
            throw new IllegalArgumentException("invalid_pending_approval");
        }
        if (!actionId.equals(pendingAction)) {
            throw new IllegalArgumentException("approval_action_mismatch");
        }
        return withStoredDocuments(
                aiActionClient.approve(actionId, sessionId, approved),
                memberId,
                sessionId
        );
    }

    public List<Map<String, Object>> ledger(UUID memberId, String sessionId) {
        SessionOwnership.require(memberId, sessionId);
        return aiActionClient.ledger(sessionId);
    }

    private AgentResponse withStoredDocuments(AgentResponse response, UUID memberId, String sessionId) {
        return new AgentResponse(
                response.schemaVersion(),
                response.reply(),
                response.ui(),
                documentState(response.state(), documentService.listReady(memberId, sessionId))
        );
    }

    private Map<String, Object> documentState(
            Map<String, Object> source,
            List<GeneratedDocument> storedDocuments
    ) {
        Map<String, Object> state = new LinkedHashMap<>(source == null ? Map.of() : source);
        List<Map<String, Object>> documents = storedDocuments.stream()
                .map(this::documentReference)
                .toList();
        state.put("documents", documents);
        return state;
    }

    private Map<String, Object> documentReference(GeneratedDocument document) {
        Map<String, Object> reference = new LinkedHashMap<>();
        reference.put("id", document.getId().toString());
        reference.put("title", document.getTitle());
        reference.put("action_id", document.getActionId());
        reference.put("preview_url", previewUrl(document.getId()));
        reference.put("pdf_url", downloadUrl(document.getId()));
        reference.put("created_at", document.getCreatedAt());
        return reference;
    }

    private Map<String, Object> pendingApproval(Map<String, Object> state) {
        if (state == null || !(state.get("pending_approval") instanceof Map<?, ?> source)) {
            return null;
        }
        Map<String, Object> pending = new LinkedHashMap<>();
        source.forEach((key, value) -> pending.put(String.valueOf(key), value));
        return pending;
    }

    private boolean alreadyExecuted(String actionId, List<Map<String, Object>> ledger) {
        return ledger.stream().anyMatch(entry -> actionId.equals(entry.get("action")));
    }

    private Map<String, Object> payloadMap(Object payload) {
        if (!(payload instanceof Map<?, ?> source)) {
            throw new IllegalArgumentException("invalid_ai_doc_preview");
        }
        Map<String, Object> result = new LinkedHashMap<>();
        source.forEach((key, value) -> result.put(String.valueOf(key), value));
        return result;
    }

    private String requiredText(Map<String, Object> payload, String key) {
        Object value = payload.get(key);
        if (!(value instanceof String text) || text.isBlank()) {
            throw new IllegalArgumentException("invalid_ai_doc_preview");
        }
        return text;
    }

    private List<String> warnings(Object value) {
        if (!(value instanceof List<?> list)) {
            return List.of();
        }
        return list.stream().filter(Objects::nonNull).map(String::valueOf).toList();
    }

    private String previewUrl(UUID documentId) {
        return "/api/documents/%s/preview".formatted(documentId);
    }

    private String downloadUrl(UUID documentId) {
        return "/api/documents/%s/download".formatted(documentId);
    }
}
