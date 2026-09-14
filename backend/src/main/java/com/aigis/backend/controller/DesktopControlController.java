package com.aigis.backend.controller;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.client.RestClient;

import java.util.Map;

/**
 * REST Controller exposing Desktop Action Control Endpoints for AIGIS.
 * Provides authorized action execution (apps, volume, folders, power state confirmation).
 */
@RestController
@RequestMapping("/api/v1/desktop")
@CrossOrigin(originPatterns = "*")
public class DesktopControlController {

    private final RestClient restClient;
    private final String pythonAiEngineUrl;

    public DesktopControlController(
            RestClient restClient,
            @Value("${aigis.ai.python-engine.url:http://localhost:8000/ai/generate}") String pythonAiEngineUrl
    ) {
        this.restClient = restClient;
        this.pythonAiEngineUrl = pythonAiEngineUrl;
    }

    @PostMapping("/action")
    public ResponseEntity<Map<?, ?>> executeAction(@RequestBody Map<String, String> request) {
        String prompt = request.getOrDefault("action", request.getOrDefault("prompt", ""));
        String sessionId = request.getOrDefault("sessionId", "default-session");

        try {
            Map<String, String> payload = Map.of(
                    "prompt", prompt,
                    "sessionId", sessionId
            );

            Map<?, ?> response = restClient.post()
                    .uri(pythonAiEngineUrl)
                    .body(payload)
                    .retrieve()
                    .body(Map.class);

            return ResponseEntity.ok(response != null ? response : Map.of("reply", "No response from desktop control service."));
        } catch (Exception e) {
            return ResponseEntity.internalServerError().body(Map.of("error", "Failed to execute desktop action: " + e.getMessage()));
        }
    }
}
