package com.aigis.backend.model.dto.groq;

import java.util.List;

public record GroqChatRequest(
        String model,
        List<GroqMessage> messages,
        double temperature
) {
    public static GroqChatRequest of(String model, String userPrompt) {
        GroqMessage systemMsg = new GroqMessage("system", "You are AIGIS, a witty AI assistant inspired by FRIDAY from Iron Man. Always call the user 'sir'. Be humorous with dry wit and clever quips, but always accurate and helpful. Keep it concise and punchy.");
        GroqMessage userMsg = new GroqMessage("user", userPrompt);
        return new GroqChatRequest(model, List.of(systemMsg, userMsg), 0.7);
    }

    public static GroqChatRequest of(String model, List<GroqMessage> messages) {
        return new GroqChatRequest(model, messages, 0.7);
    }
}
