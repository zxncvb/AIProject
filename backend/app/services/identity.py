import json
import re
from typing import Any


BUILTIN_ROLES = {"owner", "admin", "developer", "editor", "operator", "viewer"}


def claim_values(claims: dict[str, Any], claim_name: str) -> list[str]:
    """Normalize OIDC group/role claims from string, array, or space-delimited formats."""
    value = claims.get(claim_name)
    if value is None:
        return []
    if isinstance(value, str):
        return [item for item in re.split(r"[\s,]+", value.strip()) if item]
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


def parse_role_mapping(raw: str) -> dict[str, str]:
    """Parse JSON mapping and tolerate simple group=role pairs for env files."""
    if not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return {str(key).strip(): str(value).strip() for key, value in parsed.items() if str(key).strip() and str(value).strip()}
    except json.JSONDecodeError:
        pass
    mapping: dict[str, str] = {}
    for item in raw.split(","):
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        if key.strip() and value.strip():
            mapping[key.strip()] = value.strip()
    return mapping


def mapped_role(claims: dict[str, Any], groups_claim: str, roles_claim: str, mapping: dict[str, str], default_role: str) -> str:
    values = claim_values(claims, groups_claim) + claim_values(claims, roles_claim)
    for value in values:
        if value in mapping:
            return mapping[value]
    return default_role
