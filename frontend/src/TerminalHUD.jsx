import React, { useState, useEffect, useRef } from 'react';
import './TerminalHUD.css';
import VoiceSelectorModal from './VoiceSelectorModal';
import { RealtimeSessionManager } from './utils/RealtimeSessionManager';
import {
  speak,
  cancelSpeech,
  preloadVoices,
  getVoiceProvider,
  getAvailableVoices,
  getVoiceSettings,
  saveVoiceSettings,
  getResponseLanguage,
  resetElevenLabs
} from './utils/speechService';

export default function TerminalHUD({ 
  isMicActive, 
  onToggleMic, 
  onStateUpdate,
  onLatencyUpdate,
  onMemoryUpdate,
  onFocusHUD,
  onResetFocusHUD
}) {
  const [inputText, setInputText] = useState('');
  const [aiReply, setAiReply] = useState('');
  const [openedUrl, setOpenedUrl] = useState(null);
  const [isThinking, setIsThinking] = useState(false);
  const [hasError, setHasError] = useState(false);
  const [provider, setProvider] = useState('');
  const [responseMeta, setResponseMeta] = useState(null);
  const [langMode, setLangMode] = useState('en-IN');
  const [sessionId] = useState(() => 'session-' + Math.random().toString(36).substring(2, 9));
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [voiceProvider, setVoiceProvider] = useState('');
  const [micStatusMsg, setMicStatusMsg] = useState('');
  const [showVoiceModal, setShowVoiceModal] = useState(false);
  const [sttMetadata, setSttMetadata] = useState(null);

  // Voice Settings State
  const [voiceSettings, setVoiceSettingsState] = useState(() => getVoiceSettings());
  const [availableVoices, setAvailableVoices] = useState([]);
  const [apiKeyInput, setApiKeyInput] = useState(() => localStorage.getItem('ELEVENLABS_API_KEY') || '');

  const isMicActiveRef = useRef(isMicActive);
  const langModeRef = useRef(langMode);
  const isSpeakingRef = useRef(isSpeaking);
  const isThinkingRef = useRef(isThinking);
  const inputRef = useRef(null);
  const recognitionRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const realtimeSessionRef = useRef(null);

  useEffect(() => {
    if (isMicActive) {
      const audioElem = document.getElementById('aigis-realtime-remote-audio');
      const sessionMgr = new RealtimeSessionManager({
        audioElement: audioElem,
        sessionId: sessionId,
        onStateChange: (state) => {
          if (state === 'SPEAKING') {
            setIsSpeaking(true);
            onStateUpdate && onStateUpdate('speaking');
          } else if (state === 'LISTENING') {
            setIsSpeaking(false);
            setIsThinking(false);
            onStateUpdate && onStateUpdate('listening');
          }
        },
        onFallbackTriggered: (reason) => {
          console.log('Realtime voice API fallback active:', reason);
        }
      });
      realtimeSessionRef.current = sessionMgr;
      sessionMgr.startSession();
    } else {
      if (realtimeSessionRef.current) {
        realtimeSessionRef.current.stopSession();
        realtimeSessionRef.current = null;
      }
    }
  }, [isMicActive, sessionId]);

  // Dynamic Session Greeting Engine (Runs ONLY ONCE per application launch / session)
  const generateSessionGreeting = () => {
    const now = new Date();
    const hours = now.getHours();
    let greetingText = '';

    if (hours >= 5 && hours < 12) {
      greetingText = "Good morning, sir. I hope you're having a great start to the day. How may I assist you?";
    } else if (hours >= 12 && hours < 17) {
      greetingText = "Good afternoon, sir. What can I help you with today?";
    } else if (hours >= 17 && hours < 22) {
      greetingText = "Good evening, sir. Welcome back. How may I assist you?";
    } else {
      greetingText = "Good evening, sir. You're up a little late tonight. How can I assist you?";
    }

    const lastSession = localStorage.getItem('AIGIS_LAST_SESSION_TIMESTAMP');
    if (lastSession) {
      const elapsedMs = Date.now() - parseInt(lastSession, 10);
      if (elapsedMs > 24 * 60 * 60 * 1000) {
        greetingText = "Welcome back, sir. " + greetingText;
      }
    }

    localStorage.setItem('AIGIS_LAST_SESSION_TIMESTAMP', Date.now().toString());
    return greetingText;
  };

  // Pre-load browser voices & trigger session greeting on mount
  useEffect(() => {
    preloadVoices((loadedVoices) => {
      setAvailableVoices(loadedVoices);
      setVoiceProvider(getVoiceProvider());
    });
    setAvailableVoices(getAvailableVoices());
    setVoiceProvider(getVoiceProvider());

    const handleVoiceChanged = () => {
      setVoiceProvider(getVoiceProvider());
    };
    window.addEventListener('voiceChanged', handleVoiceChanged);

    // Run Dynamic Session Greeting ONLY once per application session
    const hasGreetedThisSession = sessionStorage.getItem('AIGIS_SESSION_GREETED');
    if (!hasGreetedThisSession) {
      sessionStorage.setItem('AIGIS_SESSION_GREETED', 'true');
      const greetingText = generateSessionGreeting();
      setAiReply(greetingText);
      setProvider('AIGIS Core -> Session Greeting');

      const timer = setTimeout(() => {
        setVoiceProvider(getVoiceProvider());
        speak(
          greetingText,
          () => setIsSpeaking(true),
          () => setIsSpeaking(false)
        );
      }, 500);

      return () => {
        clearTimeout(timer);
        window.removeEventListener('voiceChanged', handleVoiceChanged);
      };
    }

    return () => window.removeEventListener('voiceChanged', handleVoiceChanged);
  }, []);

  useEffect(() => {
    isMicActiveRef.current = isMicActive;
  }, [isMicActive]);

  useEffect(() => {
    langModeRef.current = langMode;
  }, [langMode]);

  useEffect(() => {
    isSpeakingRef.current = isSpeaking;
  }, [isSpeaking]);

  useEffect(() => {
    isThinkingRef.current = isThinking;
  }, [isThinking]);

  // Sync state with parent & Orb visualizer
  useEffect(() => {
    if (hasError) {
      onStateUpdate?.('error', 'red');
    } else if (isThinking) {
      onStateUpdate?.('thinking', 'violet');
    } else if (isSpeaking) {
      onStateUpdate?.('speaking', 'cyan');
    } else if (isMicActive) {
      onStateUpdate?.('listening', 'cyan');
    } else {
      onStateUpdate?.('idle', 'cyan');
    }
  }, [isThinking, isSpeaking, isMicActive, hasError, onStateUpdate]);

  // Handle Speech Interruption & Mic Activation
  const handleMicClick = async () => {
    cancelSpeech();
    setIsSpeaking(false);

    if (!isMicActive) {
      try {
        if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
          const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
          stream.getTracks().forEach((t) => t.stop());
        }
        setMicStatusMsg('');
        setHasError(false);
      } catch (err) {
        console.warn('Microphone permission error:', err);
        setMicStatusMsg('Mic Permission Denied in Browser');
        setHasError(true);
        setTimeout(() => setHasError(false), 4000);
        return;
      }
    }

    onToggleMic();
  };

  // Real-time Phonetic Post-Processing for AIGIS brand recognition
  const processTranscriptText = (text) => {
    if (!text) return '';
    return text
      .replace(/\b(i\s*guess|eye\s*guess|aegis|ai\s*gis|eyegis|aygis|a\s*i\s*g\s*i\s*s|igh\s*guess|i\s*ges|aiges)\b/gi, 'AIGIS')
      .replace(/\b(aigis)\b/gi, 'AIGIS');
  };

  const toggleLanguage = (e) => {
    e.stopPropagation();
    const modes = ['en-IN', 'hi-IN', 'en-US'];
    const nextIdx = (modes.indexOf(langMode) + 1) % modes.length;
    setLangMode(modes[nextIdx]);
  };

  const getLangLabel = () => {
    if (langMode === 'en-IN') return 'EN/HI';
    if (langMode === 'hi-IN') return 'HI';
    return 'EN';
  };

  const handleInputChange = (e) => {
    setInputText(e.target.value);
  };

  // Clear session conversation memory in Spring Boot DB
  const handleClearMemory = async () => {
    try {
      cancelSpeech();
      onStateUpdate?.('idle', 'green');
      await fetch('http://localhost:8080/api/v1/chat/clear', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sessionId }),
      });
      setAiReply('Conversation memory cleared, sir.');
      setProvider('AIGIS Core -> Memory Controller');
      setOpenedUrl(null);
      setResponseMeta({
        engine: 'local',
        badge: '⚡ AIGIS Local',
        webSearchUsed: false,
        latencyMs: 0,
        metadata: { intent: 'memory_reset' }
      });
      onMemoryUpdate?.(0);
      setTimeout(() => {
        setAiReply('');
        setResponseMeta(null);
      }, 2500);
    } catch (err) {
      console.error('Failed to clear memory:', err);
    }
  };

  // Replay speech response from the beginning
  const handleReplaySpeech = async () => {
    if (isSpeaking) {
      cancelSpeech();
      setIsSpeaking(false);
    } else if (aiReply) {
      cancelSpeech();
      setVoiceProvider(getVoiceProvider());
      await speak(
        aiReply,
        () => setIsSpeaking(true),
        () => setIsSpeaking(false)
      );
    }
  };

  // Send prompt to Spring Boot backend
  const handleSend = async (overridePrompt = null) => {
    const isVoiceInput = typeof overridePrompt === 'string' && overridePrompt.trim().length > 0;
    const cleanText = (isVoiceInput ? overridePrompt : inputText).trim();
    if (!cleanText || isThinking) return;

    if (!isVoiceInput) {
      setSttMetadata(null);
    }

    // Turn OFF mic immediately upon sending so it ONLY turns on when manually tapped!
    if (isMicActive) {
      onToggleMic();
    }
    if (recognitionRef.current) {
      try { recognitionRef.current.stop(); } catch (e) {}
    }
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      try { mediaRecorderRef.current.stop(); } catch (e) {}
    }

    cancelSpeech();
    setIsSpeaking(false);
    setHasError(false);
    setOpenedUrl(null); // Clear previous opened URL so new URLs trigger re-opening cleanly
    setResponseMeta(null);

    setIsThinking(true);
    const sentPrompt = cleanText;
    setInputText('');

    // Check if user is asking about Telemetry or Weather to focus/zoom card in center
    if (/telemetry|system|cpu|gpu|ram|metrics|groq|performance/i.test(sentPrompt)) {
      onFocusHUD?.('telemetry');
    } else if (/weather|time|clock|temperature|atmospherics|date|location|city|humidity|wind/i.test(sentPrompt)) {
      onFocusHUD?.('weather');
    }

    // Natural Processing Transition Phrases for Live Operations (News, Weather, Stocks, Web Search, File Analysis)
    const TRANSITION_PHRASES = [
      "Give me just a moment, sir.",
      "Checking the latest information.",
      "Let me verify that.",
      "I'm pulling the latest data."
    ];

    const isLiveRetrieval = /weather|news|stock|price|market|search|latest|today|forecast|file|analyze|us30|bitcoin|gold|eur\/usd|what's happening|world/i.test(sentPrompt);

    if (isLiveRetrieval) {
      const transitionText = TRANSITION_PHRASES[Math.floor(Math.random() * TRANSITION_PHRASES.length)];
      setVoiceProvider(getVoiceProvider());
      speak(
        transitionText,
        () => setIsSpeaking(true),
        () => setIsSpeaking(false)
      );
    }

    const startTime = performance.now();

    try {
      const response = await fetch('http://localhost:8080/api/v1/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          prompt: sentPrompt,
          sessionId: sessionId,
          responseLanguage: getResponseLanguage(),
        }),
      });

      const elapsed = Math.round(performance.now() - startTime);
      onLatencyUpdate?.(elapsed);

      if (!response.ok) {
        throw new Error(`Server returned HTTP ${response.status}`);
      }

      const data = await response.json();
      let replyText = data.reply || '';
      let targetUrl = data.urlToOpen || null;

      const urlMatch = replyText.match(/\[OPEN_URL:\s*(https?:\/\/[^\s\]]+)\]/i);
      if (urlMatch) {
        if (!targetUrl) targetUrl = urlMatch[1];
        replyText = replyText.replace(/\[OPEN_URL:\s*(https?:\/\/[^\s\]]+)\]/gi, '').trim();
      }

      setAiReply(replyText);
      setOpenedUrl(targetUrl);
      setProvider(data.provider);
      setResponseMeta({
        engine: data.engine || (data.isOffline ? 'local' : 'cloud'),
        badge: data.badge || '',
        webSearchUsed: !!data.webSearchUsed,
        latencyMs: data.latencyMs || elapsed,
        metadata: data.metadata || {}
      });
      onMemoryUpdate?.(prev => prev + 2);

      if (data.isOffline || (data.provider && data.provider.toLowerCase().includes('offline'))) {
        window.dispatchEvent(new CustomEvent('aigisOfflineMode', { detail: { isOffline: true, provider: data.provider } }));
      }

      if (/reminder|scheduled|removed|deleted/i.test(replyText)) {
        window.dispatchEvent(new CustomEvent('remindersUpdated'));
      }


      if (targetUrl) {
        try {
          const win = window.open(targetUrl, '_blank', 'noopener,noreferrer');
          if (!win || win.closed || typeof win.closed === 'undefined') {
            console.warn('Browser pop-up blocker prevented auto-opening window');
            setMicStatusMsg('Popup blocked by browser. Click blue badge below to open.');
          }
        } catch (e) {
          console.warn('Browser pop-up blocker prevented auto-opening window:', e);
          setMicStatusMsg('Popup blocked by browser. Click blue badge below to open.');
        }
      }

      if (replyText) {
        setVoiceProvider(getVoiceProvider());
        await speak(
          replyText,
          () => setIsSpeaking(true),
          () => {
            setIsSpeaking(false);
            // Once AI finishes responding/speaking, return HUD back to docked position smoothly
            setTimeout(() => {
              onResetFocusHUD?.();
            }, 1800);
          }
        );
      } else {
        setTimeout(() => onResetFocusHUD?.(), 3000);
      }

    } catch (err) {
      console.error('Error sending prompt to backend:', err);
      setAiReply(`Error: Could not connect to backend (${err.message})`);
      setHasError(true);
      setTimeout(() => setHasError(false), 5000);
      onResetFocusHUD?.();
    } finally {
      setIsThinking(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleSend();
    }
  };

  // M5: Speech-to-Text Engine (Primary: Local faster-whisper tiny.en | Fallback: Browser Web Speech API)
  useEffect(() => {
    const SpeechRecognitionClass = window.SpeechRecognition || window.webkitSpeechRecognition;

    let recognition = null;
    let restartTimer = null;
    let mediaStream = null;
    let recorder = null;
    let isCancelled = false;

    if (isMicActive) {
      // 1. PRIMARY: Initialize local audio recording for faster-whisper tiny.en
      const startLocalSTT = async () => {
        try {
          if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            throw new Error('getUserMedia not available in browser');
          }
          const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
          if (isCancelled) {
            stream.getTracks().forEach(t => t.stop());
            return;
          }
          mediaStream = stream;
          audioChunksRef.current = [];

          let options = {};
          if (typeof MediaRecorder !== 'undefined') {
            if (MediaRecorder.isTypeSupported('audio/webm;codecs=opus')) {
              options = { mimeType: 'audio/webm;codecs=opus' };
            } else if (MediaRecorder.isTypeSupported('audio/webm')) {
              options = { mimeType: 'audio/webm' };
            }
          }

          recorder = new MediaRecorder(stream, options);
          mediaRecorderRef.current = recorder;

          recorder.ondataavailable = (e) => {
            if (e.data && e.data.size > 0) {
              audioChunksRef.current.push(e.data);
            }
          };

          recorder.onstop = async () => {
            if (audioChunksRef.current.length === 0) return;
            const audioBlob = new Blob(audioChunksRef.current, { type: recorder.mimeType || 'audio/webm' });
            audioChunksRef.current = [];

            // Prevent processing if AIGIS is already speaking or thinking
            if (isSpeakingRef.current || isThinkingRef.current) return;

            try {
              setMicStatusMsg('🎙️ Transcribing locally (faster-whisper tiny.en)...');
              const res = await fetch('http://127.0.0.1:8000/api/v1/voice/transcribe', {
                method: 'POST',
                headers: { 'Content-Type': recorder.mimeType || 'audio/webm' },
                body: audioBlob
              });

              if (res.ok) {
                const data = await res.json();
                if (data.success && data.transcript && data.transcript.trim()) {
                  const processed = processTranscriptText(data.transcript.trim());
                  setInputText(processed);
                  setSttMetadata({
                    provider: 'faster-whisper',
                    label: `🎙️ Local STT · faster-whisper tiny.en (${data.latencyMs}ms)`,
                    type: 'local',
                    latencyMs: data.latencyMs,
                    title: `Provider: faster-whisper | Device: ${data.device} | Runtime: ${data.runtime} | RTF: ${data.realtimeFactor}`
                  });
                  setMicStatusMsg('');
                  handleSend(processed);
                  return;
                }
              }
            } catch (err) {
              console.warn('Local STT request failed; browser Web Speech fallback available:', err);
            }
            setMicStatusMsg('');
          };

          recorder.start(1000);
          setMicStatusMsg('🎙️ Listening locally (faster-whisper)...');
        } catch (err) {
          console.warn('Could not initialize local MediaRecorder STT:', err);
        }
      };

      startLocalSTT();

      // 2. FALLBACK: Browser Web Speech API
      if (SpeechRecognitionClass) {
        try {
          recognition = new SpeechRecognitionClass();
          recognitionRef.current = recognition;
          recognition.continuous = true;
          recognition.interimResults = true;
          recognition.maxAlternatives = 1;
          recognition.lang = langModeRef.current;

          recognition.onresult = (event) => {
            if (isSpeakingRef.current || isThinkingRef.current || (window.speechSynthesis && window.speechSynthesis.speaking)) {
              return;
            }

            let fullSpeech = '';
            for (let i = 0; i < event.results.length; i++) {
              fullSpeech += event.results[i][0].transcript + ' ';
            }
            if (fullSpeech.trim()) {
              const processed = processTranscriptText(fullSpeech.trim());
              setInputText(processed);
              setSttMetadata(prev => prev && prev.type === 'local' ? prev : {
                provider: 'Web Speech API',
                label: '🎙️ Browser STT · Web Speech API fallback',
                type: 'fallback',
                title: 'Browser Web Speech API (Cloud/Browser fallback - not guaranteed offline)'
              });
            }
          };

          recognition.onerror = (err) => {
            console.warn('Speech Recognition notice:', err.error);
            if (err.error === 'not-allowed') {
              setMicStatusMsg('Microphone blocked by browser settings.');
              setHasError(true);
            } else if (err.error === 'audio-capture') {
              setMicStatusMsg('No microphone detected.');
            }
          };

          recognition.onend = () => {
            if (isMicActiveRef.current) {
              restartTimer = setTimeout(() => {
                try {
                  if (isMicActiveRef.current && recognitionRef.current) {
                    recognitionRef.current.start();
                  }
                } catch (e) {}
              }, 200);
            }
          };

          recognition.start();
        } catch (err) {
          console.error('Failed to start SpeechRecognition fallback:', err);
        }
      }
    } else {
      setMicStatusMsg('');
    }

    return () => {
      isCancelled = true;
      if (restartTimer) clearTimeout(restartTimer);
      if (recorder && recorder.state !== 'inactive') {
        try { recorder.stop(); } catch (e) {}
      }
      if (mediaStream) {
        try { mediaStream.getTracks().forEach(t => t.stop()); } catch (e) {}
      }
      if (recognition) {
        try { recognition.stop(); } catch (e) {}
      }
      recognitionRef.current = null;
      mediaRecorderRef.current = null;
    };
  }, [isMicActive, langMode]);

  // Voice Settings Handlers
  const handleSaveVoiceSettings = (key, val) => {
    const updated = saveVoiceSettings({ [key]: val });
    setVoiceSettingsState(updated);
  };

  const handleSaveApiKey = (e) => {
    const val = e.target.value.trim();
    setApiKeyInput(val);
    if (val) {
      localStorage.setItem('ELEVENLABS_API_KEY', val);
      resetElevenLabs();
    } else {
      localStorage.removeItem('ELEVENLABS_API_KEY');
    }
  };

  const handleTestVoice = async () => {
    cancelSpeech();
    setVoiceProvider(getVoiceProvider());
    await speak(
      'Always at your service, sir. Systems operational and ready for your command.',
      () => setIsSpeaking(true),
      () => setIsSpeaking(false)
    );
  };

  const getProvenanceBadge = () => {
    if (!responseMeta) {
      if (provider) {
        return { label: provider, type: 'default', title: provider };
      }
      return null;
    }

    const meta = responseMeta.metadata || {};
    const intent = meta.intent || '';

    // 1. Genuine local SLM inference (SmolLM2-135M on CPU)
    if (meta.localInference || meta.model === 'SmolLM2-135M-Instruct' || (provider && provider.includes('SmolLM2'))) {
      const tokSec = meta.tokensPerSec ? ` · ${meta.tokensPerSec} tok/s` : '';
      return {
        label: `⚡ Local SLM (SmolLM2-135M${tokSec})`,
        type: 'local',
        title: `Model: SmolLM2-135M-Instruct | Device: ${meta.device || 'CPU'} | Runtime: ${meta.runtime || 'PyTorch'}`
      };
    }

    // 2. Action execution (Notepad, YouTube, app launching)
    if (intent === 'desktop_action' || intent === 'web_action' || (provider && (provider.includes('Desktop Control') || provider.includes('Desktop Action')))) {
      return {
        label: '🖥️ Desktop Action (Executed)',
        type: 'action',
        title: 'Deterministic desktop or browser navigation executed on-device'
      };
    }

    // 3. System clock / telemetry
    if (intent === 'time' || intent === 'hardware' || intent === 'privacy' || (provider && provider.includes('Local On-Device'))) {
      return {
        label: '⚙️ System Telemetry (Local Clock)',
        type: 'system',
        title: 'Deterministic local system clock and hardware telemetry'
      };
    }

    // 4. Live Web Search (Tavily/RSS)
    if (responseMeta.webSearchUsed || intent === 'live_web' || (provider && provider.includes('Live Search'))) {
      return {
        label: '🌐 Live Web (Tavily/RSS Facts)',
        type: 'live-web',
        title: 'Real-time facts fetched from the internet via verified live search'
      };
    }

    // 5. Cloud AI (Groq)
    if (responseMeta.engine === 'cloud' || (provider && provider.includes('Groq'))) {
      return {
        label: '☁️ Cloud AI (Groq)',
        type: 'cloud',
        title: 'Cloud language model synthesis'
      };
    }

    // 6. Generic Local Fallback
    if (responseMeta.engine === 'local') {
      return {
        label: '⚡ AIGIS Local (On-Device)',
        type: 'local',
        title: 'Local on-device execution'
      };
    }

    return {
      label: provider || 'AIGIS AI',
      type: 'default',
      title: provider
    };
  };

  const renderReplyContent = (text) => {
    if (!text) return null;

    const lines = text.split('\n');
    const hasStructuredFacts = lines.length > 1 && lines.some(l => 
      l.trim().startsWith('- Fact') || 
      l.trim().startsWith('* ') || 
      l.trim().startsWith('- ') ||
      l.trim().startsWith('VERIFIED REAL-TIME FACTS')
    );

    if (hasStructuredFacts) {
      return (
        <div className="formatted-reply-body">
          {lines.map((line, idx) => {
            const trimmed = line.trim();
            if (!trimmed) return <div key={idx} className="reply-spacer" />;
            if (trimmed.startsWith('VERIFIED REAL-TIME FACTS') || trimmed.startsWith('NOTE:')) {
              return (
                <div key={idx} className="reply-header-note">
                  {trimmed}
                </div>
              );
            }
            if (trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
              return (
                <div key={idx} className="reply-bullet-item">
                  <span className="bullet-bullet">›</span>
                  <span className="bullet-text">{trimmed.replace(/^[-*]\s*/, '')}</span>
                </div>
              );
            }
            return <div key={idx} className="reply-paragraph">{trimmed}</div>;
          })}
        </div>
      );
    }

    return <p className="ai-response-text">{text}</p>;
  };

  return (
    <div className="terminal-hud-wrapper">
      {/* AI Response Message Bubble Floating Above Terminal HUD */}
      {aiReply && (
        <div className="ai-response-bubble glass-panel">
          <div className="ai-response-header">
            <span className="ai-badge">$ A.I.G.I.S. RESPONSE</span>
            {(() => {
              const badge = getProvenanceBadge();
              if (!badge) return null;
              return (
                <span className={`provider-tag provenance-tag provenance-${badge.type}`} title={badge.title}>
                  {badge.label}
                </span>
              );
            })()}
            {responseMeta?.latencyMs > 0 && (
              <span className="meta-metric-pill" title="Processing latency">
                ⏱️ {responseMeta.latencyMs}ms
              </span>
            )}
            {openedUrl && <span className="web-badge-tag">🌐 WEB ACCESS</span>}
            {sttMetadata && (
              <span className={`provider-tag stt-tag stt-${sttMetadata.type}`} title={sttMetadata.title || "Speech-to-Text Provenance"}>
                {sttMetadata.label || sttMetadata.provider}
              </span>
            )}
            {voiceProvider && (
              <button 
                className="provider-tag voice-tag clickable-badge"
                onClick={() => setShowVoiceModal(true)}
                title="Click to select or change AI voice"
              >
                🔊 {voiceProvider}
              </button>
            )}

            {/* Volume / Replay Speaker Button */}
            <button 
              className={`speaker-replay-btn ${isSpeaking ? 'speaking' : ''}`}
              onClick={handleReplaySpeech}
              title={isSpeaking ? "Click to stop speech" : "Click to replay response from beginning"}
            >
              <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon>
                <path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"></path>
              </svg>
              <span>{isSpeaking ? 'STOP' : 'REPLAY'}</span>
            </button>

            <button className="close-reply-btn" onClick={() => { setAiReply(''); setOpenedUrl(null); setResponseMeta(null); cancelSpeech(); setIsSpeaking(false); }}>×</button>
          </div>
          <div className="ai-response-content">
            {renderReplyContent(aiReply)}
          </div>
          {openedUrl && (
            <div className="opened-site-banner">
              <a href={openedUrl} target="_blank" rel="noopener noreferrer" className="opened-site-link">
                🌐 Opened Website: <span>{openedUrl}</span> ↗
              </a>
            </div>
          )}
        </div>
      )}

      {/* Mic Status Warning Message */}
      {micStatusMsg && (
        <div className="mic-status-banner">
          ⚠️ {micStatusMsg}
        </div>
      )}

      {/* Ambient Glow */}
      <div className={`terminal-hud-glow ${isThinking ? 'thinking' : isMicActive ? 'listening' : ''}`}></div>

      {/* Floating HUD Terminal Bar */}
      <div className={`terminal-hud-bar ${isThinking ? 'is-thinking' : ''}`}>
        {/* Terminal Title Badge */}
        <div className="terminal-prompt-btn" title="AIGIS Interactive Speech Terminal">
          <span className="prompt-symbol">$</span>
          <span className="prompt-name">
            {isThinking ? 'THINKING' : isMicActive ? 'LISTENING' : isSpeaking ? 'SPEAKING' : 'A.I.G.I.S.'}
          </span>
          <span className="prompt-arrow">&gt;</span>
        </div>

        {/* Microphone Toggle Button */}
        <button
          className={`terminal-mic-btn ${isMicActive ? 'recording' : ''} ${isSpeaking ? 'speaking-interrupt' : ''}`}
          onClick={handleMicClick}
          title={
            isSpeaking
              ? 'Click to INTERRUPT AI response & start speaking'
              : isMicActive
              ? 'Click to stop voice recording'
              : 'Click to start voice recording'
          }
        >
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"></path>
            <path d="M19 10v2a7 7 0 0 1-14 0v-2"></path>
            <line x1="12" y1="19" x2="12" y2="23"></line>
            <line x1="8" y1="23" x2="16" y2="23"></line>
          </svg>
          {isMicActive && <span className="mic-rec-dot"></span>}
        </button>

        {/* Input Line */}
        <div className="terminal-transcript">
          <input
            ref={inputRef}
            type="text"
            className="terminal-input"
            placeholder={
              isThinking
                ? 'Processing request with AIGIS...'
                : isMicActive
                ? 'Listening... speak now or type'
                : 'Type prompt or click Mic button to speak...'
            }
            value={inputText}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            disabled={isThinking}
          />
        </div>

        {/* Clear Memory Button */}
        <button
          className="clear-mem-btn"
          onClick={handleClearMemory}
          title="Clear Conversation Memory"
        >
          RESET MEMORY
        </button>

        {/* Voice Customization Button */}
        <button
          className="voice-settings-btn"
          onClick={() => setShowVoiceModal(!showVoiceModal)}
          title="Customize FRIDAY Voice & Audio Settings"
        >
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="3"></circle>
            <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path>
          </svg>
          VOICE
        </button>

        {/* Language Selector */}
        <button
          className="lang-selector-btn"
          onClick={toggleLanguage}
          title="Toggle speech language"
        >
          {getLangLabel()}
        </button>

        {/* Send Arrow Button */}
        <button
          className={`terminal-send-btn ${inputText.trim() ? 'has-text' : ''}`}
          onClick={handleSend}
          disabled={!inputText.trim() || isThinking}
          title="Send to AIGIS AI"
        >
          {isThinking ? (
            <span className="send-spinner"></span>
          ) : (
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <line x1="22" y1="2" x2="11" y2="13"></line>
              <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
            </svg>
          )}
        </button>
      </div>

      {/* Voice Customization Matrix Modal */}
      <VoiceSelectorModal
        isOpen={showVoiceModal}
        onClose={() => setShowVoiceModal(false)}
      />
    </div>
  );
}
