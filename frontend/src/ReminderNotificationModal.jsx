import React, { useState, useEffect, useRef } from 'react';
import { speak } from './utils/speechService';
import './ReminderNotificationModal.css';

export default function ReminderNotificationModal() {
  const [notifications, setNotifications] = useState([]);
  const [startupSummary, setStartupSummary] = useState(null);
  const [showStartupModal, setShowStartupModal] = useState(false);
  const announcedIds = useRef(new Set());

  // 1. Fetch Startup Summary on Mount & Active Notifications
  useEffect(() => {
    fetchStartupSummary();
    fetchActiveNotifications();

    // 2. Poll for Background Due Notifications every 2 seconds for instant desktop delivery
    const interval = setInterval(() => {
      fetchActiveNotifications();
    }, 2000);

    const handleUpdated = () => fetchActiveNotifications();
    window.addEventListener('remindersUpdated', handleUpdated);

    return () => {
      clearInterval(interval);
      window.removeEventListener('remindersUpdated', handleUpdated);
    };
  }, []);

  const fetchStartupSummary = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/v1/reminders/startup-summary');
      if (res.ok) {
        const data = await res.json();
        if (data.has_startup_items) {
          setStartupSummary(data);
          setShowStartupModal(true);
        }
      }
    } catch (e) {
      // Background silent retry
    }
  };

  const playCyberpunkChime = () => {
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = 'sine';
      osc.frequency.setValueAtTime(587.33, ctx.currentTime);
      osc.frequency.exponentialRampToValueAtTime(880, ctx.currentTime + 0.15);
      gain.gain.setValueAtTime(0.15, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.35);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start();
      osc.stop(ctx.currentTime + 0.35);
    } catch (e) {}
  };

  const speakReminderAloud = async (text) => {
    try {
      await speak(text);
    } catch (e) {
      console.warn('Reminder speech alert error:', e);
    }
  };

  const fetchActiveNotifications = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/v1/reminders/active-notifications');
      if (res.ok) {
        const data = await res.json();
        const items = data.notifications || [];
        setNotifications(items);

        // Announce newly due reminders only once per ID
        const unannounced = items.filter(r => !announcedIds.current.has(r.id));
        if (unannounced.length > 0) {
          playCyberpunkChime();
          const latest = unannounced[0];
          speakReminderAloud(`Reminder. ${latest.title}. Scheduled for now.`);
          unannounced.forEach(r => announcedIds.current.add(r.id));
        }
      }
    } catch (e) {
      // Background silent retry
    }
  };

  const handleAction = async (reminderId, action) => {
    try {
      await fetch(`http://localhost:8000/api/v1/reminders/${reminderId}/action`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action })
      });
      setNotifications(prev => prev.filter(item => item.id !== reminderId));
      window.dispatchEvent(new CustomEvent('remindersUpdated'));
    } catch (e) {
      console.warn('Failed to update reminder action:', e);
    }
  };

  if (notifications.length === 0 && !showStartupModal) return null;

  return (
    <div className="reminder-overlay-container">
      {/* Startup Summary Modal */}
      {showStartupModal && startupSummary && (
        <div className="reminder-card startup-card">
          <div className="reminder-card-header">
            <span className="reminder-badge startup-badge">⚡ AIGIS SCHEDULE SUMMARY</span>
            <button className="reminder-close-btn" onClick={() => setShowStartupModal(false)}>✕</button>
          </div>
          <div className="reminder-card-body">
            <p className="startup-summary-text">{startupSummary.summary_text}</p>
          </div>
          <div className="reminder-card-actions">
            <button className="reminder-btn btn-primary" onClick={() => setShowStartupModal(false)}>
              Acknowledge
            </button>
          </div>
        </div>
      )}

      {/* Due / Overdue / Priority Notifications Stack */}
      {notifications.map(item => {
        const pClass = (item.priority_class || item.priority || 'ROUTINE').toUpperCase();
        return (
          <div key={item.id} className={`reminder-card notification-card ${pClass.toLowerCase()}`}>
            <div className="reminder-card-header">
              <span className={`reminder-badge priority-${pClass.toLowerCase()}`}>
                🔔 [{pClass}] REMINDER
              </span>
              <span className="reminder-type-tag">[{item.type.toUpperCase()}]</span>
              <button className="reminder-close-btn" onClick={() => handleAction(item.id, 'dismiss')}>✕</button>
            </div>
            <div className="reminder-card-body">
              <h4 className="reminder-title">{item.title}</h4>
              <p className="reminder-desc">{item.description}</p>
              <p className="reminder-time-stamp">
                ⏰ Scheduled: {new Date(item.datetime).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })}
              </p>
            </div>
            <div className="reminder-card-actions">
              <button className="reminder-btn btn-complete" onClick={() => handleAction(item.id, 'complete')}>
                ✓ Complete
              </button>
              <button className="reminder-btn btn-snooze" onClick={() => handleAction(item.id, 'snooze')}>
                ⏱ Snooze (+15m)
              </button>
              <button className="reminder-btn btn-dismiss" onClick={() => handleAction(item.id, 'dismiss')}>
                Dismiss
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
}
