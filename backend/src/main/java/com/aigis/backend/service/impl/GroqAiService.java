package com.aigis.backend.service.impl;

import com.aigis.backend.model.domain.ChatMessage;
import com.aigis.backend.model.dto.groq.GroqChatRequest;
import com.aigis.backend.model.dto.groq.GroqChatResponse;
import com.aigis.backend.model.dto.groq.GroqMessage;
import com.aigis.backend.service.AiService;
import com.aigis.backend.service.ConversationMemoryService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Primary;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * Implementation of AiService using Python AI Engine (with Tavily Web Access, Search & RAG)
 * and Groq API (llama-3.3-70b-versatile) fallback.
 */
@Service
@Primary
public class GroqAiService implements AiService {

    private static final Logger log = LoggerFactory.getLogger(GroqAiService.class);
    
    private static final String SYSTEM_PROMPT = "You are Aegis, a real-time AI companion designed to assist naturally. " +
            "Your primary job is not just to answer questions, but to be an active conversational partner. " +
            "Respond like a human partner would — not overly verbose, not terse. " +
            "Understand interruptions, filler words, side questions, and corrections. " +
            "Pause and resume tasks naturally. Use natural phrasing, rhythm, and composure. " +
            "Offer suggestions only when genuinely useful. Always keep the current task in mind, but handle interruptions gracefully. " +
            "Address the user as 'sir' with a loyal, witty, and sharp persona like FRIDAY.";

    private final RestClient restClient;
    private final ConversationMemoryService memoryService;
    private final String pythonAiEngineUrl;
    private final String apiKey;
    private final String apiUrl;
    private final String model;

    private String lastActiveProvider = "Groq (llama-3.3-70b-versatile)";

    public GroqAiService(
            RestClient restClient,
            ConversationMemoryService memoryService,
            @Value("${aigis.ai.python-engine.url:http://localhost:8000/ai/generate}") String pythonAiEngineUrl,
            @Value("${aigis.ai.groq.api-key}") String apiKey,
            @Value("${aigis.ai.groq.url}") String apiUrl,
            @Value("${aigis.ai.groq.model}") String model
    ) {
        this.restClient = restClient;
        this.memoryService = memoryService;
        this.pythonAiEngineUrl = pythonAiEngineUrl;
        this.apiKey = apiKey;
        this.apiUrl = apiUrl;
        this.model = model;
    }

