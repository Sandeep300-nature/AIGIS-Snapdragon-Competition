package com.aigis.backend.repository;

import com.aigis.backend.model.entity.UserPreferencesEntity;
import org.springframework.data.jpa.repository.JpaRepository;
import java.util.Optional;

public interface UserPreferencesRepository extends JpaRepository<UserPreferencesEntity, Long> {
    Optional<UserPreferencesEntity> findByUsername(String username);
}
