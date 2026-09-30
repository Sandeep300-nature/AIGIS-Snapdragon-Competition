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

// ── Dedicated Speech Sanitization Layer ──────────────────────────────────────
export function sanitizeSpeechText(text) {
  if (!text) return '';
  let s = String(text);

  // 1. Remove decorative / status emojis
  s = s.replace(/[\u{1F300}-\u{1F9FF}\u{1FA00}-\u{1FAFF}\u{2600}-\u{26FF}\u{2700}-\u{27BF}\u{FE00}-\u{FE0F}\u{1F1E0}-\u{1F1FF}]/gu, ' ');

  // 2. Markdown Code Blocks: remove ```language / ``` markers, preserve code body
  s = s.replace(/```[a-zA-Z0-9_-]*\n?([\s\S]*?)```/g, '$1');

  // 3. Markdown Inline Code: `code` -> code (prevent saying "backtick")
  s = s.replace(/`([^`]+)`/g, '$1');

  // 4. Markdown Images & Links: [text](url) -> text (strip URL so TTS does not read http-colon-slash)
  s = s.replace(/!\[([^\]]*)\]\([^)]+\)/g, '$1');
  s = s.replace(/\[([^\]]+)\]\([^)]+\)/g, '$1');
  s = s.replace(/https?:\/\/\S+/g, 'web link');

  // 5. Markdown Headers: # Heading -> Heading (prevent saying "hashtag" or "hash")
  s = s.replace(/^#{1,6}\s+(.+)$/gm, '$1');

  // 6. Markdown Blockquotes: > quote -> quote
  s = s.replace(/^>\s*(.+)$/gm, '$1');

  // 7. Decorative divider lines (---, ***, ===, ___) -> remove cleanly so they do not produce stray commas
  s = s.replace(/^[\s\-_=*]{3,}$/gm, '');

  // 8. Markdown Bold / Italics / Strikethrough (prevent saying "asterisk", "star", "underscore")
  s = s.replace(/\*{3}([^*]+)\*{3}/g, '$1');
  s = s.replace(/_{3}([^_]+)_{3}/g, '$1');
  s = s.replace(/\*{2}([^*]+)\*{2}/g, '$1');
  s = s.replace(/_{2}([^_]+)_{2}/g, '$1');
  s = s.replace(/\*([^*]+)\*/g, '$1');
  s = s.replace(/(?<!\w)_([^_]+)_(?!\w)/g, '$1');
  s = s.replace(/~~([^~]+)~~/g, '$1');

  // 9. Table borders / cell separators (|) -> natural pause
  s = s.replace(/\|/g, ', ');

  // 10. Trademarks & Registered symbols: Intel(R) Core(TM) -> Intel Core
  s = s.replace(/\(\s*[rR]\s*\)/g, '');
  s = s.replace(/\(\s*[tT][mM]\s*\)/g, '');
  s = s.replace(/\(\s*[cC]\s*\)/g, '');
  s = s.replace(/[®™©]/g, '');

  // 11. Technical Terms & Architecture Identifiers (processed BEFORE general symbol normalization)
  // x86_64 / x86_32 -> x86-64 / x86-32
  s = s.replace(/\bx86_64\b/gi, 'x86-64');
  s = s.replace(/\bx86_32\b/gi, 'x86-32');

  // AIGIS / A-I-G-I-S / A I G I S / A.I.G.I.S. -> Aigis
  s = s.replace(/\bA\s*-\s*I\s*-\s*G\s*-\s*I\s*-\s*S\b/gi, 'Aigis');
  s = s.replace(/\bA\s+I\s+G\s+I\s+S\b/gi, 'Aigis');
  s = s.replace(/(?:\bA\.I\.G\.I\.S\.|\bA\.I\.G\.I\.S\b)/gi, 'Aigis');
  s = s.replace(/\bAIGIS\b/g, 'Aigis');

  // GenieX -> Genie X
  s = s.replace(/\bGenieX\b/g, 'Genie X');

  // Qwen3-4B -> Qwen 3 4B, Qwen3 -> Qwen 3
  s = s.replace(/\bQwen3-4B\b/gi, 'Qwen 3 4B');
  s = s.replace(/\bQwen3\b/gi, 'Qwen 3');

  // Technical word hyphens: on-device -> on device, real-time -> real time, built-in -> built in
  // (Matches alpha words only, preserving numeric technical identifiers like x86-64)
  s = s.replace(/\b([a-zA-Z]+)-([a-zA-Z]+)\b/g, '$1 $2');

  // 12. Em-dashes and En-dashes -> natural comma pause
  s = s.replace(/\s*[—–]\s*/g, ', ');

  // 13. Parentheses, Braces, and Brackets Handling:
  // Empty brackets/parentheses
  s = s.replace(/\(\s*\)/g, '');
  s = s.replace(/\[\s*\]/g, '');
  s = s.replace(/\{\s*\}/g, '');

  // Brackets and Braces: [local] -> local, {data} -> data
  s = s.replace(/\[([^\]]+)\]/g, ' $1 ');
  s = s.replace(/\{([^}]+)\}/g, ' $1 ');

  // Specific parenthetical clauses:
  // (running on x64 development machine) -> . The system is running on an x64 development machine
  s = s.replace(
    /\(\s*running on\s+(?:an?\s+)?x64\s+development\s+machine\s*\)/gi,
    '. The system is running on an x64 development machine'
  );
  s = s.replace(/\(\s*running on\s+([^)]+)\)/gi, ', running on $1');

  // General parentheses:
  // If preceded by a linking verb or preposition, omit leading comma: e.g. "settings are (private)" -> "settings are private"
  // Otherwise, convert opening parenthesis to a natural spoken pause: "(12 threads)" -> ", 12 threads"
  const linkingWords = new Set([
    'is', 'are', 'was', 'were', 'be', 'been', 'being',
    'to', 'from', 'in', 'of', 'for', 'with', 'as', 'and', 'or'
  ]);
  s = s.replace(/(\w+)\s*\(([^)]+)\)/g, (match, pre, inner) => {
    const trimmedInner = inner.trim();
    const words = pre.trim().split(/\s+/);
    const lastWord = words[words.length - 1].toLowerCase();
    const isClauseOrMeasurement = (trimmedInner.split(/\s+/).length > 1) || /^\d+/.test(trimmedInner);
    if (isClauseOrMeasurement && !linkingWords.has(lastWord)) {
      return `${pre}, ${trimmedInner}`;
    }
    return `${pre} ${trimmedInner}`;
  });
  s = s.replace(/\(([^)]+)\)/g, ' $1 ');
  // Strip any remaining stray brackets/braces/parentheses
  s = s.replace(/[{}\[\]()]/g, ' ');

  // 14. Structured Line-by-Line Formatting (Reports, Telemetry, Bullet Lists)
  const lines = s.split('\n');
  const processedLines = [];
  for (const line of lines) {
    let stripped = line.trim();
    if (!stripped) continue;

    // Detect and convert list bullets: '• item', '- item', '* item'
    const isBullet = /^[-*•›»]\s*/.test(stripped);
    stripped = stripped.replace(/^[-*•›»]\s*/, '').trim();

    // Detect and convert numbered lists: '1. item' -> '1, item'
    const isNumbered = /^\d+\.\s*/.test(stripped);
    stripped = stripped.replace(/^(\d+)\.\s*/, '$1, ').trim();

    // If intro / heading line ends with a colon (e.g. 'Workstation Hardware Telemetry, sir:'),
    // convert colon to period for natural pause
    if (stripped.endsWith(':')) {
      stripped = stripped.slice(0, -1).trimEnd() + '.';
    }

    // Ensure bullet and numbered list items end with terminal sentence punctuation
    // to prevent TTS engines from flattening reports into one continuous run-on sentence
    if ((isBullet || isNumbered) && !/[.!?]$/.test(stripped)) {
      stripped += '.';
    }

    processedLines.append ? processedLines.append(stripped) : processedLines.push(stripped);
  }

  s = processedLines.join('\n');

  // 15. Remaining awkward notation / punctuation symbols
  s = s.replace(/[~^\\<>]/g, ' ');
  s = s.replace(/[*#_]/g, ' ');

  // Normalize repeated punctuation: "!!!" -> "!", "???" -> "?", "...." -> "..."
  s = s.replace(/!{2,}/g, '!');
  s = s.replace(/\?{2,}/g, '?');
  s = s.replace(/\.{4,}/g, '...');

  // 16. Whitespace and comma/punctuation cleanup
  // Snap punctuation back if there is space before it (e.g. "task ." -> "task.")
  s = s.replace(/\s+([.,!?;:])/g, '$1');
  s = s.replace(/,\s*,+/g, ', ');
  s = s.replace(/\s*,\s*\./g, '.');
  s = s.replace(/\s*\.\s*\./g, '.');
  s = s.replace(/\s*,\s*!/g, '!');
  s = s.replace(/\s*,\s*\?/g, '?');
  s = s.replace(/^[\s,]+/gm, '');
  s = s.replace(/[ \t]+/g, ' ');
  s = s.replace(/\n\s*\n+/g, '\n');

  return s.trim();
}

export function normalizeSTTTranscript(text) {
  if (!text) return '';
  let s = String(text);

  // 1. Conservative AIGIS recognition:
  // "A I G I S", "A-I-G-I-S", "A - I - G - I - S", "A.I.G.I.S." -> "AIGIS"
  s = s.replace(/\bA\s*-\s*I\s*-\s*G\s*-\s*I\s*-\s*S\b/gi, 'AIGIS');
  s = s.replace(/\bA\s+I\s+G\s+I\s+S\b/gi, 'AIGIS');
  s = s.replace(/(?:\bA\.I\.G\.I\.S\.|\bA\.I\.G\.I\.S\b)/gi, 'AIGIS');

  // Common phonetic mishearings for AIGIS brand recognition
  s = s.replace(/\b(i\s*guess|eye\s*guess|aegis|ai\s*gis|eyegis|aygis|igh\s*guess|i\s*ges|aiges)\b/gi, 'AIGIS');
  s = s.replace(/\b(aigis)\b/gi, 'AIGIS');

  // 2. Accidental repeated whitespace cleanup
  s = s.replace(/[ \t]+/g, ' ');
  s = s.replace(/\s*\n\s*/g, '\n');

  return s.trim();
}

function normalizeEnglishTTSText(text) {
  if (!text) return '';
  let str = text;

  // 0. Protection for specific terms & symbols (MUST run first)
  str = str.replace(/\bC\+\+(?!\w)/g, 'C plus plus');
  str = str.replace(/π/g, 'pi');
  str = str.replace(/∞/g, 'infinity');
  const hasX86 = /x86[-_]64/i.test(str);
  if (hasX86) {
    str = str.replace(/\bx86[-_]64\b/gi, '___X86_64___');
  }

  // 0. Comma-separated Large Numbers with optional Decimals
  str = str.replace(/\b\d{1,3}(?:,\d{3})+(?:\.\d+)?\b/g, (match) => {
    if (match.includes('.')) {
      const [intPart, fracPart] = match.split('.');
      const intWords = numberToWords(intPart);
      const fracWords = fracPart.split('').map(d => (d === '0' ? 'zero' : ONES[parseInt(d, 10)] || d)).join(' ');
      return `${intWords} point ${fracWords}`;
    }
    return numberToWords(match);
  });

  // 1. Scientific Notation
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

  // 2. Units of Measurement
  str = str.replace(/\b(\d+(?:\.\d+)?)\s*km\/h\b/gi, (m, n) => `${n} kilometers per hour`);
  str = str.replace(/\b(\d+(?:\.\d+)?)\s*m\/s\b/gi, (m, n) => `${n} meters per second`);
  str = str.replace(/\b(\d+(?:\.\d+)?)\s*kg\b/gi, (m, n) => `${n} kilograms`);
  str = str.replace(/\b(\d+(?:\.\d+)?)\s*(°C|degrees?\s*C|degrees?\s*Celsius)\b/gi, (m, n) => `${n} degrees Celsius`);
  str = str.replace(/\b(\d+(?:\.\d+)?)\s*(°F|degrees?\s*F|degrees?\s*Fahrenheit)\b/gi, (m, n) => `${n} degrees Fahrenheit`);
  str = str.replace(/\b(\d+(?:\.\d+)?)\s*V\b/g, (m, n) => `${n} volts`);

  // 3. Common Natural Fractions
  str = str.replace(/\b1\/2\b/g, 'one half');
  str = str.replace(/\b1\/3\b/g, 'one third');
  str = str.replace(/\b2\/3\b/g, 'two thirds');
  str = str.replace(/\b1\/4\b/g, 'one quarter');
  str = str.replace(/\b3\/4\b/g, 'three quarters');

  // 4. Decimals
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

  // 7. Math Operators: between numbers only
  str = str.replace(/(\b\d+)\s*%/g, (m, a) => `${a} percent`);
  str = str.replace(/(\b\d+)\s*[*×]\s*(\b\d+)/g, (m, a, b) => `${a} times ${b}`);
  str = str.replace(/(\b\d+)\s*[÷\/]\s*(\b\d+)/g, (m, a, b) => `${a} divided by ${b}`);
  str = str.replace(/(\b\d+)\s*\+\s*(\b\d+)/g, (m, a, b) => `${a} plus ${b}`);
  str = str.replace(/(\b\d+)\s*-\s*(\b\d+)/g, (m, a, b) => `${a} minus ${b}`);
  str = str.replace(/(\b\d+)\s*=\s*(\b\d+)/g, (m, a, b) => `${a} equals ${b}`);

  // 8. Exponents / Power (^, **) between digits
  str = str.replace(/(\b\d+)\s*(\^|\*\*)\s*(\b\d+)/g, (m, a, op, b) => `${a} to the power of ${b}`);

  // 9. Comparisons between digits
  str = str.replace(/(\b\d+)\s*>=\s*(\b\d+)/g, (m, a, b) => `${a} is greater than or equal to ${b}`);
  str = str.replace(/(\b\d+)\s*<=\s*(\b\d+)/g, (m, a, b) => `${a} is less than or equal to ${b}`);
  str = str.replace(/(\b\d+)\s*>\s*(\b\d+)/g, (m, a, b) => `${a} is greater than ${b}`);
  str = str.replace(/(\b\d+)\s*<\s*(\b\d+)/g, (m, a, b) => `${a} is less than ${b}`);

  // 10. Not equals (!=, ≠) between digits
  str = str.replace(/(\b\d+)\s*(!=|≠)\s*(\b\d+)/g, (m, a, op, b) => `${a} is not equal to ${b}`);

  // 11. Square Root (√)
  str = str.replace(/√(\b\d+)/g, (m, a) => `square root of ${a}`);

  // 12. Times: e.g. "2:05 PM", "12:30 AM", "8:15"
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

  // 13. Dates: e.g. "July 28, 2026", "28th July", "July 28"
  str = str.replace(/\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|January|February|March|April|June|July|August|September|October|November|December)\s+(\d{1,2})(?:st|nd|rd|th)?,?\s*(\d{4})?\b/gi, (match, month, day, year) => {
    const dayNum = parseInt(day, 10);
    const dayStr = ORDINALS[dayNum] || numberToWords(dayNum);
    const yearStr = year ? ' ' + numberToWords(parseInt(year, 10)) : '';
    return `${month} ${dayStr}${yearStr}`;
  });

  // 14. Percentages: e.g. "90%", "25%"
  str = str.replace(/\b(\d+)%\b/g, (match, num) => {
    return `${numberToWords(num)} percent`;
  });

  // 15. Currencies: e.g. "$50", "₹500"
  str = str.replace(/\$(\d+)\b/g, (match, num) => {
    return `${numberToWords(num)} dollars`;
  });
  str = str.replace(/₹(\d+)\b/g, (match, num) => {
    return `${numberToWords(num)} rupees`;
  });

  // 16. Standalone digits: e.g. "8 hours", "90"
  str = str.replace(/\b(\d{1,3})\b/g, (match, num) => {
    return numberToWords(num);
  });

  if (hasX86) {
    str = str.replace(/___X86_64___/g, 'x86-64');
  }

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
  const sanitizedText = sanitizeSpeechText(text);
  const processedText = (respLang !== 'hi') ? normalizeEnglishTTSText(sanitizedText) : sanitizedText;

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

  // Create dedicated speech-only representation without mutating original response
  const speechText = sanitizeSpeechText(text);

  // If a specific target voice is requested for preview or playback, use browserSpeak directly
  if (targetVoiceURI && targetVoiceURI !== 'elevenlabs' && targetVoiceURI !== 'auto') {
    browserSpeak(speechText, onStart, onEnd, targetVoiceURI);
    return;
  }

  const settings = getVoiceSettings();

  // If user explicitly chose a browser voice, bypass ElevenLabs to use their chosen voice
  if (settings.selectedVoiceURI && settings.selectedVoiceURI !== 'elevenlabs' && settings.selectedVoiceURI !== 'auto') {
    browserSpeak(speechText, onStart, onEnd);
    return;
  }

  const audioBlob = await elevenLabsSpeak(speechText);

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
      browserSpeak(speechText, onStart, onEnd);
    };

    try {
      await audio.play();
    } catch (playErr) {
      URL.revokeObjectURL(audioUrl);
      currentAudioElement = null;
      browserSpeak(speechText, onStart, onEnd);
    }
  } else {
    browserSpeak(speechText, onStart, onEnd);
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
