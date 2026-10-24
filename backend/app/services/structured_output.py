"""Small, dependency-free structured-output validation for Agent responses."""

import json
from typing import Any


class StructuredOutputError(ValueError):
    """Raised when a model response does not satisfy the requested schema."""


def normalize_output_schema(schema: dict[str, Any] | None) -> dict[str, Any] | None:
    if schema is None:
        return None
    if not isinstance(schema, dict) or schema.get("type") != "object":
        raise StructuredOutputError("output_schema 必须是 object JSON Schema")
    properties = schema.get("properties") or {}
    required = schema.get("required") or []
    if not isinstance(properties, dict) or len(properties) > 40:
        raise StructuredOutputError("output_schema.properties 必须是最多 40 个字段的对象")
    if not isinstance(required, list) or any(item not in properties for item in required):
        raise StructuredOutputError("output_schema.required 包含未声明字段")
    return {**schema, "additionalProperties": bool(schema.get("additionalProperties", False))}


def _validate(value: Any, schema: dict[str, Any], path: str = "$") -> None:
    expected = schema.get("type")
    valid = {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
        "null": value is None,
    }
    if expected and not valid.get(expected, True):
        raise StructuredOutputError(f"{path} 类型应为 {expected}")
    if isinstance(value, dict):
        properties = schema.get("properties") or {}
        missing = [name for name in schema.get("required", []) if name not in value]
        if missing:
            raise StructuredOutputError(f"{path} 缺少字段: {', '.join(missing)}")
        if schema.get("additionalProperties") is False:
            unknown = sorted(set(value) - set(properties))
            if unknown:
                raise StructuredOutputError(f"{path} 存在未声明字段: {', '.join(unknown)}")
        for name, child_schema in properties.items():
            if name in value and isinstance(child_schema, dict):
                _validate(value[name], child_schema, f"{path}.{name}")
    elif isinstance(value, list) and isinstance(schema.get("items"), dict):
        for index, item in enumerate(value):
            _validate(item, schema["items"], f"{path}[{index}]")


def parse_structured_output(text: str, schema: dict[str, Any]) -> Any:
    try:
        value = json.loads(text)
    except (TypeError, json.JSONDecodeError) as exc:
        raise StructuredOutputError("模型没有返回合法 JSON") from exc
    _validate(value, schema)
    return value


def openai_response_format(schema: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {"name": "enterprise_agent_output", "strict": True, "schema": schema},
    }
