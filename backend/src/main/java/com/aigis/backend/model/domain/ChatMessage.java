package com.aigis.backend.model.domain;

import java.time.Instant;

/**
 * Domain model representing a single message in a conversation history turn.
 */
public record ChatMessage(
        String role,     // "user" or "assistant"
        String content,  // Text payload
        Instant timestamp
) {
    public static ChatMessage user(String content) {
        return new ChatMessage("user", content, Instant.now());
    }

    public static ChatMessage assistant(String content) {
        return new ChatMessage("assistant", content, Instant.now());
    }
}
