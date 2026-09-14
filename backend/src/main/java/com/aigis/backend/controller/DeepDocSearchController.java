package com.aigis.backend.controller;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.client.RestClient;

import java.util.Map;

/**
 * REST Controller exposing Deep Document Search & Indexing Endpoints for AIGIS.
 * Completely distinct and separate from Memory and Conversation History.
 */
@RestController
@RequestMapping("/api/v1/docs")
@CrossOrigin(originPatterns = "*")
public class DeepDocSearchController {

    private final RestClient restClient;
    private final String pythonAiEngineUrl;

    public DeepDocSearchController(
            RestClient restClient,
            @Value("${aigis.ai.python-engine.url:http://localhost:8000/ai/generate}") String pythonAiEngineUrl
    ) {
        this.restClient = restClient;
        this.pythonAiEngineUrl = pythonAiEngineUrl;
    }

    @PostMapping("/index-file")
    public ResponseEntity<Map<?, ?>> indexFile(@RequestBody Map<String, String> body) {
        String path = body.getOrDefault("path", "");
        String url = pythonAiEngineUrl.replace("/ai/generate", "/api/v1/docs/index-file");
        Map<?, ?> response = restClient.post().uri(url).body(Map.of("path", path)).retrieve().body(Map.class);
        return ResponseEntity.ok(response != null ? response : Map.of());
    }

    @PostMapping("/index-directory")
    public ResponseEntity<Map<?, ?>> indexDirectory(@RequestBody Map<String, String> body) {
        String path = body.getOrDefault("path", "");
        String url = pythonAiEngineUrl.replace("/ai/generate", "/api/v1/docs/index-directory");
        Map<?, ?> response = restClient.post().uri(url).body(Map.of("path", path)).retrieve().body(Map.class);
        return ResponseEntity.ok(response != null ? response : Map.of());
    }

    @PostMapping("/search")
    public ResponseEntity<Map<?, ?>> searchDocs(@RequestBody Map<String, Object> body) {
        String url = pythonAiEngineUrl.replace("/ai/generate", "/api/v1/docs/search");
        Map<?, ?> response = restClient.post().uri(url).body(body).retrieve().body(Map.class);
        return ResponseEntity.ok(response != null ? response : Map.of());
    }

    @GetMapping("/list")
    public ResponseEntity<Map<?, ?>> listDocs() {
        String url = pythonAiEngineUrl.replace("/ai/generate", "/api/v1/docs/list");
        Map<?, ?> response = restClient.get().uri(url).retrieve().body(Map.class);
        return ResponseEntity.ok(response != null ? response : Map.of());
    }
}
