/**
 * AIGIS Speech Service — Customizable FRIDAY-style AI Voice
 * 
 * Primary:  ElevenLabs TTS (free tier, "Rachel" voice — calm, professional female)
 * Fallback: Microsoft / Browser SpeechSynthesis (female voice closest to FRIDAY)
 * 
 * Includes voice selection, speed/pitch customization, and auto-fallback.
 */

// ── ElevenLabs Configuration ───────────────────────────────────────────────────
const ELEVENLABS_VOICE_ID = '21m00Tcm4TlvDq8ikWAM';
const ELEVENLABS_API_URL = `https://api.elevenlabs.io/v1/text-to-speech/${ELEVENLABS_VOICE_ID}`;

const getApiKey = () => localStorage.getItem('ELEVENLABS_API_KEY') || '';

// ── Internal State & User Voice Settings ─────────────────────────────────────────
let elevenLabsDisabled = false;       // Flips true when quota runs out
let currentAudioElement = null;       // Tracks currently-playing <audio>
let currentUtterance = null;          // Tracks current SpeechSynthesisUtterance

const DEFAULT_SETTINGS = {
  selectedVoiceURI: '', // Custom voice URI, or empty for auto FRIDAY matching
  responseLanguage: 'en', // 'en' | 'hi' | 'en-IN'
  pitch: 0.95,          // Slightly lower pitch for FRIDAY composure (0.5 to 1.5)
  rate: 1.0,           // Speech speed rate (0.5 to 2.0)
};

export function getVoiceSettings() {
  try {
    const saved = localStorage.getItem('AIGIS_VOICE_SETTINGS');
    return saved ? { ...DEFAULT_SETTINGS, ...JSON.parse(saved) } : { ...DEFAULT_SETTINGS };
  } catch (e) {
    return { ...DEFAULT_SETTINGS };
  }
}

export function saveVoiceSettings(newSettings) {
  try {
    const current = getVoiceSettings();
    const updated = { ...current, ...newSettings };
    localStorage.setItem('AIGIS_VOICE_SETTINGS', JSON.stringify(updated));
    return updated;
  } catch (e) {
    return DEFAULT_SETTINGS;
  }
}

export function getResponseLanguage() {
  const settings = getVoiceSettings();
  return settings.responseLanguage || 'en';
}

export function setResponseLanguage(lang) {
  saveVoiceSettings({ responseLanguage: lang });
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('voiceChanged', { detail: { responseLanguage: lang } }));
  }
}

// ── Preferred Microsoft / Female browser voices (ordered by FRIDAY-likeness) ──
const PREFERRED_VOICE_NAMES = [
  'Microsoft Zira',            // Windows — clear American female
  'Microsoft Zira Desktop',
  'Microsoft Zira - English (United States)',
  'Zira',
  'Microsoft Hazel',           // Windows — British female
  'Microsoft Hazel Desktop',
  'Google US English',         // Chrome — female variant
  'Google UK English Female',
  'Samantha',                  // macOS — smooth female
  'Karen',                     // macOS — Australian female
  'Victoria',                  // macOS — American female
  'Moira',                     // macOS — Irish female
];

/**
 * Returns available system voices for selection dropdown.
 */
export function getAvailableVoices() {
  if (!('speechSynthesis' in window)) return [];
  return window.speechSynthesis.getVoices();
}

/**
 * Picks the best voice based on user preference or automatic FRIDAY matching.
 */
function getBestFallbackVoice() {
  const voices = getAvailableVoices();
  if (voices.length === 0) return null;

  const settings = getVoiceSettings();

  // 1. If user chose a specific voice URI
  if (settings.selectedVoiceURI) {
    const userVoice = voices.find(v => v.voiceURI === settings.selectedVoiceURI);
    if (userVoice) return userVoice;
  }

  // 2. Try exact preferred match (case-insensitive partial match)
  for (const preferred of PREFERRED_VOICE_NAMES) {
    const match = voices.find(v =>
      v.name.toLowerCase().includes(preferred.toLowerCase())
    );
    if (match) return match;
  }

  // 3. Try any voice with "female" in the name
  const femaleVoice = voices.find(v =>
    v.name.toLowerCase().includes('female')
  );
  if (femaleVoice) return femaleVoice;

  // 4. Try any English voice
  const englishVoice = voices.find(v =>
    v.lang?.startsWith('en')
  );
  if (englishVoice) return englishVoice;

  // 5. Absolute last resort
  return voices[0];
}

