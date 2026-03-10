# Voice Chat Setup (ArxivCast)

Voice chat uses **free, local (or optional cloud) models** for speech-to-text, LLM, and text-to-speech. No Gemini or paid API keys required by default.

## Quick start

1. **Ollama** (LLM, default)
   ```bash
   curl -fsSL https://ollama.com/install.sh | sh
   ollama pull qwen2.5:7b
   ```
2. **Piper voice** (TTS)
   - Download a voice (e.g. [en_US-lessac-medium](https://huggingface.co/rhasspy/piper-voices/tree/main)) and place the `.onnx` file in `arxvicast/voices/`, or set `PIPER_VOICE_PATH` in `.env`.
3. **faster-whisper** (STT) – installed via `pip install -r requirements.txt`; first run will download the model (e.g. `small.en`).
4. Copy `arxvicast/.env.example` to `arxvicast/.env` and adjust only if you use OpenRouter or NIM (see below).

Then run the app and open **Intelligence Briefing** → **Voice chat**: click **Start voice**, speak, then **Stop & send**.

---

## 1. Speech-to-Text (STT)

- **Provider:** `faster_whisper` (default).
- **Model:** Set `VOICE_STT_MODEL` (default `small.en`). Options: `tiny.en`, `base.en`, `small.en`, `medium.en`, etc.
- **Device:** `VOICE_STT_DEVICE=cpu` or `cuda`. `VOICE_STT_COMPUTE_TYPE=int8` (or `float16` on GPU) for speed.

First request will download the model; later runs use the cache.

---

## 2. Language model (LLM)

### Ollama (default, no API key)

1. Install: [ollama.com](https://ollama.com).
2. Pull a model:
   ```bash
   ollama pull qwen2.5:7b
   # or
   ollama pull llama3.1:8b
   ```
3. In `arxvicast/.env` (optional):
   ```env
   VOICE_LLM_PROVIDER=ollama
   OLLAMA_BASE_URL=http://localhost:11434
   OLLAMA_MODEL=qwen2.5:7b
   ```

### OpenRouter (optional fallback)

1. Get an API key at [openrouter.ai](https://openrouter.ai).
2. In `arxvicast/.env`:
   ```env
   VOICE_LLM_PROVIDER=openrouter
   OPENROUTER_KEY=sk-or-v1-...
   OPENROUTER_MODEL=openai/gpt-3.5-turbo
   ```

### NVIDIA NIM (optional fallback)

1. Deploy a chat NIM and get the completions URL and optional API key.
2. In `arxvicast/.env`:
   ```env
   VOICE_LLM_PROVIDER=nvidia_nim
   NIM_CHAT_URL=https://.../v1/chat/completions
   NIM_API_KEY=...
   ```

---

## 3. Text-to-Speech (TTS)

- **Provider:** `piper` (default).
- **Voice:** Place a Piper `.onnx` (and optional `.onnx.json`) file in `arxvicast/voices/`, or set:
   ```env
   PIPER_VOICE_PATH=/path/to/en_US-lessac-medium.onnx
   ```
- **Download voices:** e.g. [Piper voices on Hugging Face](https://huggingface.co/rhasspy/piper-voices). Use the `.onnx` for your language/variant.

---

## 4. Environment summary

| Variable | Default | Description |
|----------|---------|-------------|
| `VOICE_STT_PROVIDER` | `faster_whisper` | STT backend |
| `VOICE_STT_MODEL` | `small.en` | Whisper model |
| `VOICE_STT_DEVICE` | `cpu` | `cpu` or `cuda` |
| `VOICE_STT_COMPUTE_TYPE` | `int8` | `int8` / `float16` |
| `VOICE_LLM_PROVIDER` | `ollama` | `ollama` / `openrouter` / `nvidia_nim` |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server |
| `OLLAMA_MODEL` | `qwen2.5:7b` | Ollama model name |
| `OPENROUTER_KEY` | (none) | Required if using OpenRouter |
| `OPENROUTER_MODEL` | `openai/gpt-3.5-turbo` | OpenRouter model |
| `NIM_CHAT_URL` | (none) | Required if using NIM |
| `NIM_API_KEY` | (none) | Optional for NIM |
| `VOICE_TTS_PROVIDER` | `piper` | TTS backend |
| `PIPER_VOICE_PATH` | (none) | Path to `.onnx` or use `arxvicast/voices/` |
| `VOICE_STT_TIMEOUT` | `10` | STT timeout (seconds) |
| `VOICE_LLM_TIMEOUT` | `30` | LLM timeout |
| `VOICE_TTS_TIMEOUT` | `15` | TTS timeout |

No secrets are hardcoded; all of the above are read from the environment (e.g. `arxvicast/.env`).

---

## 5. Build and run

```bash
cd /path/to/weblogger
pip install -r requirements.txt
# Ensure Ollama is running and a Piper voice is in arxvicast/voices/
python app.py
```

Open `/intel`, then use **Voice chat** in the sidebar. Selected papers in the matrix (or all visible if none selected) are used as context for the assistant.

---

## 6. Latency and reliability

- **Timing:** The pipeline logs per-stage timings (e.g. `voice_stt=...ms`, `voice_llm=...ms`, `voice_tts=...ms`) for tuning.
- **Time to first audio:** Aim for &lt; 1.5 s; depends on Ollama load and Piper voice.
- **Interrupt:** Use the **Stop** button to abort the current response; you can start a new recording immediately.
- **Errors:** If a service is unavailable, the UI shows a short message; see server logs for details. Ensure Ollama is running and Piper voice path is valid.
