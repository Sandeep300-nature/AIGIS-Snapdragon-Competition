package com.aigis.backend.controller;

import com.aigis.backend.service.WorkflowSchedulerService;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

/**
 * REST Controller exposing independent Workflow Scheduler endpoints for AIGIS.
 * Completely separate from Reminder API.
 */
@RestController
@RequestMapping("/api/v1/workflows")
@CrossOrigin(originPatterns = "*")
public class WorkflowSchedulerController {

    private final WorkflowSchedulerService workflowService;

    public WorkflowSchedulerController(WorkflowSchedulerService workflowService) {
        this.workflowService = workflowService;
    }

    @PostMapping("/trigger")
    public ResponseEntity<Map<?, ?>> triggerWorkflow(@RequestBody Map<String, String> body) {
        String job = body.getOrDefault("job", "morning briefing");
        Map<?, ?> result = workflowService.executeJob(job);
        return ResponseEntity.ok(result);
    }
}
