/**
 * AIGIS Realtime Voice Client (WebRTC Audio & DataChannel Transport)
 * Focused media transport component responsible for:
 * - Microphone MediaStream acquisition
 * - WebRTC PeerConnection management
 * - WebRTC Remote AudioTrack binding to DOM <audio> element
 * - WebRTC DataChannel raw event routing
 * - Emitting client state callbacks (onStateChange, onSpeechStarted, onSpeechStopped, onToolCall)
 * 
 * NO TaskEngine, memory, or desktop authorization logic is contained in this file.
 */
export class RealtimeVoiceClient {
  constructor(options = {}) {
    this.audioElement = options.audioElement || null;
    this.onStateChange = options.onStateChange || (() => {});
    this.onSpeechStarted = options.onSpeechStarted || (() => {});
    this.onSpeechStopped = options.onSpeechStopped || (() => {});
    this.onToolCall = options.onToolCall || (() => {});
    this.onError = options.onError || (() => {});

    this.peerConnection = null;
    this.dataChannel = null;
    this.mediaStream = null;
    this.state = 'IDLE'; // IDLE | CONNECTING | CONNECTED | LISTENING | SPEAKING | DISCONNECTED
  }

  // Binds remote audio track to DOM audio element for hardware-accelerated playback
  setAudioElement(element) {
    this.audioElement = element;
  }

  // Establishes WebRTC PeerConnection using ephemeral client secret token
  async connect(ephemeralToken, modelName = 'gpt-4o-realtime-preview') {
    try {
      this._updateState('CONNECTING');

      // Acquire microphone MediaStream
      this.mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });

      // Create WebRTC PeerConnection
      this.peerConnection = new RTCPeerConnection();

      // Attach local mic audio track
      this.mediaStream.getTracks().forEach((track) => {
        this.peerConnection.addTrack(track, this.mediaStream);
      });

      // Bind incoming remote audio track to HTML5 <audio> element
      this.peerConnection.ontrack = (event) => {
        if (this.audioElement) {
          this.audioElement.srcObject = event.streams[0];
          this.audioElement.play().catch((err) => console.warn('Remote audio autoplay notice:', err));
        }
      };

      // Create DataChannel for realtime events & state sync
      this.dataChannel = this.peerConnection.createDataChannel('oai-events');
      this._setupDataChannelListeners();

      // Create Offer SDP
      const offer = await this.peerConnection.createOffer();
      await this.peerConnection.setLocalDescription(offer);

      // Exchange SDP with OpenAI Realtime Endpoint via ephemeral token
      const baseUrl = 'https://api.openai.com/v1/realtime';
      const response = await fetch(`${baseUrl}?model=${modelName}`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${ephemeralToken}`,
          'Content-Type': 'application/sdp',
        },
        body: offer.sdp,
      });

      if (!response.ok) {
        throw new Error(`Realtime SDP exchange failed with status ${response.status}`);
      }

      const answerSdp = await response.text();
      const answer = { type: 'answer', sdp: answerSdp };
      await this.peerConnection.setRemoteDescription(answer);

      this._updateState('CONNECTED');
    } catch (error) {
      console.error('RealtimeVoiceClient connection error:', error);
      this._updateState('DISCONNECTED');
      this.onError(error);
      throw error;
    }
  }

  // Listens to DataChannel raw JSON events
  _setupDataChannelListeners() {
    if (!this.dataChannel) return;

    this.dataChannel.onopen = () => {
      this._updateState('LISTENING');
    };

    this.dataChannel.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        this._handleServerEvent(msg);
      } catch (err) {
        console.warn('Malformed DataChannel message:', err);
      }
    };

    this.dataChannel.onerror = (err) => {
      console.error('DataChannel error:', err);
    };

    this.dataChannel.onclose = () => {
      this._updateState('DISCONNECTED');
    };
  }

  // Routes raw server events to client callbacks
  _handleServerEvent(msg) {
    switch (msg.type) {
      case 'input_audio_buffer.speech_started':
        // Physical speech activity detected: instantly mute/pause remote audio
        this._muteRemoteAudio(true);
        this._updateState('LISTENING');
        this.onSpeechStarted(msg);
        break;

      case 'input_audio_buffer.speech_stopped':
        this.onSpeechStopped(msg);
        break;

      case 'response.created':
      case 'response.audio.started':
        this._muteRemoteAudio(false);
        this._updateState('SPEAKING');
        break;

      case 'response.done':
        this._updateState('LISTENING');
        break;

      case 'response.function_call_arguments.done':
        // Tool call event: notify SessionManager (which delegates to server-side tool gateway)
        this.onToolCall(msg);
        break;

      default:
        break;
    }
  }

  // Sends event over WebRTC DataChannel
  sendEvent(eventPayload) {
    if (this.dataChannel && this.dataChannel.readyState === 'open') {
      this.dataChannel.send(JSON.stringify(eventPayload));
    }
  }

  // Mutes remote audio element immediately during barge-in
  _muteRemoteAudio(mute) {
    if (this.audioElement) {
      this.audioElement.muted = mute;
      if (mute) {
        this.audioElement.pause();
      } else {
        this.audioElement.play().catch(() => {});
      }
    }
  }

  _updateState(newState) {
    this.state = newState;
    this.onStateChange(newState);
  }

  // Clean shutdown & track cleanup
  disconnect() {
    if (this.mediaStream) {
      this.mediaStream.getTracks().forEach((t) => t.stop());
      this.mediaStream = null;
    }
    if (this.dataChannel) {
      try { this.dataChannel.close(); } catch (e) {}
      this.dataChannel = null;
    }
    if (this.peerConnection) {
      try { this.peerConnection.close(); } catch (e) {}
      this.peerConnection = null;
    }
    this._updateState('IDLE');
  }
}
