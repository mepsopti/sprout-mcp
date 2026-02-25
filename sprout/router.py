"""Model routing table and review logic."""

import json
import os
from pathlib import Path

_DEFAULT_ROUTING_TABLE: dict[str, tuple[str, str]] = {
    "biography_synthesis": ("haiku", "Factual summarization from web sources"),
    "council_description": ("haiku", "Historical summarization"),
    "document_synopsis": ("haiku", "Content summarization"),
    "json_validation": ("haiku", "Structural verification"),
    "summarization": ("haiku", "General summarization task"),
    "data_extraction": ("haiku", "Structured data extraction"),
    "fact_check_first_pass": ("sonnet", "Cross-reference claims"),
    "code_review": ("sonnet", "Code analysis and review"),
    "fact_check_final": ("opus", "Deep factual verification"),
    "theological_analysis": ("opus", "Domain expertise required"),
    "complex_analysis": ("opus", "Deep reasoning required"),
}

# Maps model short names to full identifiers
MODEL_IDS = {
    "haiku": "haiku-4.5",
    "sonnet": "sonnet-4.6",
    "opus": "opus-4.6",
}

# Auto-assign confidence based on producing model
MODEL_CONFIDENCE = {
    "haiku-4.5": "seed",
    "sonnet-4.6": "watered",
    "opus-4.6": "sprouted",
}

# Output token pricing per million tokens (Anthropic, Feb 2026)
MODEL_PRICING: dict[str, float] = {
    "haiku-4.5": 5.00,
    "sonnet-4.6": 15.00,
    "opus-4.6": 75.00,
}

# Runtime routing table (starts from defaults, can be extended)
_routing_table: dict[str, tuple[str, str]] = dict(_DEFAULT_ROUTING_TABLE)


def _load_config_routes() -> None:
    """Load custom routes from SPROUT_CONFIG file if set."""
    config_path = os.environ.get("SPROUT_CONFIG")
    if not config_path:
        return
    p = Path(config_path)
    if not p.exists():
        return
    data = json.loads(p.read_text())
    for task_type, route in data.get("routes", {}).items():
        _routing_table[task_type] = (route["tier"], route.get("reason", "Custom route"))
    for model, price in data.get("pricing", {}).items():
        MODEL_PRICING[model] = float(price)


_load_config_routes()


def get_routing_table() -> dict[str, tuple[str, str]]:
    return dict(_routing_table)


def add_route(task_type: str, tier: str, reason: str) -> None:
    _routing_table[task_type] = (tier, reason)


def recommend_model(task_type: str) -> dict:
    if task_type in _routing_table:
        tier, reason = _routing_table[task_type]
        return {
            "task_type": task_type,
            "recommended_model": MODEL_IDS[tier],
            "tier": tier,
            "reason": reason,
        }
    return {
        "task_type": task_type,
        "recommended_model": MODEL_IDS["haiku"],
        "tier": "haiku",
        "reason": "Default: start cheap, escalate if needed",
    }


def confidence_for_model(model: str) -> str:
    return MODEL_CONFIDENCE.get(model, "seed")
