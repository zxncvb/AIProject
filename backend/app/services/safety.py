import re
from typing import Any


PROMPT_INJECTION_PATTERNS = (
    r"ignore\s+(all\s+)?previous\s+instructions",
    r"忽略(之前|上面|所有)的指令",
    r"reveal\s+(the\s+)?system\s+prompt",
    r"输出系统提示词",
    r"绕过(安全|权限|审核)",
)
PII_PATTERNS = (
    (re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"), "[邮箱已脱敏]"),
    (re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"), "[手机号已脱敏]"),
    (re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)"), "[证件号已脱敏]"),
)


def inspect_text(text: str, policy: dict[str, Any] | None = None) -> dict[str, Any]:
    policy = policy or {}
    max_chars = int(policy.get("max_input_chars", 12000))
    mode = str(policy.get("mode", "redact"))
    value = text[:max_chars]
    reasons = ["prompt_injection"] if any(re.search(pattern, value, re.IGNORECASE) for pattern in PROMPT_INJECTION_PATTERNS) else []
    redacted = value
    if mode in {"redact", "block"}:
        for pattern, replacement in PII_PATTERNS:
            redacted = pattern.sub(replacement, redacted)
    blocked = bool(reasons and (mode == "block" or policy.get("block_prompt_injection", False)))
    if len(text) > max_chars:
        reasons.append("input_too_long")
        blocked = True
    return {"allowed": not blocked, "blocked": blocked, "reasons": reasons, "text": redacted, "length": len(text)}
