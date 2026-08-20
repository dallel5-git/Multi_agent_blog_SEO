"""Value objects du Quality Gate : `QualityCheck` et `QualityReport`.

Le Quality Gate est purement déterministe côté domain : aucune règle ici
n'appelle un LLM. Cela rend le comportement testable et reproductible.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Severity(str, Enum):
    """Gravité d'un contrôle raté."""

    BLOCKER = "blocker"   # renvoie obligatoirement l'article au Content Writer
    WARNING = "warning"   # signalé dans le rapport, mais non bloquant


@dataclass(frozen=True, slots=True)
class QualityCheck:
    """Résultat d'un contrôle unitaire du Quality Gate."""

    name: str
    passed: bool
    severity: Severity
    message: str = ""

    @property
    def is_blocking(self) -> bool:
        return not self.passed and self.severity is Severity.BLOCKER


@dataclass(frozen=True, slots=True)
class QualityReport:
    """Agrégat des contrôles, avec le verdict et les consignes de correction."""

    checks: tuple[QualityCheck, ...] = ()
    iteration: int = 1

    @property
    def blockers(self) -> tuple[QualityCheck, ...]:
        return tuple(c for c in self.checks if c.is_blocking)

    @property
    def warnings(self) -> tuple[QualityCheck, ...]:
        return tuple(c for c in self.checks if not c.passed and not c.is_blocking)

    @property
    def approved(self) -> bool:
        """Un article passe la porte s'il n'a aucun contrôle bloquant raté."""
        return not self.blockers

    @property
    def score(self) -> float:
        """Ratio de contrôles réussis, entre 0.0 et 1.0 (pour le reporting)."""
        if not self.checks:
            return 0.0
        return round(sum(1 for c in self.checks if c.passed) / len(self.checks), 3)

    def revision_instructions(self) -> str:
        """Consignes renvoyées au Content Writer lors de la boucle de feedback."""
        if self.approved:
            return ""
        lines = ["Corrige impérativement les points suivants :"]
        lines += [f"- [BLOQUANT] {c.message or c.name}" for c in self.blockers]
        lines += [f"- [À améliorer] {c.message or c.name}" for c in self.warnings]
        return "\n".join(lines)

    def summary(self) -> str:
        verdict = "APPROUVÉ" if self.approved else "REJETÉ"
        return (
            f"{verdict} (itération {self.iteration}) — score {self.score:.0%} "
            f"| {len(self.blockers)} bloquant(s), {len(self.warnings)} avertissement(s)"
        )
