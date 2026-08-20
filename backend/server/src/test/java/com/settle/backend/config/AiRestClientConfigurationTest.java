package com.settle.backend.config;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.settle.backend.domain.profile.client.HttpAiProfileClient;
import com.settle.backend.domain.profile.dto.ProfileConfirmRequest;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.ResponseEntity;
import org.springframework.web.client.RestClient;

class AiRestClientConfigurationTest {
    private final ObjectMapper objectMapper = new ObjectMapper();
    private HttpServer server;

    @AfterEach
    void stopServer() {
        if (server != null) {
            server.stop(0);
        }
    }

    @Test
    void sendsProfileConfirmBodyOverHttp11() throws Exception {
        AtomicReference<String> protocol = new AtomicReference<>();
        AtomicReference<String> contentType = new AtomicReference<>();
        AtomicReference<byte[]> requestBody = new AtomicReference<>();
        startServer(protocol, contentType, requestBody);

        RestClient restClient = new AiRestClientConfiguration().aiRestClient(
                RestClient.builder(),
                "http://127.0.0.1:" + server.getAddress().getPort(),
                5,
                120
        );
        HttpAiProfileClient client = new HttpAiProfileClient(restClient);

        ResponseEntity<java.util.Map<String, Object>> response = client.confirm(
                new ProfileConfirmRequest("demo-001", "{}")
        );

        JsonNode json = objectMapper.readTree(requestBody.get());
        assertThat(protocol.get()).isEqualTo("HTTP/1.1");
        assertThat(contentType.get()).startsWith("application/json");
        assertThat(json.get("session_id").asText()).isEqualTo("demo-001");
        assertThat(json.get("message").asText()).isEqualTo("{}");
        assertThat(response.getStatusCode().value()).isEqualTo(200);
    }

    private void startServer(
            AtomicReference<String> protocol,
            AtomicReference<String> contentType,
            AtomicReference<byte[]> requestBody
    ) throws IOException {
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/api/profile/confirm", exchange -> {
            protocol.set(exchange.getProtocol());
            contentType.set(exchange.getRequestHeaders().getFirst("Content-Type"));
            requestBody.set(exchange.getRequestBody().readAllBytes());

            byte[] response = "{\"ok\":true}".getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set("Content-Type", "application/json");
            exchange.sendResponseHeaders(200, response.length);
            exchange.getResponseBody().write(response);
            exchange.close();
        });
        server.start();
    }
}
