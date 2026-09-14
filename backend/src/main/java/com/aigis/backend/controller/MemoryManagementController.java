package com.aigis.backend.controller;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.client.RestClient;

import java.util.List;
import java.util.Map;

/**
 * REST Controller exposing Memory Dashboard & Management Endpoints for AIGIS.
 * Provides Facts, Preferences, Long-Term Memories, and Recent Memories dashboard views,
 * search, edit, delete, pin, export, and import capabilities.
 */
@RestController
@RequestMapping("/api/v1/memory-dashboard")
@CrossOrigin(originPatterns = "*")
public class MemoryManagementController {

    private final RestClient restClient;
    private final String pythonAiEngineUrl;

    public MemoryManagementController(
            RestClient restClient,
            @Value("${aigis.ai.python-engine.url:http://localhost:8000/ai/generate}") String pythonAiEngineUrl
    ) {
        this.restClient = restClient;
        this.pythonAiEngineUrl = pythonAiEngineUrl;
    }

    @GetMapping
    public ResponseEntity<Map<?, ?>> getDashboard(@RequestParam(required = false) String query) {
        String url = pythonAiEngineUrl.replace("/ai/generate", "/api/v1/memory/dashboard");
        if (query != null && !query.isBlank()) {
            url += "?query=" + query;
        }
        Map<?, ?> response = restClient.get().uri(url).retrieve().body(Map.class);
        return ResponseEntity.ok(response != null ? response : Map.of());
    }

    @PostMapping("/update")
    public ResponseEntity<Map<?, ?>> updateMemory(@RequestBody Map<String, Object> body) {
        String url = pythonAiEngineUrl.replace("/ai/generate", "/api/v1/memory/update");
        Map<?, ?> response = restClient.post().uri(url).body(body).retrieve().body(Map.class);
        return ResponseEntity.ok(response != null ? response : Map.of());
    }

    @PostMapping("/delete")
    public ResponseEntity<Map<?, ?>> deleteMemory(@RequestBody Map<String, String> body) {
        String url = pythonAiEngineUrl.replace("/ai/generate", "/api/v1/memory/delete");
        Map<?, ?> response = restClient.post().uri(url).body(body).retrieve().body(Map.class);
        return ResponseEntity.ok(response != null ? response : Map.of());
    }

    @PostMapping("/pin")
    public ResponseEntity<Map<?, ?>> pinMemory(@RequestBody Map<String, Object> body) {
        String url = pythonAiEngineUrl.replace("/ai/generate", "/api/v1/memory/pin");
        Map<?, ?> response = restClient.post().uri(url).body(body).retrieve().body(Map.class);
        return ResponseEntity.ok(response != null ? response : Map.of());
    }

    @GetMapping("/export")
    public ResponseEntity<Map<?, ?>> exportMemories() {
        String url = pythonAiEngineUrl.replace("/ai/generate", "/api/v1/memory/export");
        Map<?, ?> response = restClient.get().uri(url).retrieve().body(Map.class);
        return ResponseEntity.ok(response != null ? response : Map.of());
    }

    @PostMapping("/import")
    public ResponseEntity<Map<?, ?>> importMemories(@RequestBody List<Map<String, Object>> body) {
        String url = pythonAiEngineUrl.replace("/ai/generate", "/api/v1/memory/import");
        Map<?, ?> response = restClient.post().uri(url).body(body).retrieve().body(Map.class);
        return ResponseEntity.ok(response != null ? response : Map.of());
    }
}
