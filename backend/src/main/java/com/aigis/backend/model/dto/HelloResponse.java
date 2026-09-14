package com.aigis.backend.model.dto;

import java.time.Instant;

/**
 * Data Transfer Object (DTO) for the /hello endpoint response.
 * Using Java record ensures immutability, zero boilerplate, and automatic JSON serialization by Jackson.
 */
public record HelloResponse(
        String message,
        String status,
        Instant timestamp
) {
    public static HelloResponse of(String message) {
        return new HelloResponse(message, "SUCCESS", Instant.now());
    }
}
