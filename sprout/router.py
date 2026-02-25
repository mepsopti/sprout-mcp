"""Model routing table and review logic."""

ROUTING_TABLE: dict[str, tuple[str, str]] = {
    "biography_synthesis": ("haiku", "Factual summarization from web sources"),
    "council_description": ("haiku", "Historical summarization"),
    "document_synopsis": ("haiku", "Content summarization"),
    "json_validation": ("haiku", "Structural verification"),
    "fact_check_first_pass": ("sonnet", "Cross-reference claims"),
    "fact_check_final": ("opus", "Deep factual verification"),
    "theological_analysis": ("opus", "Domain expertise required"),
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


def recommend_model(task_type: str) -> dict:
    if task_type in ROUTING_TABLE:
        tier, reason = ROUTING_TABLE[task_type]
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
