"""Ollama HTTP client. Uses env config; does not import LangChain."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from backend.agent.settings import ollama_base_url, ollama_model, ollama_timeout_seconds


class OllamaError(Exception):
    pass


def ollama_is_available() -> bool:
    url = f"{ollama_base_url()}/api/tags"
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            return 200 <= response.status < 300
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def _post_json(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{ollama_base_url()}{path}",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=ollama_timeout_seconds()) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise OllamaError(f"Ollama HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise OllamaError(f"Ollama request failed: {exc}") from exc
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise OllamaError("Ollama returned invalid JSON.") from exc


def _normalize_tool_calls(raw_calls: Any) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for call in raw_calls or []:
        function = call.get("function") if isinstance(call, dict) else None
        if not isinstance(function, dict):
            continue
        name = str(function.get("name") or "")
        arguments = function.get("arguments") or {}
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments) if arguments else {}
            except json.JSONDecodeError:
                arguments = {}
        if not isinstance(arguments, dict):
            arguments = {}
        if name:
            normalized.append({"name": name, "args": arguments})
    return normalized


def chat(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    *,
    response_format: str | dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": ollama_model(),
        "messages": messages,
        "stream": False,
    }
    if tools:
        payload["tools"] = tools
    if response_format is not None:
        payload["format"] = response_format
    data = _post_json("/api/chat", payload)
    message = data.get("message") or {}
    return {
        "content": str(message.get("content") or "").strip(),
        "tool_calls": _normalize_tool_calls(message.get("tool_calls")),
        "model": data.get("model") or ollama_model(),
    }
