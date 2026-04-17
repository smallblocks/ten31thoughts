"""
Tests for v3 cleanup — verifies deleted routes return 404, kept routes work,
episodes endpoint is simplified, chat context has no frameworks/convergence,
and app starts without ImportError.
"""

import importlib
import pytest
from unittest.mock import patch, MagicMock


# ─── Test 1: Deleted routes return 404 ───

def test_deleted_routes_return_404():
    """Routes for markets, daily-brief, convergence (except principles) must 404."""
    from fastapi.testclient import TestClient
    from src.app import app

    client = TestClient(app, raise_server_exceptions=False)

    deleted_routes = [
        "/api/markets/",
        "/api/markets/predictions",
        "/api/daily-brief/",
        "/api/daily-brief/latest",
        "/api/convergence/scorecard",
        "/api/convergence/blind-spots/summary",
        "/api/convergence/blind-spots/systematic",
        "/api/convergence/narratives",
        "/api/convergence/narratives/summary",
    ]

    for route in deleted_routes:
        resp = client.get(route)
        assert resp.status_code == 404, f"Expected 404 for {route}, got {resp.status_code}"


# ─── Test 2: Kept routes still work ───

def test_kept_routes_still_work():
    """Core routes should still return 200."""
    from fastapi.testclient import TestClient
    from src.app import app

    client = TestClient(app, raise_server_exceptions=False)

    kept_routes = [
        "/api/health",
        "/api/principles/",
        "/api/principles/domains",
    ]

    for route in kept_routes:
        resp = client.get(route)
        assert resp.status_code == 200, f"Expected 200 for {route}, got {resp.status_code}"


def test_health_returns_v3():
    """Health check should report version 3.0.0."""
    from fastapi.testclient import TestClient
    from src.app import app

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["version"] == "3.0.0"


# ─── Test 3: Episodes endpoint simplified ───

def test_episodes_endpoint_simplified():
    """Episodes endpoint should return basic listing without reasoning maps."""
    from fastapi.testclient import TestClient
    from src.app import app

    client = TestClient(app, raise_server_exceptions=False)

    # The list endpoint should work (may return empty list with no DB data)
    resp = client.get("/api/episodes/")
    # Should be 200 (or 500 if no DB — but route should exist)
    assert resp.status_code in (200, 500), f"Expected 200/500 for /api/episodes/, got {resp.status_code}"

    # The reasoning-map endpoint should NOT exist
    resp = client.get("/api/episodes/fake-id/reasoning-map")
    assert resp.status_code == 404, "reasoning-map endpoint should be removed"

    # Guest-specific endpoints should NOT exist as dedicated routes.
    # /api/episodes/guests may hit the /{item_id} catch-all and return 404 or 500,
    # but the dedicated guest listing/scorecard endpoints are gone.
    resp = client.get("/api/episodes/guests/by-topic/fed_policy")
    assert resp.status_code == 404, "guest by-topic endpoint should be removed"

    resp = client.get("/api/episodes/guests/test-guest/scorecard")
    assert resp.status_code == 404, "guest scorecard endpoint should be removed"


# ─── Test 4: Chat context has no frameworks/convergence/predictions ───

def test_chat_context_no_frameworks():
    """ContextBuilder should only query notes, connections, and content — not frameworks."""
    from src.api.chat import ContextBuilder

    # Verify the class doesn't have methods for frameworks, blind spots, etc.
    builder_source = importlib.import_module("src.api.chat")
    source_code = open(builder_source.__file__).read()

    # Should NOT reference these deprecated concepts
    assert "search_frameworks" not in source_code, "Chat should not reference search_frameworks"
    assert "search_blind_spots" not in source_code, "Chat should not reference search_blind_spots"
    assert "search_thesis_elements" not in source_code, "Chat should not reference search_thesis_elements"
    assert "WeeklyBriefing" not in source_code, "Chat should not reference WeeklyBriefing"
    assert "_get_scorecard_context" not in source_code, "Chat should not have scorecard context"
    assert "_get_latest_briefing_context" not in source_code, "Chat should not have briefing context"

    # SHOULD reference these v3 concepts
    assert "search_notes" in source_code, "Chat should use search_notes"
    assert "search_connections" in source_code, "Chat should use search_connections"
    assert "search_content" in source_code, "Chat should use search_content"


# ─── Test 5: App imports clean (no ImportError) ───

def test_app_imports_clean():
    """The app module should import without errors — no dangling imports."""
    # Force reimport to catch any stale references
    try:
        import src.app
        importlib.reload(src.app)
    except ImportError as e:
        pytest.fail(f"App has dangling imports: {e}")
    except Exception as e:
        # Other errors (like missing DB) are fine — we're only checking imports
        if "import" in str(e).lower() or "module" in str(e).lower():
            pytest.fail(f"App has import-related error: {e}")


def test_deleted_modules_not_importable():
    """Deleted modules should not be importable."""
    deleted_modules = [
        "src.analysis.external_passes",
        "src.analysis.thesis_passes",
        "src.analysis.first_principles",
        "src.synthesis.frameworks",
        "src.synthesis.daily_brief",
        "src.convergence.alignment",
        "src.convergence.validation",
        "src.convergence.blindspots",
        "src.convergence.narrative",
        "src.markets",
        "src.markets.elo",
        "src.markets.matcher",
        "src.markets.resolver",
        "src.api.markets",
        "src.api.daily_brief",
        "src.api.convergence",
    ]

    for mod in deleted_modules:
        try:
            importlib.import_module(mod)
            pytest.fail(f"Deleted module {mod} is still importable")
        except (ImportError, ModuleNotFoundError):
            pass  # Expected


def test_classical_reference_still_accessible():
    """The classical reference library should still be importable and functional."""
    from src.analysis.classical_reference import (
        CLASSICAL_DOMAINS, ALL_PRINCIPLES, get_principles_for_topic
    )

    assert len(CLASSICAL_DOMAINS) > 0, "Should have classical domains"
    assert len(ALL_PRINCIPLES) > 0, "Should have principles"

    # Test topic lookup
    result = get_principles_for_topic("fed_policy")
    assert result is not None, "Should return principles for fed_policy"


def test_vector_store_no_deprecated_collections():
    """VectorStore should not initialize framework or blind_spot collections."""
    import src.db.vector as vec_module
    source_code = open(vec_module.__file__).read()

    assert "frameworks" not in source_code.lower() or "framework" not in source_code, \
        "VectorStore should not reference frameworks collection"
    assert "blind_spots" not in source_code, \
        "VectorStore should not reference blind_spots collection"
    assert "thesis_elements" not in source_code, \
        "VectorStore should not reference thesis_elements collection"

    # Should still have the kept collections
    assert "content_chunks" in source_code
    assert "notes" in source_code
    assert "connections" in source_code


def test_scheduler_no_deprecated_jobs():
    """Scheduler should not reference deprecated job functions."""
    import src.worker.scheduler as sched_module
    source_code = open(sched_module.__file__).read()

    assert "weekly_synthesis_job" not in source_code, "Should not have weekly synthesis job"
    assert "daily_brief_job" not in source_code, "Should not have daily brief job"
    assert "market_matching_job" not in source_code, "Should not have market matching job"
    assert "ThesisAnalyzer" not in source_code, "Should not reference ThesisAnalyzer"
    assert "ExternalAnalyzer" not in source_code, "Should not reference ExternalAnalyzer"

    # Should still have feed polling and analysis
    assert "poll_all_feeds_job" in source_code
    assert "process_analysis_job" in source_code
