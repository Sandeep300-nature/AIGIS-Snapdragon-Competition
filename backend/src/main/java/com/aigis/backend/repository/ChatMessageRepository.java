package com.aigis.backend.repository;

import com.aigis.backend.model.entity.ChatMessageEntity;
import org.springframework.data.jpa.repository.JpaRepository;
import java.util.List;

public interface ChatMessageRepository extends JpaRepository<ChatMessageEntity, Long> {
    List<ChatMessageEntity> findByConversationConversationIdOrderByTimestampAsc(String conversationId);
}
