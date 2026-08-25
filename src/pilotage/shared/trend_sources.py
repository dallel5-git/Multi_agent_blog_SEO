"""Veille technique gratuite, partagée par les 6 pipelines (CADRAGE.md décision
11 : « mêmes sources que le blog » — Hacker News, Reddit, dev.to, RSS Tunisie).

Réimplémenté en REST brut ici plutôt qu'importé de
`blogseo.infrastructure.sources` : la règle d'isolation interdit `pilotage`
→ `blogseo`, et ces adapters ne font que quelques lignes chacun.

Chaque source est isolée : une panne HTTP renvoie `[]`, elle ne remonte
jamais. `collect_trends()` peut donc tourner même si toutes les sources sont
mortes — c'est `PlatformPipeline._safe_watch()` qui rattrape le cas où
`collect_trends()` lèverait quand même une exception imprévue.
"""

from __future__ import annotations

import logging
import re

import requests

from ..pipelines.base import TrendItem

logger = logging.getLogger(__name__)

_TIMEOUT_S = 20
_USER_AGENT = "pilotage/1.0 (+https://github.com/dallel5-git/Multi_agent_blog_SEO)"

# Mêmes mots-clés que `blogseo.infrastructure.sources.hackernews` : on ne
# garde que ce qui recoupe la niche IA/automatisation/productivité.
_RELEVANT_TERMS = (
    "ai", "llm", "gpt", "agent", "automation", "workflow", "n8n", "make.com",
    "python", "rag", "prompt", "openai", "gemini", "claude", "langchain",
    "no-code", "nocode", "self-host", "vector", "embedding", "mcp", "copilot",
)

# Limite de mot obligatoire : un simple test de sous-chaîne fait matcher "ai"
# à l'intérieur de "paint", "main", "domain"... (constaté en conditions
# réelles — un signal Hacker News sur MS Paint est passé le filtre à cause
# de "paint" et de "main" dans l'URL).
_RELEVANT_PATTERN = re.compile(
    r"\b(?:" + "|".join(re.escape(term) for term in _RELEVANT_TERMS) + r")\b",
    re.IGNORECASE,
)

_REDDIT_SUBREDDITS = ("artificial", "LocalLLaMA", "n8n", "automation", "AI_Agents")
_DEVTO_TAGS = ("ai", "automation", "python")
_TUNISIA_RSS_FEEDS = (
    "https://www.tekiano.com/feed/",
    "https://www.leconomistemaghrebin.com/tag/startup/feed/",
)


def _is_relevant(title: str, url: str = "") -> bool:
    return bool(_RELEVANT_PATTERN.search(f"{title} {url}"))


def _fetch_hackernews(limit: int) -> list[TrendItem]:
    try:
        response = requests.get(
            "https://hacker-news.firebaseio.com/v0/topstories.json",
            timeout=_TIMEOUT_S,
            headers={"User-Agent": _USER_AGENT},
        )
        response.raise_for_status()
        story_ids = response.json()[: limit * 5]
    except (requests.RequestException, ValueError) as exc:
        logger.warning("Hacker News injoignable : %s", exc)
        return []

    items: list[TrendItem] = []
    for story_id in story_ids:
        if len(items) >= limit:
            break
        try:
            story_response = requests.get(
                f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json",
                timeout=_TIMEOUT_S,
                headers={"User-Agent": _USER_AGENT},
            )
            story_response.raise_for_status()
            story = story_response.json() or {}
        except (requests.RequestException, ValueError):
            continue
        title = story.get("title", "")
        if not _is_relevant(title, story.get("url", "")):
            continue
        items.append(
            TrendItem(
                title=title.strip(),
                url=story.get("url") or f"https://news.ycombinator.com/item?id={story_id}",
                source="Hacker News",
                summary=f"{story.get('descendants', 0)} commentaires",
                score=float(story.get("score", 0)),
            )
        )
    return items


