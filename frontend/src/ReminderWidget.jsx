import React, { useState, useEffect, useRef } from 'react';
import './ReminderWidget.css';

export default function ReminderWidget({ onOpenManager }) {
  const [reminders, setReminders] = useState([]);
  const [loading, setLoading] = useState(true);

  // Draggable Card Position State (Default Left Position below Telemetry)
  const [position, setPosition] = useState({ x: 25, y: 310 });
  const [isDragging, setIsDragging] = useState(false);

  const dragRef = useRef({
    startX: 0,
    startY: 0,
    initialPosX: 25,
    initialPosY: 310,
    hasMoved: false
  });

  useEffect(() => {
    fetchUpcomingReminders();
    const interval = setInterval(fetchUpcomingReminders, 4000);
    const handleUpdated = () => fetchUpcomingReminders();
    window.addEventListener('remindersUpdated', handleUpdated);

    return () => {
      clearInterval(interval);
      window.removeEventListener('remindersUpdated', handleUpdated);
    };
  }, []);

  const fetchUpcomingReminders = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/v1/reminders?timeframe=pending');
      if (res.ok) {
        const data = await res.json();
        setReminders(data.reminders || []);
      }
    } catch (e) {
      // Background retry
    } finally {
      setLoading(false);
    }
  };

  // Mouse Drag Handlers
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
          onOpenManager?.();
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
  }, [isDragging, onOpenManager]);

  const getNextReminder = () => {
    if (reminders.length === 0) return null;
    const sorted = [...reminders].sort((a, b) => new Date(a.datetime) - new Date(b.datetime));
    return sorted[0];
  };

  const nextItem = getNextReminder();

  const calculateTimeDiff = (targetIso) => {
    const diffMs = new Date(targetIso) - new Date();
    if (diffMs <= 0) return 'Due now';
    const diffMins = Math.round(diffMs / 60000);
    if (diffMins < 60) return `In ${diffMins} min${diffMins > 1 ? 's' : ''}`;
    const diffHours = Math.floor(diffMins / 60);
    const remMins = diffMins % 60;
    return `In ${diffHours}h ${remMins}m`;
  };

  return (
    <div
      className={`reminder-widget-card ${isDragging ? 'dragging' : ''}`}
      style={{
        left: `${position.x}px`,
        top: `${position.y}px`,
        position: 'fixed',
        zIndex: isDragging ? 1000 : 10
      }}
      onMouseDown={handleMouseDown}
      title="Drag to move | Click to open Reminder Manager"
    >
      <div className="reminder-widget-header">
        <span className="reminder-widget-title">🔔 REMINDERS</span>
        <span className="reminder-count-badge">{reminders.length} Active</span>
      </div>

      <div className="reminder-widget-content">
        {loading ? (
          <p className="reminder-empty-text">Loading schedule...</p>
        ) : nextItem ? (
          <div className="next-reminder-body">
            <span className="next-label">NEXT REMINDER</span>
            <div className="next-title-row">
              <h4 className="next-reminder-title">{nextItem.title}</h4>
              <span className={`next-priority-pill priority-${(nextItem.priority || 'normal').toLowerCase()}`}>
                {(nextItem.priority || 'NORMAL').toUpperCase()}
              </span>
            </div>
            <div className="next-time-row">
              <span className="next-time-str">
                ⏰ {new Date(nextItem.datetime).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
              </span>
              <span className="next-diff-str">({calculateTimeDiff(nextItem.datetime)})</span>
            </div>
          </div>
        ) : (
          <div className="next-reminder-empty">
            <p className="reminder-empty-text">✓ No pending reminders.</p>
            <span className="add-reminder-prompt">+ Tap to add reminder</span>
          </div>
        )}
      </div>
    </div>
  );
}
