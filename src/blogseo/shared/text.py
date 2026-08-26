"""Utilitaires texte partagés (troncature, nettoyage, extraction d'URL)."""

from __future__ import annotations

import re

_URL_PATTERN = re.compile(r"https?://[^\s<>\)\]\"']+")
_MD_LINK_PATTERN = re.compile(r"\[([^\]]*)\]\((https?://[^\)\s]+)\)")


def truncate(text: str, limit: int, suffix: str = "…") -> str:
    """Tronque proprement sur une frontière de mot."""
    if len(text) <= limit:
        return text
    cut = text[: limit - len(suffix)]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip(" ,;:.") + suffix


def extract_urls(text: str) -> list[str]:
    """Toutes les URLs du texte, liens Markdown inclus, dédoublonnées."""
    urls = [match.group(2) for match in _MD_LINK_PATTERN.finditer(text)]
    urls += _URL_PATTERN.findall(_MD_LINK_PATTERN.sub(r"\1", text))
    seen: set[str] = set()
    unique: list[str] = []
    for url in urls:
        clean = url.rstrip(".,;:!?")
        if clean not in seen:
            seen.add(clean)
            unique.append(clean)
    return unique


def strip_code_blocks(markdown: str) -> str:
    """Retire les blocs de code (analyse de ton et de densité de mots-clés)."""
    return re.sub(r"```.*?```", " ", markdown, flags=re.DOTALL)


def strip_frontmatter(markdown: str) -> str:
    """Retire un éventuel frontmatter YAML généré par erreur par le LLM.

    Le Content Writer doit produire uniquement le corps ; le frontmatter est
    construit par l'entité `Article` à partir des métadonnées SEO validées.
    """
    stripped = markdown.lstrip()
    if not stripped.startswith("---"):
        return markdown
    parts = stripped.split("---", 2)
    return parts[2].lstrip("\n") if len(parts) >= 3 else markdown


def escape_markdown_v2(text: str) -> str:
    """Échappe les caractères réservés de MarkdownV2 (API Telegram)."""
    return re.sub(r"([_*\[\]()~`>#+\-=|{}.!\\])", r"\\\1", text)


def word_count(text: str) -> int:
    return len(re.findall(r"\b[\wÀ-ÿ'-]+\b", strip_code_blocks(text)))


def quote_yaml_scalar(value: str) -> str:
    """Échappe une chaîne pour un scalaire YAML entre guillemets doubles.

    Partagé entre `Article.to_frontmatter()` et le refresh ciblé (issue #42) :
    les deux écrivent des lignes de frontmatter et doivent échapper à l'identique
    pour que la relecture (`parse_frontmatter`) reste symétrique.
    """
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