/**
 * Pre-load voices on app init.
 */
export function preloadVoices(onVoicesLoaded) {
  if ('speechSynthesis' in window) {
    window.speechSynthesis.getVoices();
    window.speechSynthesis.onvoiceschanged = () => {
      const voices = window.speechSynthesis.getVoices();
      if (onVoicesLoaded) onVoicesLoaded(voices);
    };
  }
}

// ── ElevenLabs TTS ─────────────────────────────────────────────────────────────
async function elevenLabsSpeak(text) {
  const apiKey = getApiKey();
  if (!apiKey || elevenLabsDisabled) return null;

  try {
    const response = await fetch(ELEVENLABS_API_URL, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'xi-api-key': apiKey,
      },
      body: JSON.stringify({
        text,
        model_id: 'eleven_multilingual_v2',
        voice_settings: {
          stability: 0.5,
          similarity_boost: 0.75,
          style: 0.4,
          use_speaker_boost: true,
        },
      }),
    });

    if (response.status === 401 || response.status === 429) {
      console.warn('[AIGIS Speech] ElevenLabs quota exhausted. Switching to browser voice.');
      elevenLabsDisabled = true;
      return null;
    }

    if (!response.ok) return null;

    return await response.blob();
  } catch (err) {
    console.warn('[AIGIS Speech] ElevenLabs error, using fallback:', err.message);
    return null;
  }
}

// ── English Text Normalizer for TTS ──────────────────────────────────────────
const ONES = ['', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten', 
              'eleven', 'twelve', 'thirteen', 'fourteen', 'fifteen', 'sixteen', 'seventeen', 'eighteen', 'nineteen'];
const TENS = ['', '', 'twenty', 'thirty', 'forty', 'fifty', 'sixty', 'seventy', 'eighty', 'ninety'];

const ORDINALS = {
  1: 'first', 2: 'second', 3: 'third', 4: 'fourth', 5: 'fifth', 6: 'sixth', 7: 'seventh', 8: 'eighth', 9: 'ninth', 10: 'tenth',
  11: 'eleventh', 12: 'twelfth', 13: 'thirteenth', 14: 'fourteenth', 15: 'fifteenth', 16: 'sixteenth', 17: 'seventeenth',
  18: 'eighteenth', 19: 'nineteenth', 20: 'twentieth', 21: 'twenty-first', 22: 'twenty-second', 23: 'twenty-third',
  24: 'twenty-fourth', 25: 'twenty-fifth', 26: 'twenty-sixth', 27: 'twenty-seventh', 28: 'twenty-eighth',
  29: 'twenty-ninth', 30: 'thirtieth', 31: 'thirty-first'
};

function numberToWords(num) {
  if (num === null || num === undefined) return '';
  const numStr = num.toString().replace(/,/g, '');
  const n = parseInt(numStr, 10);
  if (isNaN(n)) return num.toString();
  if (n === 0) return 'zero';

  if (n < 0) return 'minus ' + numberToWords(Math.abs(n));

  if (n < 20) return ONES[n];

  if (n < 100) {
    const tens = Math.floor(n / 10);
    const rest = n % 10;
    return TENS[tens] + (rest ? '-' + ONES[rest] : '');
  }

  if (n < 1000) {
    const hundred = Math.floor(n / 100);
    const rest = n % 100;
    return ONES[hundred] + ' hundred' + (rest ? ' ' + numberToWords(rest) : '');
  }

  if (n >= 1900 && n <= 2099 && typeof num === 'string' && !num.includes(',')) {
    const century = Math.floor(n / 100);
    const rest = n % 100;
    return numberToWords(century) + ' ' + (rest < 10 ? 'oh ' + numberToWords(rest) : numberToWords(rest));
  }

  if (n < 1000000) {
    const thousands = Math.floor(n / 1000);
    const rest = n % 1000;
    return numberToWords(thousands) + ' thousand' + (rest ? ' ' + numberToWords(rest) : '');
  }

  if (n < 1000000000) {
    const millions = Math.floor(n / 1000000);
    const rest = n % 1000000;
    return numberToWords(millions) + ' million' + (rest ? ' ' + numberToWords(rest) : '');
  }

  if (n < 1000000000000) {
    const billions = Math.floor(n / 1000000000);
    const rest = n % 1000000000;
    return numberToWords(billions) + ' billion' + (rest ? ' ' + numberToWords(rest) : '');
  }

  if (n < 1000000000000000) {
    const trillions = Math.floor(n / 1000000000000);
    const rest = n % 1000000000000;
    return numberToWords(trillions) + ' trillion' + (rest ? ' ' + numberToWords(rest) : '');
  }

  return n.toString();
}

