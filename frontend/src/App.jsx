import { useState, useEffect } from 'react';
import Navbar from './Navbar';
import Blob from './Blob';
import TerminalHUD from './TerminalHUD';
import SystemMetricsHUD from './SystemMetricsHUD';
import WeatherTimeHUD from './WeatherTimeHUD';
import ReminderNotificationModal from './ReminderNotificationModal';
import ReminderWidget from './ReminderWidget';
import ReminderManagerModal from './ReminderManagerModal';
import MemoryManagerModal from './MemoryManagerModal';
import DocumentManagerModal from './DocumentManagerModal';
import './App.css';


function App() {
  const [isReminderManagerOpen, setIsReminderManagerOpen] = useState(false);
  const [isMemoryManagerOpen, setIsMemoryManagerOpen] = useState(false);
  const [isDocumentManagerOpen, setIsDocumentManagerOpen] = useState(false);

  const [blobParams, setBlobParams] = useState({
    timeScale: 1.2,
    plasmaBrightness: 1.4,
    plasmaScale: 0.22,
    colorMid: '#00bfff',
    colorBright: '#00ffe1',
    rotationSpeedY: 0.005,
    micSensitivity: 2.2,
    jiggleAmount: 0.35,
    isMicActive: false,
  });

  const [currentState, setCurrentState] = useState('idle'); // 'idle' | 'listening' | 'thinking' | 'speaking' | 'error'
  const [currentMood, setCurrentMood] = useState('cyan');   // 'cyan' | 'red' | 'green' | 'violet' | 'amber'
  const [latencyMs, setLatencyMs] = useState(250);
  const [memoryCount, setMemoryCount] = useState(142);
  const [showMetricsHUD, setShowMetricsHUD] = useState(true);
  const [showWeatherHUD, setShowWeatherHUD] = useState(true);

  // HUD Focus State for Center Zoom Animation ('none' | 'telemetry' | 'weather')
  const [focusedHUD, setFocusedHUD] = useState('none');

  const [backendStatus, setBackendStatus] = useState({
    connected: false,
    message: 'Connecting to Spring Boot backend...',
    timestamp: null
  });

  useEffect(() => {
    const checkStatus = () => {
      if (!navigator.onLine) {
        setBackendStatus({
          connected: true,
          message: 'Offline Mode',
          timestamp: new Date().toISOString()
        });
        return;
      }

      fetch('http://localhost:8080/hello')
        .then((res) => {
          if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
          return res.json();
        })
        .then((data) => {
          setBackendStatus((prev) => ({
            connected: true,
            message: prev.message === 'Offline Mode' ? 'Offline Mode' : data.message,
            timestamp: data.timestamp
          }));
        })
        .catch((err) => {
          console.warn('Backend connection failed:', err);
          setBackendStatus({
            connected: false,
            message: 'Backend offline (http://localhost:8080)',
            timestamp: null
          });
          setCurrentState('error');
          setCurrentMood('red');
        });
    };

    checkStatus();

    const handleOffline = () => {
      setBackendStatus({
        connected: true,
        message: 'Offline Mode',
        timestamp: new Date().toISOString()
      });
    };

    const handleOnline = () => {
      checkStatus();
    };

    const handleCustomOfflineEvent = (e) => {
      if (e.detail?.isOffline || (e.detail?.provider && e.detail.provider.toLowerCase().includes('offline'))) {
        setBackendStatus({
          connected: true,
          message: 'Offline Mode',
          timestamp: new Date().toISOString()
        });
      }
    };

    window.addEventListener('offline', handleOffline);
    window.addEventListener('online', handleOnline);
    window.addEventListener('aigisOfflineMode', handleCustomOfflineEvent);

    return () => {
      window.removeEventListener('offline', handleOffline);
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('aigisOfflineMode', handleCustomOfflineEvent);
    };
  }, []);


  const handleUpdateParam = (key, value) => {
    setBlobParams((prev) => ({
      ...prev,
      [key]: value,
    }));
  };

  const handleToggleMic = () => {
    handleUpdateParam('isMicActive', !blobParams.isMicActive);
  };

  const handleStateUpdate = (state, mood) => {
    setCurrentState(state);
    if (mood) setCurrentMood(mood);
  };

  return (
    <div className="app-container">
      {/* Overlay Backdrop when a HUD is focused in center */}
      {focusedHUD !== 'none' && (
        <div 
          className="hud-focus-overlay"
          onClick={() => setFocusedHUD('none')}
          title="Click backdrop to dismiss zoom focus"
        />
      )}

      {/* Top Navigation Bar */}
      <Navbar
        blobParams={blobParams}
        onUpdateParam={handleUpdateParam}
        backendStatus={backendStatus}
        currentMood={currentMood}
        onMoodChange={(mood) => setCurrentMood(mood)}
        showMetrics={showMetricsHUD}
        onToggleMetrics={() => setShowMetricsHUD(!showMetricsHUD)}
        showWeather={showWeatherHUD}
        onToggleWeather={() => setShowWeatherHUD(!showWeatherHUD)}
        onOpenMemoryManager={() => setIsMemoryManagerOpen(true)}
        onOpenDocumentManager={() => setIsDocumentManagerOpen(true)}
      />

      {/* Movable Telemetry HUD Card (Left Side) */}
      <SystemMetricsHUD
        latencyMs={latencyMs}
        memoryCount={memoryCount}
        isVisible={showMetricsHUD}
        isFocused={focusedHUD === 'telemetry'}
        onToggleFocus={() => setFocusedHUD(prev => prev === 'telemetry' ? 'none' : 'telemetry')}
      />

      {/* Movable Weather & Time HUD Card (Right Side) */}
      <WeatherTimeHUD
        isVisible={showWeatherHUD}
        isFocused={focusedHUD === 'weather'}
        onToggleFocus={() => setFocusedHUD(prev => prev === 'weather' ? 'none' : 'weather')}
      />

      {/* 3D Audio-Reactive Orb Component (Main Character with Cyan Light Theme) */}
      <Blob
        blobParams={blobParams}
        onUpdateParam={handleUpdateParam}
        currentState={currentState}
        currentMood={currentMood}
      />

      <main className="main-content">
        <h1 className="app-title">AIGIS</h1>
        <p className="app-description">
          Interactive Audio-Reactive 3D Assistant
        </p>

        {/* Backend Connection Status Badge */}
        <div className={`backend-status-badge ${backendStatus.connected ? 'online' : 'offline'}`}>
          <span className="status-dot"></span>
          <span className="status-text">{backendStatus.message}</span>
        </div>
      </main>

      {/* Floating Draggable Reminders HUD Widget */}
      <ReminderWidget onOpenManager={() => setIsReminderManagerOpen(true)} />

      {/* Speech-to-Text Floating HUD Terminal */}
      <TerminalHUD
        isMicActive={blobParams.isMicActive}
        onToggleMic={handleToggleMic}
        onStateUpdate={handleStateUpdate}
        onLatencyUpdate={(ms) => setLatencyMs(ms)}
        onMemoryUpdate={(countOrFn) => {
          if (typeof countOrFn === 'function') {
            setMemoryCount(countOrFn);
          } else {
            setMemoryCount(countOrFn);
          }
        }}
        onFocusHUD={(hudName) => setFocusedHUD(hudName)}
        onResetFocusHUD={() => setFocusedHUD('none')}
        onOpenDocumentManager={() => setIsDocumentManagerOpen(true)}
      />

      {/* AIGIS Native Reminder & Scheduler Subsystem Overlay */}
      <ReminderNotificationModal />

      {/* Full Reminder Manager Modal */}
      <ReminderManagerModal
        isOpen={isReminderManagerOpen}
        onClose={() => setIsReminderManagerOpen(false)}
      />

      {/* Full Memory Dashboard Manager Modal */}
      <MemoryManagerModal
        isOpen={isMemoryManagerOpen}
        onClose={() => setIsMemoryManagerOpen(false)}
      />

      {/* Full Document Vault Manager Modal */}
      <DocumentManagerModal
        isOpen={isDocumentManagerOpen}
        onClose={() => setIsDocumentManagerOpen(false)}
      />
      {/* Hidden Audio DOM element for WebRTC Remote Audio Track playback */}
      <audio id="aigis-realtime-remote-audio" autoPlay style={{ display: 'none' }} />
    </div>
  );
}


export default App;
