package com.aigis.backend.repository;

import com.aigis.backend.model.entity.ConversationEntity;
import org.springframework.data.jpa.repository.JpaRepository;
import java.util.Optional;

public interface ConversationRepository extends JpaRepository<ConversationEntity, Long> {
    Optional<ConversationEntity> findByConversationId(String conversationId);
}
