package com.aigis.backend.controller;

import com.aigis.backend.model.dto.HelloResponse;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * REST Controller providing health check / initial connection endpoint for AIGIS.
 *
 * Annotations explained:
 * - @RestController: Combination of @Controller and @ResponseBody. Tells Spring that every method
 *   returns domain objects directly serialized to JSON (via Jackson) instead of rendering HTML templates.
 * - @RequestMapping: Defines base URL path prefix for all endpoints in this controller.
 */
@RestController
@RequestMapping("/hello")
public class HelloController {

    /**
     * GET /hello
     * Returns a structured JSON payload confirming backend operational status.
     *
     * ResponseEntity allows full control over HTTP response headers, status codes (200 OK), and body.
     */
    @GetMapping
    public ResponseEntity<HelloResponse> getHello() {
        HelloResponse response = HelloResponse.of("Hello from AIGIS Backend! Java Spring Boot 3 service is active.");
        return ResponseEntity.ok(response);
    }
}
