"""Tiny LLM client (stdlib only). Providers: anthropic, openai (OpenAI-compatible)."""
import json
import os
import urllib.error
import urllib.request


def _post(url, headers, body, timeout=90):
    req = urllib.request.Request(url, json.dumps(body).encode(), headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"LLM HTTP {e.code}: {e.read().decode(errors='replace')[:400]}")


def complete(system: str, user: str) -> str:
    provider = os.environ.get("LLM_PROVIDER", "anthropic").lower()
    model = os.environ.get("LLM_MODEL")
    if provider == "anthropic":
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set (see .env.example)")
        data = _post(
            "https://api.anthropic.com/v1/messages",
            {"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            {"model": model or "claude-haiku-5-5", "max_tokens": 400, "temperature": 0,
             "system": system, "messages": [{"role": "user", "content": user}]},
        )
        return "".join(b.get("text", "") for b in data["content"])
    if provider in ("openai", "ollama"):
        if provider == "ollama":  # Ollama Cloud (hosted) via its OpenAI-compatible endpoint
            key = os.environ.get("OLLAMA_API_KEY")
            if not key:
                raise RuntimeError("OLLAMA_API_KEY is not set (create one at ollama.com/settings/keys)")
            base = os.environ.get("OLLAMA_BASE_URL", "https://ollama.com/v1").rstrip("/")
            model = model or "gpt-oss:120b"
        else:
            key = os.environ.get("OPENAI_API_KEY", "x")
            base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        if not model:
            raise RuntimeError("Set LLM_MODEL for the openai provider")
        data = _post(
            base + "/chat/completions",
            {"Authorization": f"Bearer {key}", "content-type": "application/json"},
            {"model": model, "temperature": 0, "max_tokens": 2000,  # headroom for reasoning models
             "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]},
        )
        text = data["choices"][0]["message"].get("content") or ""
        if not text.strip():
            raise RuntimeError("Model returned empty content (try another LLM_MODEL)")
        return text
    raise RuntimeError(f"Unknown LLM_PROVIDER: {provider}")
