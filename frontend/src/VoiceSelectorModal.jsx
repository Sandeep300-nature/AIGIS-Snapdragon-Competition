import React, { useState, useEffect } from 'react';
import ReactDOM from 'react-dom';
import {
  getAvailableVoices,
  setSelectedVoice,
  getEffectiveActiveVoiceURI,
  getResponseLanguage,
  findGoogleHindiVoice,
  speak,
  cancelSpeech,
  isElevenLabsConfigured
} from './utils/speechService';
import './VoiceSelectorModal.css';

export default function VoiceSelectorModal({ isOpen, onClose }) {
  const [voices, setVoices] = useState([]);
  const [currentVoiceURI, setCurrentVoiceURI] = useState('');
  const [currentLang, setCurrentLang] = useState('en');
  const [searchQuery, setSearchQuery] = useState('');
  const [previewingKey, setPreviewingKey] = useState(null);

  useEffect(() => {
    if (!isOpen) return;

    const loadVoices = () => {
      const avail = getAvailableVoices();
      setVoices(avail);
      setCurrentVoiceURI(getEffectiveActiveVoiceURI());
      setCurrentLang(getResponseLanguage());
    };

    loadVoices();

    if ('speechSynthesis' in window) {
      window.speechSynthesis.onvoiceschanged = loadVoices;
    }

    const handleVoiceChange = () => {
      setCurrentVoiceURI(getEffectiveActiveVoiceURI());
      setCurrentLang(getResponseLanguage());
    };

    window.addEventListener('voiceChanged', handleVoiceChange);
    return () => {
      window.removeEventListener('voiceChanged', handleVoiceChange);
    };
  }, [isOpen]);

  if (!isOpen) return null;

  const handleSelectProfile = (uri, lang, profileName, samplePhrase) => {
    setSelectedVoice(uri, lang);
    setCurrentVoiceURI(uri);
    setCurrentLang(lang);
    cancelSpeech();

    const key = `${uri}:${lang}`;
    setPreviewingKey(key);
    speak(
      samplePhrase,
      () => setPreviewingKey(key),
      () => setPreviewingKey(null),
      uri
    );
  };

  const handlePreviewProfile = (e, uri, lang, samplePhrase) => {
    e.stopPropagation();
    cancelSpeech();
    const key = `${uri}:${lang}`;
    setPreviewingKey(key);
    speak(
      samplePhrase,
      () => setPreviewingKey(key),
      () => setPreviewingKey(null),
      uri
    );
  };

  const hindiVoiceObj = findGoogleHindiVoice(voices);
  const hindiVoiceURI = hindiVoiceObj ? hindiVoiceObj.voiceURI : 'google-hindi';

  const filteredVoices = voices.filter(v =>
    v.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    v.lang.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const hasElevenLabs = isElevenLabsConfigured();

  return ReactDOM.createPortal(
    <div className="voice-modal-overlay" onClick={onClose}>
      <div className="voice-modal-container glass-panel" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="voice-modal-header">
          <div className="voice-modal-title-row">
            <span className="voice-icon">🎙️</span>
            <h3 className="voice-modal-title">AIGIS VOICE & LANGUAGE MATRIX</h3>
          </div>
          <button className="voice-close-btn" onClick={onClose}>✕</button>
        </div>

        {/* Search Toolbar */}
        <div className="voice-modal-toolbar">
          <input
            type="text"
            className="voice-search-input"
            placeholder="Search voices by name or lang (e.g. Zira, David, en-US)..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
          <span className="voice-count-tag">{filteredVoices.length} Voices</span>
        </div>

        {/* Voice List */}
        <div className="voice-list-scroll">
          {/* Section: Dual Indian Profiles */}
          <div className="voice-section-divider">DEDICATED VOICE PROFILES</div>

          {/* Profile 1: Google Hindi (Hindi) */}
          {(() => {
            const isActive = currentVoiceURI === hindiVoiceURI && currentLang === 'hi';
            const key = `${hindiVoiceURI}:hi`;
            const isPreviewing = previewingKey === key;
            return (
              <div
                className={`voice-item-card ${isActive ? 'active' : ''}`}
                onClick={() => handleSelectProfile(
                  hindiVoiceURI,
                  'hi',
                  'Google Hindi (Hindi)',
                  'नमस्ते श्रीमान। AIGIS हिंदी वॉइस सिस्टम सक्रिय है।'
                )}
              >
                <div className="voice-item-info">
                  <div className="voice-title-row">
                    <span className="voice-item-name">🇮🇳 Google Hindi (Hindi)</span>
                    <span className="voice-lang-badge">hi-IN</span>
                    <span className="voice-default-tag">Hindi Generation</span>
                  </div>
                  <span className="voice-item-sub">Voice: Google Hindi | Response: Hindi (Devanagari)</span>
                </div>

                <div className="voice-item-actions">
                  <button
                    className={`voice-preview-btn ${isPreviewing ? 'playing' : ''}`}
                    onClick={(e) => handlePreviewProfile(
                      e,
                      hindiVoiceURI,
                      'hi',
                      'नमस्ते श्रीमान। AIGIS हिंदी वॉइस सिस्टम सक्रिय है।'
                    )}
                    title="Preview Google Hindi (Hindi)"
                  >
                    {isPreviewing ? '🔊 Playing...' : '▶ Preview'}
                  </button>
                  {isActive && <span className="voice-active-badge">✔ ACTIVE</span>}
                </div>
              </div>
            );
          })()}

          {/* Profile 2: FRIDAY Voice */}
          {(() => {
            const isActive = currentVoiceURI === hindiVoiceURI && currentLang === 'en';
            const key = `${hindiVoiceURI}:en`;
            const isPreviewing = previewingKey === key;
            return (
              <div
                className={`voice-item-card ${isActive ? 'active' : ''}`}
                onClick={() => handleSelectProfile(
                  hindiVoiceURI,
                  'en',
                  'FRIDAY Voice',
                  'Hello sir. FRIDAY voice active. All systems operational.'
                )}
              >
                <div className="voice-item-info">
                  <div className="voice-title-row">
                    <span className="voice-item-name">✨ FRIDAY Voice</span>
                    <span className="voice-lang-badge">en-IN</span>
                    <span className="voice-default-tag">English Generation</span>
                  </div>
                  <span className="voice-item-sub">Voice: Indian Accent Engine | Response: English</span>
                </div>

                <div className="voice-item-actions">
                  <button
                    className={`voice-preview-btn ${isPreviewing ? 'playing' : ''}`}
                    onClick={(e) => handlePreviewProfile(
                      e,
                      hindiVoiceURI,
                      'en',
                      'Hello sir. FRIDAY voice active. All systems operational.'
                    )}
                    title="Preview FRIDAY Voice"
                  >
                    {isPreviewing ? '🔊 Playing...' : '▶ Preview'}
                  </button>
                  {isActive && <span className="voice-active-badge">✔ ACTIVE</span>}
                </div>
              </div>
            );
          })()}

          {/* ElevenLabs if configured */}
          {hasElevenLabs && (
            <div
              className={`voice-item-card ${currentVoiceURI === 'elevenlabs' ? 'active' : ''}`}
              onClick={() => handleSelectProfile('elevenlabs', 'en', 'ElevenLabs Rachel', 'Hello sir. Testing ElevenLabs neural voice.')}
            >
              <div className="voice-item-info">
                <span className="voice-item-name">⚡ ElevenLabs (Rachel)</span>
                <span className="voice-item-sub">Ultra-realistic neural AI voice synthesis</span>
              </div>
              {currentVoiceURI === 'elevenlabs' && <span className="voice-active-badge">✔ ACTIVE</span>}
            </div>
          )}

          <div className="voice-section-divider">INSTALLED SYSTEM VOICES</div>

          {filteredVoices.length === 0 ? (
            <div className="voice-empty-state">
              <p>No matching system voices found.</p>
            </div>
          ) : (
            filteredVoices.map((v) => {
              const isActive = currentVoiceURI === v.voiceURI && currentLang !== 'hi';
              const key = `${v.voiceURI}:en`;
              const isPreviewing = previewingKey === key;

              return (
                <div
                  key={v.voiceURI}
                  className={`voice-item-card ${isActive ? 'active' : ''}`}
                  onClick={() => handleSelectProfile(
                    v.voiceURI,
                    'en',
                    v.name,
                    `Hello sir. Testing ${v.name.replace(/Microsoft |Google /g, '')} voice synthesis.`
                  )}
                >
                  <div className="voice-item-info">
                    <div className="voice-title-row">
                      <span className="voice-item-name">{v.name}</span>
                      <span className="voice-lang-badge">{v.lang}</span>
                      {v.default && <span className="voice-default-tag">OS Default</span>}
                    </div>
                    <span className="voice-item-sub">{v.localService ? 'Local System Voice' : 'Network Web Voice'}</span>
                  </div>

                  <div className="voice-item-actions">
                    <button
                      className={`voice-preview-btn ${isPreviewing ? 'playing' : ''}`}
                      onClick={(e) => handlePreviewProfile(
                        e,
                        v.voiceURI,
                        'en',
                        `Hello sir. Testing ${v.name.replace(/Microsoft |Google /g, '')} voice synthesis.`
                      )}
                      title={`Preview ${v.name}`}
                    >
                      {isPreviewing ? '🔊 Playing...' : '▶ Preview'}
                    </button>
                    {isActive && <span className="voice-active-badge">✔ ACTIVE</span>}
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>,
    document.body
  );
}
