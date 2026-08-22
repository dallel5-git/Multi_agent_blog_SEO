"""Agent 7/9 — Quality Gate : checklist de validation 100 % déterministe.

**Aucun appel LLM ici.** C'est délibéré : la porte de qualité doit être
reproductible, testable unitairement et impossible à « charmer » par un modèle.

Si l'article est rejeté et qu'il reste des itérations disponibles, le graphe le
renvoie au Content Writer avec `state.revision_instructions`.
"""

from __future__ import annotations

import re

from ...domain.value_objects.quality_report import QualityCheck, QualityReport, Severity
from ...domain.value_objects.seo_metadata import (
    DESCRIPTION_MAX,
    DESCRIPTION_MIN,
    TITLE_MAX,
    TITLE_MIN,
    contains_keyword,
)
from ...shared.text import strip_code_blocks
from ..dto.pipeline_state import PipelineState
from .base import Agent

#: Mots grammaticaux très fréquents en français. Leur proportion dans le texte
#: est un indicateur de langue simple, robuste et sans dépendance externe.
_FRENCH_MARKERS = frozenset({
    "le", "la", "les", "un", "une", "des", "du", "de", "et", "est", "sont",
    "vous", "nous", "pour", "dans", "avec", "sur", "que", "qui", "plus",
    "pas", "ce", "cette", "ces", "son", "sa", "ses", "votre", "vos", "en",
    "au", "aux", "par", "mais", "ou", "donc", "car", "si", "quand", "comme",
    "tout", "tous", "toute", "faire", "peut", "être", "avoir", "ainsi",
})

#: Mots grammaticaux anglais, pour détecter une bascule involontaire de langue.
_ENGLISH_MARKERS = frozenset({
    "the", "and", "you", "your", "with", "this", "that", "for", "from",
    "will", "can", "have", "are", "was", "were", "they", "their", "which",
    "here", "there", "when", "what", "how", "about", "would", "should",
})

_WORD_PATTERN = re.compile(r"\b[\wÀ-ÿ']+\b", re.UNICODE)