function normalizeEnglishTTSText(text) {
  if (!text) return '';
  let str = text;

  // 0. Protection for specific terms & symbols (MUST run first)
  str = str.replace(/\bC\+\+(?!\w)/g, 'C plus plus');
  str = str.replace(/π/g, 'pi');
  str = str.replace(/∞/g, 'infinity');

  // 0. Comma-separated Large Numbers with optional Decimals (MUST run before any single-digit / decimal splitting)
  str = str.replace(/\b\d{1,3}(?:,\d{3})+(?:\.\d+)?\b/g, (match) => {
    if (match.includes('.')) {
      const [intPart, fracPart] = match.split('.');
      const intWords = numberToWords(intPart);
      const fracWords = fracPart.split('').map(d => (d === '0' ? 'zero' : ONES[parseInt(d, 10)] || d)).join(' ');
      return `${intWords} point ${fracWords}`;
    }
    return numberToWords(match);
  });

  // 1. Scientific Notation (MUST run before general decimals & exponents)
  str = str.replace(/\b(\d+(?:\.\d+)?)[eE]([+-]?\d+)\b/g, (match, base, exp) => {
    let baseText = base;
    if (base.includes('.')) {
      const [intP, fracP] = base.split('.');
      const intW = numberToWords(intP);
      const fracW = fracP.split('').map(d => (d === '0' ? 'zero' : ONES[parseInt(d, 10)] || d)).join(' ');
      baseText = `${intW} point ${fracW}`;
    } else {
      baseText = numberToWords(base);
    }
    
    let expNum = parseInt(exp, 10);
    let expText = expNum < 0 ? `minus ${numberToWords(Math.abs(expNum))}` : numberToWords(expNum);
    return `${baseText} times ten to the power of ${expText}`;
  });

  // 2. Units of Measurement (MUST run before general decimals & division)
  str = str.replace(/\b(\d+(?:\.\d+)?)\s*km\/h\b/gi, (m, n) => `${n} kilometers per hour`);
  str = str.replace(/\b(\d+(?:\.\d+)?)\s*m\/s\b/gi, (m, n) => `${n} meters per second`);
  str = str.replace(/\b(\d+(?:\.\d+)?)\s*kg\b/gi, (m, n) => `${n} kilograms`);
  str = str.replace(/\b(\d+(?:\.\d+)?)\s*(°C|degrees?\s*C|degrees?\s*Celsius)\b/gi, (m, n) => `${n} degrees Celsius`);
  str = str.replace(/\b(\d+(?:\.\d+)?)\s*(°F|degrees?\s*F|degrees?\s*Fahrenheit)\b/gi, (m, n) => `${n} degrees Fahrenheit`);
  str = str.replace(/\b(\d+(?:\.\d+)?)\s*V\b/g, (m, n) => `${n} volts`);

  // 3. Common Natural Fractions (MUST run before general division)
  str = str.replace(/\b1\/2\b/g, 'one half');
  str = str.replace(/\b1\/3\b/g, 'one third');
  str = str.replace(/\b2\/3\b/g, 'two thirds');
  str = str.replace(/\b1\/4\b/g, 'one quarter');
  str = str.replace(/\b3\/4\b/g, 'three quarters');

  // 4. Decimals (BEFORE integer normalization)
  str = str.replace(/\b(\d+)\.(\d+)\b/g, (match, intPart, fracPart) => {
    const intWords = numberToWords(intPart);
    const fracWords = fracPart.split('').map(d => (d === '0' ? 'zero' : ONES[parseInt(d, 10)] || d)).join(' ');
    return `${intWords} point ${fracWords}`;
  });

  // 5. Programming & Logical Operators
  str = str.replace(/(\b\w+|\d+)\s*===\s*(\b\w+|\d+)/g, (m, a, b) => `${a} strictly equals ${b}`);
  str = str.replace(/(\b\w+|\d+)\s*!==\s*(\b\w+|\d+)/g, (m, a, b) => `${a} strictly not equal to ${b}`);
  str = str.replace(/(\b\w+|\d+)\s*==\s*(\b\w+|\d+)/g, (m, a, b) => `${a} is equal to ${b}`);
  str = str.replace(/(\b\w+|\d+)\s*&&\s*(\b\w+|\d+)/g, (m, a, b) => `${a} and ${b}`);
  str = str.replace(/(\b\w+|\d+)\s*\|\|\s*(\b\w+|\d+)/g, (m, a, b) => `${a} or ${b}`);
  str = str.replace(/(?:^|\s)!([a-zA-Z_]\w*)\b/g, (match, varName) => {
    const prefix = match.startsWith(' ') ? ' ' : '';
    return `${prefix}not ${varName}`;
  });

  // 6. Arrows & Mappings
  str = str.replace(/(\b\w+|\d+)\s*->\s*(\b\w+|\d+)/g, (m, a, b) => `${a} points to ${b}`);
  str = str.replace(/(\b\w+|\d+)\s*=>\s*(\b\w+|\d+)/g, (m, a, b) => `${a} maps to ${b}`);
  str = str.replace(/←/g, 'left arrow');
  str = str.replace(/→/g, 'right arrow');

  // 7. Math Operators: *, ×, /, ÷, +, -, =, %
  str = str.replace(/(\b\w+|\d+)\s*%/g, (m, a) => `${a} percent`);
  str = str.replace(/(\b\w+|\d+)\s*[*×]\s*(\b\w+|\d+)/g, (m, a, b) => `${a} times ${b}`);
  str = str.replace(/(\b\w+|\d+)\s*[÷]\s*(\b\w+|\d+)/g, (m, a, b) => `${a} divided by ${b}`);
  str = str.replace(/(\b\w+|\d+)\s*\/\s*(\b\w+|\d+)/g, (m, a, b) => `${a} divided by ${b}`);
  str = str.replace(/(\b\w+|\d+)\s*\+\s*(\b\w+|\d+)/g, (m, a, b) => `${a} plus ${b}`);
  str = str.replace(/(\b\w+|\d+)\s+-\s+(\b\w+|\d+)/g, (m, a, b) => `${a} minus ${b}`);
  str = str.replace(/(\b\d+)\s*-\s*(\b\d+)/g, (m, a, b) => `${a} minus ${b}`);
  str = str.replace(/(\b\w+|\d+)\s*=\s*(\b\w+|\d+)/g, (m, a, b) => `${a} equals ${b}`);

  // 8. Exponents / Power (^, **)
  str = str.replace(/(\b\w+|\d+)\s*(\^|\*\*)\s*(\b\w+|\d+)/g, (m, a, op, b) => `${a} to the power of ${b}`);

  // 9. Comparisons (>=, <=, >, <)
  str = str.replace(/(\b\w+|\d+)\s*>=\s*(\b\w+|\d+)/g, (m, a, b) => `${a} is greater than or equal to ${b}`);
  str = str.replace(/(\b\w+|\d+)\s*<=\s*(\b\w+|\d+)/g, (m, a, b) => `${a} is less than or equal to ${b}`);
  str = str.replace(/(\b\w+|\d+)\s*>\s*(\b\w+|\d+)/g, (m, a, b) => `${a} is greater than ${b}`);
  str = str.replace(/(\b\w+|\d+)\s*<\s*(\b\w+|\d+)/g, (m, a, b) => `${a} is less than ${b}`);

  // 10. Not equals (!=, ≠)
  str = str.replace(/(\b\w+|\d+)\s*(!=|≠)\s*(\b\w+|\d+)/g, (m, a, op, b) => `${a} is not equal to ${b}`);

  // 11. Approximately equal (≈, ~=)
  str = str.replace(/(\b\w+|\d+)\s*(≈|~=)\s*(\b\w+|\d+)/g, (m, a, op, b) => `${a} is approximately ${b}`);

  // 12. Square Root (√)
  str = str.replace(/√(\b\w+|\d+)/g, (m, a) => `square root of ${a}`);

  // 13. Times: e.g. "2:05 PM", "12:30 AM", "8:15"
  str = str.replace(/\b(\d{1,2}):(\d{2})\s*(AM|PM|am|pm)?\b/g, (match, h, m, meridiem) => {
    const hourNum = parseInt(h, 10);
    const minNum = parseInt(m, 10);
    const hourStr = numberToWords(hourNum);
    let minStr = '';
    if (minNum === 0) {
      minStr = '';
    } else if (minNum < 10) {
      minStr = 'oh ' + ONES[minNum];
    } else {
      minStr = numberToWords(minNum);
    }
    const ampmStr = meridiem ? ' ' + meridiem.toUpperCase() : '';
    return `${hourStr} ${minStr}${ampmStr}`.trim();
  });

  // 14. Dates: e.g. "July 28, 2026", "28th July", "July 28"
  str = str.replace(/\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|January|February|March|April|June|July|August|September|October|November|December)\s+(\d{1,2})(?:st|nd|rd|th)?,?\s*(\d{4})?\b/gi, (match, month, day, year) => {
    const dayNum = parseInt(day, 10);
    const dayStr = ORDINALS[dayNum] || numberToWords(dayNum);
    const yearStr = year ? ' ' + numberToWords(parseInt(year, 10)) : '';
    return `${month} ${dayStr}${yearStr}`;
  });

  // 15. Percentages: e.g. "90%", "25%"
  str = str.replace(/\b(\d+)%\b/g, (match, num) => {
    return `${numberToWords(num)} percent`;
  });

  // 16. Currencies: e.g. "$50", "₹500"
  str = str.replace(/\$(\d+)\b/g, (match, num) => {
    return `${numberToWords(num)} dollars`;
  });
  str = str.replace(/₹(\d+)\b/g, (match, num) => {
    return `${numberToWords(num)} rupees`;
  });

  // 17. Standalone digits: e.g. "8 hours", "90"
  str = str.replace(/\b(\d{1,3})\b/g, (match, num) => {
    return numberToWords(num);
  });

  return str;
}

