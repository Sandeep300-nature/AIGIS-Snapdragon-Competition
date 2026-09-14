package com.aigis.backend.model.entity;

import jakarta.persistence.*;

@Entity
@Table(name = "user_preferences")
public class UserPreferencesEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(unique = true, nullable = false)
    private String username;

    private boolean darkMode = true;
    private double speechRate = 1.0;
    private double micSensitivity = 2.2;
    private boolean autoSpeak = true;
    private String themeColor = "#00bfff";

    public UserPreferencesEntity() {}

    public UserPreferencesEntity(String username) {
        this.username = username;
    }

    public Long getId() { return id; }
    public String getUsername() { return username; }
    public void setUsername(String username) { this.username = username; }
    public boolean isDarkMode() { return darkMode; }
    public void setDarkMode(boolean darkMode) { this.darkMode = darkMode; }
    public double getSpeechRate() { return speechRate; }
    public void setSpeechRate(double speechRate) { this.speechRate = speechRate; }
    public double getMicSensitivity() { return micSensitivity; }
    public void setMicSensitivity(double micSensitivity) { this.micSensitivity = micSensitivity; }
    public boolean isAutoSpeak() { return autoSpeak; }
    public void setAutoSpeak(boolean autoSpeak) { this.autoSpeak = autoSpeak; }
    public String getThemeColor() { return themeColor; }
    public void setThemeColor(String themeColor) { this.themeColor = themeColor; }
}
