package com.aigis.backend.controller;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.client.RestTemplate;

import java.util.HashMap;
import java.util.Map;

/**
 * Controller responsible for negotiating ephemeral client tokens for OpenAI Realtime API sessions.
 * Guarantees zero key exposure — permanent OpenAI API keys remain strictly server-side.
 */
@RestController
@RequestMapping("/api/v1/realtime")
@CrossOrigin(origins = "*")
public class RealtimeSessionController {

    @Value("${aigis.ai.openai.api-key:}")
    private String openAiApiKey;

    @Value("${aigis.ai.openai.realtime-model:gpt-4o-realtime-preview}")
    private String realtimeModel;

    @Value("${aigis.ai.openai.voice:alloy}")
    private String realtimeVoice;

    private final RestTemplate restTemplate = new RestTemplate();

    @PostMapping("/session")
    public ResponseEntity<Map<String, Object>> createRealtimeSession() {
        Map<String, Object> responseMap = new HashMap<>();

        if (openAiApiKey == null || openAiApiKey.trim().isEmpty() || openAiApiKey.contains("placeholder")) {
            responseMap.put("realtimeAvailable", false);
            responseMap.put("reason", "OPENAI_API_KEY is not configured on the backend server.");
            responseMap.put("fallbackMode", true);
            return ResponseEntity.ok(responseMap);
        }

        try {
            HttpHeaders headers = new HttpHeaders();
            headers.setContentType(MediaType.APPLICATION_JSON);
            headers.setBearerAuth(openAiApiKey.trim());

            Map<String, Object> requestBody = new HashMap<>();
            requestBody.put("model", realtimeModel);
            requestBody.put("voice", realtimeVoice);

            HttpEntity<Map<String, Object>> entity = new HttpEntity<>(requestBody, headers);

            ResponseEntity<Map> openAiResponse = restTemplate.exchange(
                "https://api.openai.com/v1/realtime/sessions",
                HttpMethod.POST,
                entity,
                Map.class
            );

            if (openAiResponse.getStatusCode().is2xxSuccessful() && openAiResponse.getBody() != null) {
                Map body = openAiResponse.getBody();
                responseMap.put("realtimeAvailable", true);
                responseMap.put("clientSecret", body.get("client_secret"));
                responseMap.put("model", realtimeModel);
                responseMap.put("voice", realtimeVoice);
                responseMap.put("session", body);
                return ResponseEntity.ok(responseMap);
            } else {
                responseMap.put("realtimeAvailable", false);
                responseMap.put("reason", "Failed to negotiate session with OpenAI Realtime endpoint.");
                responseMap.put("fallbackMode", true);
                return ResponseEntity.ok(responseMap);
            }
        } catch (Exception e) {
            responseMap.put("realtimeAvailable", false);
            responseMap.put("reason", "Realtime auth exception: " + e.getMessage());
            responseMap.put("fallbackMode", true);
            return ResponseEntity.ok(responseMap);
        }
    }

    @GetMapping("/config")
    public ResponseEntity<Map<String, Object>> getRealtimeConfig() {
        Map<String, Object> config = new HashMap<>();
        boolean isConfigured = openAiApiKey != null && !openAiApiKey.trim().isEmpty() && !openAiApiKey.contains("placeholder");
        config.put("configured", isConfigured);
        config.put("model", realtimeModel);
        config.put("voice", realtimeVoice);
        return ResponseEntity.ok(config);
    }
}
