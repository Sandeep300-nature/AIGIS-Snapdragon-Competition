import os
import io
import time
import tempfile
import psutil
from typing import Optional, Dict, Any, Union, BinaryIO

try:
    from faster_whisper import WhisperModel
    FASTER_WHISPER_AVAILABLE = True
except ImportError:
    FASTER_WHISPER_AVAILABLE = False


class LocalSTTService:
    """
    On-Device Speech-to-Text (STT) Service powered by faster-whisper.
    Executes speech transcription strictly on-device using CTranslate2 CPU execution.
    Zero cloud network calls (networkUsed=False).
    """

    DEFAULT_MODEL_DIR = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "models",
        "faster-whisper-tiny.en"
    )

    def __init__(
        self,
        model_dir: Optional[str] = None,
        device: str = "cpu",
        compute_type: str = "int8",
        auto_load: bool = True
    ):
        self.model_dir = model_dir or os.getenv("AIGIS_LOCAL_STT_PATH", self.DEFAULT_MODEL_DIR)
        self.device = device
        self.compute_type = compute_type
        self.model = None
        self.is_loaded = False
        self.load_error = None
        self.load_time_sec = 0.0
        self.memory_delta_mb = 0.0

        if auto_load:
            self.load_model()

    def load_model(self) -> bool:
        """Loads faster-whisper tiny.en weights strictly from local disk."""
        if self.is_loaded and self.model is not None:
            return True

        if not FASTER_WHISPER_AVAILABLE:
            self.load_error = "faster-whisper library is not installed in Python environment"
            return False

        if not os.path.exists(self.model_dir):
            self.load_error = f"Model directory not found at: {self.model_dir}"
            return False

        try:
            proc = psutil.Process()
            m0 = proc.memory_info().rss
            t0 = time.perf_counter()

            # Attempt loading with requested compute_type; fall back to float32 if int8 is not supported
            try:
                self.model = WhisperModel(
                    self.model_dir,
                    device=self.device,
                    compute_type=self.compute_type,
                    local_files_only=True
                )
            except Exception as ce:
                # Fallback to float32 if int8 is unsupported
                self.compute_type = "float32"
                self.model = WhisperModel(
                    self.model_dir,
                    device=self.device,
                    compute_type="float32",
                    local_files_only=True
                )

            t1 = time.perf_counter()
            m1 = proc.memory_info().rss

            self.load_time_sec = round(t1 - t0, 4)
            self.memory_delta_mb = round((m1 - m0) / (1024 * 1024), 2)
            self.is_loaded = True
            self.load_error = None
            return True
        except Exception as e:
            self.is_loaded = False
            self.model = None
            self.load_error = str(e)
            return False

    def is_available(self) -> bool:
        """Returns True only if the local faster-whisper model is actively loaded and ready."""
        return self.is_loaded and self.model is not None

    def get_service_info(self) -> Dict[str, Any]:
        """Returns truthful runtime metadata for the local STT service."""
        return {
            "available": self.is_available(),
            "provider": "faster-whisper",
            "model": "tiny.en",
            "runtime": "CTranslate2",
            "device": self.device,
            "computeType": self.compute_type,
            "modelDir": self.model_dir,
            "loadTimeSec": self.load_time_sec,
            "memoryDeltaMb": self.memory_delta_mb,
            "localInference": True,
            "networkUsed": False,
            "error": self.load_error
        }

    def transcribe(
        self,
        audio_input: Union[str, bytes, BinaryIO],
        beam_size: int = 1
    ) -> Dict[str, Any]:
        """
        Transcribes audio locally using faster-whisper.
        Accepts:
          - File path (str)
          - Audio bytes (bytes)
          - File-like binary stream (BinaryIO)
        Returns:
          Dict containing transcript, latency, language, and truthful provenance metadata.
        """
        if not self.is_available():
            loaded = self.load_model()
            if not loaded:
                return {
                    "transcript": "",
                    "success": False,
                    "provider": "faster-whisper",
                    "model": "tiny.en",
                    "runtime": "CTranslate2",
                    "device": self.device,
                    "computeType": self.compute_type,
                    "latencyMs": 0,
                    "audioDurationSec": 0.0,
                    "realtimeFactor": 0.0,
                    "networkUsed": False,
                    "localInference": True,
                    "isFallback": True,
                    "fallbackReason": self.load_error or "Local STT model not loaded"
                }

        temp_audio_file = None
        try:
            # Handle in-memory bytes or stream by saving to a temporary file
            if isinstance(audio_input, bytes):
                tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
                tmp.write(audio_input)
                tmp.flush()
                tmp.close()
                audio_path = tmp.name
                temp_audio_file = audio_path
            elif hasattr(audio_input, "read"):
                tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
                tmp.write(audio_input.read())
                tmp.flush()
                tmp.close()
                audio_path = tmp.name
                temp_audio_file = audio_path
            elif isinstance(audio_input, str):
                audio_path = audio_input
            else:
                raise ValueError("Unsupported audio_input type. Must be file path, bytes, or binary stream.")

            t0 = time.perf_counter()
            segments, info = self.model.transcribe(audio_path, beam_size=beam_size)
            seg_list = list(segments)
            t1 = time.perf_counter()

            transcription_sec = t1 - t0
            latency_ms = int(transcription_sec * 1000)
            audio_duration = round(getattr(info, "duration", 0.0) or 0.0, 3)
            rtf = round(transcription_sec / audio_duration, 3) if audio_duration > 0 else 0.0

            transcript = " ".join(s.text for s in seg_list).strip()

            return {
                "transcript": transcript,
                "success": True,
                "language": getattr(info, "language", "en"),
                "languageProbability": round(getattr(info, "language_probability", 1.0) or 1.0, 3),
                "latencyMs": latency_ms,
                "audioDurationSec": audio_duration,
                "realtimeFactor": rtf,
                "provider": "faster-whisper",
                "model": "tiny.en",
                "runtime": "CTranslate2",
                "device": self.device,
                "computeType": self.compute_type,
                "networkUsed": False,
                "localInference": True,
                "isFallback": False
            }

        except Exception as e:
            return {
                "transcript": "",
                "success": False,
                "provider": "faster-whisper",
                "model": "tiny.en",
                "runtime": "CTranslate2",
                "device": self.device,
                "computeType": self.compute_type,
                "latencyMs": 0,
                "audioDurationSec": 0.0,
                "realtimeFactor": 0.0,
                "networkUsed": False,
                "localInference": True,
                "isFallback": True,
                "fallbackReason": str(e)
            }
        finally:
            if temp_audio_file and os.path.exists(temp_audio_file):
                try:
                    os.remove(temp_audio_file)
                except Exception:
                    pass
