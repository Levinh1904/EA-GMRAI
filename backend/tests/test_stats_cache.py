"""History stats cache + rate-limit coverage.

The cache exists because every `/stats/*` call re-materialised the whole run.
What must be true:
  * a done run is computed once, then served from cache
  * a run that is still `running` is NEVER cached (it is still being written)
  * different params (e.g. period) do not collide
  * invalidation works per run and globally
"""
import pytest

from app.services import stats_cache


@pytest.fixture(autouse=True)
def _clear_cache():
    stats_cache.invalidate()
    yield
    stats_cache.invalidate()


def test_cache_returns_same_object_on_second_call():
    calls = {"n": 0}

    def compute():
        calls["n"] += 1
        return {"value": 42}

    a = stats_cache.get_or_compute(("run", 1, "duration"), compute)
    b = stats_cache.get_or_compute(("run", 1, "duration"), compute)
    assert a == b
    assert calls["n"] == 1, "second call must be served from cache"


def test_cache_keys_are_distinct_per_params():
    calls = {"n": 0}

    def make(v):
        def _c():
            calls["n"] += 1
            return {"v": v}
        return _c

    stats_cache.get_or_compute((1, "periods", (("period", "day"),)), make("day"))
    stats_cache.get_or_compute((1, "periods", (("period", "week"),)), make("week"))
    assert calls["n"] == 2


def test_cache_ttl_expires():
    calls = {"n": 0}

    def compute():
        calls["n"] += 1
        return calls["n"]

    stats_cache.get_or_compute(("k",), compute, ttl=0.0)
    stats_cache.get_or_compute(("k",), compute, ttl=0.0)
    assert calls["n"] == 2


def test_invalidate_one_run_only():
    stats_cache.get_or_compute((1, "duration"), lambda: "a")
    stats_cache.get_or_compute((2, "duration"), lambda: "b")
    removed = stats_cache.invalidate(1)
    assert removed == 1
    info = stats_cache.info()
    assert info["entries"] == 1


def test_invalidate_all():
    stats_cache.get_or_compute((1, "x"), lambda: 1)
    stats_cache.get_or_compute((2, "y"), lambda: 2)
    assert stats_cache.invalidate() == 2
    assert stats_cache.info()["entries"] == 0


def test_info_reports_hit_rate():
    stats_cache.get_or_compute(("a",), lambda: 1)
    stats_cache.get_or_compute(("a",), lambda: 1)  # hit
    info = stats_cache.info()
    assert info["hits"] == 1 and info["misses"] == 1
    assert info["hit_rate_pct"] == 50.0


def test_cache_is_bounded():
    for i in range(stats_cache.MAX_ENTRIES + 10):
        stats_cache.get_or_compute((i,), lambda i=i: i)
    info = stats_cache.info()
    assert info["entries"] == stats_cache.MAX_ENTRIES
    assert info["evictions"] > 0


# ---------------------------------------------------------------------------
# Endpoint integration: done runs cached, running runs not
# ---------------------------------------------------------------------------

def test_done_run_stats_served_from_cache(client, admin_token, db):
    from app.db import session
    from app.models import RegimeHistoryRun

    with session() as s:
        run = RegimeHistoryRun(symbol="XAUUSD", timeframe="M15", status="done",
                               bar_count=0, segment_count=0, data_source="ftmo_mt5")
        s.add(run)
        s.commit()
        rid = run.id

    h = {"Authorization": f"Bearer {admin_token}"}
    assert client.get(f"/api/v1/history/runs/{rid}/stats/duration", headers=h).status_code == 200
    before = stats_cache.info()["misses"]
    assert client.get(f"/api/v1/history/runs/{rid}/stats/duration", headers=h).status_code == 200
    after = stats_cache.info()

    assert after["misses"] == before, "second call must not recompute"
    assert after["hits"] >= 1


def test_running_run_is_never_cached(client, admin_token, db):
    from app.db import session
    from app.models import RegimeHistoryRun

    with session() as s:
        run = RegimeHistoryRun(symbol="XAUUSD", timeframe="M15", status="running",
                               bar_count=0, segment_count=0, data_source="ftmo_mt5")
        s.add(run)
        s.commit()
        rid = run.id

    h = {"Authorization": f"Bearer {admin_token}"}
    client.get(f"/api/v1/history/runs/{rid}/stats/duration", headers=h)
    client.get(f"/api/v1/history/runs/{rid}/stats/duration", headers=h)
    # A running run writes rows while it is inspected; caching would serve stale data.
    assert stats_cache.info()["entries"] == 0


def test_cache_admin_endpoints(client, admin_token, analyst_token):
    h_admin = {"Authorization": f"Bearer {admin_token}"}
    h_analyst = {"Authorization": f"Bearer {analyst_token}"}

    assert client.get("/api/v1/history/cache/stats", headers=h_admin).status_code == 200
    assert client.get("/api/v1/history/cache/stats", headers=h_analyst).status_code == 403

    r = client.post("/api/v1/history/cache/invalidate", headers=h_admin)
    assert r.status_code == 200
    assert "invalidated" in r.json()
