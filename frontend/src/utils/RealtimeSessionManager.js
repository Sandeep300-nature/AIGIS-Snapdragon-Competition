import { RealtimeVoiceClient } from './RealtimeVoiceClient';

/**
 * AIGIS Realtime Session Manager
 * Orchestrates session lifecycle, ephemeral credential fetching, WebRTC connection state,
 * auto-reconnects, clean shutdown, and forwards tool events to the server-side AIGIS Tool Gateway.
 * 
 * Tool Security Rule:
 * This component NEVER authorizes or executes tools locally. All tool execution is strictly routed
 * to the authenticated server-side gateway endpoint (POST http://localhost:8000/api/v1/realtime/tools/execute).
 */
export class RealtimeSessionManager {
  constructor(options = {}) {
    this.backendUrl = options.backendUrl || 'http://localhost:8080';
    this.aiEngineUrl = options.aiEngineUrl || 'http://localhost:8000';
    this.audioElement = options.audioElement || null;
    this.sessionId = options.sessionId || 'default-session';

    this.onStateChange = options.onStateChange || (() => {});
    this.onFallbackTriggered = options.onFallbackTriggered || (() => {});
    this.onTranscriptUpdate = options.onTranscriptUpdate || (() => {});

    this.voiceClient = null;
    this.reconnectAttempts = 0;
    this.maxReconnects = 3;
    this.isFallbackActive = false;
  }

  // Binds HTML5 <audio> DOM element for remote audio track playback
  setAudioElement(element) {
    this.audioElement = element;
    if (this.voiceClient) {
      this.voiceClient.setAudioElement(element);
    }
  }

  // Start Realtime Session
  async startSession() {
    try {
      this.onStateChange('CONNECTING');

      // Step 1: Request ephemeral client token from backend gateway
      const tokenRes = await fetch(`${this.backendUrl}/api/v1/realtime/session`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });

      if (!tokenRes.ok) {
        throw new Error(`Session gateway returned status ${tokenRes.status}`);
      }

      const sessionData = await tokenRes.json();

      if (!sessionData.realtimeAvailable || !sessionData.clientSecret) {
        console.warn('Realtime API unavailable on backend:', sessionData.reason);
        this._triggerFallback(sessionData.reason);
        return false;
      }

      const clientSecretValue = typeof sessionData.clientSecret === 'object'
        ? sessionData.clientSecret.value
        : sessionData.clientSecret;

      // Step 2: Instantiate RealtimeVoiceClient
      this.voiceClient = new RealtimeVoiceClient({
        audioElement: this.audioElement,
        onStateChange: (state) => this._handleVoiceClientState(state),
        onSpeechStarted: (msg) => this._handleSpeechStarted(msg),
        onSpeechStopped: (msg) => this._handleSpeechStopped(msg),
        onToolCall: (msg) => this._handleToolCall(msg),
        onError: (err) => this._handleVoiceClientError(err),
      });

      // Step 3: Connect WebRTC PeerConnection
      await this.voiceClient.connect(clientSecretValue, sessionData.model);
      this.reconnectAttempts = 0;
      this.isFallbackActive = false;
      return true;
    } catch (error) {
      console.error('Failed to start Realtime session:', error);
      this._triggerFallback(error.message);
      return false;
    }
  }

  _handleVoiceClientState(state) {
    this.onStateChange(state);
  }

  _handleSpeechStarted(msg) {
    // Notify server-side synchronizer (Physical speech activity detected)
    fetch(`${this.aiEngineUrl}/api/v1/realtime/sync`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        sessionId: this.sessionId,
        eventType: 'speech_started',
      }),
    }).catch((e) => console.warn('Sync notice:', e));
  }

  _handleSpeechStopped(msg) {
    // Turn stopped signal
  }

  // Forward Tool Call to Authenticated Server-Side Tool Gateway
  async _handleToolCall(msg) {
    try {
      const callId = msg.call_id;
      const toolName = msg.name;
      const toolArgs = JSON.parse(msg.arguments || '{}');

      // Forward to Python AIGIS Tool Gateway for server-side authorization & execution
      const res = await fetch(`${this.aiEngineUrl}/api/v1/realtime/tools/execute`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: toolName,
          arguments: toolArgs,
        }),
      });

      const resultPayload = await res.json();

      // Send tool response back over WebRTC DataChannel
      if (this.voiceClient) {
        this.voiceClient.sendEvent({
          type: 'conversation.item.create',
          item: {
            type: 'function_call_output',
            call_id: callId,
            output: JSON.stringify(resultPayload),
          },
        });

        // Instruct model to continue outputting audio seamlessly
        this.voiceClient.sendEvent({ type: 'response.create' });
      }
    } catch (err) {
      console.error('Failed to execute tool via server gateway:', err);
    }
  }

  _handleVoiceClientError(err) {
    if (this.reconnectAttempts < this.maxReconnects) {
      this.reconnectAttempts++;
      console.log(`Attempting WebRTC reconnect (${this.reconnectAttempts}/${this.maxReconnects})...`);
      setTimeout(() => this.startSession(), 1000);
    } else {
      this._triggerFallback('Max reconnect attempts reached.');
    }
  }

  _triggerFallback(reason) {
    this.isFallbackActive = true;
    this.onStateChange('FALLBACK');
    this.onFallbackTriggered(reason);
  }

  // Clean Session Shutdown
  stopSession() {
    if (this.voiceClient) {
      this.voiceClient.disconnect();
      this.voiceClient = null;
    }
    this.onStateChange('IDLE');
  }
}
