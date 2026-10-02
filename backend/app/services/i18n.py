"""Shared language-instruction helper for every LLM-backed Agent (research/news/compliance).
Keeps the prompt-language convention in one place instead of duplicated per service."""

LANGUAGE_NAMES = {"en": "English", "zh": "Simplified Chinese"}
DEFAULT_LANG = "en"


def language_instruction(lang: str) -> str:
    name = LANGUAGE_NAMES.get(lang, LANGUAGE_NAMES[DEFAULT_LANG])
    return f" Respond in {name}."
