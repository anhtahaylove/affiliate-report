from pathlib import Path


def test_service_worker_bypasses_private_routes_before_cache_handling():
    source = (Path(__file__).parents[1] / "web" / "public" / "sw.js").read_text(encoding="utf-8")

    assert 'const BYPASS_PREFIXES = ["/api/", "/auth/", "/health"]' in source
    assert source.index("shouldBypass(event.request)") < source.index("event.respondWith(")
    assert "if (response.ok)" in source
