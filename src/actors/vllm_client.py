from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    yaml = None  # type: ignore

from src.data.schemas import repo_root


@dataclass
class ActorConfig:
    name: str
    base_url: str
    model: str
    tensor_parallel_size: int = 1
    gpu_id: int = 0


@dataclass
class VLLMConfig:
    actors: List[ActorConfig]
    timeout_sec: int = 60
    max_tokens: int = 512


def _config_path() -> Path:
    return repo_root() / "configs" / "vllm_actors.yaml"


def _load_config() -> VLLMConfig:
    cfg_path = _config_path()
    if not cfg_path.exists() or yaml is None:
        # Minimal default pointing at a single localhost actor.
        return VLLMConfig(
            actors=[
                ActorConfig(
                    name="default",
                    base_url="http://127.0.0.1:8000",
                    model="qwen2-14b-instruct",
                )
            ],
            timeout_sec=60,
            max_tokens=512,
        )

    data = yaml.safe_load(cfg_path.read_text()) or {}
    timeout_sec = int(data.get("timeout_sec", 60))
    max_tokens = int(data.get("max_tokens", 512))
    actors_raw = data.get("actors") or []
    actors: List[ActorConfig] = []
    for raw in actors_raw:
        actors.append(
            ActorConfig(
                name=str(raw.get("name")),
                base_url=str(raw.get("base_url")),
                model=str(raw.get("model")),
                tensor_parallel_size=int(raw.get("tensor_parallel_size", 1)),
                gpu_id=int(raw.get("gpu_id", 0)),
            )
        )
    if not actors:
        actors.append(
            ActorConfig(
                name="default",
                base_url="http://127.0.0.1:8000",
                model="qwen2-14b-instruct",
            )
        )
    return VLLMConfig(actors=actors, timeout_sec=timeout_sec, max_tokens=max_tokens)


class VLLMClient:
    """Minimal HTTP client for a vLLM text generation server.

    This targets the standard vLLM HTTP engine endpoint:
    POST /generate with JSON body and a simple text response.
    """

    def __init__(self, actor_name: Optional[str] = None):
        cfg = _load_config()
        if actor_name is None:
            actor = cfg.actors[0]
        else:
            matches = [a for a in cfg.actors if a.name == actor_name]
            if not matches:
                raise ValueError(f"Unknown actor_name: {actor_name}")
            actor = matches[0]
        self._cfg = cfg
        self._actor = actor

    @property
    def base_url(self) -> str:
        return self._actor.base_url.rstrip("/")

    @property
    def model(self) -> str:
        return self._actor.model

    def health(self) -> bool:
        """Return True if the actor responds successfully to a health check."""
        url = f"{self.base_url}/health"
        try:
            resp = requests.get(url, timeout=self._cfg.timeout_sec)
        except Exception:
            return False
        if resp.status_code != 200:
            return False
        try:
            payload = resp.json()
        except json.JSONDecodeError:
            return True
        status = payload.get("status")
        return status in (None, "ok", "healthy")

    def generate(
        self,
        prompt: str,
        stop: Optional[List[str]] = None,
        temperature: float = 0.1,
        seed: Optional[int] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Call the vLLM server and return the generated text.

        This uses the /generate endpoint with a simple text prompt.
        """
        url = f"{self.base_url}/generate"
        payload: Dict[str, Any] = {
            "prompt": prompt,
            "model": self.model,
            "temperature": float(temperature),
            "max_tokens": int(max_tokens or self._cfg.max_tokens),
        }
        if stop:
            payload["stop"] = stop
        if seed is not None:
            payload["seed"] = int(seed)

        resp = requests.post(url, json=payload, timeout=self._cfg.timeout_sec)
        resp.raise_for_status()
        data = resp.json()

        # Be tolerant of different response shapes.
        if isinstance(data, dict):
            if "text" in data:
                text = data["text"]
                if isinstance(text, list):
                    return str(text[0])
                return str(text)
            if "choices" in data:
                choices = data["choices"]
                if isinstance(choices, list) and choices:
                    first = choices[0]
                    if isinstance(first, dict):
                        if "text" in first:
                            return str(first["text"])
                        message = first.get("message")
                            # Chat-style response shape.
                        if isinstance(message, dict) and "content" in message:
                            return str(message["content"])

        raise RuntimeError("Unexpected vLLM response format")


__all__ = [
    "ActorConfig",
    "VLLMConfig",
    "VLLMClient",
]

