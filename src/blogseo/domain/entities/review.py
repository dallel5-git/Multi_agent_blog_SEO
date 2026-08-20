"""Entités de relecture : `ReviewFinding` et `ReviewResult`.

Utilisées par le Technical Reviewer (exactitude technique) et, indirectement,
par le Quality Gate qui consomme le verdict.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class FindingKind(str, Enum):
    OUTDATED_VERSION = "outdated_version"
    BROKEN_LINK = "broken_link"
    CODE_ERROR = "code_error"
    FACTUAL_ERROR = "factual_error"
    MISSING_CONTEXT = "missing_context"
    STYLE = "style"


@dataclass(frozen=True, slots=True)
class ReviewFinding:
    """Un problème identifié par le relecteur technique."""

    kind: FindingKind
    excerpt: str          # extrait fautif de l'article
    problem: str          # description du problème
    suggestion: str = ""  # correction proposée
    blocking: bool = False

    def as_instruction(self) -> str:
        fix = f" → {self.suggestion}" if self.suggestion else ""
        flag = "[BLOQUANT] " if self.blocking else ""
        return f"{flag}({self.kind.value}) {self.problem}{fix}"


@dataclass(slots=True)
class ReviewResult:
    """Verdict complet du Technical Reviewer."""

    findings: list[ReviewFinding] = field(default_factory=list)
    checked_urls: dict[str, bool] = field(default_factory=dict)  # url -> joignable
    notes: str = ""

    @property
    def blocking_findings(self) -> list[ReviewFinding]:
        return [f for f in self.findings if f.blocking]

    @property
    def broken_urls(self) -> list[str]:
        return [url for url, ok in self.checked_urls.items() if not ok]

    @property
    def is_clean(self) -> bool:
        return not self.blocking_findings and not self.broken_urls

    def as_instructions(self) -> str:
        if self.is_clean and not self.findings:
            return ""
        lines = [f.as_instruction() for f in self.findings]
        lines += [f"[BLOQUANT] (broken_link) Lien mort à retirer ou remplacer : {u}" for u in self.broken_urls]
        return "\n".join(lines)
