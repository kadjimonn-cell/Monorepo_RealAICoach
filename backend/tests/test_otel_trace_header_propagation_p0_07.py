from pathlib import Path


def test_otel_fetch_trace_propagation_is_scoped_to_first_party_api_domain() -> None:
    source = Path("/app/frontend/src/services/otelClient.ts").read_text(encoding="utf-8")

    assert "propagateTraceHeaderCorsUrls: [/.*/]" not in source
    assert "propagateTraceHeaderCorsUrls: [/api\\.realaicoach\\.app/]" in source
