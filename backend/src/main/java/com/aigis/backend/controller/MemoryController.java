package com.aigis.backend.controller;

import com.aigis.backend.model.domain.ChatMessage;
import com.aigis.backend.service.ConversationMemoryService;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

/**
 * REST Controller exposing memory management endpoints (/api/memory) for AIGIS.
 * Exposes Spring Boot's H2 Database memory to Python AI Engine and React Frontend via HTTP REST.
 */
@RestController
@RequestMapping("/api/memory")
@CrossOrigin(originPatterns = "*")
public class MemoryController {

    private final ConversationMemoryService memoryService;

    public MemoryController(ConversationMemoryService memoryService) {
        this.memoryService = memoryService;
    }

    /**
     * GET /api/memory?sessionId=...
     * Returns past conversation messages for the session from Spring Boot H2 Database.
     */
    @GetMapping
    public ResponseEntity<List<ChatMessage>> getMemory(@RequestParam(defaultValue = "default-session") String sessionId) {
        List<ChatMessage> history = memoryService.getHistory(sessionId);
        return ResponseEntity.ok(history);
    }

    /**
     * POST /api/memory
     * Stores a new message (role: user/assistant, content, sessionId) into Spring Boot H2 Database.
     */
    @PostMapping
    public ResponseEntity<Map<String, String>> addMemory(@RequestBody MemoryRecordDTO record) {
        if (record == null || record.content() == null || record.content().isBlank()) {
            return ResponseEntity.badRequest().body(Map.of("error", "Content cannot be empty"));
        }
        
        String role = (record.role() == null || record.role().isBlank()) ? "user" : record.role();
        String sessionId = (record.sessionId() == null || record.sessionId().isBlank()) ? "default-session" : record.sessionId();

        if ("assistant".equalsIgnoreCase(role)) {
            memoryService.addMessage(sessionId, ChatMessage.assistant(record.content()));
        } else {
            memoryService.addMessage(sessionId, ChatMessage.user(record.content()));
        }

        return ResponseEntity.ok(Map.of(
                "status", "success",
                "message", "Message persisted to Spring Boot H2 Database",
                "sessionId", sessionId
        ));
    }

    /**
     * DELETE /api/memory?sessionId=...
     * Clears memory history for the specified session from Spring Boot H2 Database.
     */
    @DeleteMapping
    public ResponseEntity<Map<String, String>> clearMemory(@RequestParam(defaultValue = "default-session") String sessionId) {
        memoryService.clearMemory(sessionId);
        return ResponseEntity.ok(Map.of(
                "status", "success",
                "message", "Memory cleared from H2 Database for session: " + sessionId
        ));
    }

    public record MemoryRecordDTO(String sessionId, String role, String content) {}
}
