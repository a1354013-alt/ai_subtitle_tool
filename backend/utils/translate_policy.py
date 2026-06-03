def is_translation_request(target_lang: str, source_lang: str | None = None) -> bool:
    normalized = (target_lang or "").strip().lower()
    if normalized in {"original", "source", "auto", ""}:
        return False
    if source_lang and normalized == source_lang.strip().lower():
        return False
    return True


def translation_targets_requested(target_langs: list[str], source_lang: str | None = "Auto") -> bool:
    return any(is_translation_request(lang, source_lang) for lang in target_langs)


def should_translate(target_lang: str, source_lang: str | None = None, openai_enabled: bool = False) -> bool:
    return openai_enabled and is_translation_request(target_lang, source_lang)