// ── Browser Fallback TTS ───────────────────────────────────────────────────────
function browserSpeak(text, onStart, onEnd, targetVoiceURI = null) {
  if (!('speechSynthesis' in window)) {
    onEnd?.();
    return;
  }

  window.speechSynthesis.cancel();

  const settings = getVoiceSettings();
  const respLang = settings.responseLanguage || 'en';
  const processedText = (respLang !== 'hi') ? normalizeEnglishTTSText(text) : text;

  const utterance = new SpeechSynthesisUtterance(processedText);
  
  let voice = null;
  if (targetVoiceURI && targetVoiceURI !== 'auto') {
    const voices = getAvailableVoices();
    voice = voices.find(v => v.voiceURI === targetVoiceURI);
  }
  if (!voice) {
    voice = getBestFallbackVoice();
  }

  if (voice) {
    utterance.voice = voice;
  }

  // Ensure utterance language matches response language setting
  // If response language is English, force 'en-IN' so numbers (90%), times (8 hours), and percentages stay in English
  if (respLang === 'hi') {
    utterance.lang = 'hi-IN';
  } else {
    utterance.lang = 'en-IN';
  }

  utterance.rate = settings.rate || 1.0;
  utterance.pitch = settings.pitch || 0.95;
  utterance.volume = 1.0;

  utterance.onstart = () => onStart?.();
  utterance.onend = () => {
    currentUtterance = null;
    onEnd?.();
  };
  utterance.onerror = () => {
    currentUtterance = null;
    onEnd?.();
  };

  currentUtterance = utterance;
  window.speechSynthesis.speak(utterance);
}

