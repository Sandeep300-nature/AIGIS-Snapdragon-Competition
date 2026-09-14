package com.aigis.backend.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

/**
 * Spring Configuration defining the RestClient bean for HTTP outbound calls.
 * RestClient is Spring Boot 3.2+'s modern fluent HTTP client.
 */
@Configuration
public class RestClientConfig {

    @Bean
    public RestClient restClient(RestClient.Builder builder) {
        return builder.build();
    }
}
