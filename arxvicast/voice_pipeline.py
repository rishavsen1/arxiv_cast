"""
Voice pipeline: STT (faster-whisper) -> LLM (Ollama/OpenRouter/NIM) -> TTS (Piper).
Streaming with timeouts, retries, and latency instrumentation.
"""

import io
import json
import logging
import time
from typing import Any, Generator, List, Optional, Tuple

from . import voice_config as config

logger = logging.getLogger(__name__)

# Optional imports (lazy so app runs without voice deps)
_whisper_model = None
_piper_voice = None


def _log_timing(stage: str, ms: float, extra: Optional[str] = None):
    msg = f"voice_{stage}={ms:.0f}ms"
    if extra:
        msg += f" ({extra})"
    logger.info(msg)


def _load_whisper():
    global _whisper_model
    if _whisper_model is not None:
        return _whisper_model
    try:
        from faster_whisper import WhisperModel
        _whisper_model = WhisperModel(
            config.VOICE_STT_MODEL,
            device=config.VOICE_STT_DEVICE,
            compute_type=config.VOICE_STT_COMPUTE_TYPE,
        )
        return _whisper_model
    except Exception as e:
        logger.warning("faster_whisper not available: %s", e)
        return None


def transcribe(audio_bytes: bytes, timeout: float = None) -> Tuple[Optional[str], float]:
    """STT: audio bytes (16kHz mono 16-bit PCM or WAV) -> text. Returns (text, ms)."""
    timeout = timeout or config.VOICE_STT_TIMEOUT
    model = _load_whisper()
    if model is None:
        return None, 0.0
    t0 = time.perf_counter()
    try:
        import numpy as np
        import wave
        buf = io.BytesIO(audio_bytes)
        try:
            with wave.open(buf, "rb") as wav:
                framerate = wav.getframerate()
                frames = wav.readframes(wav.getnframes())
        except Exception:
            framerate = 16000
            frames = audio_bytes
        if not frames:
            return "", (time.perf_counter() - t0) * 1000
        audio_np = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
        if framerate != 16000 and len(audio_np) > 0:
            try:
                from scipy import signal
                num_samples = int(len(audio_np) * 16000 / framerate)
                audio_np = signal.resample(audio_np, num_samples).astype(np.float32)
            except ImportError:
                pass  # assume client sent 16kHz or accept potential quality loss
        if audio_np.size == 0:
            return "", (time.perf_counter() - t0) * 1000
        segments, _ = model.transcribe(audio_np, language="en", vad_filter=True)
        text = " ".join(s.text for s in segments if s.text).strip()
        ms = (time.perf_counter() - t0) * 1000
        _log_timing("stt", ms)
        return text or "", ms
    except Exception as e:
        logger.exception("STT failed: %s", e)
        return None, (time.perf_counter() - t0) * 1000


def _llm_stream_ollama(messages: List[dict], system: str, timeout: float) -> Generator[str, None, None]:
    try:
        import requests
        url = f"{config.OLLAMA_BASE_URL}/api/chat"
        body = {
            "model": config.OLLAMA_MODEL,
            "messages": [{"role": "system", "content": system}] + messages,
            "stream": True,
        }
        r = requests.post(url, json=body, stream=True, timeout=timeout)
        r.raise_for_status()
        for line in r.iter_lines():
            if not line:
                continue
            try:
                data = json.loads(line)
                content = (data.get("message") or {}).get("content")
                if content:
                    yield content
                if data.get("done"):
                    break
            except json.JSONDecodeError:
                continue
    except Exception as e:
        logger.exception("Ollama stream failed: %s", e)
        raise


