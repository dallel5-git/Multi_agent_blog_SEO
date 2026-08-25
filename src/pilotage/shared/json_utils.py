"""Extraction JSON tolérante depuis une réponse LLM.

Un LLM en mode JSON renvoie parfois du texte autour de l'objet (préambule,
fences markdown) : on isole le premier bloc `{...}` plutôt que d'exiger une
réponse strictement pure.
"""

from __future__ import annotations

import json
import re

_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)


def extract_json(text: str) -> dict:
    match = _JSON_OBJECT.search(text)
    if not match:
        return {}
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}