// ── Public API ─────────────────────────────────────────────────────────────────
export function findGoogleHindiVoice(voices = null) {
  const list = voices || getAvailableVoices();
  return list.find(v => 
    v.name.toLowerCase().includes('हिन्दी') || 
    v.name.toLowerCase().includes('hindi') || 
    (v.lang && v.lang.toLowerCase() === 'hi-in')
  ) || null;
}

export function setSelectedVoice(voiceURI, responseLanguage = null) {
  const payload = { selectedVoiceURI: voiceURI };
  if (responseLanguage) {
    payload.responseLanguage = responseLanguage;
  }
  saveVoiceSettings(payload);
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('voiceChanged', { detail: { voiceURI, responseLanguage } }));
  }
}

export function getEffectiveActiveVoiceURI() {
  const settings = getVoiceSettings();
  if (settings.selectedVoiceURI && settings.selectedVoiceURI !== 'auto') {
    return settings.selectedVoiceURI;
  }
  const best = getBestFallbackVoice();
  return best ? best.voiceURI : '';
}

export async function speak(text, onStart, onEnd, targetVoiceURI = null) {
  if (!text) {
    onEnd?.();
    return;
  }

  // If a specific target voice is requested for preview or playback, use browserSpeak directly
  if (targetVoiceURI && targetVoiceURI !== 'elevenlabs' && targetVoiceURI !== 'auto') {
    browserSpeak(text, onStart, onEnd, targetVoiceURI);
    return;
  }

  const settings = getVoiceSettings();

  // If user explicitly chose a browser voice, bypass ElevenLabs to use their chosen voice
  if (settings.selectedVoiceURI && settings.selectedVoiceURI !== 'elevenlabs' && settings.selectedVoiceURI !== 'auto') {
    browserSpeak(text, onStart, onEnd);
    return;
  }

  const audioBlob = await elevenLabsSpeak(text);

  if (audioBlob) {
    const audioUrl = URL.createObjectURL(audioBlob);
    const audio = new Audio(audioUrl);
    currentAudioElement = audio;

    audio.onplay = () => onStart?.();
    audio.onended = () => {
      URL.revokeObjectURL(audioUrl);
      currentAudioElement = null;
      onEnd?.();
    };
    audio.onerror = () => {
      URL.revokeObjectURL(audioUrl);
      currentAudioElement = null;
      browserSpeak(text, onStart, onEnd);
    };

    try {
      await audio.play();
    } catch (playErr) {
      URL.revokeObjectURL(audioUrl);
      currentAudioElement = null;
      browserSpeak(text, onStart, onEnd);
    }
  } else {
    browserSpeak(text, onStart, onEnd);
  }
}

