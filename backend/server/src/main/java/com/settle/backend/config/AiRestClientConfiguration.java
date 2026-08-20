package com.settle.backend.config;

import java.net.http.HttpClient;
import java.time.Duration;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

@Configuration
public class AiRestClientConfiguration {

    @Bean("aiRestClient")
    public RestClient aiRestClient(
            RestClient.Builder builder,
            @Value("${settle.ai.base-url}") String baseUrl,
            @Value("${settle.ai.connect-timeout-seconds:5}") long connectTimeoutSeconds,
            @Value("${settle.ai.read-timeout-seconds:120}") long readTimeoutSeconds
    ) {
        HttpClient httpClient = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_1_1)
                .connectTimeout(Duration.ofSeconds(connectTimeoutSeconds))
                .build();
        JdkClientHttpRequestFactory requestFactory = new JdkClientHttpRequestFactory(httpClient);
        requestFactory.setReadTimeout(Duration.ofSeconds(readTimeoutSeconds));

        return builder
                .requestFactory(requestFactory)
                .baseUrl(baseUrl)
                .build();
    }
}
