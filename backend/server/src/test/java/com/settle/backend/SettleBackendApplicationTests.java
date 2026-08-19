package com.settle.backend;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.when;

import com.settle.backend.domain.file.service.S3FileGateway;
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

    @MockitoBean
    private S3FileGateway s3FileGateway;

    @Test
    void healthCheck() throws Exception {
        mockMvc.perform(get("/health"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("ok"));
    }

    @Test
    void createsPngUpload() throws Exception {
        when(s3FileGateway.createPngUploadUrl(anyString(), any()))
                .thenReturn("https://s3.example.test/upload");

        mockMvc.perform(post("/api/v1/uploads")
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
}
