import React, { useState, useEffect } from 'react';
import './ReminderManagerModal.css';

export default function ReminderManagerModal({ isOpen, onClose }) {
  const [reminders, setReminders] = useState([]);
  const [filter, setFilter] = useState('all'); // 'all' | 'upcoming' | 'completed' | 'overdue'
  const [searchQuery, setSearchQuery] = useState('');
  
  // Form State for New / Edit Reminder
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [title, setTitle] = useState('');
  const [datetime, setDatetime] = useState('');
  const [type, setType] = useState('reminder');
  const [priority, setPriority] = useState('normal');

  useEffect(() => {
    if (isOpen) {
      fetchReminders();
      const interval = setInterval(fetchReminders, 3000);
      const handleUpdated = () => fetchReminders();
      window.addEventListener('remindersUpdated', handleUpdated);

      return () => {
        clearInterval(interval);
        window.removeEventListener('remindersUpdated', handleUpdated);
      };
    }
  }, [isOpen, filter]);

  const fetchReminders = async () => {
    try {
      let url = 'http://localhost:8000/api/v1/reminders';
      if (filter === 'upcoming') url += '?timeframe=pending';
      else if (filter === 'overdue') url += '?timeframe=overdue';
      else if (filter === 'completed') url += '?status=completed';

      const res = await fetch(url);
      if (res.ok) {
        const data = await res.json();
        setReminders(data.reminders || []);
      }
    } catch (e) {
      console.warn('Failed to fetch reminders:', e);
    }
  };

  const handleCreateReminder = async (e) => {
    e.preventDefault();
    if (!title.trim() || !datetime) return;

    try {
      await fetch('http://localhost:8000/api/v1/reminders', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: title.trim(),
          datetime: new Date(datetime).toISOString(),
          type,
          priority
        })
      });
      setTitle('');
      setDatetime('');
      setShowCreateForm(false);
      fetchReminders();
      window.dispatchEvent(new CustomEvent('remindersUpdated'));
    } catch (err) {
      console.warn('Failed to create reminder:', err);
    }
  };

  const handleAction = async (id, action, newDt = null) => {
    try {
      await fetch(`http://localhost:8000/api/v1/reminders/${id}/action`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action, datetime: newDt })
      });
      fetchReminders();
      window.dispatchEvent(new CustomEvent('remindersUpdated'));
    } catch (e) {
      console.warn('Failed action:', e);
    }
  };

  const handleDelete = async (id) => {
    try {
      await fetch(`http://localhost:8000/api/v1/reminders/${id}`, {
        method: 'DELETE'
      });
      fetchReminders();
      window.dispatchEvent(new CustomEvent('remindersUpdated'));
    } catch (e) {
      console.warn('Failed delete:', e);
    }
  };

  if (!isOpen) return null;

  const filteredReminders = reminders.filter(r =>
    r.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
    (r.description && r.description.toLowerCase().includes(searchQuery.toLowerCase()))
  );

  return (
    <div className="reminder-modal-overlay">
      <div className="reminder-modal-container">
        {/* Header */}
        <div className="reminder-modal-header">
          <div className="header-title-row">
            <span className="modal-icon">🔔</span>
            <h2 className="modal-title">AIGIS REMINDER MANAGER</h2>
          </div>
          <button className="modal-close-btn" onClick={onClose}>✕</button>
        </div>

        {/* Toolbar: Search, Filters, Add Button */}
        <div className="reminder-modal-toolbar">
          <input
            type="text"
            className="reminder-search-input"
            placeholder="Search reminders..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />

          <div className="filter-tabs">
            <button className={`filter-btn ${filter === 'all' ? 'active' : ''}`} onClick={() => setFilter('all')}>All</button>
            <button className={`filter-btn ${filter === 'upcoming' ? 'active' : ''}`} onClick={() => setFilter('upcoming')}>Upcoming</button>
            <button className={`filter-btn ${filter === 'overdue' ? 'active' : ''}`} onClick={() => setFilter('overdue')}>Overdue</button>
            <button className={`filter-btn ${filter === 'completed' ? 'active' : ''}`} onClick={() => setFilter('completed')}>Completed</button>
          </div>

          <button className="create-reminder-btn" onClick={() => setShowCreateForm(!showCreateForm)}>
            {showCreateForm ? '✕ Cancel' : '+ New Reminder'}
          </button>
        </div>

        {/* Create Form */}
        {showCreateForm && (
          <form className="create-reminder-form" onSubmit={handleCreateReminder}>
            <input
              type="text"
              className="form-input"
              placeholder="Title (e.g. Call Mom, Team Meeting)"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              required
            />
            <input
              type="datetime-local"
              className="form-input"
              value={datetime}
              onChange={(e) => setDatetime(e.target.value)}
              required
            />
            <select className="form-select" value={type} onChange={(e) => setType(e.target.value)}>
              <option value="reminder">Reminder</option>
              <option value="meeting">Meeting</option>
              <option value="appointment">Appointment</option>
              <option value="task">Task</option>
              <option value="bill">Bill</option>
              <option value="medication">Medication</option>
            </select>
            <select className="form-select" value={priority} onChange={(e) => setPriority(e.target.value)}>
              <option value="normal">Normal Priority</option>
              <option value="high">High Priority</option>
              <option value="critical">Critical Priority</option>
            </select>
            <button type="submit" className="form-submit-btn">Save Reminder</button>
          </form>
        )}

        {/* Reminders Table / List */}
        <div className="reminder-list-container">
          {filteredReminders.length === 0 ? (
            <div className="modal-empty-state">
              <p>No matching reminders found.</p>
            </div>
          ) : (
            filteredReminders.map(r => (
              <div key={r.id} className={`reminder-item-card ${r.completed ? 'completed' : r.status}`}>
                <div className="item-main-info">
                  <div className="item-title-row">
                    <span className="item-title">{r.title}</span>
                    <span className={`priority-tag p-${(r.priority || 'normal').toLowerCase()}`}>
                      {(r.priority || 'normal').toUpperCase()}
                    </span>
                    <span className="type-tag">[{r.type.toUpperCase()}]</span>
                  </div>
                  <span className="item-time">
                    ⏰ {new Date(r.datetime).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })}
                  </span>
                </div>

                <div className="item-actions-row">
                  {!r.completed && (
                    <>
                      <button className="action-btn btn-done" title="Mark Complete" onClick={() => handleAction(r.id, 'complete')}>✓</button>
                      <button className="action-btn btn-snooze" title="Snooze 15m" onClick={() => handleAction(r.id, 'snooze')}>⏱</button>
                    </>
                  )}
                  <button className="action-btn btn-del" title="Delete" onClick={() => handleDelete(r.id)}>🗑</button>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
