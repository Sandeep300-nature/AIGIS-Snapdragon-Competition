package com.aigis.backend.controller;

import com.aigis.backend.model.domain.ChatMessage;
import com.aigis.backend.model.dto.ChatRequest;
import com.aigis.backend.model.dto.ChatResponse;
import com.aigis.backend.service.AiService;
import com.aigis.backend.service.ConversationMemoryService;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

/**
 * REST Controller exposing Chat API endpoints with Database Conversation Memory support for AIGIS.
 */
@RestController
@RequestMapping("/api/v1/chat")
@CrossOrigin(originPatterns = "*")
public class ChatController {

    private final AiService aiService;
    private final ConversationMemoryService memoryService;

    public ChatController(AiService aiService, ConversationMemoryService memoryService) {
        this.aiService = aiService;
        this.memoryService = memoryService;
    }

    /**
     * POST /api/v1/chat
     * Receives a user prompt or speech transcript, forwards it to Groq AI with session history,
     * persists conversation memory to Database, and returns structured AI response.
     */
    @PostMapping
    public ResponseEntity<ChatResponse> chat(@RequestBody ChatRequest request) {
        if (request == null || request.prompt() == null || request.prompt().isBlank()) {
            return ResponseEntity.badRequest()
                    .body(ChatResponse.of("Prompt cannot be empty.", aiService.getProviderName()));
        }

        String sessionId = request.getEffectiveSessionId();
        String responseLanguage = request.getEffectiveResponseLanguage();
        ChatResponse response = aiService.generateChatResponse(sessionId, request.prompt(), responseLanguage);

        return ResponseEntity.ok(response);
    }

    /**
     * GET /api/v1/chat/history/{sessionId}
     * Retrieves persisted conversation memory history from Database for the given session.
     */
    @GetMapping("/history/{sessionId}")
    public ResponseEntity<List<ChatMessage>> getHistory(@PathVariable String sessionId) {
        List<ChatMessage> history = memoryService.getHistory(sessionId);
        return ResponseEntity.ok(history);
    }

    /**
     * POST /api/v1/chat/clear
     * Clears conversation memory history for the given session ID.
     */
    @PostMapping("/clear")
    public ResponseEntity<Map<String, String>> clearMemory(@RequestBody Map<String, String> body) {
        String sessionId = body.getOrDefault("sessionId", "default-session");
        memoryService.clearMemory(sessionId);
        return ResponseEntity.ok(Map.of("message", "Conversation memory cleared for session: " + sessionId));
    }
}
