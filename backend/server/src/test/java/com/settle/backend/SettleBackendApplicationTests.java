package com.settle.backend;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.when;

import com.settle.backend.domain.file.service.S3FileGateway;
import com.settle.backend.domain.auth.service.JwtTokenService;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

@SpringBootTest
@AutoConfigureMockMvc
class SettleBackendApplicationTests {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private JwtTokenService jwtTokenService;

    @MockitoBean
    private S3FileGateway s3FileGateway;

    @Test
    void healthCheck() throws Exception {
        mockMvc.perform(get("/health"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("ok"));
    }

    @Test
    void publishesAgentV1OpenApiContractWithBearerSecurity() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.info.version").value("1"))
                .andExpect(jsonPath("$.components.securitySchemes.bearerAuth.type").value("http"))
                .andExpect(jsonPath("$['paths']['/api/session']['post']['security'][0].bearerAuth").isArray())
                .andExpect(jsonPath("$['paths']['/api/profile/confirm']['post']['responses']['403']").exists())
                .andExpect(jsonPath("$['paths']['/api/v1/documents/extractions']['post']['responses']['415']").exists())
                .andExpect(jsonPath("$['paths']['/api/v1/uploads']['post']['responses']['401']").exists());
    }

    @Test
    void createsPngUpload() throws Exception {
        when(s3FileGateway.createPngUploadUrl(anyString(), any()))
                .thenReturn("https://s3.example.test/upload");

        mockMvc.perform(post("/api/v1/uploads")
                        .header("Authorization", "Bearer " + jwtTokenService.issue(
                                UUID.randomUUID(), "user@example.com"
                        ))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "documentType": "passport"
                                }
                                """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.uploadId").isString())
                .andExpect(jsonPath("$.uploadUrl").value("https://s3.example.test/upload"))
                .andExpect(jsonPath("$.expiresInSeconds").value(300));
    }

    @Test
    void rejectsUploadWithoutToken() throws Exception {
        mockMvc.perform(post("/api/v1/uploads")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"documentType": "passport"}
                                """))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.detail.error").value("invalid_or_missing_token"));
    }
}
