package com.settle.backend.domain.agent.client;

import static org.assertj.core.api.Assertions.assertThat;

import com.settle.backend.config.AiRestClientConfiguration;
import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.ResponseEntity;
import org.springframework.web.client.RestClient;

class HttpAiAgentClientTest {
    private HttpServer server;

    @AfterEach
    void stopServer() {
        if (server != null) {
            server.stop(0);
        }
    }

    @Test
    void createsSessionWithQueryParametersAndForwardsEnvelope() throws Exception {
        AtomicReference<String> query = new AtomicReference<>();
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/api/session", exchange -> {
            query.set(exchange.getRequestURI().getRawQuery());
            byte[] response = "{\"state\":{\"session_id\":\"member-id\"}}"
                    .getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set("Content-Type", "application/json");
            exchange.sendResponseHeaders(200, response.length);
            exchange.getResponseBody().write(response);
            exchange.close();
        });
        server.start();
        HttpAiAgentClient client = client();

        ResponseEntity<Map<String, Object>> response = client.createSession("member-id", "ko", false, null);

        assertThat(query.get()).isEqualTo("session_id=member-id&locale=ko&reset=false");
        assertThat(response.getStatusCode().value()).isEqualTo(200);
        assertThat(response.getBody()).containsKey("state");
    }

    @Test
    void forwardsUpstreamFailureStatusAndBody() throws Exception {
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/api/session", exchange -> {
            byte[] response = "{\"detail\":{\"error\":\"internal\"}}"
                    .getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set("Content-Type", "application/json");
            exchange.sendResponseHeaders(503, response.length);
            exchange.getResponseBody().write(response);
            exchange.close();
        });
        server.start();

        ResponseEntity<Map<String, Object>> response = client().createSession(
                UUID.randomUUID().toString(), "ko", false, null
        );

        assertThat(response.getStatusCode().value()).isEqualTo(503);
        assertThat(response.getBody()).containsKey("detail");
    }

    private HttpAiAgentClient client() {
        RestClient restClient = new AiRestClientConfiguration().aiRestClient(
                RestClient.builder(),
                "http://127.0.0.1:" + server.getAddress().getPort(),
                5,
                120
        );
        return new HttpAiAgentClient(restClient);
    }
}