    @Override
    public com.aigis.backend.model.dto.ChatResponse generateChatResponse(String sessionId, String prompt, String responseLanguage) {
        log.info("Processing prompt [sessionId={}, lang={}, model={}]: {}", sessionId, responseLanguage, model, prompt);

        // 1. First, attempt to route to Python AI Engine (Port 8000) for Tavily Web Access, Search & RAG
        try {
            log.info("Routing request to Python AI Engine at {}", pythonAiEngineUrl);
            Map<String, String> pythonReqPayload = Map.of(
                    "prompt", prompt,
                    "sessionId", sessionId,
                    "model", "groq",
                    "responseLanguage", responseLanguage != null ? responseLanguage : "en"
            );

            Map<?, ?> response = restClient.post()
                    .uri(pythonAiEngineUrl)
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(pythonReqPayload)
                    .retrieve()
                    .body(Map.class);

            if (response != null && response.containsKey("reply")) {
                String reply = (String) response.get("reply");
                String provider = response.containsKey("provider") && response.get("provider") != null
                        ? (String) response.get("provider")
                        : this.lastActiveProvider;
                this.lastActiveProvider = provider;

                String urlToOpen = response.get("urlToOpen") != null ? response.get("urlToOpen").toString() : null;
                boolean isOffline = Boolean.TRUE.equals(response.get("isOffline"));
                Object engineObj = response.get("engine");
                String engine = engineObj != null ? engineObj.toString() : (isOffline ? "local" : "cloud");
                Object badgeObj = response.get("badge");
                String badge = badgeObj != null ? badgeObj.toString() : (isOffline ? "⚡ AIGIS Local" : "☁ Cloud");
                boolean webSearchUsed = Boolean.TRUE.equals(response.get("webSearchUsed"));
                int latencyMs = response.containsKey("latencyMs") && response.get("latencyMs") instanceof Number n
                        ? n.intValue()
                        : 0;
                @SuppressWarnings("unchecked")
                Map<String, Object> metadata = response.get("metadata") instanceof Map<?, ?> m
                        ? (Map<String, Object>) m
                        : Map.of();

                log.info("Successfully received reply from Python AI Engine (provider={}, engine={})", provider, engine);
                return new com.aigis.backend.model.dto.ChatResponse(
                        reply,
                        provider,
                        java.time.Instant.now(),
                        urlToOpen,
                        isOffline,
                        engine,
                        badge,
                        webSearchUsed,
                        latencyMs,
                        metadata
                );
            }
        } catch (Exception e) {
            log.warn("Python AI Engine unavailable or failed ({}), falling back to direct Groq API execution...", e.getMessage());
        }


        // 2. Fallback: Direct Groq API Execution
        long startFallback = System.currentTimeMillis();
        List<ChatMessage> history = memoryService.getHistory(sessionId);

        // Check if user requested opening a common website directly
        String targetUrl = detectWebsiteShortcutUrl(prompt);

        List<GroqMessage> messages = new ArrayList<>();
        String systemInstruction = SYSTEM_PROMPT;
        if (targetUrl != null) {
            systemInstruction += "\n[ACTION REQUIREMENT: User requested to open website '" + targetUrl + "'. Confirm politely that you are opening it.]";
        }

        messages.add(new GroqMessage("system", systemInstruction));

        for (ChatMessage msg : history) {
            messages.add(new GroqMessage(msg.role(), msg.content()));
        }
        messages.add(new GroqMessage("user", prompt));

        GroqChatRequest requestPayload = GroqChatRequest.of(model, messages);

        try {
            GroqChatResponse response = restClient.post()
                    .uri(apiUrl)
                    .header("Authorization", "Bearer " + apiKey)
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(requestPayload)
                    .retrieve()
                    .body(GroqChatResponse.class);

            int elapsed = (int) (System.currentTimeMillis() - startFallback);

            if (response != null) {
                String reply = response.extractContent();
                if (targetUrl != null && !reply.contains("[OPEN_URL:")) {
                    reply = reply.strip() + "\n\n[OPEN_URL: " + targetUrl + "]";
                }

                log.info("Received successful fallback response from Groq API (length={} chars)", reply.length());

                // Save user prompt & assistant response to conversation memory
                memoryService.addMessage(sessionId, ChatMessage.user(prompt));
                memoryService.addMessage(sessionId, ChatMessage.assistant(reply));

                this.lastActiveProvider = "Groq (" + model + ")";
                return new com.aigis.backend.model.dto.ChatResponse(
                        reply,
                        this.lastActiveProvider,
                        java.time.Instant.now(),
                        targetUrl,
                        false,
                        "cloud",
                        "☁️ Groq AI",
                        false,
                        elapsed,
                        Map.of("intent", "general_ai", "routingMode", "fallback_cloud")
                );
            } else {
                log.warn("Received empty response payload from Groq API");
                return new com.aigis.backend.model.dto.ChatResponse(
                        "Groq AI did not return a response.",
                        "Groq (" + model + ")",
                        java.time.Instant.now(),
                        null,
                        false,
                        "cloud",
                        "☁️ Groq AI",
                        false,
                        elapsed,
                        Map.of("error", "Empty response")
                );
            }

        } catch (Exception e) {
            int elapsed = (int) (System.currentTimeMillis() - startFallback);
            log.error("Failed to communicate with Groq API: {}", e.getMessage(), e);
            return new com.aigis.backend.model.dto.ChatResponse(
                    "Error calling Groq AI Service: " + e.getMessage(),
                    "Groq (Error)",
                    java.time.Instant.now(),
                    null,
                    false,
                    "cloud",
                    "☁️ Groq AI (Error)",
                    false,
                    elapsed,
                    Map.of("error", e.getMessage() != null ? e.getMessage() : "Unknown error")
            );
        }
    }

    @Override
    public String generateResponse(String sessionId, String prompt, String responseLanguage) {
        return generateChatResponse(sessionId, prompt, responseLanguage).reply();
    }

    @Override
    public String getProviderName() {
        return lastActiveProvider != null ? lastActiveProvider : ("Groq (" + model + ")");
    }


    private String detectWebsiteShortcutUrl(String prompt) {
        if (prompt == null) return null;
        String p = prompt.toLowerCase().trim();
        if (p.contains("open youtube") || p.contains("youtube.com")) return "https://www.youtube.com";
        if (p.contains("open google") || p.contains("google.com")) return "https://www.google.com";
        if (p.contains("open github") || p.contains("github.com")) return "https://www.github.com";
        if (p.contains("open twitter") || p.contains("open x")) return "https://x.com";
        if (p.contains("open reddit") || p.contains("reddit.com")) return "https://www.reddit.com";
        if (p.contains("open wikipedia")) return "https://www.wikipedia.org";
        return null;
    }
}
