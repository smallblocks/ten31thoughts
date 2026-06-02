# Ten31 Thoughts — Instructions

## Getting Started

1. After installation, open the Ten31 Thoughts web interface from your StartOS dashboard.
2. The system comes pre-seeded with two feeds:
   - **Ten31 Timestamp** (your weekly newsletter via Substack RSS)
   - **MacroVoices** (weekly macro interview podcast)
3. The service will begin polling these feeds automatically.

## Configuration

### LLM API Keys

Ten31 Thoughts requires at least one LLM API key to run analysis. Set your preferred key(s) via the service configuration:

- **Anthropic API Key** — For Claude models (recommended for analysis passes)
- **OpenAI API Key** — For GPT models and embeddings

You can configure which model handles each task type (analysis, chat, synthesis, embeddings) for cost optimization.

### Adding RSS Feeds

To add a new source:

1. Open the web interface
2. Navigate to **Feed Management**
3. Click **Add Feed** and paste the RSS/Atom URL
4. Classify it as "Our Thesis" (your writing) or "External Interview" (other voices)

Alternatively, use the chat: type "Add this RSS feed: [URL]" and follow the prompt.

### Feed Categories

| Category | Use For | Analysis |
|----------|---------|----------|
| Our Thesis | Your newsletters, podcast appearances, research notes | Thesis extraction, data skepticism, predictions |
| External Interview | MacroVoices, Real Vision, macro commentary | Framework extraction, blind spots, reasoning quality |

## How It Works

### Automatic Processing

The service runs three background processes:
- **Feed polling** every 15 minutes — checks for new content
- **Analysis** every 5 minutes — processes queued content through LLM passes
- **Weekly synthesis** every Sunday at 6 AM UTC — generates the weekly briefing

### Weekly Briefing

Every Sunday, the system produces a structured briefing containing:
- **Top 5 Macro Frameworks** — ranked by accuracy, robustness, and novelty
- **Prediction Scorecard** — your accuracy vs. external guests
- **Convergence Map** — where your views align or diverge
- **Blind Spot Alerts** — topics nobody is covering
- **Narrative Shifts** — how positions are evolving

Access briefings from the chat interface or the Briefings section.

### Chat Interface

Ask the intelligence layer anything:
- "Show me the top 5 frameworks"
- "Where do I disagree with [guest name]?"
- "What am I not talking about?"
- "How has my view on the Fed evolved?"
- "Who predicted the payroll revision correctly?"

## Voice Capture

The CaptureBox on the This Week page includes a microphone button for voice-to-text note capture.

### Browser Dictation (default)

On supported browsers (Chrome, Edge, Safari 17+), tapping the mic button uses the browser's built-in `SpeechRecognition` API for on-device transcription. No server calls are made — it's free, fast, and works offline.

- Tap 🎤 to start, speak naturally, and stop talking for ~1.5 seconds to auto-save.
- Tap "● Listening" to cancel without saving (partial transcript stays in the textarea for manual editing).
- Live interim transcripts stream into the textarea as you speak.

### Whisper Fallback

If your browser doesn't support SpeechRecognition (e.g., Firefox, or iOS Safari over plain HTTP), the app falls back to recording audio and sending it to a local Whisper-compatible server for transcription.

**Recommended server:** [faster-whisper-server](https://github.com/fedirz/faster-whisper-server) running on your DGX Spark or any local GPU.

To configure:

1. In StartOS, go to **Ten31 Thoughts → Actions → Configure LLM**.
2. Set **Whisper Server URL** to your server (e.g., `http://192.168.86.28:8000`).
3. Set **Whisper Server Type** to match your server (`faster-whisper-server` or `whisper.cpp`).
4. Set **Whisper Model** (e.g., `whisper-large-v3`).

If no Whisper URL is configured and the browser doesn't support SpeechRecognition, the mic button will not appear.

### iOS Safari Note

iOS Safari requires HTTPS for the `SpeechRecognition` API. If you access Ten31 Thoughts over plain HTTP on a `.local` address, browser dictation won't work — but the Whisper fallback will handle it automatically (as long as a Whisper server is configured). For full browser dictation support on iOS, access the service through an HTTPS gateway (e.g., StartTunnel).

## Data & Privacy

All data is stored locally on your StartOS device. No data leaves your server except for LLM API calls (which send content to your configured provider for analysis). Voice transcription via browser SpeechRecognition stays entirely on-device. The Whisper fallback sends audio only to your configured local server — never to an external service. Consider using a local Ollama model for maximum privacy.
