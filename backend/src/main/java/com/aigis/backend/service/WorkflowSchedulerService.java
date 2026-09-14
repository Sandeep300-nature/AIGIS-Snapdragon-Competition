package com.aigis.backend.service;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

import java.util.Map;

/**
 * Independent Workflow Scheduler Automation Service for AIGIS.
 * Completely separate and decoupled from the User Reminder System.
 * Manages automated scheduled jobs: Morning Briefing, Daily Digest, Weekly Maintenance, System Health Audit.
 */
@Service
public class WorkflowSchedulerService {

    private static final Logger log = LoggerFactory.getLogger(WorkflowSchedulerService.class);

    private final RestClient restClient;
    private final String pythonAiEngineUrl;

    public WorkflowSchedulerService(
            RestClient restClient,
            @Value("${aigis.ai.python-engine.url:http://localhost:8000/ai/generate}") String pythonAiEngineUrl
    ) {
        this.restClient = restClient;
        this.pythonAiEngineUrl = pythonAiEngineUrl;
    }

    /**
     * Automated Morning Briefing Job - Runs daily at 8:00 AM.
     */
    @Scheduled(cron = "0 0 8 * * *")
    public void triggerMorningBriefing() {
        log.info("[WORKFLOW SCHEDULER] Triggering Automated Morning Briefing Job...");
        executeJob("morning briefing");
    }

    /**
     * Automated Daily Digest Job - Runs daily at 8:00 PM.
     */
    @Scheduled(cron = "0 0 20 * * *")
    public void triggerDailyDigest() {
        log.info("[WORKFLOW SCHEDULER] Triggering Automated Daily Digest Job...");
        executeJob("daily digest");
    }

    /**
     * Automated Weekly Maintenance Cleanup - Runs every Sunday at 12:00 AM.
     */
    @Scheduled(cron = "0 0 0 * * SUN")
    public void triggerWeeklyCleanup() {
        log.info("[WORKFLOW SCHEDULER] Triggering Automated Weekly Maintenance Cleanup Job...");
        executeJob("weekly cleanup");
    }

    /**
     * Automated System Health Report - Runs every 6 hours.
     */
    @Scheduled(fixedRate = 21600000)
    public void triggerSystemHealthReport() {
        log.info("[WORKFLOW SCHEDULER] Executing Automated System Health Audit...");
        executeJob("system report");
    }

    public Map<?, ?> executeJob(String jobPrompt) {
        try {
            Map<String, String> payload = Map.of(
                    "prompt", jobPrompt,
                    "sessionId", "workflow-scheduled-jobs"
            );

            return restClient.post()
                    .uri(pythonAiEngineUrl)
                    .body(payload)
                    .retrieve()
                    .body(Map.class);
        } catch (Exception e) {
            log.error("[WORKFLOW SCHEDULER ERROR] Failed to execute job '{}': {}", jobPrompt, e.getMessage());
            return Map.of("error", e.getMessage());
        }
    }
}
