"""Tests never require real provider credentials or model calls."""

import pytest


@pytest.fixture(autouse=True)
def operator_settings(tmp_path_factory, monkeypatch):
    path = tmp_path_factory.mktemp("settings") / "operator.yaml"
    path.write_text(
        "models:\n  filter: test-model\n  pair_verification: test-model\n  candidate: test-model\napi_gateway:\n  base_url: http://127.0.0.1:9/v1\n  api_key: test-key\n"
    )
    monkeypatch.setenv("PERFRACE_SETTINGS", str(path))
    monkeypatch.setenv("LLM_BASE_URL", "http://127.0.0.1:9/v1")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
