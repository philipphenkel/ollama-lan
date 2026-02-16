#!/usr/bin/env python3

import argparse
import json
import re
import time

import gradio as gr
import requests

APP_TITLE = "ollama-lan"
DEFAULT_BASE_URL = "http://localhost:11434"
TAGS_TIMEOUT_SECONDS = 15
CHAT_CONNECT_TIMEOUT_SECONDS = 5
CHAT_READ_TIMEOUT_SECONDS = 300
STREAM_UI_UPDATE_INTERVAL_SECONDS = 0.12
STREAM_UI_UPDATE_MIN_CHARS = 24

STATUS_READY = "ready"
STATUS_GENERATING = "gen"
STATUS_THINKING = "think"
STATUS_ERROR = "err"

def header_text(status: str) -> str:
    return f"## {APP_TITLE} ㅤ {status_text(status)}"

def status_text(status: str) -> str:
    text = {
        STATUS_READY: "🟢 Ready",
        STATUS_GENERATING: "✍ Generating",
        STATUS_THINKING: " 🧠 Thinking",
        STATUS_ERROR: "⚠️ Ollama unreachable",
    }.get(status, "🟢 Ready")
    return text


def normalize_base_url(base_url: str) -> str:
    url = (base_url or DEFAULT_BASE_URL).strip()
    if not url:
        url = DEFAULT_BASE_URL
    return url.rstrip("/")


def ns_to_s(value: object) -> float:
    if not value:
        return 0.0
    return float(value) / 1_000_000_000


def compute_speed(count: object, duration_ns: object) -> float:
    duration_s = ns_to_s(duration_ns)
    if not count or duration_s <= 0:
        return 0.0
    return float(count) / duration_s


def format_bytes(num_bytes: object) -> str | None:
    if not num_bytes:
        return None
    size = float(num_bytes)
    units = ["B", "KB", "MB", "GB", "TB"]
    idx = 0
    while size >= 1024 and idx < len(units) - 1:
        size /= 1024
        idx += 1
    return f"{size:.2f} {units[idx]}"


def format_context_length(value: object) -> str | None:
    if value is None or value == "":
        return None
    try:
        size = int(value)
        if size >= 1024:
            kilo = size / 1024
            if kilo.is_integer():
                return f"{int(kilo)}k"
            return f"{kilo:.1f}k"
        return f"{size:,}"
    except (TypeError, ValueError):
        return str(value)


def optional_str(value: object) -> str | None:
    if value is None or value == "":
        return None
    return str(value)


def build_model_info(selected_model: str | None, model_map: dict[str, dict[str, object]]) -> str:
    if not selected_model:
        return "### Selected Model\nNo model selected."

    model_meta = model_map.get(selected_model)
    if not model_meta:
        return f"### Selected Model\n`{selected_model}` metadata unavailable."

    details = model_meta.get("details", {})
    vram_size = format_bytes(model_meta.get("size_vram"))
    family = optional_str(details.get("family"))
    quantization = optional_str(details.get("quantization_level"))
    param_size = optional_str(details.get("parameter_size"))
    context_length = format_context_length(model_meta.get("context_length"))

    lines = [f"### {selected_model}"]
    for label, value in (
        ("Family", family),
        ("Parameters", param_size),
        ("Quantization", quantization),
        ("VRAM size", vram_size),
        ("Context length", context_length),
    ):
        if value is not None:
            lines.append(f"- {label}: **{value}**")
    return "\n".join(lines)


def choose_model(model_names: list[str], preferred_model: str | None) -> str:
    if preferred_model and preferred_model in model_names:
        return preferred_model
    return model_names[0]