def _fetch_reddit(limit: int) -> list[TrendItem]:
    items: list[TrendItem] = []
    per_sub = max(2, limit // max(1, len(_REDDIT_SUBREDDITS)) + 1)
    for subreddit in _REDDIT_SUBREDDITS:
        try:
            response = requests.get(
                f"https://www.reddit.com/r/{subreddit}/hot.json",
                params={"limit": per_sub, "t": "week"},
                timeout=_TIMEOUT_S,
                headers={"User-Agent": _USER_AGENT},
            )
            if response.status_code >= 400:
                logger.warning("Reddit r/%s → HTTP %s", subreddit, response.status_code)
                continue
            children = response.json().get("data", {}).get("children", [])
        except (requests.RequestException, ValueError) as exc:
            logger.warning("Reddit r/%s injoignable : %s", subreddit, exc)
            continue

        for child in children:
            data = child.get("data", {})
            if data.get("stickied") or data.get("over_18"):
                continue
            items.append(
                TrendItem(
                    title=(data.get("title") or "").strip(),
                    url=f"https://www.reddit.com{data.get('permalink', '')}",
                    source=f"r/{subreddit}",
                    summary=(data.get("selftext") or "")[:200],
                    score=float(data.get("ups", 0)),
                )
            )
    items.sort(key=lambda item: item.score, reverse=True)
    return items[:limit]


def _fetch_devto(limit: int) -> list[TrendItem]:
    items: list[TrendItem] = []
    per_tag = max(2, limit // max(1, len(_DEVTO_TAGS)) + 1)
    for tag in _DEVTO_TAGS:
        try:
            response = requests.get(
                "https://dev.to/api/articles",
                params={"tag": tag, "top": 7, "per_page": per_tag},
                timeout=_TIMEOUT_S,
                headers={"User-Agent": _USER_AGENT},
            )
            if response.status_code >= 400:
                logger.warning("dev.to tag=%s → HTTP %s", tag, response.status_code)
                continue
            articles = response.json()
        except (requests.RequestException, ValueError) as exc:
            logger.warning("dev.to tag=%s injoignable : %s", tag, exc)
            continue

        for article in articles:
            items.append(
                TrendItem(
                    title=(article.get("title") or "").strip(),
                    url=article.get("url", ""),
                    source=f"dev.to/{tag}",
                    summary=(article.get("description") or "").strip()[:200],
                    score=float(article.get("positive_reactions_count", 0)),
                )
            )
    items.sort(key=lambda item: item.score, reverse=True)
    return items[:limit]


def _fetch_tunisia_rss(limit: int) -> list[TrendItem]:
    from xml.etree import ElementTree

    items: list[TrendItem] = []
    for feed_url in _TUNISIA_RSS_FEEDS:
        try:
            response = requests.get(feed_url, timeout=_TIMEOUT_S, headers={"User-Agent": _USER_AGENT})
            if response.status_code >= 400:
                logger.warning("Flux %s → HTTP %s", feed_url, response.status_code)
                continue
            root = ElementTree.fromstring(response.content)
        except (requests.RequestException, ElementTree.ParseError) as exc:
            logger.warning("Flux %s illisible : %s", feed_url, exc)
            continue

        for entry in root.findall(".//item")[:limit]:
            title = (entry.findtext("title") or "").strip()
            link = (entry.findtext("link") or "").strip()
            if not title:
                continue
            items.append(TrendItem(title=title, url=link or feed_url, source="RSS Tunisie"))
    return items[:limit]


def collect_trends(*, limit: int = 15, offline: bool = False, label: str = "pilotage") -> list[TrendItem]:
    """Agrège HN, Reddit, dev.to et le RSS tunisien, filtrés sur la niche.

    `offline=True` court-circuite tout appel réseau et renvoie `[]` : c'est
    ce qui permet à un pipeline de tourner sans réseau ni clé. `label` ne
    sert qu'au journal, pour distinguer quelle plateforme a déclenché l'appel.
    """
    if offline:
        return []

    items: list[TrendItem] = []
    items.extend(_fetch_hackernews(limit))
    items.extend(_fetch_reddit(limit))
    items.extend(_fetch_devto(limit))
    items.extend(_fetch_tunisia_rss(limit))

    logger.info("%s signal(aux) collecté(s) pour %s", len(items), label)
    return items
