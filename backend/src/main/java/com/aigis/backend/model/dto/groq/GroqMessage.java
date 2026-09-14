package com.aigis.backend.model.dto.groq;

public record GroqMessage(
        String role,
        String content
) {}
