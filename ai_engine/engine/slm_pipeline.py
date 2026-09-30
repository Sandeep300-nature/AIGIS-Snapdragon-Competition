import os
import time
from typing import Optional, Dict, Any, Tuple

try:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    TRANSFORMERS_AVAILABLE = True
except ImportError:
    TRANSFORMERS_AVAILABLE = False

try:
    from .prompts import get_competition_system_prompt
except ImportError:
    from ai_engine.engine.prompts import get_competition_system_prompt


class LocalSLMPipeline:
    """
    On-device Small Language Model (SLM) pipeline.
    Executes genuine neural network token generation locally on the host CPU.
    Strictly isolated: local_files_only=True guarantees zero network requests during inference.
    Designed so the execution backend can later be substituted/augmented with an ONNX/QNN runtime.
    """

    DEFAULT_MODEL_DIR = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "models",
        "SmolLM2-135M-Instruct"
    )

    def __init__(self, model_dir: Optional[str] = None, auto_load: bool = True):
        self.model_dir = model_dir or os.getenv("AIGIS_LOCAL_SLM_PATH", self.DEFAULT_MODEL_DIR)
        self.model = None
        self.tokenizer = None
        self.is_loaded = False
        self.load_error = None
        self.model_name = "SmolLM2-135M-Instruct"
        self.runtime_name = "PyTorch (transformers)"
        self.device = "cpu"
        self.load_time_sec = 0.0

        if auto_load:
            self.load_model()

    def load_model(self) -> bool:
        """Loads the tokenizer and model weights strictly from local disk."""
        if self.is_loaded:
            return True

        if not TRANSFORMERS_AVAILABLE:
            self.load_error = "transformers or torch library not installed in Python environment"
            return False

        if not os.path.exists(self.model_dir):
            self.load_error = f"Model directory not found at: {self.model_dir}"
            return False

        try:
            t0 = time.perf_counter()
            self.tokenizer = AutoTokenizer.from_pretrained(
                self.model_dir,
                local_files_only=True
            )
            self.model = AutoModelForCausalLM.from_pretrained(
                self.model_dir,
                local_files_only=True
            )
            self.model.eval()
            self.is_loaded = True
            self.load_error = None
            self.load_time_sec = round(time.perf_counter() - t0, 3)
            return True
        except Exception as e:
            self.is_loaded = False
            self.load_error = str(e)
            return False

    def is_available(self) -> bool:
        return self.is_loaded and self.model is not None and self.tokenizer is not None

    def generate(
        self,
        prompt: str,
        max_new_tokens: int = 96,
        system_prompt: Optional[str] = None
    ) -> Tuple[str, int, int, float, Dict[str, Any]]:
        """
        Generates genuine tokens using the local model.
        Returns: (reply_text, tokens_generated, latency_ms, tokens_per_sec, metadata)
        """
        if not self.is_available():
            err = self.load_error or "Model weights not loaded"
            return (
                f"Local SLM is unavailable ({err}); no local model inference was performed.",
                0,
                0,
                0.0,
                {"error": err, "available": False, "networkUsed": False}
            )

        sys_msg = system_prompt or get_competition_system_prompt()

        messages = [
            {"role": "system", "content": sys_msg},
            {"role": "user", "content": prompt}
        ]

        t0 = time.perf_counter()

        try:
            input_text = self.tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True
            )
            inputs = self.tokenizer(input_text, return_tensors="pt")
            input_len = inputs["input_ids"].shape[1]

            with torch.no_grad():
                outputs = self.model.generate(
                    **inputs,
                    max_new_tokens=max_new_tokens,
                    do_sample=False,
                    pad_token_id=self.tokenizer.eos_token_id
                )

            gen_time = time.perf_counter() - t0
            latency_ms = max(1, int(gen_time * 1000))

            new_tokens = outputs[0][input_len:]
            token_count = int(len(new_tokens))
            tokens_per_sec = round(token_count / gen_time, 1) if gen_time > 0 else 0.0

            reply = self.tokenizer.decode(new_tokens, skip_special_tokens=True).strip()

            metadata = {
                "model": self.model_name,
                "runtime": self.runtime_name,
                "device": self.device,
                "tokensGenerated": token_count,
                "generationTimeSec": round(gen_time, 3),
                "tokensPerSec": tokens_per_sec,
                "networkUsed": False,
                "localInference": True
            }

            return reply, token_count, latency_ms, tokens_per_sec, metadata

        except Exception as e:
            elapsed_ms = max(1, int((time.perf_counter() - t0) * 1000))
            return (
                f"Local SLM inference error: {str(e)}",
                0,
                elapsed_ms,
                0.0,
                {"error": str(e), "available": False, "networkUsed": False}
            )

    def get_pipeline_info(self) -> Dict[str, Any]:
        return {
            "modelName": self.model_name,
            "runtime": self.runtime_name,
            "device": self.device,
            "loaded": self.is_loaded,
            "modelDir": self.model_dir,
            "parameters": "135M",
            "architecture": "LlamaForCausalLM",
            "loadError": self.load_error
        }
