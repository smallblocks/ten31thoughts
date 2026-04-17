"""
Tests for the v3 connection-first scheduler job.
Verifies routing, batch limits, error handling, and no-op behaviour.
"""

import types
from unittest.mock import MagicMock, patch, call

import pytest

from src.db.models import AnalysisStatus, FeedCategory


# ── Helpers ──────────────────────────────────────────────────────────────

def _make_item(item_id: str, category: FeedCategory):
    """Return a lightweight mock ContentItem with a parent Feed."""
    feed = MagicMock()
    feed.category = category

    item = MagicMock()
    item.item_id = item_id
    item.feed = feed
    item.analysis_status = AnalysisStatus.PENDING
    return item


# ── Fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _reset_scheduler_module():
    """Ensure a clean import of the scheduler module for each test."""
    import importlib
    import src.worker.scheduler as mod
    yield
    importlib.reload(mod)


@pytest.fixture()
def job_env():
    """
    Set up the scheduler module with mock ConnectionAnalyzer / NoteExtractor
    injected and return helpers for assertions.
    """
    import src.worker.scheduler as mod

    mock_analyzer_cls = MagicMock()
    mock_extractor_cls = MagicMock()
    mod.ConnectionAnalyzer = mock_analyzer_cls
    mod.NoteExtractor = mock_extractor_cls

    mock_session = MagicMock()
    mock_llm = MagicMock()

    with patch.object(mod, "_get_session", return_value=mock_session), \
         patch("src.llm.router.LLMRouter", return_value=mock_llm):
        yield types.SimpleNamespace(
            mod=mod,
            analyzer_cls=mock_analyzer_cls,
            extractor_cls=mock_extractor_cls,
            session=mock_session,
            llm=mock_llm,
        )


def _set_pending(ns, items):
    """Configure the mock session to return `items` from the pending query."""
    ns.session.query.return_value.filter.return_value.limit.return_value.all.return_value = items


# ── Tests ────────────────────────────────────────────────────────────────

def test_routes_external_to_connection_pass(job_env):
    """External-category items should be routed to ConnectionAnalyzer."""
    item = _make_item("ext-1", FeedCategory.EXTERNAL_INTERVIEW)
    _set_pending(job_env, [item])

    job_env.mod.process_connection_job()

    job_env.analyzer_cls.assert_called_once()
    job_env.analyzer_cls.return_value.analyze.assert_called_once_with("ext-1")
    job_env.extractor_cls.assert_not_called()


def test_routes_our_thesis_to_note_extractor(job_env):
    """OUR_THESIS items should be routed to NoteExtractor."""
    item = _make_item("thesis-1", FeedCategory.OUR_THESIS)
    _set_pending(job_env, [item])

    job_env.mod.process_connection_job()

    job_env.extractor_cls.assert_called_once()
    job_env.extractor_cls.return_value.extract.assert_called_once_with("thesis-1")
    job_env.analyzer_cls.assert_not_called()


def test_skips_non_pending(job_env):
    """When the DB returns no pending items, neither analyzer should be invoked."""
    _set_pending(job_env, [])

    job_env.mod.process_connection_job()

    job_env.analyzer_cls.assert_not_called()
    job_env.extractor_cls.assert_not_called()


def test_handles_analyzer_error(job_env):
    """If the analyzer raises, the item should be marked ERROR and the job should not crash."""
    item = _make_item("err-1", FeedCategory.EXTERNAL_INTERVIEW)
    job_env.analyzer_cls.return_value.analyze.side_effect = RuntimeError("LLM exploded")
    _set_pending(job_env, [item])

    # Should not raise
    job_env.mod.process_connection_job()

    assert item.analysis_status == AnalysisStatus.ERROR
    job_env.session.commit.assert_called()


def test_limits_batch_size(job_env):
    """The query should use .limit(20)."""
    items = [
        _make_item(f"item-{i}", FeedCategory.EXTERNAL_INTERVIEW)
        for i in range(20)
    ]
    _set_pending(job_env, items)

    job_env.mod.process_connection_job()

    # Verify .limit(20) was called
    job_env.session.query.return_value.filter.return_value.limit.assert_called_with(20)
    assert job_env.analyzer_cls.return_value.analyze.call_count == 20


def test_no_pending_is_noop(job_env):
    """No pending items → no LLMRouter instantiation, clean return."""
    _set_pending(job_env, [])

    job_env.mod.process_connection_job()

    job_env.analyzer_cls.assert_not_called()
    job_env.extractor_cls.assert_not_called()
