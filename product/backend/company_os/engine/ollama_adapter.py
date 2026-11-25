"""MOD-005: Free local Ollama adapter for AI Proje Ofisi.

Uses only Python stdlib HTTP requests against loopback Ollama (default
http://127.0.0.1:11434) with the free local model (qwen2.5-coder:3b).
Never falls back to paid remote providers.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_OLLAMA_MODEL = "qwen2.5-coder:3b"
DEFAULT_OLLAMA_EXE = Path(r"E:\ollama_local\bin\ollama.exe")
DEFAULT_OLLAMA_MODELS_DIR = Path(r"E:\ollama_local\models")
ALLOWED_LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost"})


class OllamaError(RuntimeError):
    """Fail-closed error raised when local Ollama invocation fails."""


@dataclass(frozen=True)
class OllamaGenerationResult:
    """Verified metadata and text returned by a local Ollama generation call."""

    model: str
    response: str
    response_sha256: str
    prompt_eval_count: int
    eval_count: int
    total_duration_ms: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "response": self.response,
            "response_sha256": self.response_sha256,
            "prompt_eval_count": self.prompt_eval_count,
            "eval_count": self.eval_count,
            "total_duration_ms": self.total_duration_ms,
        }


def _validate_local_base_url(base_url: str) -> str:
    if type(base_url) is not str or not base_url.strip():
        raise OllamaError("OLLAMA_BASE_URL_REQUIRED")
    cleaned = base_url.strip().rstrip("/")
    parsed = urllib.parse.urlparse(cleaned)
    if parsed.scheme != "http" or parsed.hostname not in ALLOWED_LOCAL_HOSTS:
        raise OllamaError("OLLAMA_LOOPBACK_HTTP_REQUIRED")
    return cleaned


class OllamaClient:
    """Bounded loopback HTTP client for local Ollama inference."""

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_OLLAMA_BASE_URL,
        default_model: str = DEFAULT_OLLAMA_MODEL,
        timeout_seconds: float = 90.0,
        max_response_bytes: int = 131072,
    ) -> None:
        self.base_url = _validate_local_base_url(base_url)
        if type(default_model) is not str or not default_model.strip():
            raise OllamaError("OLLAMA_MODEL_REQUIRED")
        if timeout_seconds <= 0 or timeout_seconds > 300:
            raise OllamaError("OLLAMA_TIMEOUT_OUT_OF_RANGE")
        if max_response_bytes < 1024 or max_response_bytes > 1048576:
            raise OllamaError("OLLAMA_MAX_BYTES_OUT_OF_RANGE")
        self.default_model = default_model.strip()
        self.timeout_seconds = float(timeout_seconds)
        self.max_response_bytes = int(max_response_bytes)

    def _request_json(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        data = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        effective_timeout = self.timeout_seconds if timeout is None else float(timeout)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(req, timeout=effective_timeout) as resp:
                raw = resp.read(self.max_response_bytes + 1)
                if len(raw) > self.max_response_bytes:
                    raise OllamaError("OLLAMA_RESPONSE_TOO_LARGE")
                parsed = json.loads(raw.decode("utf-8"))
                if not isinstance(parsed, dict):
                    raise OllamaError("OLLAMA_INVALID_JSON_OBJECT")
                return parsed
        except OllamaError:
            raise
        except urllib.error.HTTPError as exc:
            raise OllamaError(f"OLLAMA_HTTP_{exc.code}") from None
        except urllib.error.URLError:
            raise OllamaError("OLLAMA_UNREACHABLE") from None
        except (TimeoutError, OSError):
            raise OllamaError("OLLAMA_TIMEOUT_OR_IO") from None
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise OllamaError("OLLAMA_MALFORMED_JSON") from None

    def check_health(self, *, timeout: float = 2.5) -> dict[str, Any]:
        """Return availability and installed local models without throwing."""
        try:
            data = self._request_json("GET", "/api/tags", timeout=timeout)
            raw_models = data.get("models")
            names = [
                str(item["name"])
                for item in (raw_models if isinstance(raw_models, list) else [])
                if isinstance(item, dict) and item.get("name")
            ]
            return {
                "available": True,
                "base_url": self.base_url,
                "default_model": self.default_model,
                "models": names,
                "default_model_ready": self.default_model in names,
            }
        except OllamaError as exc:
            return {
                "available": False,
                "base_url": self.base_url,
                "default_model": self.default_model,
                "models": [],
                "default_model_ready": False,
                "error": str(exc),
            }

    def generate(
        self,
        prompt: str,
        *,
        model: str | None = None,
        system: str | None = None,
        temperature: float = 0.2,
        num_predict: int = 768,
        repeat_penalty: float = 1.15,
    ) -> OllamaGenerationResult:
        """Invoke local Ollama /api/generate synchronously and validate output."""
        if type(prompt) is not str or not prompt.strip():
            raise OllamaError("OLLAMA_PROMPT_REQUIRED")
        chosen_model = (model or self.default_model).strip()
        if not chosen_model:
            raise OllamaError("OLLAMA_MODEL_REQUIRED")
        if not isinstance(num_predict, int) or isinstance(num_predict, bool) or num_predict < 32 or num_predict > 4096:
            raise OllamaError("OLLAMA_NUM_PREDICT_OUT_OF_RANGE")
        if isinstance(repeat_penalty, bool) or not isinstance(repeat_penalty, (int, float)) or repeat_penalty < 1.0 or repeat_penalty > 2.0:
            raise OllamaError("OLLAMA_REPEAT_PENALTY_OUT_OF_RANGE")

        body: dict[str, Any] = {
            "model": chosen_model,
            "prompt": prompt.strip(),
            "stream": False,
            "options": {
                "temperature": float(temperature),
                "num_predict": int(num_predict),
                "repeat_penalty": float(repeat_penalty),
            },
        }
        if system and system.strip():
            body["system"] = system.strip()

        started = time.monotonic()
        data = self._request_json("POST", "/api/generate", body)
        elapsed_ms = int((time.monotonic() - started) * 1000)

        text = str(data.get("response") or "").strip()
        if not text:
            raise OllamaError("OLLAMA_EMPTY_RESPONSE")
        total_ns = data.get("total_duration")
        duration_ms = int(total_ns // 1_000_000) if isinstance(total_ns, int) and total_ns > 0 else elapsed_ms
        return OllamaGenerationResult(
            model=str(data.get("model") or chosen_model),
            response=text,
            response_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            prompt_eval_count=int(data.get("prompt_eval_count") or 0),
            eval_count=int(data.get("eval_count") or 0),
            total_duration_ms=duration_ms,
        )


def ensure_local_ollama_running(
    *,
    ollama_exe: Path = DEFAULT_OLLAMA_EXE,
    models_dir: Path = DEFAULT_OLLAMA_MODELS_DIR,
    base_url: str = DEFAULT_OLLAMA_BASE_URL,
    default_model: str = DEFAULT_OLLAMA_MODEL,
    wait_seconds: float = 10.0,
) -> dict[str, Any]:
    """Start local Ollama on Windows if installed and not already listening."""
    client = OllamaClient(base_url=base_url, default_model=default_model)
    health = client.check_health(timeout=1.5)
    if health["available"]:
        health["started_by_launcher"] = False
        return health

    if sys.platform != "win32" or not ollama_exe.is_file():
        health["started_by_launcher"] = False
        return health

    env = dict(os.environ)
    if models_dir.is_dir():
        env["OLLAMA_MODELS"] = str(models_dir)
    env.setdefault("OLLAMA_HOST", "127.0.0.1:11434")

    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(
        subprocess, "CREATE_NEW_PROCESS_GROUP", 0
    )
    try:
        subprocess.Popen(
            [str(ollama_exe), "serve"],
            cwd=str(ollama_exe.parent),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
        )
    except OSError as exc:
        health["started_by_launcher"] = False
        health["error"] = f"OLLAMA_START_FAILED:{type(exc).__name__}"
        return health

    deadline = time.monotonic() + max(1.0, float(wait_seconds))
    while time.monotonic() < deadline:
        time.sleep(0.4)
        health = client.check_health(timeout=1.5)
        if health["available"]:
            health["started_by_launcher"] = True
            return health
    health["started_by_launcher"] = False
    return health