def _llm_stream_openrouter(messages: List[dict], system: str, timeout: float) -> Generator[str, None, None]:
    if not config.OPENROUTER_KEY:
        raise RuntimeError("OPENROUTER_KEY not set for voice LLM")
    try:
        import requests
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {"Authorization": f"Bearer {config.OPENROUTER_KEY}"}
        body = {
            "model": config.OPENROUTER_MODEL,
            "messages": [{"role": "system", "content": system}] + messages,
            "stream": True,
        }
        r = requests.post(url, json=body, headers=headers, stream=True, timeout=timeout)
        r.raise_for_status()
        for line in r.iter_lines():
            if not line or not line.strip().startswith(b"data:"):
                continue
            line = line.decode("utf-8").strip()
            if line == "data: [DONE]":
                break
            try:
                data = json.loads(line[5:])
                delta = (data.get("choices") or [{}])[0].get("delta", {}).get("content")
                if delta:
                    yield delta
            except (json.JSONDecodeError, IndexError, KeyError):
                continue
    except Exception as e:
        logger.exception("OpenRouter stream failed: %s", e)
        raise


def _llm_stream_nim(messages: List[dict], system: str, timeout: float) -> Generator[str, None, None]:
    if not config.NIM_CHAT_URL:
        raise RuntimeError("NIM_CHAT_URL not set for voice LLM")
    try:
        import requests
        headers = {}
        if config.NIM_API_KEY:
            headers["Authorization"] = f"Bearer {config.NIM_API_KEY}"
        body = {
            "model": "default",
            "messages": [{"role": "system", "content": system}] + messages,
            "stream": True,
        }
        r = requests.post(config.NIM_CHAT_URL, json=body, headers=headers or None, stream=True, timeout=timeout)
        r.raise_for_status()
        for line in r.iter_lines():
            if not line or not line.strip().startswith(b"data:"):
                continue
            line = line.decode("utf-8").strip()
            if line == "data: [DONE]":
                break
            try:
                data = json.loads(line[5:])
                delta = (data.get("choices") or [{}])[0].get("delta", {}).get("content")
                if delta:
                    yield delta
            except (json.JSONDecodeError, IndexError, KeyError):
                continue
    except Exception as e:
        logger.exception("NIM stream failed: %s", e)
        raise


def llm_stream(messages: List[dict], system_prompt: str, timeout: float = None) -> Generator[str, None, None]:
    """Stream LLM response tokens. system_prompt should include paper context if any."""
    timeout = timeout or config.VOICE_LLM_TIMEOUT
    prov = config.VOICE_LLM_PROVIDER
    if prov == "ollama":
        return _llm_stream_ollama(messages, system_prompt, timeout)
    if prov == "openrouter":
        return _llm_stream_openrouter(messages, system_prompt, timeout)
    if prov == "nvidia_nim" or prov == "nvidia-nim":
        return _llm_stream_nim(messages, system_prompt, timeout)
    raise ValueError(f"Unknown VOICE_LLM_PROVIDER: {prov}")


def _load_piper():
    global _piper_voice
    if _piper_voice is not None:
        return _piper_voice
    try:
        import os
        from pathlib import Path
        import requests
        from piper import PiperVoice

        path = config.get_piper_voice_path()
        if not path:
            # Auto-download a default English voice into arxvicast/voices
            default_name = "en_US-lessac-medium.onnx"
            voices_dir = config.PIPER_VOICE_DIR
            voices_dir.mkdir(parents=True, exist_ok=True)
            dest = voices_dir / default_name
            if not dest.is_file():
                url = (
                    "https://huggingface.co/rhasspy/piper-voices/resolve/"
                    "v1.0.0/en/en_US/lessac/medium/en_US-lessac-medium.onnx?download=true"
                )
                logger.info("Downloading default Piper voice to %s", dest)
                try:
                    with requests.get(url, stream=True, timeout=120) as r:
                        r.raise_for_status()
                        with open(dest, "wb") as f:
                            for chunk in r.iter_content(chunk_size=8192):
                                if chunk:
                                    f.write(chunk)
                except Exception as e:
                    logger.warning("Could not download Piper voice: %s", e)
            if dest.is_file():
                path = str(dest.resolve())
            else:
                path = None

        if not path:
            return None

        _piper_voice = PiperVoice.load(path)
        return _piper_voice
    except Exception as e:
        logger.warning("Piper not available: %s", e)
        return None


