from pathlib import Path

import types

import pytest

from src.actors.vllm_client import VLLMClient, _config_path


class DummyResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if not (200 <= self.status_code < 300):
            raise RuntimeError(f"HTTP {self.status_code}")


def test_health_true_on_ok(monkeypatch, tmp_path):
    cfg_path = tmp_path / "vllm_actors.yaml"
    cfg_path.write_text(
        "actors:\n"
        "  - name: a0\n"
        "    base_url: http://localhost:9999\n"
        "    model: dummy\n"
    )

    monkeypatch.setattr("src.actors.vllm_client._config_path", lambda: cfg_path)

    calls = {}

    def fake_get(url, timeout):
        calls["url"] = url
        return DummyResponse(status_code=200, payload={"status": "ok"})

    monkeypatch.setattr("src.actors.vllm_client.requests.get", fake_get)

    client = VLLMClient(actor_name="a0")
    assert client.health() is True
    assert "health" in calls["url"]


def test_generate_uses_generate_endpoint_and_returns_text(monkeypatch, tmp_path):
    cfg_path = tmp_path / "vllm_actors.yaml"
    cfg_path.write_text(
        "actors:\n"
        "  - name: a0\n"
        "    base_url: http://localhost:9999\n"
        "    model: dummy\n"
        "timeout_sec: 5\n"
        "max_tokens: 16\n"
    )

    monkeypatch.setattr("src.actors.vllm_client._config_path", lambda: cfg_path)

    recorded = {}

    def fake_post(url, json, timeout):  # type: ignore[override]
        recorded["url"] = url
        recorded["json"] = json
        return DummyResponse(
            status_code=200,
            payload={"text": ["hello world"]},
        )

    monkeypatch.setattr("src.actors.vllm_client.requests.post", fake_post)

    client = VLLMClient(actor_name="a0")
    text = client.generate("hi", stop=["\n"], temperature=0.5, seed=123, max_tokens=10)

    assert text == "hello world"
    assert recorded["url"].endswith("/generate")
    body = recorded["json"]
    assert body["prompt"] == "hi"
    assert body["model"] == "dummy"
    assert body["temperature"] == 0.5
    assert body["max_tokens"] == 10
    assert body["stop"] == ["\n"]
    assert body["seed"] == 123