def fetch_models(normalized_base_url: str) -> list[dict[str, object]]:
    response = requests.get(
        f"{normalized_base_url}/api/tags",
        timeout=TAGS_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    payload = response.json()
    models = [model for model in payload.get("models", []) if model.get("name")]
    models.sort(key=lambda model: model.get("name", ""))
    return models


def refresh_models(base_url: str, selected_model: str | None):
    normalized = normalize_base_url(base_url)
    try:
        models = fetch_models(normalized)
    except requests.RequestException as exc:
        info = f"### Selected Model\nUnavailable. Could not reach `{normalized}`.\n\n`{exc}`"
        return gr.update(choices=[], value=None), info, {}, header_text(STATUS_ERROR)

    model_names = [model["name"] for model in models]
    model_map = {model["name"]: model for model in models}

    if not model_names:
        return (
            gr.update(choices=[], value=None),
            "### Selected Model\nNo models found.",
            {},
            header_text(STATUS_READY),
        )

    value = choose_model(model_names, selected_model)
    info = build_model_info(value, model_map)
    return gr.update(choices=model_names, value=value), info, model_map, header_text(STATUS_READY)


def format_metrics(meta: dict[str, object]) -> str:
    prompt_tps = compute_speed(meta.get("prompt_eval_count"), meta.get("prompt_eval_duration"))
    gen_tps = compute_speed(meta.get("eval_count"), meta.get("eval_duration"))
    total_s = ns_to_s(meta.get("total_duration"))
    load_s = ns_to_s(meta.get("load_duration"))
    return (
        "### Response Metrics\n"
        f"- Prompt speed: **{prompt_tps:.2f} tok/s**\n"
        f"- Generation speed: **{gen_tps:.2f} tok/s**\n"
        f"- Total duration: **{total_s:.2f} s**\n"
        f"- Load duration: **{load_s:.2f} s**"
    )


def fetch_ps_entry(normalized_base_url: str, model: str) -> dict[str, object] | None:
    try:
        response = requests.get(
            f"{normalized_base_url}/api/ps",
            timeout=TAGS_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, json.JSONDecodeError):
        return None

    models = payload.get("models", [])
    for entry in models:
        entry_name = entry.get("name") or entry.get("model") or ""
        if entry_name == model:
            return entry
    return None


def render_assistant_text(text: str) -> str:
    rendered = text.replace("\r\n", "\n").replace("\r", "\n")

    # Convert multiline block math emitted as:
    # [
    #   ...math...
    # ]
    # Accepts indentation and both [ ... ] and \[ ... \] styles.
    block_pattern = re.compile(r"(?ms)(^|\n)\s*\\?\[\s*\n(.*?)\n\s*\\?\]\s*(?=\n|$)")
    rendered, _ = block_pattern.subn(lambda m: f"{m.group(1)}$$\n{m.group(2).strip()}\n$$", rendered)

    # Convert single-line bracket math like [h = \tfrac12,g,t^{2}.]
    inline_pattern = re.compile(r"\[\s*([^\[\]\n]*[=\\^_][^\[\]\n]*)\s*\]")
    rendered, _ = inline_pattern.subn(lambda m: f"$${m.group(1).strip()}$$", rendered)

    return rendered


def stream_chat(
    message: str,
    ui_history: list[dict[str, str]],
    api_history: list[dict[str, str]],
    base_url: str,
    model: str,
    model_map: dict[str, dict[str, object]],
):
    clean_ui = list(ui_history or [])
    clean_api = list(api_history or [])
    model_map = model_map or {}
    model_info = build_model_info(model, model_map)

    if not message.strip():
        yield clean_ui, clean_ui, clean_api, header_text(STATUS_READY), "No metrics yet.", model_info, model_map
        return

    if not model:
        yield clean_ui, clean_ui, clean_api, header_text(STATUS_READY), "No metrics yet.", model_info, model_map
        return

    normalized = normalize_base_url(base_url)
    request_messages = clean_api.copy()
    request_messages.append({"role": "user", "content": message})
    display_history = clean_ui + [
        {"role": "user", "content": message},
        {"role": "assistant", "content": ""},
    ]
    yield display_history, display_history, clean_api, header_text(STATUS_GENERATING), "No metrics yet.", model_info, model_map

    payload = {
        "model": model,
        "messages": request_messages,
        "stream": True,
    }

    text = ""
    final_meta: dict[str, Any] = {}
    last_ui_emit = time.monotonic()
    last_ui_len = 0
    try:
        with requests.post(
            f"{normalized}/api/chat",
            json=payload,
            timeout=(CHAT_CONNECT_TIMEOUT_SECONDS, CHAT_READ_TIMEOUT_SECONDS),
            stream=True,
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines(decode_unicode=True):
                if not line:
                    continue
                event = json.loads(line)
                message_event = event.get("message", {})
                status_key = STATUS_THINKING if message_event.get("thinking") else STATUS_GENERATING

                if message_event.get("content"):
                    text += message_event["content"]

                if message_event.get("thinking") or message_event.get("content"):
                    now = time.monotonic()
                    chars_delta = len(text) - last_ui_len
                    should_emit = (
                        chars_delta >= STREAM_UI_UPDATE_MIN_CHARS
                        or now - last_ui_emit >= STREAM_UI_UPDATE_INTERVAL_SECONDS
                        or (message_event.get("thinking") and not message_event.get("content"))
                    )
                    if should_emit:
                        display_history[-1] = {"role": "assistant", "content": text}
                        last_ui_emit = now
                        last_ui_len = len(text)
                        yield display_history, display_history, clean_api, header_text(status_key), "No metrics yet.", model_info, model_map

                if event.get("done"):
                    final_meta = event
                    break
    except (requests.RequestException, json.JSONDecodeError) as exc:
        display_history[-1] = {"role": "assistant", "content": f"[Error] {exc}"}
        yield display_history, display_history, clean_api, header_text(STATUS_ERROR), "No metrics yet.", model_info, model_map
        return

    metrics = format_metrics(final_meta) if final_meta else "No metrics returned by Ollama."
    ps_entry = fetch_ps_entry(normalized, model)
    if ps_entry:
        entry = dict(model_map.get(model) or {})
        if ps_entry.get("context_length"):
            entry["context_length"] = ps_entry.get("context_length")
        if ps_entry.get("size_vram"):
            entry["size_vram"] = ps_entry.get("size_vram")
        if entry:
            model_map[model] = entry
            model_info = build_model_info(model, model_map)
    display_history[-1] = {"role": "assistant", "content": render_assistant_text(text)}
    updated_api = request_messages + [{"role": "assistant", "content": text}]
    yield display_history, display_history, updated_api, header_text(STATUS_READY), metrics, model_info, model_map


def build_app(
    initial_base_url: str = DEFAULT_BASE_URL,
    initial_model: str | None = None,
) -> gr.Blocks:
    with gr.Blocks(title=APP_TITLE) as app:
        base_url_state = gr.State(normalize_base_url(initial_base_url))
        startup_model_state = gr.State(initial_model)
        model_map_state = gr.State({})
        ui_history_state = gr.State([])
        api_history_state = gr.State([])


        headline = gr.Markdown(header_text(STATUS_READY))

        with gr.Row():

            with gr.Column(scale=3, min_width=480):
                with gr.Row():
                    prompt = gr.Textbox(show_label=False, placeholder="Ask something...")
                chat = gr.Chatbot(allow_tags=False)

            with gr.Column(scale=1, min_width=280):
                model = gr.Dropdown(
                    label=f"Models at {normalize_base_url(initial_base_url)}",
                    choices=[],
                    value=None,
                    allow_custom_value=False,
                    filterable=False,
                )
                model_info = gr.Markdown("### Selected Model\nLoading...")
                metrics = gr.Markdown("No metrics yet.")

        app.load(
            fn=refresh_models,
            inputs=[base_url_state, startup_model_state],
            outputs=[model, model_info, model_map_state, headline],
        )
        model.change(
            fn=lambda m, mm: build_model_info(m, mm or {}),
            inputs=[model, model_map_state],
            outputs=[model_info],
        )

        prompt.submit(
            fn=stream_chat,
            inputs=[prompt, ui_history_state, api_history_state, base_url_state, model, model_map_state],
            outputs=[chat, ui_history_state, api_history_state, headline, metrics, model_info, model_map_state],
        ).then(
            fn=lambda: "",
            inputs=[],
            outputs=[prompt],
        )

        chat.clear(
            fn=lambda mm: ([], [], [], header_text(STATUS_READY), "No metrics yet.", gr.update(), mm),
            inputs=[model_map_state],
            outputs=[chat, ui_history_state, api_history_state, headline, metrics, model_info, model_map_state],
        )

    return app


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=f"Run {APP_TITLE}.")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind Gradio server to.")
    parser.add_argument("--port", type=int, default=11440, help="Port to bind Gradio server to.")
    parser.add_argument("--share", action="store_true", help="Enable Gradio share URL.")
    parser.add_argument(
        "--ollama-base-url",
        default=DEFAULT_BASE_URL,
        help="Ollama base URL (example: http://localhost:11434).",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Model name to preselect at startup (example: gpt-oss:20b).",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    demo = build_app(initial_base_url=args.ollama_base_url, initial_model=args.model)
    demo.launch(server_name=args.host, server_port=args.port, share=args.share)
