"""Tableau de bord HTML statique généré depuis `storage/runs/*.json`.

Page auto-suffisante (CSS + `<details>` natif, aucun JS ni dépendance
externe) : elle s'ouvre directement dans un navigateur via `file://`, sans
serveur local. Voir `cmd_dashboard` dans `cli.py`.
"""

from __future__ import annotations

import html
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean

from ..domain.entities.pipeline_run import Decision, PipelineRun, RunStatus

#: Libellé + classe CSS par statut de run.
_STATUS_LABELS: dict[RunStatus, tuple[str, str]] = {
    RunStatus.PUBLISHED: ("✅ Publié", "ok"),
    RunStatus.SAVED_LOCALLY: ("💾 En local", "warn"),
    RunStatus.AWAITING_REVIEW: ("⏳ En attente", "warn"),
    RunStatus.FAILED: ("✖ Échec", "fail"),
    RunStatus.DISCARDED: ("🗑 Rejeté", "warn"),
    RunStatus.RUNNING: ("▶ En cours", "warn"),
}

_DECISION_LABELS: dict[Decision, str] = {
    Decision.APPROVE: "✅ Publier",
    Decision.REJECT: "❌ Local",
    Decision.REWRITE: "🔁 Réécrire",
}


def _esc(text: str) -> str:
    return html.escape(str(text), quote=True)


def _fmt_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.0f}s"
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes}min{secs:02d}s"


