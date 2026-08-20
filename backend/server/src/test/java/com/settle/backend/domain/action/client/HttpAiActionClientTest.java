package com.settle.backend.domain.action.client;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatIllegalArgumentException;

import org.junit.jupiter.api.Test;

class HttpAiActionClientTest {

    @Test
    void acceptsOnlyAiDocumentPdfPath() {
        String path = "/api/documents/4da08524-open_bank_account.pdf";

        assertThat(HttpAiActionClient.requirePdfPath(path)).isEqualTo(path);
    }

    @Test
    void rejectsOtherRelativeAndAbsoluteUrls() {
        for (String url : new String[]{
                "/api/state",
                "/other/document.pdf",
                "//example.com/document.pdf",
                "https://example.com/document.pdf"
        }) {
            assertThatIllegalArgumentException()
                    .isThrownBy(() -> HttpAiActionClient.requirePdfPath(url))
                    .withMessage("invalid_ai_pdf_url");
        }
    }
}
