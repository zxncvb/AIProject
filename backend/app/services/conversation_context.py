"""Bound conversation history before it reaches a model provider."""

from __future__ import annotations

from typing import Any


def compress_history(
    history: list[dict[str, Any]],
    *,
    max_messages: int = 20,
    max_chars: int = 16000,
) -> list[dict[str, Any]]:
    """Keep recent turns and a small, auditable summary of omitted context.

    This is deliberately deterministic: it bounds provider payload size without
    making a second model call or leaking untrusted history into instructions.
    """
    if not history:
        return []
    max_messages = max(2, min(int(max_messages), 100))
    max_chars = max(1000, min(int(max_chars), 100000))
    selected: list[dict[str, Any]] = []
    used = 0
    for message in reversed(history[-max_messages:]):
        content = str(message.get("content") or "")
        cost = len(content) + 32
        if selected and used + cost > max_chars:
            break
        selected.append({"role": str(message.get("role") or "user"), "content": content})
        used += cost
    selected.reverse()
    omitted = history[: len(history) - len(selected)]
    if omitted:
        snippets = []
        for item in omitted[-3:]:
            content = " ".join(str(item.get("content") or "").split())
            snippets.append(f"{item.get('role', 'user')}: {content[:180]}")
        selected.insert(0, {
            "role": "system",
            "content": "Earlier conversation was compressed for context limits. Relevant excerpts:\n- " + "\n- ".join(snippets),
        })
    return selected