class QualityGateAgent(Agent):
    """Checklist automatique avant publication."""

    name = "quality_gate"
    label = "Quality Gate — validation"
    critical = True

    def __init__(
        self,
        *,
        min_words: int = 1200,
        max_words: int = 2000,
        min_h2: int = 4,
        min_keyword_density: float = 0.003,
        max_keyword_density: float = 0.025,
        tunisia_terms: tuple[str, ...] = ("tunis", "tunisie", "tunisien", "dinar"),
        duplicate_threshold: float = 0.85,
    ) -> None:
        super().__init__()
        self.min_words = min_words
        self.max_words = max_words
        self.min_h2 = min_h2
        self.min_keyword_density = min_keyword_density
        self.max_keyword_density = max_keyword_density
        self.tunisia_terms = tunisia_terms
        self.duplicate_threshold = duplicate_threshold

    # ------------------------------------------------------------------ #
    def run(self, state: PipelineState) -> PipelineState:
        article = state.article
        if article is None:
            raise ValueError("Quality Gate : aucun article à valider")

        checks: list[QualityCheck] = []
        checks += self._check_language(article)
        checks += self._check_length(article)
        checks += self._check_structure(article)
        checks += self._check_keywords(article)
        checks += self._check_tunisia_angle(article)
        checks += self._check_seo(article)
        checks += self._check_originality(state)
        checks += self._check_technical_review(state)
        checks += self._check_cta(article)

        report = QualityReport(checks=tuple(checks), iteration=state.iteration)
        state.quality = report
        state.run.quality_score = report.score

        for check in checks:
            if not check.passed:
                level = "BLOQUANT" if check.is_blocking else "avertissement"
                self.logger.warning("  ✖ [%s] %s — %s", level, check.name, check.message)

        self.logger.info("Quality Gate : %s", report.summary())

        if not report.approved:
            state.revision_instructions = report.revision_instructions()
        return state

    # ------------------------------------------------------------------ #
    # Contrôles unitaires
    # ------------------------------------------------------------------ #
    @staticmethod
    def _check_language(article) -> list[QualityCheck]:
        """L'article DOIT être rédigé en français — exigence éditoriale absolue.

        Contrôle déterministe par proportion de mots grammaticaux : un texte
        français contient typiquement plus de 12 % de mots-outils français, un
        texte anglais quasiment aucun. On compare aussi au marqueur anglais pour
        détecter une bascule de langue du modèle en cours de rédaction.
        """
        text = strip_code_blocks(article.body_markdown).lower()
        words = _WORD_PATTERN.findall(text)
        total = len(words)
        if total < 50:
            return [QualityCheck("langue_francaise", False, Severity.BLOCKER,
                                 "Article trop court pour vérifier la langue.")]

        french = sum(1 for w in words if w in _FRENCH_MARKERS) / total
        english = sum(1 for w in words if w in _ENGLISH_MARKERS) / total

        return [
            QualityCheck(
                name="langue_francaise",
                passed=french >= 0.12 and french > english * 2,
                severity=Severity.BLOCKER,
                message=(
                    f"L'article ne semble pas rédigé en français "
                    f"(marqueurs FR {french:.1%}, EN {english:.1%}). "
                    f"RÉÉCRIVEZ INTÉGRALEMENT L'ARTICLE EN FRANÇAIS : titres, "
                    f"paragraphes, listes et commentaires de code compris. "
                    f"Seuls les noms d'outils et les mots-clés techniques restent en anglais."
                ),
            ),
            QualityCheck(
                name="titres_en_francais",
                passed=not any(
                    sum(1 for w in _WORD_PATTERN.findall(titre.lower()) if w in _ENGLISH_MARKERS) >= 2
                    for _, titre in article.headings
                ),
                severity=Severity.WARNING,
                message="Un ou plusieurs titres de section semblent rédigés en anglais.",
            ),
        ]

    def _check_length(self, article) -> list[QualityCheck]:
        words = article.word_count
        too_short = words < self.min_words
        too_long = words > self.max_words * 1.15  # 15 % de tolérance haute
        return [
            QualityCheck(
                name="longueur_minimale",
                passed=not too_short,
                severity=Severity.BLOCKER,
                message=f"L'article fait {words} mots, il en faut au moins {self.min_words}. "
                        f"Développez les sections existantes avec des exemples concrets.",
            ),
            QualityCheck(
                name="longueur_maximale",
                passed=not too_long,
                severity=Severity.WARNING,
                message=f"L'article fait {words} mots, au-delà de la cible de {self.max_words}. "
                        f"Resserrez les passages redondants.",
            ),
        ]

    def _check_structure(self, article) -> list[QualityCheck]:
        has_h1 = any(level == 1 for level, _ in article.headings)
        return [
            QualityCheck(
                name="sections_h2",
                passed=article.h2_count >= self.min_h2,
                severity=Severity.BLOCKER,
                message=f"Seulement {article.h2_count} section(s) ## ; il en faut au moins {self.min_h2}.",
            ),
            QualityCheck(
                name="pas_de_h1",
                passed=not has_h1,
                severity=Severity.BLOCKER,
                message="Le corps contient un titre H1 (#), ce qui duplique le titre du site. "
                        "Utilisez ## pour les sections.",
            ),
            QualityCheck(
                name="blocs_de_code_equilibres",
                passed=article.has_balanced_code_fences,
                severity=Severity.BLOCKER,
                message="Un bloc de code n'est pas fermé (nombre impair de ```), le rendu MDX casserait.",
            ),
            QualityCheck(
                name="presence_code_ou_liste",
                passed="```" in article.body_markdown or "\n- " in article.body_markdown,
                severity=Severity.WARNING,
                message="Aucun bloc de code ni liste : ajoutez un exemple concret ou une liste d'étapes.",
            ),
        ]

    def _check_keywords(self, article) -> list[QualityCheck]:
        focus = article.seo.focus_keyword
        if not focus:
            return [QualityCheck("mot_cle_defini", False, Severity.BLOCKER,
                                 "Aucun mot-clé principal n'est défini.")]

        density = article.keyword_density(focus)
        # `contains_keyword` tolère la présence des mots du mot-clé séparés (« automatiser »
        # + « n8n ») ET ignore la ponctuation qui les relie (tirets, apostrophes) : un modèle
        # écrit parfois « auto‑hébergée » avec un tiret typographique (U+2011) plutôt qu'un
        # tiret ASCII, ce qu'un simple `focus.split()` par espaces ne tolère pas.
        focus_words = _WORD_PATTERN.findall(focus.lower())

        return [
            QualityCheck(
                name="mot_cle_dans_le_corps",
                passed=contains_keyword(article.body_markdown, focus),
                severity=Severity.BLOCKER,
                message=f"Le mot-clé principal « {focus} » n'apparaît pas dans le corps de l'article.",
            ),
            QualityCheck(
                name="densite_mot_cle",
                passed=density <= self.max_keyword_density,
                severity=Severity.WARNING,
                message=f"Densité du mot-clé trop élevée ({density:.2%}) : cela ressemble à du bourrage. "
                        f"Variez les formulations.",
            ),
            QualityCheck(
                name="mot_cle_dans_un_titre",
                passed=any(
                    any(word in text.lower() for word in focus_words)
                    for _, text in article.headings
                ),
                severity=Severity.WARNING,
                message=f"Aucune section ne reprend le mot-clé « {focus} ».",
            ),
        ]

    def _check_tunisia_angle(self, article) -> list[QualityCheck]:
        text = strip_code_blocks(article.body_markdown).lower()
        occurrences = sum(text.count(term) for term in self.tunisia_terms)
        # L'angle doit apparaître tôt : on regarde les 1200 premiers caractères.
        early = any(term in text[:1200] for term in self.tunisia_terms)
        return [
            QualityCheck(
                name="angle_tunisien_present",
                passed=occurrences >= 2,
                severity=Severity.BLOCKER,
                message="L'angle tunisien est absent ou trop superficiel. Ancrez l'article dans le "
                        "contexte local : coûts en dinars, cas d'usage à Tunis/Sfax, contraintes réelles.",
            ),
            QualityCheck(
                name="angle_tunisien_en_intro",
                passed=early,
                severity=Severity.WARNING,
                message="L'angle tunisien n'apparaît pas dans l'introduction.",
            ),
        ]

    def _check_seo(self, article) -> list[QualityCheck]:
        seo = article.seo
        title_len, desc_len = len(seo.meta_title), len(seo.meta_description)
        return [
            QualityCheck(
                name="meta_title_longueur",
                passed=TITLE_MIN <= title_len <= TITLE_MAX,
                severity=Severity.WARNING,
                message=f"meta_title de {title_len} caractères (cible {TITLE_MIN}-{TITLE_MAX}).",
            ),
            QualityCheck(
                name="meta_description_longueur",
                passed=DESCRIPTION_MIN <= desc_len <= DESCRIPTION_MAX,
                severity=Severity.WARNING,
                message=f"meta_description de {desc_len} caractères (cible {DESCRIPTION_MIN}-{DESCRIPTION_MAX}).",
            ),
            QualityCheck(
                name="meta_description_presente",
                passed=desc_len > 0,
                severity=Severity.BLOCKER,
                message="La meta description est vide.",
            ),
        ]

    def _check_originality(self, state: PipelineState) -> list[QualityCheck]:
        topic = state.topic
        if topic is None:
            return []
        return [
            QualityCheck(
                name="originalite_sujet",
                passed=not topic.is_duplicate(self.duplicate_threshold),
                severity=Severity.BLOCKER,
                message=f"Le sujet est trop proche de l'article « {topic.similar_slug} » "
                        f"({topic.similarity_score:.0%} de similarité).",
            )
        ]

    @staticmethod
    def _check_technical_review(state: PipelineState) -> list[QualityCheck]:
        review = state.review
        if review is None:
            return [QualityCheck("relecture_technique", True, Severity.WARNING,
                                 "Relecture technique non effectuée.")]
        blocking = review.blocking_findings
        return [
            QualityCheck(
                name="relecture_technique",
                passed=not blocking,
                severity=Severity.BLOCKER,
                message="Le relecteur technique a relevé des erreurs bloquantes :\n"
                        + "\n".join(f"  · {f.as_instruction()}" for f in blocking),
            ),
            QualityCheck(
                name="liens_valides",
                passed=not review.broken_urls,
                severity=Severity.WARNING,
                message="Liens morts à remplacer : " + ", ".join(review.broken_urls[:5]),
            ),
        ]

    @staticmethod
    def _check_cta(article) -> list[QualityCheck]:
        text = article.body_markdown.lower()
        has_cta = "youtube" in text or "chaîne" in text or "chaine" in text
        return [
            QualityCheck(
                name="appel_a_action",
                passed=has_cta,
                severity=Severity.WARNING,
                message="Aucun appel à l'action vers la chaîne YouTube en fin d'article.",
            )
        ]

    def describe(self, state: PipelineState) -> str:
        return state.quality.summary() if state.quality else "non évalué"
