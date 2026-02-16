# ollama-lan

Run Ollama on one machine — use it from all your devices.
Lightweight LAN chat UI to access your models from any device in your local network.

This is a minimal single-file Gradio UI for Ollama (~400 lines), designed to stay readable, hackable, and easy to embed into other setups.

Features:

- Chat conversation UI
- Model picker
- Live generation status (thinking / generating / done)
- Model metadata (VRAM, quantization, context length)
- Performance metrics (tokens/sec, load time, duration)

No database. No backend framework. Just Python + Gradio + Ollama.

---

## Requirements

- Python **3.10+**
- A running **Ollama** instance  
  (default: `http://localhost:11434`)

Test your Ollama first:

```bash
ollama list
```

---

## Quickstart

```bash
python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
python ollama-lan.py
```

Then open:

```
http://localhost:11440
```

Default bind: `0.0.0.0:11440`

---

## Command Line Options

| Option | Default | Description |
|------|------|------|
| `--host` | `0.0.0.0` | Web server bind address |
| `--port` | `11440` | Web UI port |
| `--share` | off | Gradio public share link |
| `--ollama-host` | `http://localhost:11434` | Ollama API base URL |
| `--model` | auto | Preselect model at startup |

---

## Examples

Run locally only:

```bash
python ollama-lan.py --host 127.0.0.1 --port 8080
```

Connect to remote Ollama server:

```bash
python ollama-lan.py \
  --ollama-host http://192.168.1.20:11434 \
  --model gpt-oss:20b
```

Expose temporary public link:

```bash
python ollama-lan.py --share
```

---

## What Makes This Different

This project intentionally avoids:

- databases
- auth layers
- async frameworks
- heavy frontends

The goal is a **debuggable, hackable reference UI** you can read in one sitting and modify easily.

## License

MIT
