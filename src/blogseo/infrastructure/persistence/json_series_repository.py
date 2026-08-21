"""Persistance des séries d'articles en JSON (un fichier par série)."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from ...domain.entities.series import ArticleSeries, SeriesTopic
from ...domain.ports.repositories import SeriesRepositoryPort
from ...domain.value_objects.category import Category

logger = logging.getLogger(__name__)


class JsonSeriesRepository(SeriesRepositoryPort):
    """Stockage fichier des `ArticleSeries`, sous `storage/series/`."""

    def __init__(self, series_dir: Path) -> None:
        self.series_dir = series_dir
        self.series_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, series_id: str) -> Path:
        return self.series_dir / f"{series_id}.json"

    # ------------------------------------------------------------------ #
    def save(self, series: ArticleSeries) -> None:
        payload = {
            "series_id": series.series_id,
            "theme": series.theme,
            "title": series.title,
            "created_at": series.created_at.isoformat(),
            "topics": [
                {
                    "title": t.title,
                    "angle": t.angle,
                    "category": t.category.value,
                    "primary_keyword": t.primary_keyword,
                    "secondary_keywords": list(t.secondary_keywords),
                    "outline": list(t.outline),
                    "rationale": t.rationale,
                    "status": t.status,
                    "slug": t.slug,
                }
                for t in series.topics
            ],
        }
        try:
            self._path(series.series_id).write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError as exc:
            logger.error("Impossible d'enregistrer la série %s : %s", series.series_id, exc)

    def get(self, series_id: str) -> ArticleSeries | None:
        path = self._path(series_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            logger.error("Série %s illisible : %s", series_id, exc)
            return None
        return self._to_entity(data)

    def find_active(self) -> ArticleSeries | None:
        candidates = sorted(self._load_all(), key=lambda s: s.created_at, reverse=True)
        for series in candidates:
            if series.is_active:
                return series
        return None

    def list_all(self) -> list[ArticleSeries]:
        return sorted(self._load_all(), key=lambda s: s.created_at, reverse=True)

    # ------------------------------------------------------------------ #
    def _load_all(self) -> list[ArticleSeries]:
        series: list[ArticleSeries] = []
        for path in self.series_dir.glob("*.json"):
            try:
                series.append(self._to_entity(json.loads(path.read_text(encoding="utf-8"))))
            except (OSError, ValueError, KeyError) as exc:
                logger.debug("Série ignorée (%s) : %s", path.name, exc)
        return series

    @staticmethod
    def _to_entity(data: dict) -> ArticleSeries:
        return ArticleSeries(
            series_id=data["series_id"],
            theme=data.get("theme", ""),
            title=data.get("title", ""),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(),
            topics=[
                SeriesTopic(
                    title=t["title"],
                    angle=t.get("angle", ""),
                    category=Category.coerce(t.get("category")),
                    primary_keyword=t.get("primary_keyword", ""),
                    secondary_keywords=tuple(t.get("secondary_keywords", [])),
                    outline=tuple(t.get("outline", [])),
                    rationale=t.get("rationale", ""),
                    status=t.get("status", "pending"),
                    slug=t.get("slug", ""),
                )
                for t in data.get("topics", [])
            ],
        )
