import React, { useState } from 'react';
import './Navbar.css';

export default function Navbar({ 
  blobParams, 
  onUpdateParam, 
  showMetrics, 
  onToggleMetrics,
  showWeather,
  onToggleWeather,
  onOpenMemoryManager
}) {
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [activeTab, setActiveTab] = useState('HOME');

  const navItems = ['HOME', 'MEMORY', 'SETTINGS', 'ABOUT'];

  const handleNavClick = (item) => {
    setActiveTab(item);
    if (item === 'SETTINGS') {
      setIsSettingsOpen(!isSettingsOpen);
    } else if (item === 'MEMORY') {
      setIsSettingsOpen(false);
      onOpenMemoryManager?.();
    } else {
      setIsSettingsOpen(false);
    }
  };


  return (
    <header className="navbar-wrapper">
      <div className="navbar-glow"></div>

      <nav className="navbar">
        <div className="nav-brand">
          <span className="brand-name">A.I.G.I.S.</span>
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
    </header>
  );
}
