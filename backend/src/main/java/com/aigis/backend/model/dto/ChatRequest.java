package com.aigis.backend.model.dto;

public record ChatRequest(
        String prompt,
        String sessionId,
        String responseLanguage
) {
    public String getEffectiveSessionId() {
        return (sessionId == null || sessionId.isBlank()) ? "default-session" : sessionId.trim();
    }

    public String getEffectiveResponseLanguage() {
        return (responseLanguage == null || responseLanguage.isBlank()) ? "en" : responseLanguage.trim();
    }
}

