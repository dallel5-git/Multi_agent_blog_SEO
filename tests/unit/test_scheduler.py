"""Tests unitaires du planificateur hebdomadaire (`blogseo.interfaces.scheduler`).

Vérifie :
- L'intervalle de déclenchement hebdomadaire (168 h / 7 jours) ;
- La configuration du job APScheduler (coalesce, max_instances, trigger) ;
- L'exécution de `run_once` ;
- Le fonctionnement du repli en boucle naïve `_naive_loop`.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from blogseo.interfaces import scheduler


def test_interval_hours_est_hebdomadaire():
    """L'intervalle doit correspondre exactement à 7 jours (168 h)."""
    assert scheduler.INTERVAL_HOURS == 168
    assert scheduler.INTERVAL_HOURS == 7 * 24


def test_run_once_execute_le_use_case(monkeypatch):
    mock_use_case_cls = MagicMock()
    mock_use_case_instance = MagicMock()
    mock_use_case_cls.return_value = mock_use_case_instance
    mock_state = MagicMock()
    mock_state.run.summary.return_value = "Run OK"
    mock_use_case_instance.execute.return_value = mock_state

    monkeypatch.setattr(
        "blogseo.interfaces.scheduler.GenerateArticleUseCase",
        mock_use_case_cls,
    )
    monkeypatch.setattr(
        "blogseo.interfaces.scheduler.Container",
        MagicMock(),
    )
    monkeypatch.setattr(
        "blogseo.interfaces.scheduler.Settings",
        MagicMock(),
    )

    scheduler.run_once(dry_run=True)

    mock_use_case_instance.execute.assert_called_once_with(dry_run=True)


def test_start_configure_apscheduler_avec_intervalle_7_jours(monkeypatch):
    mock_scheduler_cls = MagicMock()
    mock_scheduler_instance = MagicMock()
    mock_scheduler_cls.return_value = mock_scheduler_instance

    mock_trigger_cls = MagicMock()

    monkeypatch.setattr(
        "blogseo.interfaces.scheduler.Settings",
        MagicMock(),
    )
    monkeypatch.setattr(
        "blogseo.interfaces.scheduler.setup_logging",
        MagicMock(),
    )

    with patch.dict("sys.modules", {
        "apscheduler.schedulers.blocking": MagicMock(BlockingScheduler=mock_scheduler_cls),
        "apscheduler.triggers.interval": MagicMock(IntervalTrigger=mock_trigger_cls),
    }):
        mock_scheduler_instance.start.side_effect = None

        code = scheduler.start(dry_run=False, run_immediately=False)

        assert code == 0
        mock_scheduler_instance.add_job.assert_called_once()
        _, kwargs = mock_scheduler_instance.add_job.call_args
        assert kwargs["id"] == "blogseo_pipeline"
        assert kwargs["max_instances"] == 1
        assert kwargs["coalesce"] is True
        assert kwargs["misfire_grace_time"] == 3600
        assert "7 jours" in kwargs["name"]

        mock_trigger_cls.assert_called_once()
        assert mock_trigger_cls.call_args[1]["hours"] == 168


def test_naive_loop_execute_puis_leve_interruption(monkeypatch):
    mock_run_once = MagicMock()
    monkeypatch.setattr("blogseo.interfaces.scheduler.run_once", mock_run_once)

    monkeypatch.setattr("time.sleep", MagicMock(side_effect=KeyboardInterrupt))

    with pytest.raises(KeyboardInterrupt):
        scheduler._naive_loop(dry_run=True, run_immediately=True)

    mock_run_once.assert_called_once_with(dry_run=True)
