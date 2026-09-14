package com.aigis.backend.service;

/**
 * Standard interface for AI Provider Services in AIGIS.
 * Provides abstraction across different LLM backends (Groq, Gemini, Ollama).
 */
public interface AiService {

    /**
     * Generates an AI response for the given user prompt within a specific conversation session and response language.
     *
     * @param sessionId The session identifier for maintaining conversation memory
     * @param prompt The input text prompt from user/speech transcript
     * @param responseLanguage Language code ('en', 'hi', etc.)
     * @return Generated AI text response
     */
    String generateResponse(String sessionId, String prompt, String responseLanguage);

    /**
     * Generates an AI response for the given user prompt within a specific conversation session.
     *
     * @param sessionId The session identifier for maintaining conversation memory
     * @param prompt The input text prompt from user/speech transcript
     * @return Generated AI text response
     */
    default String generateResponse(String sessionId, String prompt) {
        return generateResponse(sessionId, prompt, "en");
    }

    /**
     * Generates an AI response for the given user prompt using default session.
     *
     * @param prompt The input text prompt from user/speech transcript
     * @return Generated AI text response
     */
    default String generateResponse(String prompt) {
        return generateResponse("default-session", prompt, "en");
    }

    /**
     * Returns the name and model of the active AI provider.
     */
    String getProviderName();

    /**
     * Generates a full ChatResponse with provider metadata.
     */
    default com.aigis.backend.model.dto.ChatResponse generateChatResponse(String sessionId, String prompt, String responseLanguage) {
        String reply = generateResponse(sessionId, prompt, responseLanguage);
        return com.aigis.backend.model.dto.ChatResponse.of(reply, getProviderName());
    }
}