def _fmt_date(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M")


# --------------------------------------------------------------------------- #
def _kpis(runs: list[PipelineRun]) -> dict[str, str]:
    total = len(runs)
    published = sum(1 for r in runs if r.status is RunStatus.PUBLISHED)
    saved_locally = sum(1 for r in runs if r.status is RunStatus.SAVED_LOCALLY)
    failed = sum(1 for r in runs if r.status is RunStatus.FAILED)
    scored = [r.quality_score for r in runs if r.quality_score > 0]
    finished = [r.duration_s for r in runs if r.finished_at]

    return {
        "total": str(total),
        "published": str(published),
        "saved_locally": str(saved_locally),
        "failed": str(failed),
        "avg_quality": f"{mean(scored):.0%}" if scored else "—",
        "avg_duration": _fmt_duration(mean(finished)) if finished else "—",
    }


def _duration_by_agent(runs: list[PipelineRun]) -> list[tuple[str, float, int]]:
    """Durée moyenne par agent, triée du plus lent au plus rapide."""
    by_name: dict[str, list[float]] = {}
    for run in runs:
        for step in run.steps:
            if step.finished_at:
                by_name.setdefault(step.name, []).append(step.duration_s)
    rows = [(name, mean(values), len(values)) for name, values in by_name.items()]
    rows.sort(key=lambda row: row[1], reverse=True)
    return rows


# --------------------------------------------------------------------------- #
def _render_kpi_cards(kpis: dict[str, str]) -> str:
    cards = [
        ("Runs", kpis["total"], ""),
        ("Publiés", kpis["published"], "ok"),
        ("En local", kpis["saved_locally"], "warn" if kpis["saved_locally"] != "0" else ""),
        ("Échecs", kpis["failed"], "fail" if kpis["failed"] != "0" else ""),
        ("Qualité moyenne", kpis["avg_quality"], ""),
        ("Durée moyenne", kpis["avg_duration"], ""),
    ]
    return "\n".join(
        f'<div class="card {css}"><div class="card-value">{_esc(value)}</div>'
        f'<div class="card-label">{_esc(label)}</div></div>'
        for label, value, css in cards
    )


def _render_agent_durations(rows: list[tuple[str, float, int]]) -> str:
    if not rows:
        return "<p class=\"empty\">Aucune donnée.</p>"
    max_duration = max(r[1] for r in rows) or 1.0
    lines = []
    for name, avg_s, count in rows:
        width = round(100 * avg_s / max_duration, 1)
        lines.append(
            '<div class="bar-row">'
            f'<span class="bar-label">{_esc(name)}</span>'
            f'<span class="bar-track"><span class="bar-fill" style="width:{width}%"></span></span>'
            f'<span class="bar-value">{_fmt_duration(avg_s)} · {count} run(s)</span>'
            "</div>"
        )
    return "\n".join(lines)


def _render_run_row(run: PipelineRun) -> str:
    label, css = _STATUS_LABELS.get(run.status, (run.status.value, ""))
    decision = _DECISION_LABELS.get(run.decision, "—") if run.decision else "—"
    highlight = " class=\"row-fail\"" if run.status is RunStatus.FAILED else (
        " class=\"row-warn\"" if run.status is RunStatus.SAVED_LOCALLY else ""
    )

    steps_rows = "\n".join(
        f'<tr class="{"" if step.ok else "row-fail"}">'
        f"<td>{_esc(step.name)}</td>"
        f'<td>{"✔" if step.ok else "✖"}</td>'
        f"<td>{_fmt_duration(step.duration_s)}</td>"
        f"<td>{_esc(step.detail)}</td>"
        "</tr>"
        for step in run.steps
    ) or '<tr><td colspan="4" class="empty">Aucune étape enregistrée.</td></tr>'

    errors = (
        '<p class="errors">' + "<br>".join(_esc(e) for e in run.errors) + "</p>"
        if run.errors else ""
    )

    return f"""
<tr{highlight}>
  <td>{_fmt_date(run.started_at)}</td>
  <td>{_esc(run.topic_title) or '<span class="empty">—</span>'}</td>
  <td><span class="badge badge-{css}">{label}</span></td>
  <td>{decision}</td>
  <td>{run.quality_score:.0%}</td>
  <td>{_fmt_duration(run.duration_s)}</td>
  <td>
    <details>
      <summary>{len(run.steps)} étape(s)</summary>
      <table class="steps">
        <thead><tr><th>Agent</th><th></th><th>Durée</th><th>Détail</th></tr></thead>
        <tbody>{steps_rows}</tbody>
      </table>
      {errors}
    </details>
  </td>
</tr>"""


_CSS = """
:root {
  color-scheme: light dark;
  --bg: #f7f7f8; --surface: #ffffff; --border: #e2e2e6;
  --text: #1c1c1f; --muted: #6b6b74;
  --ok: #1a7f4e; --ok-bg: #e6f6ee;
  --warn: #9a6400; --warn-bg: #fdf3dc;
  --fail: #b3261e; --fail-bg: #fceeed;
  --accent: #3a5bd9;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #17181c; --surface: #1f2024; --border: #2f3036;
    --text: #eaeaee; --muted: #9a9aa2;
    --ok: #4ade95; --ok-bg: #163326;
    --warn: #f0b752; --warn-bg: #3a2e10;
    --fail: #f18b85; --fail-bg: #3a1a18;
    --accent: #7d97f4;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0; padding: 2rem 1.5rem 4rem; background: var(--bg); color: var(--text);
  font: 15px/1.5 -apple-system, "Segoe UI", Roboto, sans-serif;
}
h1 { font-size: 1.4rem; margin: 0 0 0.25rem; }
.subtitle { color: var(--muted); margin: 0 0 1.75rem; font-size: 0.9rem; }
.container { max-width: 1100px; margin: 0 auto; }
.cards {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 0.75rem; margin-bottom: 2rem;
}
.card {
  background: var(--surface); border: 1px solid var(--border); border-radius: 10px;
  padding: 0.9rem 1rem;
}
.card-value { font-size: 1.6rem; font-weight: 600; }
.card-label { color: var(--muted); font-size: 0.8rem; margin-top: 0.15rem; }
.card.ok .card-value { color: var(--ok); }
.card.warn .card-value { color: var(--warn); }
.card.fail .card-value { color: var(--fail); }
section { margin-bottom: 2.25rem; }
h2 { font-size: 1rem; margin: 0 0 0.9rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.03em; }
.bar-row { display: flex; align-items: center; gap: 0.75rem; margin-bottom: 0.5rem; font-size: 0.85rem; }
.bar-label { width: 140px; flex-shrink: 0; }
.bar-track { flex: 1; background: var(--border); border-radius: 4px; height: 10px; overflow: hidden; }
.bar-fill { display: block; height: 100%; background: var(--accent); border-radius: 4px; }
.bar-value { width: 150px; flex-shrink: 0; color: var(--muted); text-align: right; }
table { width: 100%; border-collapse: collapse; background: var(--surface); border: 1px solid var(--border); border-radius: 10px; overflow: hidden; }
th, td { text-align: left; padding: 0.6rem 0.75rem; border-bottom: 1px solid var(--border); font-size: 0.85rem; vertical-align: top; }
thead th { color: var(--muted); font-weight: 600; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.02em; }
tbody tr:last-child td { border-bottom: none; }
tr.row-fail { background: var(--fail-bg); }
tr.row-warn { background: var(--warn-bg); }
.badge { display: inline-block; padding: 0.15rem 0.5rem; border-radius: 999px; font-size: 0.78rem; white-space: nowrap; }
.badge-ok { background: var(--ok-bg); color: var(--ok); }
.badge-warn { background: var(--warn-bg); color: var(--warn); }
.badge-fail { background: var(--fail-bg); color: var(--fail); }
.badge- { background: var(--border); color: var(--muted); }
details summary { cursor: pointer; color: var(--accent); font-size: 0.82rem; }
table.steps { margin-top: 0.6rem; box-shadow: none; }
table.steps th, table.steps td { font-size: 0.78rem; padding: 0.4rem 0.6rem; }
.errors { color: var(--fail); font-size: 0.8rem; margin: 0.5rem 0 0; }
.empty { color: var(--muted); font-style: italic; }
footer { margin-top: 2.5rem; color: var(--muted); font-size: 0.78rem; text-align: center; }
"""


def render_dashboard(runs: list[PipelineRun]) -> str:
    """Génère la page HTML complète pour la liste de runs donnée."""
    runs = sorted(runs, key=lambda r: r.started_at, reverse=True)
    kpis = _kpis(runs)
    agent_rows = _duration_by_agent(runs)
    generated_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

    runs_table = "\n".join(_render_run_row(r) for r in runs) or (
        '<tr><td colspan="7" class="empty">Aucun run enregistré pour l\'instant.</td></tr>'
    )

    return f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Tableau de bord — blogseo-agents</title>
<style>{_CSS}</style>
</head>
<body>
<div class="container">
  <h1>Tableau de bord — blogseo-agents</h1>
  <p class="subtitle">Généré le {generated_at} · {len(runs)} run(s)</p>

  <div class="cards">
    {_render_kpi_cards(kpis)}
  </div>

  <section>
    <h2>Durée moyenne par agent</h2>
    {_render_agent_durations(agent_rows)}
  </section>

  <section>
    <h2>Historique des runs</h2>
    <table>
      <thead>
        <tr><th>Date</th><th>Sujet</th><th>Statut</th><th>Décision</th><th>Qualité</th><th>Durée</th><th>Étapes</th></tr>
      </thead>
      <tbody>
        {runs_table}
      </tbody>
    </table>
  </section>

  <footer>Généré localement par <code>blogseo dashboard</code> — aucune donnée n'a quitté cette machine.</footer>
</div>
</body>
</html>
"""


def write_dashboard(runs: list[PipelineRun], output_path: Path) -> Path:
    """Écrit la page sur disque et renvoie le chemin final."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_dashboard(runs), encoding="utf-8")
    return output_path
