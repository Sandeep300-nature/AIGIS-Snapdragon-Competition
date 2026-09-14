import React, { useState, useEffect, useRef } from 'react';
import './WeatherTimeHUD.css';

export default function WeatherTimeHUD({ 
  isVisible = true,
  isFocused = false,
  onToggleFocus 
}) {
  const [timeStr, setTimeStr] = useState('');
  const [dateStr, setDateStr] = useState('');
  const [locationIndex, setLocationIndex] = useState(0);

  // Sample locations for interactive toggle
  const weatherLocations = [
    { city: 'LOCAL SYSTEM', temp: '28°C', condition: '🌤️ Clear Sky', humidity: '62%', wind: '12 km/h' },
    { city: 'NEW YORK', temp: '24°C', condition: '☀️ Sunny', humidity: '55%', wind: '14 km/h' },
    { city: 'LONDON', temp: '19°C', condition: '🌧️ Light Rain', humidity: '78%', wind: '18 km/h' },
    { city: 'TOKYO', temp: '26°C', condition: '☁️ Parted Clouds', humidity: '70%', wind: '9 km/h' }
  ];

  // Initialize position on top right using window width
  const [position, setPosition] = useState(() => ({
    x: Math.max(20, (window.innerWidth || 1200) - 265),
    y: 90
  }));

  const [isDragging, setIsDragging] = useState(false);
  const dragRef = useRef({ 
    startX: 0, 
    startY: 0, 
    initialPosX: 0, 
    initialPosY: 90,
    hasMoved: false 
  });

  // Update Live Clock
  useEffect(() => {
    const updateClock = () => {
      const now = new Date();
      setTimeStr(now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }));
      setDateStr(now.toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' }));
    };

    updateClock();
    const timer = setInterval(updateClock, 1000);
    return () => clearInterval(timer);
  }, []);

  // Mouse Drag & Click Event Handlers
  const handleMouseDown = (e) => {
    if (e.button !== 0) return;
    setIsDragging(true);
    dragRef.current = {
      startX: e.clientX,
      startY: e.clientY,
      initialPosX: position.x,
      initialPosY: position.y,
      hasMoved: false
    };
  };

  useEffect(() => {
    const handleMouseMove = (e) => {
      if (!isDragging) return;
      const dx = e.clientX - dragRef.current.startX;
      const dy = e.clientY - dragRef.current.startY;

      if (Math.hypot(dx, dy) > 5) {
        dragRef.current.hasMoved = true;
      }

      setPosition({
        x: dragRef.current.initialPosX + dx,
        y: dragRef.current.initialPosY + dy
      });
    };

    const handleMouseUp = () => {
      if (isDragging) {
        setIsDragging(false);
        if (!dragRef.current.hasMoved) {
          onToggleFocus?.();
        }
      }
    };

    if (isDragging) {
      window.addEventListener('mousemove', handleMouseMove);
      window.addEventListener('mouseup', handleMouseUp);
    }

    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isDragging, onToggleFocus]);

  const toggleLocation = (e) => {
    e.stopPropagation();
    setLocationIndex((prev) => (prev + 1) % weatherLocations.length);
  };

  if (!isVisible) return null;

  const currentWeather = weatherLocations[locationIndex];

  return (
    <div
      className={`weather-hud-card glass-panel ${isDragging ? 'is-dragging' : ''} ${isFocused ? 'is-focused' : ''}`}
      style={{
        left: isFocused ? '50%' : `${position.x}px`,
        top: isFocused ? '26%' : `${position.y}px`,
        cursor: isDragging ? 'grabbing' : 'pointer'
      }}
      onMouseDown={handleMouseDown}
      title={isFocused ? "Click to return to docked position" : "Click to focus in center, or drag to move"}
    >
      {/* Header with drag dots */}
      <div className="weather-drag-handle">
        <span className="drag-dots">⋮⋮</span>
        <span className="weather-header-title">TIME & ATMOSPHERICS</span>
        <button className="loc-toggle-btn" onClick={toggleLocation} title="Switch Location">
          🔄
        </button>
      </div>

      {/* Live Time Display */}
      <div className="weather-time-block">
        <span className="live-time">{timeStr}</span>
        <span className="live-date">{dateStr}</span>
      </div>

      {/* Weather Update Block */}
      <div className="weather-info-block">
        <div className="weather-main-row">
          <span className="weather-city">{currentWeather.city}</span>
          <span className="weather-temp">{currentWeather.temp}</span>
        </div>
        <div className="weather-cond-row">
          <span className="weather-condition">{currentWeather.condition}</span>
        </div>
        <div className="weather-stats-row">
          <span>💧 Humidity {currentWeather.humidity}</span>
          <span>💨 Wind {currentWeather.wind}</span>
        </div>
      </div>
    </div>
  );
}
