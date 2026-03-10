"""
Voice conversation config: STT, LLM, TTS provider selection via environment.
No hardcoded secrets. See docs/VOICE_SETUP.md for setup.
"""

import os
from pathlib import Path

_ARXIVCAST_ROOT = Path(__file__).resolve().parent

# STT: faster-whisper model (e.g. small.en, base.en, tiny.en)
VOICE_STT_PROVIDER = os.environ.get("VOICE_STT_PROVIDER", "faster_whisper").strip().lower()
VOICE_STT_MODEL = os.environ.get("VOICE_STT_MODEL", "small.en").strip()
VOICE_STT_DEVICE = os.environ.get("VOICE_STT_DEVICE", "cpu").strip().lower()  # cpu or cuda
VOICE_STT_COMPUTE_TYPE = os.environ.get("VOICE_STT_COMPUTE_TYPE", "int8").strip()  # int8, float16, etc.

# LLM: ollama (default), openrouter, nvidia_nim
VOICE_LLM_PROVIDER = os.environ.get("VOICE_LLM_PROVIDER", "ollama").strip().lower()
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").strip().rstrip("/")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b").strip()
OPENROUTER_KEY = os.environ.get("OPENROUTER_KEY", "").strip()
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "openai/gpt-3.5-turbo").strip()
NIM_CHAT_URL = os.environ.get("NIM_CHAT_URL", "").strip()  # e.g. https://.../v1/chat/completions
NIM_API_KEY = os.environ.get("NIM_API_KEY", "").strip()

# TTS: piper (default)
VOICE_TTS_PROVIDER = os.environ.get("VOICE_TTS_PROVIDER", "piper").strip().lower()
PIPER_VOICE_PATH = os.environ.get("PIPER_VOICE_PATH", "").strip()  # path to .onnx voice file
# Default voice: use bundled or system path; if empty, pipeline will try arxvicast/voices/ or disable TTS
PIPER_VOICE_DIR = _ARXIVCAST_ROOT / "voices"

# Timeouts (seconds)
VOICE_STT_TIMEOUT = float(os.environ.get("VOICE_STT_TIMEOUT", "10"))
VOICE_LLM_TIMEOUT = float(os.environ.get("VOICE_LLM_TIMEOUT", "30"))
VOICE_TTS_TIMEOUT = float(os.environ.get("VOICE_TTS_TIMEOUT", "15"))

# Retry
VOICE_RETRY_MAX = int(os.environ.get("VOICE_RETRY_MAX", "2"))
VOICE_RETRY_BASE_DELAY = float(os.environ.get("VOICE_RETRY_BASE_DELAY", "0.5"))


def get_piper_voice_path():
    """Resolve Piper voice .onnx path from env or default dir."""
    if PIPER_VOICE_PATH and Path(PIPER_VOICE_PATH).is_file():
        return str(Path(PIPER_VOICE_PATH).resolve())
    # Try voices/ in arxvicast
    if PIPER_VOICE_DIR.is_dir():
        for f in PIPER_VOICE_DIR.iterdir():
            if f.suffix == ".onnx":
                return str(f.resolve())
    return None
