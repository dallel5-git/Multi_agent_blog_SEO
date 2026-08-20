"""Extraction tolérante de JSON depuis une réponse de LLM.

Les modèles gratuits (Gemini Flash, Llama sur Groq) ajoutent régulièrement du
texte autour du JSON, des fences ```json, des virgules finales ou des
apostrophes typographiques. Cette fonction encaisse ces défauts plutôt que de
faire planter tout le pipeline sur un `json.JSONDecodeError`.
"""

from __future__ import annotations

import json
import re

_FENCE_PATTERN = re.compile(r"```(?:json|JSON)?\s*(.*?)```", re.DOTALL)
_TRAILING_COMMA_PATTERN = re.compile(r",\s*([}\]])")


def _strip_fences(text: str) -> str:
    match = _FENCE_PATTERN.search(text)
    return match.group(1) if match else text


def _first_balanced_block(text: str) -> str | None:
    """Extrait le premier objet/tableau JSON équilibré, en ignorant le bruit autour."""
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        if start == -1:
            continue
        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(text)):
            char = text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == opener:
                depth += 1
            elif char == closer:
                depth -= 1
                if depth == 0:
                    return text[start : index + 1]
    return None


def extract_json(text: str, *, default: dict | None = None) -> dict:
    """Renvoie le premier objet JSON trouvé dans `text`.

    Lève `ValueError` si rien n'est exploitable et qu'aucun `default` n'est fourni.
    """
    if not text or not text.strip():
        if default is not None:
            return default
        raise ValueError("Réponse LLM vide : aucun JSON à extraire")

    candidates = [_strip_fences(text).strip(), text.strip()]
    block = _first_balanced_block(candidates[0]) or _first_balanced_block(candidates[1])
    if block:
        candidates.insert(0, block)

    for candidate in candidates:
        for attempt in (candidate, _TRAILING_COMMA_PATTERN.sub(r"\1", candidate)):
            try:
                parsed = json.loads(attempt)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed
            if isinstance(parsed, list):
                return {"items": parsed}

    if default is not None:
        return default
    preview = text[:200].replace("\n", " ")
    raise ValueError(f"Impossible d'extraire un JSON valide de la réponse LLM : {preview!r}")


def extract_list(text: str, key: str = "items") -> list:
    """Variante pour les réponses attendues sous forme de liste."""
    data = extract_json(text, default={key: []})
    value = data.get(key, [])
    return value if isinstance(value, list) else [value]