export function cancelSpeech() {
  if (currentAudioElement) {
    currentAudioElement.pause();
    currentAudioElement.currentTime = 0;
    currentAudioElement = null;
  }
  if (currentUtterance) {
    currentUtterance = null;
  }
  if ('speechSynthesis' in window) {
    window.speechSynthesis.cancel();
  }
}

export function getVoiceProvider() {
  const settings = getVoiceSettings();
  const apiKey = getApiKey();
  const lang = settings.responseLanguage || 'en';

  if (settings.selectedVoiceURI === 'elevenlabs') {
    return 'ElevenLabs (Rachel)';
  }

  const voices = getAvailableVoices();
  const hindiVoice = findGoogleHindiVoice(voices);

  if (settings.selectedVoiceURI && settings.selectedVoiceURI !== 'auto') {
    if (hindiVoice && (settings.selectedVoiceURI === hindiVoice.voiceURI || settings.selectedVoiceURI === 'google-hindi')) {
      return lang === 'hi' ? 'Google Hindi (Hindi)' : 'FRIDAY Voice';
    }

    const match = voices.find(v => v.voiceURI === settings.selectedVoiceURI);
    if (match) {
      return `Browser: ${match.name.replace(/Microsoft |Google /g, '')}`;
    }
  }

  if (apiKey && !elevenLabsDisabled) {
    return 'ElevenLabs (Rachel)';
  }

  const voice = getBestFallbackVoice();
  if (voice && hindiVoice && voice.voiceURI === hindiVoice.voiceURI) {
    return lang === 'hi' ? 'Google Hindi (Hindi)' : 'FRIDAY Voice';
  }

  return voice ? `Browser: ${voice.name.replace(/Microsoft |Google /g, '')}` : 'Browser Voice';
}

export function isElevenLabsConfigured() {
  return !!getApiKey();
}

export function resetElevenLabs() {
  elevenLabsDisabled = false;
}

export const LEGACY_VOICE_FALLBACK_ACTIVE = true;

export function isLegacyFallbackAvailable() {
  return typeof window !== 'undefined' && ('speechSynthesis' in window || 'webkitSpeechRecognition' in window);
}
