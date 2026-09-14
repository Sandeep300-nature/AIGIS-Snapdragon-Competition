import React, { useState, useEffect, useCallback } from 'react';
import './DocumentManagerModal.css';

const API_ENDPOINTS = {
  list: ['http://localhost:8080/api/v1/docs/list', 'http://localhost:8000/api/v1/docs/list'],
  search: ['http://localhost:8080/api/v1/docs/search', 'http://localhost:8000/api/v1/docs/search'],
};

export default function DocumentManagerModal({ isOpen, onClose }) {
  const [activeTab, setActiveTab] = useState('DOCS'); // 'DOCS' | 'SEARCH'
  const [documents, setDocuments] = useState([]);
  const [isLoadingDocs, setIsLoadingDocs] = useState(false);
  const [docsError, setDocsError] = useState(null);

  // Search state
  const [searchQuery, setSearchQuery] = useState('');
  const [searchMode, setSearchMode] = useState('hybrid'); // 'hybrid' | 'lexical' | 'semantic'
  const [topK, setTopK] = useState(5);
  const [isSearching, setIsSearching] = useState(false);
  const [searchResults, setSearchResults] = useState(null);
  const [searchError, setSearchError] = useState(null);
  const [embeddingStatus, setEmbeddingStatus] = useState(null);

  // Helper to fetch with primary Spring Boot -> fallback Python FastAPI
  const fetchWithFallback = useCallback(async (endpoints, options = {}) => {
    let lastError = null;
    for (const url of endpoints) {
      try {
        const res = await fetch(url, options);
        if (res.ok) {
          return await res.json();
        }
      } catch (err) {
        lastError = err;
      }
    }
    throw lastError || new Error('All endpoints unreachable');
  }, []);

  // Fetch indexed documents list
  const fetchDocuments = useCallback(async () => {
    setIsLoadingDocs(true);
    setDocsError(null);
    try {
      const data = await fetchWithFallback(API_ENDPOINTS.list);
      setDocuments(Array.isArray(data.documents) ? data.documents : []);
    } catch (err) {
      console.warn('Failed to fetch documents from vault:', err);
      setDocsError('Unable to connect to document vault (Spring Boot / Python engine offline).');
    } finally {
      setIsLoadingDocs(false);
    }
  }, [fetchWithFallback]);

  // Execute document search
  const handleSearch = useCallback(async (queryOverride, modeOverride) => {
    const q = (queryOverride !== undefined ? queryOverride : searchQuery).trim();
    const m = modeOverride !== undefined ? modeOverride : searchMode;

    if (!q) return;

    setIsSearching(true);
    setSearchError(null);

    try {
      const payload = {
        query: q,
        topK: Number(topK) || 5,
        mode: m
      };

      const data = await fetchWithFallback(API_ENDPOINTS.search, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      setSearchResults({
        query: q,
        mode: data.mode || m,
        retrievalMode: data.retrievalMode || (m === 'lexical' ? 'LEXICAL' : (m === 'semantic' ? 'SEMANTIC' : 'HYBRID')),
        fallbackUsed: !!data.fallbackUsed,
        results: Array.isArray(data.results) ? data.results : [],
        count: data.count || (Array.isArray(data.results) ? data.results.length : 0),
        status: data.status || 'SUCCESS',
        message: data.message || ''
      });

      if (data.embeddingStatus) {
        setEmbeddingStatus(data.embeddingStatus);
      }
    } catch (err) {
      console.error('Document search error:', err);
      setSearchError('Search failed: Local document search service unreachable.');
    } finally {
      setIsSearching(false);
    }
  }, [searchQuery, searchMode, topK, fetchWithFallback]);

  useEffect(() => {
    if (isOpen) {
      fetchDocuments();
    }
  }, [isOpen, fetchDocuments]);

  if (!isOpen) return null;

  // Format file size
  const formatSize = (bytes) => {
    if (!bytes && bytes !== 0) return null;
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  // Quick search when clicking a document
  const handleQuickDocSearch = (doc) => {
    const term = doc.title || doc.path || '';
    setSearchQuery(term);
    setActiveTab('SEARCH');
    handleSearch(term, searchMode);
  };

  const isEmbeddingsUnavailable = embeddingStatus && embeddingStatus.available === false;
  const isFallbackActive = searchResults?.fallbackUsed || searchResults?.retrievalMode === 'LEXICAL_FALLBACK';

  return (
    <div className="doc-modal-overlay" onClick={onClose}>
      <div className="doc-modal-container" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="doc-modal-header">
          <div className="doc-header-title-group">
            <span className="doc-vault-badge">
              <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                <polyline points="14 2 14 8 20 8"></polyline>
                <line x1="16" y1="13" x2="8" y2="13"></line>
                <line x1="16" y1="17" x2="8" y2="17"></line>
                <polyline points="10 9 9 9 8 9"></polyline>
              </svg>
              A.I.G.I.S. LOCAL DOCUMENT VAULT
            </span>

            {/* Embedding Status Pill */}
            {embeddingStatus ? (
              embeddingStatus.available ? (
                <span className="doc-status-pill active" title={`Provider: ${embeddingStatus.executionProvider || 'CPU'}`}>
                  🟢 ONNX Embeddings Active ({embeddingStatus.modelName || 'all-MiniLM-L6-v2'})
                </span>
              ) : (
                <span className="doc-status-pill fallback" title={embeddingStatus.errorMessage || 'Local model weights not loaded'}>
                  🟠 Lexical Fallback Active (Embeddings Unavailable)
                </span>
              )
            ) : (
              <span className="doc-status-pill fallback">
                ⚡ Local SQLite Storage Active
              </span>
            )}
          </div>

          <button className="doc-modal-close-btn" onClick={onClose} title="Close Document Vault">
            ×
          </button>
        </div>

        {/* Tabs */}
        <div className="doc-modal-tabs">
          <button
            className={`doc-tab-btn ${activeTab === 'DOCS' ? 'active' : ''}`}
            onClick={() => setActiveTab('DOCS')}
          >
            <span>📁 INDEXED DOCUMENTS</span>
            <span className="doc-tab-count">{documents.length}</span>
          </button>
          <button
            className={`doc-tab-btn ${activeTab === 'SEARCH' ? 'active' : ''}`}
            onClick={() => setActiveTab('SEARCH')}
          >
            <span>🔍 DOCUMENT SEARCH</span>
            {searchResults && <span className="doc-tab-count">{searchResults.count}</span>}
          </button>
        </div>

        {/* Truthful Fallback Banner */}
        {(isEmbeddingsUnavailable || isFallbackActive) && (
          <div className="doc-truthful-banner">
            <span>⚠️</span>
            <span>
              <strong>Truthful Provenance:</strong> Semantic vector embeddings are unavailable on this device. Lexical keyword search is being used as fallback.
            </span>
          </div>
        )}

        {/* Actions Bar */}
        <div className="doc-actions-bar">
          {activeTab === 'DOCS' ? (
            <>
              <div className="doc-meta-subtext">
                <span>Total Indexed Files: <strong>{documents.length}</strong></span>
                <span>•</span>
                <span>Storage: <strong>Local SQLite Vault</strong></span>
                <span>•</span>
                <span>Incremental Watcher: <strong>Active</strong></span>
              </div>
              <button className="doc-refresh-btn" onClick={fetchDocuments} disabled={isLoadingDocs}>
                {isLoadingDocs ? <span className="doc-spinner" style={{ width: 14, height: 14 }} /> : '🔄'}
                <span>REFRESH VAULT</span>
              </button>
            </>
          ) : (
            <>
              <div className="doc-search-input-wrapper">
                <span className="doc-search-icon">🔍</span>
                <input
                  type="text"
                  className="doc-search-input"
                  placeholder="Search local documents (e.g. project architecture, notes, code)..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault();
                      handleSearch();
                    }
                  }}
                />
              </div>

              {/* Retrieval Mode Toggle */}
              <div className="doc-mode-selector" title="Select document retrieval strategy">
                <button
                  className={`doc-mode-btn ${searchMode === 'hybrid' ? 'active' : ''}`}
                  onClick={() => setSearchMode('hybrid')}
                  title="Combines keyword matching and vector similarity (falls back cleanly)"
                >
                  HYBRID
                </button>
                <button
                  className={`doc-mode-btn ${searchMode === 'lexical' ? 'active' : ''}`}
                  onClick={() => setSearchMode('lexical')}
                  title="Keyword token matching across chunk headings and text"
                >
                  LEXICAL
                </button>
                <button
                  className={`doc-mode-btn ${searchMode === 'semantic' ? 'active' : ''}`}
                  onClick={() => setSearchMode('semantic')}
                  title="Vector cosine similarity over float32 on-device embeddings"
                >
                  SEMANTIC
                </button>
              </div>

              <button
                className="doc-exec-search-btn"
                onClick={() => handleSearch()}
                disabled={isSearching || !searchQuery.trim()}
              >
                {isSearching ? <span className="doc-spinner" style={{ width: 14, height: 14 }} /> : 'SEARCH'}
              </button>
            </>
          )}
        </div>

        {/* Modal Content */}
        <div className="doc-modal-content">
          {activeTab === 'DOCS' ? (
            /* Tab 1: Indexed Documents List */
            isLoadingDocs ? (
              <div className="doc-state-container">
                <div className="doc-spinner" />
                <div className="doc-state-text">Scanning local document vault...</div>
              </div>
            ) : docsError ? (
              <div className="doc-state-container">
                <div className="doc-state-icon">⚠️</div>
                <div className="doc-state-text" style={{ color: '#f87171' }}>{docsError}</div>
                <button className="doc-refresh-btn" onClick={fetchDocuments}>Try Again</button>
              </div>
            ) : documents.length === 0 ? (
              <div className="doc-state-container">
                <div className="doc-state-icon">📄</div>
                <div className="doc-state-text">No local documents indexed in vault yet.</div>
                <div className="doc-state-subtext">
                  Place files in watched project folders or register directories to automatically extract and chunk them.
                </div>
              </div>
            ) : (
              documents.map((doc, idx) => {
                const ext = (doc.extension || '').replace('.', '');
                const sizeStr = formatSize(doc.sizeBytes);

                return (
                  <div key={doc.path || idx} className="doc-item-card">
                    <div className="doc-item-left">
                      <div className="doc-ext-badge">{ext || 'DOC'}</div>
                      <div className="doc-info-block">
                        <div className="doc-title-text" title={doc.path || doc.title}>
                          {doc.title || doc.path}
                        </div>
                        <div className="doc-meta-subtext">
                          {doc.collection && (
                            <span className="doc-meta-item">
                              📁 {doc.collection}
                            </span>
                          )}
                          {sizeStr && (
                            <span className="doc-meta-item">
                              💾 {sizeStr}
                            </span>
                          )}
                          {doc.modifiedDate && (
                            <span className="doc-meta-item">
                              🕒 {doc.modifiedDate}
                            </span>
                          )}
                          {doc.status && (
                            <span className="doc-meta-item" style={{ color: '#34d399' }}>
                              ✓ {doc.status}
                            </span>
                          )}
                        </div>
                      </div>
                    </div>

                    <div className="doc-item-right">
                      {doc.chunkCount !== undefined && (
                        <span className="doc-chunks-pill" title="Number of indexed chunks in vault">
                          {doc.chunkCount} chunks
                        </span>
                      )}
                      <button
                        className="doc-quick-search-btn"
                        onClick={() => handleQuickDocSearch(doc)}
                        title="Search within this document"
                      >
                        Search File
                      </button>
                    </div>
                  </div>
                );
              })
            )
          ) : (
            /* Tab 2: Document Search Results */
            isSearching ? (
              <div className="doc-state-container">
                <div className="doc-spinner" />
                <div className="doc-state-text">Searching local document chunks...</div>
                <div className="doc-state-subtext">Retrieval mode: {searchMode.toUpperCase()}</div>
              </div>
            ) : searchError ? (
              <div className="doc-state-container">
                <div className="doc-state-icon">⚠️</div>
                <div className="doc-state-text" style={{ color: '#f87171' }}>{searchError}</div>
              </div>
            ) : !searchResults ? (
              <div className="doc-state-container">
                <div className="doc-state-icon">🔍</div>
                <div className="doc-state-text">Enter a search query to search across local document chunks.</div>
                <div className="doc-state-subtext">
                  Supports lexical keyword search, semantic vector search, and hybrid retrieval.
                </div>
              </div>
            ) : searchResults.results.length === 0 ? (
              <div className="doc-state-container">
                <div className="doc-state-icon">📭</div>
                <div className="doc-state-text">No matching chunks found for: &ldquo;{searchResults.query}&rdquo;</div>
                <div className="doc-state-subtext">
                  {searchResults.mode === 'semantic' && isEmbeddingsUnavailable
                    ? 'Semantic vector model is unavailable on this device. Try switching to Lexical or Hybrid mode.'
                    : 'Try broader keywords or verify that documents are indexed in the vault.'}
                </div>
              </div>
            ) : (
              searchResults.results.map((chunk, idx) => {
                const modeType = (chunk.retrieval_mode || searchResults.retrievalMode || 'HYBRID').toLowerCase();
                const isLexicalFallback = modeType === 'lexical_fallback';
                const scoreVal = chunk.score !== undefined ? Number(chunk.score) : null;

                return (
                  <div key={chunk.id || idx} className="doc-chunk-card">
                    <div className="doc-chunk-header">
                      <div className="doc-chunk-source">
                        <span>📄 {chunk.title || 'Local Document'}</span>
                        {chunk.heading && <span style={{ color: '#94a3b8' }}>› {chunk.heading}</span>}
                        {chunk.chunk_index !== undefined && (
                          <span style={{ color: '#64748b', fontSize: '0.72rem' }}>[Chunk #{chunk.chunk_index}]</span>
                        )}
                      </div>

                      <div className="doc-chunk-badges">
                        {/* Retrieval Mode Badge */}
                        <span className={`doc-retrieval-mode-badge ${isLexicalFallback ? 'fallback' : modeType}`}>
                          {isLexicalFallback
                            ? 'LEXICAL FALLBACK'
                            : modeType === 'lexical'
                            ? 'LEXICAL MATCH'
                            : modeType === 'semantic'
                            ? 'SEMANTIC VECTOR'
                            : 'HYBRID'}
                        </span>

                        {/* Similarity / Score if provided */}
                        {scoreVal !== null && (
                          <span className="doc-score-badge" title="Retrieval score">
                            Score: {scoreVal.toFixed(3)}
                          </span>
                        )}
                      </div>
                    </div>

                    <div className="doc-chunk-snippet">
                      {chunk.text || chunk.content || 'No text snippet'}
                    </div>
                  </div>
                );
              })
            )
          )}
        </div>

        {/* Footer with Grounding & Privacy Provenance */}
        <div className="doc-modal-footer">
          <div className="doc-provenance-tags">
            <span className="doc-provenance-pill">
              🔒 LOCAL • 100% On-Device
            </span>
            <span className="doc-provenance-pill">
              🌐 Network: OFF
            </span>
            <span className="doc-provenance-pill">
              📑 Vault: SQLite
            </span>
          </div>

          <div>
            <span>AIGIS Document Intelligence v1.2</span>
          </div>
        </div>
      </div>
    </div>
  );
}
