import React, { useState } from 'react';
import './Navbar.css';

export default function Navbar({ 
  blobParams, 
  onUpdateParam, 
  showMetrics, 
  onToggleMetrics,
  showWeather,
  onToggleWeather,
  onOpenMemoryManager,
  onOpenDocumentManager
}) {
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [isAboutOpen, setIsAboutOpen] = useState(false);
  const [activeTab, setActiveTab] = useState('HOME');

  const navItems = ['HOME', 'DOCUMENTS', 'MEMORY', 'SETTINGS', 'ABOUT'];

  const handleNavClick = (item) => {
    setActiveTab(item);
    if (item === 'SETTINGS') {
      setIsSettingsOpen(!isSettingsOpen);
      setIsAboutOpen(false);
    } else if (item === 'DOCUMENTS') {
      setIsSettingsOpen(false);
      setIsAboutOpen(false);
      onOpenDocumentManager?.();
    } else if (item === 'MEMORY') {
      setIsSettingsOpen(false);
      setIsAboutOpen(false);
      onOpenMemoryManager?.();
    } else if (item === 'ABOUT') {
      setIsSettingsOpen(false);
      setIsAboutOpen(!isAboutOpen);
    } else {
      setIsSettingsOpen(false);
      setIsAboutOpen(false);
    }
  };


  return (
    <header className="navbar-wrapper">
      <div className="navbar-glow"></div>

      <nav className="navbar">
        <div className="nav-brand">
          <span className="brand-name">A.I.G.I.S.</span>
          <span className="brand-arch-badge" title="Local-First Snapdragon X Target Architecture">
            <span className="badge-pulse-dot"></span>
            ON-DEVICE AI · SNAPDRAGON TARGET
          </span>
          <span className="brand-competition-label" title="Snapdragon Competition Version">
            (Snapdragon Competition v_3)
          </span>
        </div>

        <div className="nav-links">
          {navItems.map((item) => (
            <div key={item} className="nav-item-wrapper">
              <button
                className={`nav-link ${activeTab === item ? 'active' : ''}`}
                onClick={() => handleNavClick(item)}
              >
                {item}
              </button>

              {item === 'SETTINGS' && isSettingsOpen && (
                <div className="settings-menu glass-panel">
                  <div className="settings-header">
                    <h3>Assistant Settings</h3>
                  </div>

                  {/* Telemetry & Weather HUD Toggles */}
                  <div className="control-group">
                    <div className="control-header">
                      <span className="control-label">Telemetry Stats HUD</span>
                      <button
                        className={`mic-toggle-btn ${showMetrics ? 'active' : ''}`}
                        onClick={onToggleMetrics}
                      >
                        <span className="dot"></span>
                        {showMetrics ? 'ON' : 'OFF'}
                      </button>
                    </div>

                    <div className="control-header" style={{ marginTop: '8px' }}>
                      <span className="control-label">Weather & Time HUD</span>
                      <button
                        className={`mic-toggle-btn ${showWeather ? 'active' : ''}`}
                        onClick={onToggleWeather}
                      >
                        <span className="dot"></span>
                        {showWeather ? 'ON' : 'OFF'}
                      </button>
                    </div>
                  </div>

                  {/* Microphone Settings */}
                  <div className="control-group">
                    <div className="control-header">
                      <span className="control-label">Microphone</span>
                      <button
                        className={`mic-toggle-btn ${blobParams.isMicActive ? 'active' : ''}`}
                        onClick={() => onUpdateParam('isMicActive', !blobParams.isMicActive)}
                      >
                        <span className="dot"></span>
                        {blobParams.isMicActive ? 'ON' : 'OFF'}
                      </button>
                    </div>

                    <div className="slider-item">
                      <div className="slider-label">
                        <span>Sensitivity</span>
                        <span className="val-text">{blobParams.micSensitivity.toFixed(1)}</span>
                      </div>
                      <input
                        type="range"
                        min="0.5"
                        max="5.0"
                        step="0.1"
                        value={blobParams.micSensitivity}
                        onChange={(e) => onUpdateParam('micSensitivity', parseFloat(e.target.value))}
                        className="styled-range"
                      />
                    </div>
                  </div>

                  {/* Plasma Core */}
                  <div className="control-group">
                    <div className="control-header">
                      <span className="control-label">Plasma Core</span>
                    </div>

                    <div className="slider-item">
                      <div className="slider-label">
                        <span>Anim Speed</span>
                        <span className="val-text">{blobParams.timeScale.toFixed(1)}</span>
                      </div>
                      <input
                        type="range"
                        min="0.0"
                        max="2.0"
                        step="0.1"
                        value={blobParams.timeScale}
                        onChange={(e) => onUpdateParam('timeScale', parseFloat(e.target.value))}
                        className="styled-range"
                      />
                    </div>

                    <div className="slider-item">
                      <div className="slider-label">
                        <span>Brightness</span>
                        <span className="val-text">{blobParams.plasmaBrightness.toFixed(1)}</span>
                      </div>
                      <input
                        type="range"
                        min="0.5"
                        max="3.0"
                        step="0.1"
                        value={blobParams.plasmaBrightness}
                        onChange={(e) => onUpdateParam('plasmaBrightness', parseFloat(e.target.value))}
                        className="styled-range"
                      />
                    </div>
                  </div>

                  {/* Rotation */}
                  <div className="control-group">
                    <div className="control-header">
                      <span className="control-label">Rotation</span>
                    </div>
                    <div className="slider-item">
                      <div className="slider-label">
                        <span>Rotation Speed</span>
                        <span className="val-text">{(blobParams.rotationSpeedY * 1000).toFixed(0)}</span>
                      </div>
                      <input
                        type="range"
                        min="-0.01"
                        max="0.01"
                        step="0.001"
                        value={blobParams.rotationSpeedY}
                        onChange={(e) => onUpdateParam('rotationSpeedY', parseFloat(e.target.value))}
                        className="styled-range"
                      />
                    </div>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      </nav>

      {/* Competition Architecture About Modal */}
      {isAboutOpen && (
        <div className="about-modal-backdrop" onClick={() => setIsAboutOpen(false)}>
          <div className="about-modal-card glass-panel" onClick={(e) => e.stopPropagation()}>
            <div className="about-modal-header">
              <div className="about-brand-title">
                <span className="about-icon">⚡</span>
                <h3>A.I.G.I.S. Architecture</h3>
                <span className="about-version-badge">COMPETITION READY</span>
              </div>
              <button className="about-close-btn" onClick={() => setIsAboutOpen(false)}>×</button>
            </div>

            <div className="about-modal-body">
              <p className="about-intro">
                <strong>Autonomous Intelligent Grounded Interactive System</strong> is an on-device first, privacy-governed AI assistant designed for Windows-on-Arm and Snapdragon X Elite NPU deployment.
              </p>

              <div className="about-pillars-grid">
                <div className="about-pillar-card">
                  <div className="pillar-header">
                    <span className="pillar-icon">⚡</span>
                    <h4>On-Device SLM</h4>
                  </div>
                  <p>SmolLM2-135M running locally for instant, offline intelligence without external cloud reliance.</p>
                </div>

                <div className="about-pillar-card">
                  <div className="pillar-header">
                    <span className="pillar-icon">🔒</span>
                    <h4>M7 Privacy Guard</h4>
                  </div>
                  <p>Code-enforced zero-leak boundaries. Local memories and private documents never egress to cloud endpoints.</p>
                </div>

                <div className="about-pillar-card">
                  <div className="pillar-header">
                    <span className="pillar-icon">📄</span>
                    <h4>Document Intelligence</h4>
                  </div>
                  <p>Local SQLite document vault with hybrid search, text chunking, and verifiable RAG provenance.</p>
                </div>

                <div className="about-pillar-card">
                  <div className="pillar-header">
                    <span className="pillar-icon">🛡️</span>
                    <h4>M8 Action Safety Guard</h4>
                  </div>
                  <p>Deterministic allowlisting for desktop applications and web actions. Zero arbitrary command execution.</p>
                </div>

                <div className="about-pillar-card full-width">
                  <div className="pillar-header">
                    <span className="pillar-icon">🎯</span>
                    <h4>Qualcomm Snapdragon X Target Architecture</h4>
                  </div>
                  <p>Architected for Qualcomm Snapdragon X Elite NPU acceleration via Snapdragon AI Hub and ONNX Runtime. Host development runtime executes on local CPU (x86_64).</p>
                </div>
              </div>
            </div>

            <div className="about-modal-footer">
              <span className="about-runtime-tag">HOST: CPU (x86_64) · TARGET: SNAPDRAGON X ELITE</span>
              <button className="about-done-btn" onClick={() => setIsAboutOpen(false)}>Close</button>
            </div>
          </div>
        </div>
      )}
    </header>
  );
}
