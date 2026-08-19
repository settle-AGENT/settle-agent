package com.settle.backend.domain.document.client;

import com.settle.backend.domain.file.entity.DocumentType;
import java.util.Map;

public interface AiDocumentClient {

    Map<String, Object> extract(String objectKey, DocumentType documentType);
}
