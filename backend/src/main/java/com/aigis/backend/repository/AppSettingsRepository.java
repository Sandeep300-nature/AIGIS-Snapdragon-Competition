package com.aigis.backend.repository;

import com.aigis.backend.model.entity.AppSettingsEntity;
import org.springframework.data.jpa.repository.JpaRepository;
import java.util.Optional;

public interface AppSettingsRepository extends JpaRepository<AppSettingsEntity, Long> {
    Optional<AppSettingsEntity> findBySettingKey(String settingKey);
}
