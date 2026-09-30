package com.aigis.backend.service;

import com.aigis.backend.model.domain.ChatMessage;
import com.aigis.backend.model.entity.ChatMessageEntity;
import com.aigis.backend.model.entity.ConversationEntity;
import com.aigis.backend.repository.ChatMessageRepository;
import com.aigis.backend.repository.ConversationRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.stream.Collectors;

/**
 * Service for maintaining multi-turn conversation memory history per session.
 * Stores conversation IDs, session metadata, and chat history directly into
 * Spring Data JPA Database.
 */
@Service
public class ConversationMemoryService {

    private static final Logger log = LoggerFactory.getLogger(ConversationMemoryService.class);
    private static final int MAX_HISTORY_MESSAGES = 20;

    private final ConversationRepository conversationRepository;
    private final ChatMessageRepository chatMessageRepository;

    public ConversationMemoryService(
            ConversationRepository conversationRepository,
            ChatMessageRepository chatMessageRepository) {
        this.conversationRepository = conversationRepository;
        this.chatMessageRepository = chatMessageRepository;
    }

    /**
     * Retrieves the list of past chat messages for a given session from Database.
     */
    @Transactional(readOnly = true)
    public List<ChatMessage> getHistory(String sessionId) {
        String key = sanitizeSessionId(sessionId);
        List<ChatMessageEntity> entities = chatMessageRepository
                .findByConversationConversationIdOrderByTimestampAsc(key);

        // Sliding window limit
        if (entities.size() > MAX_HISTORY_MESSAGES) {
            entities = entities.subList(entities.size() - MAX_HISTORY_MESSAGES, entities.size());
        }

        return entities.stream()
                .map(e -> new ChatMessage(e.getRole(), e.getContent(), e.getTimestamp()))
                .collect(Collectors.toList());
    }

    /**
     * Appends a new chat message (user or assistant) to session history in
     * Database.
     */
    @Transactional
    public void addMessage(String sessionId, ChatMessage message) {
        String key = sanitizeSessionId(sessionId);

        ConversationEntity conversation = conversationRepository.findByConversationId(key)
                .orElseGet(() -> conversationRepository.save(new ConversationEntity(key, "Session: " + key)));

        ChatMessageEntity entity = new ChatMessageEntity(message.role(), message.content());
        entity.setConversation(conversation);
        chatMessageRepository.save(entity);

        log.info("Persisted message to DB [session={}, role={}]: {}", key, message.role(), message.content());
    }

    /**
     * Clears conversation memory history for the specified session from Database.
     */
    @Transactional
    public void clearMemory(String sessionId) {
        String key = sanitizeSessionId(sessionId);
        Optional<ConversationEntity> convOpt = conversationRepository.findByConversationId(key);
        convOpt.ifPresent(conversationRepository::delete);
        log.info("Cleared conversation memory in DB for session: {}", key);
    }

    private String sanitizeSessionId(String sessionId) {
        return (sessionId == null || sessionId.isBlank()) ? "default-session" : sessionId.trim();
    }
}
