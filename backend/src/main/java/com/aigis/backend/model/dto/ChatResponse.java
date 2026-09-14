package com.aigis.backend.model.dto;

import java.time.Instant;
import java.util.Map;

public record ChatResponse(
        String reply,
        String provider,
        Instant timestamp,
        String urlToOpen,
        boolean isOffline,
        String engine,
        String badge,
        boolean webSearchUsed,
        int latencyMs,
        Map<String, Object> metadata
) {
    public static ChatResponse of(String reply, String provider) {
        return new ChatResponse(reply, provider, Instant.now(), null, false, "local", "⚡ AIGIS", false, 0, Map.of());
    }

    public static ChatResponse of(String reply, String provider, String urlToOpen) {
        return new ChatResponse(reply, provider, Instant.now(), urlToOpen, false, "local", "⚡ AIGIS", false, 0, Map.of());
    }

    public static ChatResponse of(String reply, String provider, String urlToOpen, boolean isOffline) {
        return new ChatResponse(reply, provider, Instant.now(), urlToOpen, isOffline, isOffline ? "local" : "cloud", isOffline ? "⚡ AIGIS Local" : "☁ Cloud", false, 0, Map.of());
    }
}

