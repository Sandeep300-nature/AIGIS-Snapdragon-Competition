package com.aigis.backend.controller;

import com.aigis.backend.model.entity.AppSettingsEntity;
import com.aigis.backend.model.entity.UserPreferencesEntity;
import com.aigis.backend.model.entity.UserProfileEntity;
import com.aigis.backend.repository.AppSettingsRepository;
import com.aigis.backend.repository.UserPreferencesRepository;
import com.aigis.backend.repository.UserProfileRepository;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;

/**
 * Controller for Application Memory: User Profile, Preferences, Settings.
 */
@RestController
@RequestMapping("/api/v1/user")
@CrossOrigin(originPatterns = "*")
public class UserController {

    private final UserProfileRepository profileRepository;
    private final UserPreferencesRepository preferencesRepository;
    private final AppSettingsRepository settingsRepository;

    public UserController(
            UserProfileRepository profileRepository,
            UserPreferencesRepository preferencesRepository,
            AppSettingsRepository settingsRepository
    ) {
        this.profileRepository = profileRepository;
        this.preferencesRepository = preferencesRepository;
        this.settingsRepository = settingsRepository;
    }

    @GetMapping("/profile/{username}")
    public ResponseEntity<UserProfileEntity> getProfile(@PathVariable String username) {
        UserProfileEntity profile = profileRepository.findByUsername(username)
                .orElseGet(() -> profileRepository.save(new UserProfileEntity(username, username, username + "@aigis.ai", "en-IN")));
        return ResponseEntity.ok(profile);
    }

    @PostMapping("/profile")
    public ResponseEntity<UserProfileEntity> updateProfile(@RequestBody UserProfileEntity profile) {
        UserProfileEntity saved = profileRepository.save(profile);
        return ResponseEntity.ok(saved);
    }

    @GetMapping("/preferences/{username}")
    public ResponseEntity<UserPreferencesEntity> getPreferences(@PathVariable String username) {
        UserPreferencesEntity prefs = preferencesRepository.findByUsername(username)
                .orElseGet(() -> preferencesRepository.save(new UserPreferencesEntity(username)));
        return ResponseEntity.ok(prefs);
    }

    @PostMapping("/preferences")
    public ResponseEntity<UserPreferencesEntity> updatePreferences(@RequestBody UserPreferencesEntity prefs) {
        UserPreferencesEntity saved = preferencesRepository.save(prefs);
        return ResponseEntity.ok(saved);
    }

    @GetMapping("/settings")
    public ResponseEntity<List<AppSettingsEntity>> getSettings() {
        return ResponseEntity.ok(settingsRepository.findAll());
    }

    @PostMapping("/settings")
    public ResponseEntity<AppSettingsEntity> saveSetting(@RequestBody AppSettingsEntity setting) {
        AppSettingsEntity existing = settingsRepository.findBySettingKey(setting.getSettingKey())
                .map(s -> {
                    s.setSettingValue(setting.getSettingValue());
                    return settingsRepository.save(s);
                })
                .orElseGet(() -> settingsRepository.save(setting));
        return ResponseEntity.ok(existing);
    }
}