def tts_stream(text: str, timeout: float = None) -> Generator[bytes, None, None]:
    """TTS: stream raw audio chunks (16-bit PCM). Piper yields chunks with audio_int16_bytes."""
    timeout = timeout or config.VOICE_TTS_TIMEOUT
    voice = _load_piper()
    if not voice or not text.strip():
        return
    t0 = time.perf_counter()
    try:
        for chunk in voice.synthesize(text.strip()):
            raw = getattr(chunk, "audio_int16_bytes", None) or (
                chunk if isinstance(chunk, bytes) else None
            )
            if raw:
                yield raw
        ms = (time.perf_counter() - t0) * 1000
        _log_timing("tts", ms, f"{len(text)} chars")
    except Exception as e:
        logger.exception("TTS failed: %s", e)
        raise


def build_system_prompt(paper_context: Optional[str] = None) -> str:
    base = (
        "You are a helpful research assistant in a voice conversation. "
        "Answer concisely in 1-3 sentences when possible. Be natural and conversational."
    )
    if paper_context and paper_context.strip():
        return base + "\n\nRelevant papers (use as context for answers):\n" + paper_context.strip()
    return base


def run_voice_turn(
    audio_b64: str,
    paper_ids: Optional[List[str]] = None,
    conversation_history: Optional[List[dict]] = None,
) -> Generator[dict, None, None]:
    """
    Run one voice turn: decode audio -> STT -> LLM stream -> TTS stream.
    Yields event dicts: {event, ...} for status, user_transcript, timing, assistant_text, audio, done, error.
    """
    import base64 as b64
    t0_total = time.perf_counter()
    conversation_history = conversation_history or []

    try:
        audio_bytes = b64.b64decode(audio_b64)
    except Exception as e:
        yield {"event": "error", "message": f"Invalid audio: {e}"}
        return

    from . import core
    paper_context = core.get_papers_context(paper_ids or [])

    system_prompt = build_system_prompt(paper_context or None)

    yield {"event": "status", "message": "Transcribing..."}
    user_text, stt_ms = transcribe(audio_bytes)
    if user_text is None:
        yield {"event": "error", "message": "Speech recognition unavailable. Check VOICE_STT_* and faster-whisper."}
        return
    yield {"event": "timing", "stage": "stt", "ms": round(stt_ms)}
    yield {"event": "user_transcript", "text": user_text}
    if not user_text.strip():
        yield {"event": "status", "message": "No speech detected."}
        yield {"event": "done"}
        return

    messages = conversation_history + [{"role": "user", "content": user_text}]
    yield {"event": "status", "message": "Thinking..."}
    t_llm0 = time.perf_counter()
    full_reply = []
    try:
        for delta in llm_stream(messages, system_prompt):
            full_reply.append(delta)
            yield {"event": "assistant_text", "delta": delta}
        llm_ms = (time.perf_counter() - t_llm0) * 1000
        yield {"event": "timing", "stage": "llm", "ms": round(llm_ms)}
    except Exception as e:
        yield {"event": "error", "message": f"LLM error: {e}"}
        return

    reply_text = "".join(full_reply).strip()
    if not reply_text:
        yield {"event": "done"}
        return

    yield {"event": "status", "message": "Speaking..."}
    t_tts0 = time.perf_counter()
    first_chunk = True
    try:
        for chunk in tts_stream(reply_text):
            if chunk:
                yield {"event": "audio", "format": "pcm", "base64": b64.b64encode(chunk).decode("ascii"), "sample_rate": 22050}
                if first_chunk:
                    yield {"event": "timing", "stage": "tts_first", "ms": round((time.perf_counter() - t_tts0) * 1000)}
                    first_chunk = False
        tts_ms = (time.perf_counter() - t_tts0) * 1000
        yield {"event": "timing", "stage": "tts", "ms": round(tts_ms)}
    except Exception as e:
        yield {"event": "error", "message": f"TTS error: {e}"}
        return

    total_ms = (time.perf_counter() - t0_total) * 1000
    yield {"event": "timing", "stage": "total", "ms": round(total_ms)}
    yield {"event": "done"}
