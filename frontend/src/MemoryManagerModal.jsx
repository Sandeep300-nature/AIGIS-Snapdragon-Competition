import React, { useState, useEffect } from 'react';
import './MemoryManagerModal.css';

export default function MemoryManagerModal({ isOpen, onClose }) {
  const [activeTab, setActiveTab] = useState('ALL'); // 'ALL' | 'FACTS' | 'PREFERENCES' | 'LONG_TERM' | 'RECENT'
  const [searchQuery, setSearchQuery] = useState('');
  const [memoryData, setMemoryData] = useState({
    facts: [],
    preferences: [],
    longTerm: [],
    recent: [],
    totalCount: 0
  });
  const [isLoading, setIsLoading] = useState(false);
  const [editingMemory, setEditingMemory] = useState(null);
  const [editContent, setEditContent] = useState('');
  const [newCategory, setNewCategory] = useState('GENERAL_KNOWLEDGE');
  const [newContent, setNewContent] = useState('');
  const [isAdding, setIsAdding] = useState(false);

  useEffect(() => {
    if (isOpen) {
      fetchDashboardData();
    }
  }, [isOpen, searchQuery]);

  const fetchDashboardData = () => {
    setIsLoading(true);
    const url = searchQuery
      ? `http://localhost:8080/api/v1/memory-dashboard?query=${encodeURIComponent(searchQuery)}`
      : 'http://localhost:8080/api/v1/memory-dashboard';

    fetch(url)
      .then((res) => res.json())
      .then((data) => {
        setMemoryData({
          facts: data.facts || [],
          preferences: data.preferences || [],
          longTerm: data.longTerm || [],
          recent: data.recent || [],
          totalCount: data.totalCount || 0
        });
      })
      .catch((err) => console.warn('Memory Dashboard fetch error:', err))
      .finally(() => setIsLoading(false));
  };

  const handleTogglePin = (id, currentPinned) => {
    fetch('http://localhost:8080/api/v1/memory-dashboard/pin', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id, isPinned: !currentPinned })
    })
      .then(() => fetchDashboardData())
      .catch((err) => console.error('Pin error:', err));
  };

  const handleDelete = (id) => {
    if (!window.confirm('Are you sure you want to delete this memory item, sir?')) return;
    fetch('http://localhost:8080/api/v1/memory-dashboard/delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id })
    })
      .then(() => fetchDashboardData())
      .catch((err) => console.error('Delete error:', err));
  };

  const handleSaveEdit = () => {
    if (!editingMemory || !editContent.trim()) return;
    fetch('http://localhost:8080/api/v1/memory-dashboard/update', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: editingMemory.id, content: editContent })
    })
      .then(() => {
        setEditingMemory(null);
        fetchDashboardData();
      })
      .catch((err) => console.error('Update error:', err));
  };

  const handleCreateMemory = () => {
    if (!newContent.trim()) return;
    fetch('http://localhost:8080/api/v1/memory-dashboard/update', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: 'new', content: newContent, category: newCategory })
    })
      .then(() => {
        setNewContent('');
        setIsAdding(false);
        fetchDashboardData();
      })
      .catch((err) => console.error('Create error:', err));
  };

  const handleExport = () => {
    fetch('http://localhost:8080/api/v1/memory-dashboard/export')
      .then((res) => res.json())
      .then((data) => {
        const jsonStr = JSON.stringify(data.memories || [], null, 2);
        const blob = new Blob([jsonStr], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `AIGIS_Memory_Backup_${new Date().toISOString().slice(0, 10)}.json`;
        a.click();
      })
      .catch((err) => console.error('Export error:', err));
  };

  const handleImport = (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (evt) => {
      try {
        const parsed = JSON.parse(evt.target.result);
        fetch('http://localhost:8080/api/v1/memory-dashboard/import', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(parsed)
        })
          .then(() => fetchDashboardData())
          .catch((err) => console.error('Import error:', err));
      } catch (err) {
        alert('Invalid JSON file format.');
      }
    };
    reader.readAsText(file);
  };

  if (!isOpen) return null;

  const renderSection = (title, items, icon) => {
    if (!items || items.length === 0) return null;
    return (
      <div className="memory-section">
        <div className="section-title">
          <span className="sec-icon">{icon}</span>
          <h3>{title}</h3>
          <span className="sec-badge">{items.length}</span>
        </div>

        <div className="memory-cards-grid">
          {items.map((m) => (
            <div key={m.id} className={`memory-card glass-card ${m.is_pinned ? 'pinned' : ''}`}>
              <div className="card-top">
                <div className="top-badge-group">
                  <span className="cat-badge">{m.category}</span>
                  <span className="stars-badge" title={`Importance: ${m.importance_label || 'Permanent'}`}>
                    {m.stars || '★★★★★'} {m.importance_label || 'Permanent'}
                  </span>
                </div>
                <div className="card-actions">
                  <button
                    className={`icon-btn pin-btn ${m.is_pinned ? 'active' : ''}`}
                    onClick={() => handleTogglePin(m.id, m.is_pinned)}
                    title={m.is_pinned ? 'Unpin Memory' : 'Pin Memory'}
                  >
                    📌
                  </button>
                  <button
                    className="icon-btn edit-btn"
                    onClick={() => {
                      setEditingMemory(m);
                      setEditContent(m.content);
                    }}
                    title="Edit Memory"
                  >
                    ✏️
                  </button>
                  <button
                    className="icon-btn delete-btn"
                    onClick={() => handleDelete(m.id)}
                    title="Delete Memory"
                  >
                    🗑️
                  </button>
                </div>
              </div>

              <div className="card-body">
                <p>{m.content}</p>
              </div>


              <div className="card-footer">
                <span className="timestamp-text">
                  Updated {m.updated_at ? new Date(m.updated_at).toLocaleDateString() : 'Recently'}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  };

  return (
    <div className="modal-backdrop">
      <div className="memory-dashboard-modal glass-panel">
        <div className="modal-header">
          <div className="header-left">
            <h2>🧠 Memory Dashboard</h2>
            <span className="total-badge">{memoryData.totalCount} Active Memories</span>
          </div>
          <button className="close-btn" onClick={onClose}>×</button>
        </div>

        {/* Search & Action Bar */}
        <div className="dashboard-action-bar">
          <div className="search-box">
            <span className="search-icon">🔍</span>
            <input
              type="text"
              placeholder="Search facts, preferences, and project memories..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="search-input"
            />
            {searchQuery && (
              <button className="clear-search" onClick={() => setSearchQuery('')}>✕</button>
            )}
          </div>

          <div className="action-buttons">
            <button className="btn-secondary" onClick={() => setIsAdding(!isAdding)}>
              {isAdding ? 'Cancel' : '+ Add Memory'}
            </button>
            <button className="btn-secondary" onClick={handleExport} title="Export JSON backup">
              📥 Export
            </button>
            <label className="btn-secondary import-label" title="Import JSON backup">
              📤 Import
              <input type="file" accept=".json" onChange={handleImport} style={{ display: 'none' }} />
            </label>
          </div>
        </div>

        {/* Add Memory Form */}
        {isAdding && (
          <div className="add-memory-form glass-card">
            <h4>Add New Memory Fact</h4>
            <div className="form-row">
              <select value={newCategory} onChange={(e) => setNewCategory(e.target.value)} className="styled-select">
                <option value="GENERAL_KNOWLEDGE">Fact</option>
                <option value="USER_PREFERENCE">Preference</option>
                <option value="PROJECT_CONTEXT">Long-Term Memory</option>
              </select>
              <input
                type="text"
                placeholder="Enter memory content (e.g. Favorite IDE is VS Code)..."
                value={newContent}
                onChange={(e) => setNewContent(e.target.value)}
                className="styled-input"
              />
              <button className="btn-primary" onClick={handleCreateMemory}>Save</button>
            </div>
          </div>
        )}

        {/* Edit Modal / Inline Editor */}
        {editingMemory && (
          <div className="edit-memory-overlay">
            <div className="edit-dialog glass-panel">
              <h3>Edit Memory Item</h3>
              <textarea
                value={editContent}
                onChange={(e) => setEditContent(e.target.value)}
                className="styled-textarea"
                rows={4}
              />
              <div className="edit-actions">
                <button className="btn-secondary" onClick={() => setEditingMemory(null)}>Cancel</button>
                <button className="btn-primary" onClick={handleSaveEdit}>Save Changes</button>
              </div>
            </div>
          </div>
        )}

        {/* Main Categorized Dashboard Content */}
        <div className="dashboard-content scrollable">
          {isLoading ? (
            <div className="loading-spinner">Loading Memory Dashboard...</div>
          ) : (
            <>
              {renderSection('Facts', memoryData.facts, '💡')}
              {renderSection('Preferences', memoryData.preferences, '⚙️')}
              {renderSection('Long-Term Memories', memoryData.longTerm, '📚')}
              {renderSection('Recent Memories', memoryData.recent, '🕒')}

              {memoryData.totalCount === 0 && (
                <div className="empty-state">
                  <p>No active memory facts found.</p>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
