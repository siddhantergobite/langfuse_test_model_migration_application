"""OpenAI-compatible parent gateway for unchanged child application prompts."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
from contextlib import nullcontext
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlsplit

import requests
from flask import Blueprint, Response, current_app, jsonify, request, stream_with_context


gateway = Blueprint("parent_gateway", __name__)
DATA_DIR = Path(os.getenv("LOCALAPPDATA", str(Path.home() / ".local" / "share"))) / "ModelTransitionLab"
DB_PATH = DATA_DIR / "evaluation.sqlite3"
HTTP_TIMEOUT = float(os.getenv("GATEWAY_UPSTREAM_TIMEOUT_SECONDS", "90"))
MAX_TELEMETRY_CONTENT_CHARS = 200_000
MAX_CAPTURE_BYTES = 750_000
MAX_CAPTURE_RECORDS = 100
RAG_APP_ID = "rag-knowledge-retrieval"
_INTERNAL_EVALUATION: ContextVar[Optional[Dict[str, Any]]] = ContextVar(
    "parent_internal_evaluation", default=None
)
ALLOWED_API_PREFIXES = (
    "chat/completions", "responses", "embeddings", "moderations", "models",
    "files", "vector_stores", "assistants", "threads", "batches", "uploads",
)

SAMPLE_APPS = [
    {
        "id": "rag-knowledge-retrieval",
        "name": "Knowledge Retrieval RAG",
        "category": "RAG",
        "repository": "https://github.com/openai/openai-knowledge-retrieval",
        "description": "Retrieval, citations, and grounded answers.",
        "requested_model": "gpt-5",
    },
    {
        "id": "support-agent",
        "name": "Customer Support Agent",
        "category": "Agent",
        "repository": "https://github.com/openai/openai-support-agent-demo",
        "description": "Multi-turn agent with tools, file search, and human review.",
        "requested_model": "gpt-5.2",
    },
    {
        "id": "resume-extraction",
        "name": "Resume Extraction",
        "category": "Structured output",
        "repository": "https://github.com/openai/openai-structured-outputs-samples",
        "description": "Streaming structured output validated against a schema.",
        "requested_model": "gpt-4o-mini",
    },
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect_db() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(DB_PATH), timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def init_gateway_database() -> None:
    connection = connect_db()
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS connected_apps (
          id TEXT PRIMARY KEY,
          name TEXT NOT NULL,
          category TEXT NOT NULL,
          repository TEXT NOT NULL DEFAULT '',
          description TEXT NOT NULL DEFAULT '',
          token_hash TEXT,
          active INTEGER NOT NULL DEFAULT 1,
          created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS model_routes (
          id INTEGER PRIMARY KEY,
          app_id TEXT NOT NULL REFERENCES connected_apps(id) ON DELETE CASCADE,
          requested_model TEXT NOT NULL,
          provider TEXT NOT NULL,
          upstream_model TEXT NOT NULL,
          enabled INTEGER NOT NULL DEFAULT 1,
          max_output_tokens INTEGER,
          is_default INTEGER NOT NULL DEFAULT 0,
          updated_at TEXT NOT NULL,
          UNIQUE(app_id, requested_model)
        );
        CREATE TABLE IF NOT EXISTS gateway_requests (
          id INTEGER PRIMARY KEY,
          request_id TEXT NOT NULL UNIQUE,
          app_id TEXT NOT NULL,
          requested_model TEXT,
          provider TEXT NOT NULL,
          upstream_model TEXT,
          endpoint TEXT NOT NULL,
          status_code INTEGER,
          success INTEGER NOT NULL DEFAULT 0,
          latency_ms REAL,
          input_tokens INTEGER,
          output_tokens INTEGER,
          cost_usd REAL,
          error_code TEXT,
          created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS gateway_capture_settings (
          app_id TEXT PRIMARY KEY REFERENCES connected_apps(id) ON DELETE CASCADE,
          enabled INTEGER NOT NULL DEFAULT 0,
          updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS gateway_captures (
          id INTEGER PRIMARY KEY,
          request_id TEXT NOT NULL UNIQUE,
          app_id TEXT NOT NULL,
          requested_model TEXT NOT NULL,
          provider TEXT NOT NULL,
          upstream_model TEXT NOT NULL,
          endpoint TEXT NOT NULL,
          request_json TEXT NOT NULL,
          response_json TEXT,
          response_text TEXT,
          status_code INTEGER NOT NULL,
          latency_ms REAL,
          input_tokens INTEGER,
          output_tokens INTEGER,
          cost_usd REAL,
          includes_tool_result INTEGER NOT NULL DEFAULT 0,
          created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_gateway_captures_app
          ON gateway_captures(app_id, id DESC);
        CREATE TABLE IF NOT EXISTS app_quality_policies (
          app_id TEXT PRIMARY KEY REFERENCES connected_apps(id) ON DELETE CASCADE,
          minimum_quality_score REAL NOT NULL DEFAULT 4.0,
          max_quality_drop REAL NOT NULL DEFAULT 0.0,
          max_latency_regression_pct REAL NOT NULL DEFAULT 25.0,
          max_cost_regression_pct REAL NOT NULL DEFAULT 25.0,
          updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS rag_evaluations (
          id INTEGER PRIMARY KEY,
          app_id TEXT NOT NULL,
          capture_id INTEGER NOT NULL REFERENCES gateway_captures(id),
          baseline_provider TEXT NOT NULL,
          baseline_model TEXT NOT NULL,
          baseline_output TEXT,
          baseline_status_code INTEGER NOT NULL,
          baseline_latency_ms REAL,
          baseline_input_tokens INTEGER,
          baseline_output_tokens INTEGER,
          baseline_cost_usd REAL,
          candidate_provider TEXT NOT NULL,
          candidate_model TEXT NOT NULL,
          candidate_output TEXT,
          candidate_status_code INTEGER NOT NULL,
          candidate_latency_ms REAL,
          candidate_input_tokens INTEGER,
          candidate_output_tokens INTEGER,
          candidate_cost_usd REAL,
          baseline_quality_score REAL,
          candidate_quality_score REAL,
          recommendation TEXT NOT NULL,
          status TEXT NOT NULL,
          previous_provider TEXT NOT NULL,
          previous_model TEXT NOT NULL,
          previous_routes_json TEXT NOT NULL DEFAULT '[]',
          created_at TEXT NOT NULL,
          reviewed_at TEXT,
          promoted_at TEXT,
          rolled_back_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_gateway_requests_created
          ON gateway_requests(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_gateway_requests_app
          ON gateway_requests(app_id, created_at DESC);
        """
    )
    route_columns = {row["name"] for row in connection.execute("PRAGMA table_info(model_routes)")}
    if "max_output_tokens" not in route_columns:
        connection.execute("ALTER TABLE model_routes ADD COLUMN max_output_tokens INTEGER")
    evaluation_columns = {row["name"] for row in connection.execute("PRAGMA table_info(rag_evaluations)")}
    if "previous_routes_json" not in evaluation_columns:
        connection.execute("ALTER TABLE rag_evaluations ADD COLUMN previous_routes_json TEXT NOT NULL DEFAULT '[]'")

    # Seed examples without credentials. Keys are generated by the admin UI and
    # only their SHA-256 hashes are stored.
    for sample in SAMPLE_APPS:
        connection.execute(
            """INSERT OR IGNORE INTO connected_apps
               (id,name,category,repository,description,created_at)
               VALUES(?,?,?,?,?,?)""",
            (sample["id"], sample["name"], sample["category"], sample["repository"],
             sample["description"], utc_now()),
        )
        provider = os.getenv("CANDIDATE_PROVIDER", "azure").strip().lower()
        if provider not in {"openai", "openrouter", "azure", "custom"}:
            provider = "openrouter"
        target = os.getenv("CANDIDATE_MODEL", "").strip()
        if provider == "azure":
            target = os.getenv("AZURE_OPENAI_MODEL", target).strip()
        target = target or sample["requested_model"]
        connection.execute(
            """INSERT OR IGNORE INTO model_routes
               (app_id,requested_model,provider,upstream_model,enabled,is_default,updated_at)
               VALUES(?,?,?,?,1,1,?)""",
            (sample["id"], sample["requested_model"], provider, target, utc_now()),
        )
        if sample["id"] == "rag-knowledge-retrieval":
            connection.execute(
                "INSERT OR IGNORE INTO app_quality_policies(app_id,updated_at) VALUES(?,?)",
                (sample["id"], utc_now()),
            )
            connection.execute(
                """INSERT OR IGNORE INTO model_routes
                   (app_id,requested_model,provider,upstream_model,enabled,is_default,updated_at)
                   VALUES(?,?,?, ?,1,0,?)""",
                (sample["id"], "gpt-5-mini", provider, target, utc_now()),
            )
            embedding_model = os.getenv("AZURE_OPENAI_EMBEDDING_MODEL", "").strip()
            if provider == "azure" and embedding_model:
                connection.execute(
                    """INSERT OR IGNORE INTO model_routes
                       (app_id,requested_model,provider,upstream_model,enabled,is_default,updated_at)
                       VALUES(?,?,?,?,1,0,?)""",
                    (sample["id"], "text-embedding-3-small", "azure", embedding_model, utc_now()),
                )
    connection.commit()
    connection.close()


def provider_config(provider: str) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """Return (base URL, secret, auth header, public label) without exposing secrets."""
    provider = (provider or "").strip().lower()
    if provider == "openrouter":
        return (
            os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/"),
            os.getenv("OPENROUTER_API_KEY"), "Authorization", "OpenRouter",
        )
    if provider == "openai":
        return (
            os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
            os.getenv("OPENAI_API_KEY"), "Authorization", "OpenAI",
        )
    if provider == "azure":
        endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "").strip().rstrip("/")
        if endpoint and not endpoint.endswith("/openai/v1"):
            endpoint += "/v1" if endpoint.endswith("/openai") else "/openai/v1"
        return endpoint, os.getenv("AZURE_OPENAI_API_KEY"), "api-key", "Azure OpenAI"
    if provider == "custom":
        return (
            os.getenv("GATEWAY_CUSTOM_BASE_URL", "").strip().rstrip("/"),
            os.getenv("GATEWAY_CUSTOM_API_KEY"), "Authorization", "Custom OpenAI-compatible",
        )
    return None, None, None, provider or "Unknown provider"


def provider_catalog() -> list:
    result = []
    for key in ("openai", "openrouter", "azure", "custom"):
        base, secret, _, label = provider_config(key)
        display_url = ""
        if base:
            try:
                parsed = urlsplit(base)
                if parsed.scheme and parsed.hostname:
                    host = parsed.hostname
                    if ":" in host:
                        host = "[" + host + "]"
                    if parsed.port:
                        host += ":" + str(parsed.port)
                    display_url = parsed.scheme + "://" + host + parsed.path.rstrip("/")
            except ValueError:
                pass
        result.append({"id": key, "name": label, "configured": bool(base and secret), "base_url": display_url})
    return result


def langfuse_configured() -> bool:
    return bool(os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"))


def telemetry_context(app_name: str, request_id: str, route: sqlite3.Row, body: Any, endpoint: str):
    if not langfuse_configured():
        return nullcontext(None)
    try:
        from langfuse import get_client

        client = get_client()
        capture = os.getenv("LANGFUSE_CAPTURE_CONTENT", "false").strip().lower() in {"1", "true", "yes"}
        if capture:
            observation_input = body
        else:
            observation_input = {
                "endpoint": endpoint,
                "message_count": len(body.get("messages", [])) if isinstance(body, dict) and isinstance(body.get("messages"), list) else None,
                "input_bytes": len(json.dumps(body, ensure_ascii=False).encode("utf-8")) if body is not None else None,
                "content_capture": False,
            }
        metadata = {"request_id": request_id, "app_id": route["app_id"],
                    "requested_model": route["requested_model"], "provider": route["provider"]}
        evaluation = _INTERNAL_EVALUATION.get()
        if evaluation:
            metadata.update({key: evaluation[key] for key in ("evaluation_id", "condition", "capture_id")
                             if evaluation.get(key) is not None})
        return client.start_as_current_observation(
            as_type="generation", name=f"{app_name} · {endpoint}",
            model=route["upstream_model"], input=observation_input,
            metadata=metadata,
        )
    except Exception:
        # Telemetry outages must not prevent an app from reaching its model.
        return nullcontext(None)


def extract_usage(payload: Any) -> Tuple[Optional[int], Optional[int], Optional[float]]:
    if not isinstance(payload, dict):
        return None, None, None
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        return None, None, None
    input_tokens = usage.get("prompt_tokens", usage.get("input_tokens"))
    output_tokens = usage.get("completion_tokens", usage.get("output_tokens"))
    cost = usage.get("cost")
    try:
        input_tokens = int(input_tokens) if input_tokens is not None else None
    except (TypeError, ValueError):
        input_tokens = None
    try:
        output_tokens = int(output_tokens) if output_tokens is not None else None
    except (TypeError, ValueError):
        output_tokens = None
    try:
        cost = float(cost) if cost is not None else None
    except (TypeError, ValueError):
        cost = None
    return input_tokens, output_tokens, cost


def record_request(request_id: str, app_id: str, requested_model: Optional[str], route: sqlite3.Row,
                   endpoint: str, status_code: int, latency_ms: float, payload: Any = None,
                   error_code: Optional[str] = None) -> None:
    input_tokens, output_tokens, cost = extract_usage(payload)
    connection = connect_db()
    connection.execute(
        """INSERT OR REPLACE INTO gateway_requests
           (request_id,app_id,requested_model,provider,upstream_model,endpoint,status_code,success,
            latency_ms,input_tokens,output_tokens,cost_usd,error_code,created_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (request_id, app_id, requested_model, route["provider"], route["upstream_model"], endpoint,
          int(status_code), int(200 <= status_code < 400 and not error_code), round(latency_ms, 2), input_tokens,
         output_tokens, cost, error_code, utc_now()),
    )
    connection.commit()
    connection.close()


def authenticate_app() -> Optional[sqlite3.Row]:
    evaluation = _INTERNAL_EVALUATION.get()
    if evaluation and evaluation.get("app_id") and request.path.startswith("/v1/"):
        connection = connect_db()
        app_row = connection.execute(
            "SELECT * FROM connected_apps WHERE id=? AND active=1", (evaluation["app_id"],)
        ).fetchone()
        connection.close()
        return app_row
    supplied = request.headers.get("Authorization", "")
    if supplied.lower().startswith("bearer "):
        token = supplied[7:].strip()
    else:
        token = request.headers.get("x-api-key", "").strip()
    if not token:
        return None
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    connection = connect_db()
    candidates = connection.execute(
        "SELECT * FROM connected_apps WHERE active=1 AND token_hash IS NOT NULL"
    ).fetchall()
    app_row = next((row for row in candidates if hmac.compare_digest(row["token_hash"], digest)), None)
    connection.close()
    return app_row


def model_route(app_id: str, requested_model: Optional[str]) -> Optional[sqlite3.Row]:
    evaluation = _INTERNAL_EVALUATION.get()
    if (evaluation and evaluation.get("app_id") == app_id
            and evaluation.get("requested_model") == requested_model):
        return evaluation.get("route")
    connection = connect_db()
    if requested_model:
        row = connection.execute(
            """SELECT r.*,a.name AS app_name FROM model_routes r JOIN connected_apps a ON a.id=r.app_id
               WHERE r.app_id=? AND r.requested_model=? AND r.enabled=1""",
            (app_id, requested_model),
        ).fetchone()
    else:
        row = connection.execute(
            """SELECT r.*,a.name AS app_name FROM model_routes r JOIN connected_apps a ON a.id=r.app_id
               WHERE r.app_id=? AND r.enabled=1 ORDER BY r.is_default DESC,r.id LIMIT 1""",
            (app_id,),
        ).fetchone()
    connection.close()
    return row


def capture_enabled(app_id: str) -> bool:
    connection = connect_db()
    row = connection.execute(
        "SELECT enabled FROM gateway_capture_settings WHERE app_id=?", (app_id,)
    ).fetchone()
    connection.close()
    return bool(row and row["enabled"])


def request_has_tool_result(value: Any) -> bool:
    """Check whether a replay includes a completed retrieval/tool result."""
    if isinstance(value, list):
        return any(request_has_tool_result(item) for item in value)
    if not isinstance(value, dict):
        return False
    item_type = str(value.get("type", "")).lower()
    role = str(value.get("role", "")).lower()
    if item_type in {"function_call_output", "tool_result", "tool_output"} or role == "tool":
        return True
    return any(request_has_tool_result(item) for item in value.values())


def response_output_text(payload: Any) -> str:
    if isinstance(payload, dict):
        if isinstance(payload.get("output_text"), str):
            return payload["output_text"]
        choices = payload.get("choices")
        if isinstance(choices, list) and choices:
            message = choices[0].get("message", {}) if isinstance(choices[0], dict) else {}
            content = message.get("content") if isinstance(message, dict) else None
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                return "\n".join(str(item.get("text", "")) for item in content if isinstance(item, dict))
        parts = []
        for item in payload.get("output", []) if isinstance(payload.get("output"), list) else []:
            if not isinstance(item, dict):
                continue
            for content in item.get("content", []) if isinstance(item.get("content"), list) else []:
                if isinstance(content, dict) and content.get("type") in {"output_text", "text"}:
                    parts.append(str(content.get("text", "")))
        return "\n".join(part for part in parts if part)
    return ""


def response_text_from_stream(raw: bytes) -> str:
    deltas = []
    for line in raw.decode("utf-8", errors="replace").splitlines():
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if not data or data == "[DONE]":
            continue
        try:
            event = json.loads(data)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get("type") in {"response.output_text.delta", "response.text.delta"}:
            delta = event.get("delta")
            if isinstance(delta, str):
                deltas.append(delta)
        choices = event.get("choices")
        if isinstance(choices, list) and choices:
            delta = choices[0].get("delta", {}) if isinstance(choices[0], dict) else {}
            if isinstance(delta, dict) and isinstance(delta.get("content"), str):
                deltas.append(delta["content"])
    return "".join(deltas)


def store_capture(request_id: str, app_id: str, requested_model: Optional[str], route: Any,
                  endpoint: str, request_body: Any, response_payload: Any, response_text: str,
                  status_code: int, latency_ms: float, usage_payload: Any = None) -> None:
    if not requested_model or not isinstance(request_body, dict):
        return
    try:
        request_json = json.dumps(request_body, ensure_ascii=False)
        response_json = json.dumps(response_payload, ensure_ascii=False) if response_payload is not None else None
        if len(request_json.encode("utf-8")) > MAX_CAPTURE_BYTES:
            return
        if response_json and len(response_json.encode("utf-8")) > MAX_CAPTURE_BYTES:
            response_json = None
    except (TypeError, ValueError):
        return
    input_tokens, output_tokens, cost = extract_usage(usage_payload)
    connection = connect_db()
    connection.execute(
        """INSERT OR REPLACE INTO gateway_captures
           (request_id,app_id,requested_model,provider,upstream_model,endpoint,request_json,response_json,
            response_text,status_code,latency_ms,input_tokens,output_tokens,cost_usd,includes_tool_result,created_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (request_id, app_id, requested_model, route["provider"], route["upstream_model"], endpoint,
         request_json, response_json, (response_text or "")[:MAX_CAPTURE_BYTES], int(status_code),
         round(latency_ms, 2), input_tokens, output_tokens, cost,
         int(request_has_tool_result(request_body)), utc_now()),
    )
    connection.execute(
        """DELETE FROM gateway_captures WHERE app_id=? AND id NOT IN
           (SELECT id FROM gateway_captures WHERE app_id=? ORDER BY id DESC LIMIT ?)""",
        (app_id, app_id, MAX_CAPTURE_RECORDS),
    )
    connection.commit()
    connection.close()


def parse_body() -> Any:
    if request.mimetype != "application/json":
        return None
    raw = request.get_data(cache=True, parse_form_data=False)
    if not raw:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


def endpoint_allowed(path: str) -> bool:
    normalized = path.strip("/")
    if not normalized.startswith("v1/"):
        return False
    subpath = normalized[3:]
    return any(subpath == prefix or subpath.startswith(prefix + "/") for prefix in ALLOWED_API_PREFIXES)


def upstream_url(base_url: str, path: str) -> str:
    normalized = path.strip("/")
    # Provider base URLs normally end in /v1; Azure's endpoint ends in /openai/v1.
    suffix = normalized[3:] if normalized.startswith("v1/") else normalized
    return base_url.rstrip("/") + "/" + suffix


def safe_upstream_headers(provider: str, secret: str, auth_header: str) -> Dict[str, str]:
    blocked = {
        "host", "content-length", "connection", "authorization", "api-key", "x-api-key",
        "transfer-encoding", "cookie", "proxy-authorization", "proxy-authenticate", "origin",
        "referer", "http-referer", "x-forwarded-for", "x-forwarded-host", "x-forwarded-proto",
    }
    headers = {key: value for key, value in request.headers.items() if key.lower() not in blocked}
    if auth_header == "api-key":
        headers["api-key"] = secret
    else:
        headers["Authorization"] = "Bearer " + secret
    if provider == "openrouter":
        default_referer = "http://localhost:" + os.getenv("PARENT_PORT", "5001")
        headers["HTTP-Referer"] = os.getenv("OPENROUTER_HTTP_REFERER", default_referer)
        headers.setdefault("X-Title", "Parent Model System")
    return headers


def response_headers(upstream: requests.Response) -> Dict[str, str]:
    excluded = {"content-length", "content-encoding", "transfer-encoding", "connection", "keep-alive", "set-cookie"}
    return {key: value for key, value in upstream.headers.items() if key.lower() not in excluded}


@gateway.get("/api/control/overview")
def control_overview():
    connection = connect_db()
    app_count = connection.execute("SELECT COUNT(*) FROM connected_apps WHERE active=1").fetchone()[0]
    route_count = connection.execute("SELECT COUNT(*) FROM model_routes WHERE enabled=1").fetchone()[0]
    today = datetime.now(timezone.utc).date().isoformat()
    usage = connection.execute(
        """SELECT COUNT(*) AS total, COALESCE(SUM(success),0) AS successes,
                  COALESCE(AVG(latency_ms),0) AS avg_latency,
                  SUM(cost_usd) AS cost, COUNT(cost_usd) AS cost_samples
           FROM gateway_requests WHERE substr(created_at,1,10)=?""", (today,),
    ).fetchone()
    connection.close()
    return jsonify({
        "apps": app_count, "routes": route_count, "requests_today": usage["total"],
        "success_rate": (usage["successes"] / usage["total"]) if usage["total"] else None,
        "avg_latency_ms": round(usage["avg_latency"], 2) if usage["total"] else None,
        "cost_today_usd": round(usage["cost"], 8) if usage["cost_samples"] else None,
        "cost_samples_today": usage["cost_samples"],
        "langfuse_configured": langfuse_configured(),
        "providers": provider_catalog(),
        "gateway_base_url": request.host_url.rstrip("/") + "/v1",
        "capture_content": os.getenv("LANGFUSE_CAPTURE_CONTENT", "false").lower() in {"1", "true", "yes"},
    })


@gateway.get("/api/control/apps")
def list_apps():
    connection = connect_db()
    apps = connection.execute("SELECT * FROM connected_apps ORDER BY created_at,id").fetchall()
    result = []
    for app_row in apps:
        routes = connection.execute(
            "SELECT * FROM model_routes WHERE app_id=? ORDER BY is_default DESC,id", (app_row["id"],)
        ).fetchall()
        result.append({
            "id": app_row["id"], "name": app_row["name"], "category": app_row["category"],
            "repository": app_row["repository"], "description": app_row["description"],
            "active": bool(app_row["active"]), "has_api_key": bool(app_row["token_hash"]),
            "created_at": app_row["created_at"],
            "routes": [{"requested_model": route["requested_model"], "provider": route["provider"],
                        "upstream_model": route["upstream_model"], "enabled": bool(route["enabled"]),
                        "max_output_tokens": route["max_output_tokens"],
                        "is_default": bool(route["is_default"]), "updated_at": route["updated_at"]}
                       for route in routes],
        })
    connection.close()
    return jsonify(apps=result)


@gateway.post("/api/control/apps")
def create_app():
    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "")).strip()
    category = str(data.get("category", "Other")).strip() or "Other"
    requested_model = str(data.get("requested_model", "")).strip()
    provider = str(data.get("provider", "")).strip().lower()
    upstream_model = str(data.get("upstream_model", "")).strip()
    repository = str(data.get("repository", "")).strip()
    if not name or not requested_model or not upstream_model:
        return jsonify(error="Enter the app name, requested model, and routed model."), 400
    if provider not in {"openai", "openrouter", "azure", "custom"}:
        return jsonify(error="Choose a supported provider."), 400
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:48] or "app"
    app_id = slug
    connection = connect_db()
    if connection.execute("SELECT 1 FROM connected_apps WHERE id=?", (app_id,)).fetchone():
        app_id = slug + "-" + secrets.token_hex(3)
    now = utc_now()
    connection.execute(
        "INSERT INTO connected_apps(id,name,category,repository,description,created_at) VALUES(?,?,?,?,?,?)",
        (app_id, name, category, repository, str(data.get("description", "")).strip(), now),
    )
    connection.execute(
        """INSERT INTO model_routes(app_id,requested_model,provider,upstream_model,enabled,is_default,updated_at)
           VALUES(?,?,?,?,1,1,?)""", (app_id, requested_model, provider, upstream_model, now),
    )
    connection.commit()
    connection.close()
    return jsonify(id=app_id), 201


@gateway.post("/api/control/apps/<app_id>/key")
def rotate_app_key(app_id: str):
    token = "pgw_live_" + secrets.token_urlsafe(32)
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    connection = connect_db()
    cursor = connection.execute("UPDATE connected_apps SET token_hash=? WHERE id=?", (digest, app_id))
    connection.commit()
    connection.close()
    if cursor.rowcount == 0:
        return jsonify(error="Application not found."), 404
    return jsonify(api_key=token, warning="Copy this key now. The system stores only its hash."), 201


@gateway.put("/api/control/apps/<app_id>/route")
def update_app_route(app_id: str):
    data = request.get_json(silent=True) or {}
    requested_model = str(data.get("requested_model", "")).strip()
    provider = str(data.get("provider", "")).strip().lower()
    upstream_model = str(data.get("upstream_model", "")).strip()
    enabled = bool(data.get("enabled", True))
    raw_max_output_tokens = data.get("max_output_tokens")
    try:
        max_output_tokens = int(raw_max_output_tokens) if raw_max_output_tokens not in (None, "") else None
    except (TypeError, ValueError):
        return jsonify(error="Max output tokens must be a positive integer."), 400
    if max_output_tokens is not None and max_output_tokens < 1:
        return jsonify(error="Max output tokens must be a positive integer."), 400
    if not requested_model or not upstream_model:
        return jsonify(error="Requested model and routed model are required."), 400
    if provider not in {"openai", "openrouter", "azure", "custom"}:
        return jsonify(error="Choose a supported provider."), 400
    connection = connect_db()
    if not connection.execute("SELECT 1 FROM connected_apps WHERE id=?", (app_id,)).fetchone():
        connection.close()
        return jsonify(error="Application not found."), 404
    connection.execute(
        """INSERT INTO model_routes(app_id,requested_model,provider,upstream_model,enabled,is_default,updated_at)
           VALUES(?,?,?,?,?,0,?)
           ON CONFLICT(app_id,requested_model) DO UPDATE SET
             provider=excluded.provider,upstream_model=excluded.upstream_model,
             enabled=excluded.enabled,updated_at=excluded.updated_at""",
        (app_id, requested_model, provider, upstream_model, int(enabled), utc_now()),
    )
    connection.execute(
        "UPDATE model_routes SET max_output_tokens=? WHERE app_id=? AND requested_model=?",
        (max_output_tokens, app_id, requested_model),
    )
    connection.commit()
    connection.close()
    return jsonify(ok=True)


@gateway.post("/api/control/apps/<app_id>/routes")
def create_app_route(app_id: str):
    data = request.get_json(silent=True) or {}
    requested_model = str(data.get("requested_model", "")).strip()
    provider = str(data.get("provider", "")).strip().lower()
    upstream_model = str(data.get("upstream_model", "")).strip()
    raw_max_output_tokens = data.get("max_output_tokens")
    try:
        max_output_tokens = int(raw_max_output_tokens) if raw_max_output_tokens not in (None, "") else None
    except (TypeError, ValueError):
        return jsonify(error="Max output tokens must be a positive integer."), 400
    if max_output_tokens is not None and max_output_tokens < 1:
        return jsonify(error="Max output tokens must be a positive integer."), 400
    if not requested_model or not upstream_model:
        return jsonify(error="App model ID and routed model are required."), 400
    if provider not in {"openai", "openrouter", "azure", "custom"}:
        return jsonify(error="Choose a supported provider."), 400
    connection = connect_db()
    if not connection.execute("SELECT 1 FROM connected_apps WHERE id=?", (app_id,)).fetchone():
        connection.close()
        return jsonify(error="Application not found."), 404
    try:
        connection.execute(
            """INSERT INTO model_routes
               (app_id,requested_model,provider,upstream_model,enabled,max_output_tokens,is_default,updated_at)
               VALUES(?,?,?,?,1,?,0,?)""",
            (app_id, requested_model, provider, upstream_model, max_output_tokens, utc_now()),
        )
        connection.commit()
    except sqlite3.IntegrityError:
        connection.close()
        return jsonify(error="This application already has a route for that model ID."), 409
    connection.close()
    return jsonify(ok=True), 201


@gateway.get("/api/control/requests")
def list_requests():
    try:
        limit = min(max(int(request.args.get("limit", 100)), 1), 500)
    except ValueError:
        limit = 100
    connection = connect_db()
    rows = connection.execute(
        """SELECT r.*,a.name AS app_name FROM gateway_requests r
           LEFT JOIN connected_apps a ON a.id=r.app_id ORDER BY r.id DESC LIMIT ?""", (limit,),
    ).fetchall()
    connection.close()
    return jsonify(requests=[dict(row) for row in rows])


@gateway.get("/api/control/health")
def control_health():
    return jsonify(ok=True, langfuse_configured=langfuse_configured(), providers=provider_catalog())


def rag_workspace_payload():
    connection = connect_db()
    setting = connection.execute(
        "SELECT enabled FROM gateway_capture_settings WHERE app_id=?", (RAG_APP_ID,)
    ).fetchone()
    policy_row = connection.execute(
        "SELECT * FROM app_quality_policies WHERE app_id=?", (RAG_APP_ID,)
    ).fetchone()
    captures = connection.execute(
        """SELECT id,request_id,requested_model,provider,upstream_model,endpoint,status_code,latency_ms,
                  input_tokens,output_tokens,cost_usd,includes_tool_result,created_at,
                  substr(response_text,1,180) AS output_preview
           FROM gateway_captures WHERE app_id=? ORDER BY id DESC LIMIT 30""", (RAG_APP_ID,),
    ).fetchall()
    evaluations = connection.execute(
        """SELECT id,capture_id,baseline_provider,baseline_model,candidate_provider,candidate_model,
                  baseline_quality_score,candidate_quality_score,recommendation,status,created_at,
                  promoted_at,rolled_back_at FROM rag_evaluations WHERE app_id=? ORDER BY id DESC LIMIT 20""",
        (RAG_APP_ID,),
    ).fetchall()
    routes = connection.execute(
        """SELECT requested_model,provider,upstream_model,enabled,max_output_tokens,is_default
           FROM model_routes WHERE app_id=? AND enabled=1 ORDER BY is_default DESC,id""", (RAG_APP_ID,),
    ).fetchall()
    connection.close()
    return {
        "capture_enabled": bool(setting and setting["enabled"]),
        "captures": [dict(row) for row in captures],
        "evaluations": [dict(row) for row in evaluations],
        "routes": [dict(row) for row in routes],
        "policy": dict(policy_row) if policy_row else {
            "minimum_quality_score": 4.0, "max_quality_drop": 0.0,
            "max_latency_regression_pct": 25.0, "max_cost_regression_pct": 25.0,
        },
    }


@gateway.get("/api/control/rag")
def rag_workspace():
    return jsonify(rag_workspace_payload())


@gateway.put("/api/control/rag/capture")
def set_rag_capture():
    data = request.get_json(silent=True) or {}
    enabled = data.get("enabled")
    if not isinstance(enabled, bool):
        return jsonify(error="Capture setting must be true or false."), 400
    connection = connect_db()
    connection.execute(
        """INSERT INTO gateway_capture_settings(app_id,enabled,updated_at) VALUES(?,?,?)
           ON CONFLICT(app_id) DO UPDATE SET enabled=excluded.enabled,updated_at=excluded.updated_at""",
        (RAG_APP_ID, int(enabled), utc_now()),
    )
    connection.commit()
    connection.close()
    return jsonify(ok=True, enabled=enabled)


@gateway.get("/api/control/rag/captures/<int:capture_id>")
def rag_capture_detail(capture_id: int):
    connection = connect_db()
    row = connection.execute(
        "SELECT * FROM gateway_captures WHERE id=? AND app_id=?", (capture_id, RAG_APP_ID)
    ).fetchone()
    connection.close()
    if row is None:
        return jsonify(error="Captured request not found."), 404
    result = dict(row)
    result["request"] = json.loads(result.pop("request_json"))
    result["response"] = json.loads(result.pop("response_json")) if result.get("response_json") else None
    return jsonify(capture=result)


@gateway.delete("/api/control/rag/captures")
def clear_rag_captures():
    connection = connect_db()
    connection.execute("DELETE FROM rag_evaluations WHERE app_id=?", (RAG_APP_ID,))
    connection.execute("DELETE FROM gateway_captures WHERE app_id=?", (RAG_APP_ID,))
    connection.commit()
    connection.close()
    return jsonify(ok=True)


@gateway.put("/api/control/rag/policy")
def update_rag_policy():
    data = request.get_json(silent=True) or {}
    try:
        minimum = float(data.get("minimum_quality_score", 4.0))
        drop = float(data.get("max_quality_drop", 0.0))
        latency = float(data.get("max_latency_regression_pct", 25.0))
        cost = float(data.get("max_cost_regression_pct", 25.0))
    except (TypeError, ValueError):
        return jsonify(error="Quality and regression thresholds must be numbers."), 400
    if not 1 <= minimum <= 5 or not 0 <= drop <= 4 or not 0 <= latency <= 1000 or not 0 <= cost <= 1000:
        return jsonify(error="Use quality scores from 1–5 and regression percentages from 0–1000."), 400
    connection = connect_db()
    connection.execute(
        """INSERT INTO app_quality_policies
           (app_id,minimum_quality_score,max_quality_drop,max_latency_regression_pct,max_cost_regression_pct,updated_at)
           VALUES(?,?,?,?,?,?) ON CONFLICT(app_id) DO UPDATE SET
             minimum_quality_score=excluded.minimum_quality_score,max_quality_drop=excluded.max_quality_drop,
             max_latency_regression_pct=excluded.max_latency_regression_pct,
             max_cost_regression_pct=excluded.max_cost_regression_pct,updated_at=excluded.updated_at""",
        (RAG_APP_ID, minimum, drop, latency, cost, utc_now()),
    )
    connection.commit()
    connection.close()
    return jsonify(ok=True)


@gateway.post("/api/control/rag/evaluations")
def create_rag_evaluation():
    data = request.get_json(silent=True) or {}
    try:
        capture_id = int(data.get("capture_id"))
    except (TypeError, ValueError):
        return jsonify(error="Choose a captured RAG request first."), 400
    candidate_provider = str(data.get("candidate_provider", "")).strip().lower()
    candidate_model = str(data.get("candidate_model", "")).strip()
    if candidate_provider not in {"openai", "openrouter", "azure", "custom"} or not candidate_model:
        return jsonify(error="Choose a configured candidate provider and enter its model or deployment ID."), 400
    candidate_base, candidate_secret, _, _ = provider_config(candidate_provider)
    if not candidate_base or not candidate_secret:
        return jsonify(error="The selected candidate provider has no credentials configured in the Parent System."), 400

    connection = connect_db()
    capture = connection.execute(
        "SELECT * FROM gateway_captures WHERE id=? AND app_id=?", (capture_id, RAG_APP_ID)
    ).fetchone()
    if capture is None:
        connection.close()
        return jsonify(error="Captured RAG request not found. Capture a real RAG request first."), 404
    if capture["endpoint"] not in {"responses", "chat/completions"}:
        connection.close()
        return jsonify(error="Only a captured text-generation request can be replayed."), 400
    if not capture["includes_tool_result"]:
        connection.close()
        return jsonify(error="This capture has no completed retrieval/tool result in its input. Select the final RAG model call after retrieval."), 409
    try:
        original_body = json.loads(capture["request_json"])
    except json.JSONDecodeError:
        connection.close()
        return jsonify(error="The saved RAG request is not valid JSON. Capture a fresh request."), 409
    requested_model = str(capture["requested_model"])
    baseline_route = connection.execute(
        """SELECT r.*,a.name AS app_name FROM model_routes r JOIN connected_apps a ON a.id=r.app_id
           WHERE r.app_id=? AND r.requested_model=? AND r.enabled=1""", (RAG_APP_ID, requested_model),
    ).fetchone()
    if baseline_route is None:
        connection.close()
        return jsonify(error="The captured request's route is no longer enabled. Repair the route, then capture a new baseline."), 409
    if (capture["provider"] != baseline_route["provider"]
            or capture["upstream_model"] != baseline_route["upstream_model"]):
        connection.close()
        return jsonify(error="The RAG route changed after this baseline was captured. Capture a fresh request on the current route."), 409
    if (candidate_provider == capture["provider"]
            and candidate_model.casefold() == capture["upstream_model"].casefold()):
        connection.close()
        return jsonify(error="Candidate is the same provider deployment as the captured baseline."), 400

    created_at = utc_now()
    cursor = connection.execute(
        """INSERT INTO rag_evaluations
           (app_id,capture_id,baseline_provider,baseline_model,baseline_output,baseline_status_code,
            baseline_latency_ms,baseline_input_tokens,baseline_output_tokens,baseline_cost_usd,
            candidate_provider,candidate_model,candidate_status_code,recommendation,status,
            previous_provider,previous_model,created_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,'Candidate replay is running.','running',?,?,?)""",
        (RAG_APP_ID, capture_id, capture["provider"], capture["upstream_model"], capture["response_text"],
         capture["status_code"], capture["latency_ms"], capture["input_tokens"], capture["output_tokens"],
         capture["cost_usd"], candidate_provider, candidate_model, 0, baseline_route["provider"],
         baseline_route["upstream_model"], created_at),
    )
    evaluation_id = cursor.lastrowid
    connection.commit()
    route = dict(baseline_route)
    route.update(provider=candidate_provider, upstream_model=candidate_model)
    connection.close()

    result = run_gateway_replay(
        app_id=RAG_APP_ID, requested_model=requested_model, endpoint=capture["endpoint"],
        request_body=original_body, route=route,
        metadata={"evaluation_id": evaluation_id, "condition": "candidate", "capture_id": capture_id},
    )
    success = 200 <= result["status_code"] < 400 and bool(result["output_text"].strip())
    status = "pending_review" if success else "failed"
    recommendation = ("Replay succeeded. Human quality review and threshold checks are required before promotion."
                     if success else "Candidate replay failed or returned no text; promotion is blocked.")
    connection = connect_db()
    connection.execute(
        """UPDATE rag_evaluations SET candidate_output=?,candidate_status_code=?,candidate_latency_ms=?,
           candidate_input_tokens=?,candidate_output_tokens=?,candidate_cost_usd=?,recommendation=?,status=?
           WHERE id=?""",
        (result["output_text"], result["status_code"], result["latency_ms"], result["input_tokens"],
         result["output_tokens"], result["cost_usd"], recommendation, status, evaluation_id),
    )
    connection.commit()
    connection.close()
    return jsonify(evaluation=rag_evaluation_detail(evaluation_id)), 201


def rag_evaluation_detail(evaluation_id: int) -> Optional[Dict[str, Any]]:
    connection = connect_db()
    row = connection.execute(
        "SELECT * FROM rag_evaluations WHERE id=? AND app_id=?", (evaluation_id, RAG_APP_ID)
    ).fetchone()
    connection.close()
    return dict(row) if row else None


@gateway.get("/api/control/rag/evaluations/<int:evaluation_id>")
def get_rag_evaluation(evaluation_id: int):
    result = rag_evaluation_detail(evaluation_id)
    if result is None:
        return jsonify(error="RAG evaluation not found."), 404
    return jsonify(evaluation=result)


def rag_review_decision(evaluation: Dict[str, Any], policy: Dict[str, Any]) -> tuple[bool, list[str]]:
    reasons = []
    if not 200 <= int(evaluation["baseline_status_code"]) < 400:
        reasons.append("The captured baseline request did not succeed.")
    if not 200 <= int(evaluation["candidate_status_code"]) < 400 or not (evaluation.get("candidate_output") or "").strip():
        reasons.append("The candidate request failed or returned no answer.")
    baseline_score = evaluation.get("baseline_quality_score")
    candidate_score = evaluation.get("candidate_quality_score")
    if baseline_score is None or candidate_score is None:
        reasons.append("Both outputs need human quality scores from 1 to 5.")
    else:
        if candidate_score < float(policy["minimum_quality_score"]):
            reasons.append("Candidate quality is below the configured minimum.")
        if baseline_score - candidate_score > float(policy["max_quality_drop"]):
            reasons.append("Candidate quality regression exceeds the allowed drop.")
    baseline_latency = evaluation.get("baseline_latency_ms")
    candidate_latency = evaluation.get("candidate_latency_ms")
    if baseline_latency is None or candidate_latency is None:
        reasons.append("Latency data is missing for one side of the comparison.")
    elif baseline_latency > 0:
        regression = max(0.0, (candidate_latency - baseline_latency) / baseline_latency * 100)
        if regression > float(policy["max_latency_regression_pct"]):
            reasons.append("Candidate latency regression exceeds the configured limit.")
    baseline_cost = evaluation.get("baseline_cost_usd")
    candidate_cost = evaluation.get("candidate_cost_usd")
    if baseline_cost is None or candidate_cost is None:
        reasons.append("Cost is unknown. Add measured per-request cost from Langfuse/provider usage before promotion.")
    elif baseline_cost > 0:
        regression = max(0.0, (candidate_cost - baseline_cost) / baseline_cost * 100)
        if regression > float(policy["max_cost_regression_pct"]):
            reasons.append("Candidate cost regression exceeds the configured limit.")
    elif candidate_cost > 0:
        reasons.append("Baseline cost is zero, so the relative cost regression cannot be evaluated.")
    return not reasons, reasons


@gateway.post("/api/control/rag/evaluations/<int:evaluation_id>/review")
def review_rag_evaluation(evaluation_id: int):
    data = request.get_json(silent=True) or {}
    try:
        baseline_score = float(data.get("baseline_quality_score"))
        candidate_score = float(data.get("candidate_quality_score"))
    except (TypeError, ValueError):
        return jsonify(error="Enter a human quality score for both baseline and candidate (1–5)."), 400
    if not 1 <= baseline_score <= 5 or not 1 <= candidate_score <= 5:
        return jsonify(error="Quality scores must be from 1 to 5."), 400
    overrides = {}
    for key in ("baseline_cost_usd", "candidate_cost_usd"):
        value = data.get(key)
        if value not in (None, ""):
            try:
                value = float(value)
            except (TypeError, ValueError):
                return jsonify(error="Cost overrides must be non-negative numbers."), 400
            if value < 0:
                return jsonify(error="Cost overrides must be non-negative numbers."), 400
            overrides[key] = value
    connection = connect_db()
    evaluation = connection.execute(
        "SELECT * FROM rag_evaluations WHERE id=? AND app_id=?", (evaluation_id, RAG_APP_ID)
    ).fetchone()
    policy = connection.execute(
        "SELECT * FROM app_quality_policies WHERE app_id=?", (RAG_APP_ID,)
    ).fetchone()
    if evaluation is None:
        connection.close()
        return jsonify(error="RAG evaluation not found."), 404
    values = dict(evaluation)
    values.update(overrides)
    values["baseline_quality_score"] = baseline_score
    values["candidate_quality_score"] = candidate_score
    passed, reasons = rag_review_decision(values, dict(policy))
    status = "approved" if passed else "rejected"
    recommendation = ("PASS — candidate meets the configured quality, latency, and cost policy. Ready for explicit promotion."
                     if passed else "BLOCKED — " + " ".join(reasons))
    connection.execute(
        """UPDATE rag_evaluations SET baseline_quality_score=?,candidate_quality_score=?,baseline_cost_usd=?,
           candidate_cost_usd=?,recommendation=?,status=?,reviewed_at=? WHERE id=?""",
        (baseline_score, candidate_score, values.get("baseline_cost_usd"), values.get("candidate_cost_usd"),
         recommendation, status, utc_now(), evaluation_id),
    )
    connection.commit()
    connection.close()
    return jsonify(evaluation=rag_evaluation_detail(evaluation_id))


@gateway.post("/api/control/rag/evaluations/<int:evaluation_id>/promote")
def promote_rag_evaluation(evaluation_id: int):
    connection = connect_db()
    evaluation = connection.execute(
        "SELECT * FROM rag_evaluations WHERE id=? AND app_id=?", (evaluation_id, RAG_APP_ID)
    ).fetchone()
    if evaluation is None:
        connection.close()
        return jsonify(error="RAG evaluation not found."), 404
    if evaluation["status"] != "approved":
        connection.close()
        return jsonify(error="This candidate has not passed the human review and configured quality, latency, and cost gates."), 409
    current = connection.execute(
        """SELECT provider,upstream_model FROM model_routes WHERE app_id=? AND requested_model=? AND enabled=1""",
        (RAG_APP_ID, connection.execute("SELECT requested_model FROM gateway_captures WHERE id=?", (evaluation["capture_id"],)).fetchone()[0]),
    ).fetchone()
    if (current is None or current["provider"] != evaluation["baseline_provider"]
            or current["upstream_model"] != evaluation["baseline_model"]):
        connection.close()
        return jsonify(error="The active baseline route changed since evaluation. Compare again before promoting."), 409
    routes = connection.execute(
        """SELECT id,requested_model,provider,upstream_model FROM model_routes
           WHERE app_id=? AND enabled=1 AND provider=? AND upstream_model=?
             AND lower(requested_model) NOT LIKE 'text-embedding-%'""",
        (RAG_APP_ID, evaluation["baseline_provider"], evaluation["baseline_model"]),
    ).fetchall()
    if not routes:
        connection.close()
        return jsonify(error="No active RAG generation aliases still point to the evaluated baseline."), 409
    previous_routes = [dict(row) for row in routes]
    for route in routes:
        connection.execute(
            "UPDATE model_routes SET provider=?,upstream_model=?,updated_at=? WHERE id=?",
            (evaluation["candidate_provider"], evaluation["candidate_model"], utc_now(), route["id"]),
        )
    connection.execute(
        """UPDATE rag_evaluations SET status='promoted',promoted_at=?,previous_routes_json=? WHERE id=?""",
        (utc_now(), json.dumps(previous_routes), evaluation_id),
    )
    connection.commit()
    connection.close()
    return jsonify(ok=True, updated_aliases=[route["requested_model"] for route in previous_routes],
                   evaluation=rag_evaluation_detail(evaluation_id))


@gateway.post("/api/control/rag/evaluations/<int:evaluation_id>/rollback")
def rollback_rag_evaluation(evaluation_id: int):
    connection = connect_db()
    evaluation = connection.execute(
        "SELECT * FROM rag_evaluations WHERE id=? AND app_id=?", (evaluation_id, RAG_APP_ID)
    ).fetchone()
    if evaluation is None:
        connection.close()
        return jsonify(error="RAG evaluation not found."), 404
    if evaluation["status"] != "promoted":
        connection.close()
        return jsonify(error="Only a promoted RAG evaluation can be rolled back."), 409
    previous_routes = json.loads(evaluation["previous_routes_json"] or "[]")
    for route in previous_routes:
        current = connection.execute(
            "SELECT provider,upstream_model FROM model_routes WHERE id=? AND app_id=?",
            (route["id"], RAG_APP_ID),
        ).fetchone()
        if (current is None or current["provider"] != evaluation["candidate_provider"]
                or current["upstream_model"] != evaluation["candidate_model"]):
            connection.close()
            return jsonify(error="At least one route has changed since promotion. Refusing to overwrite a newer edit."), 409
    for route in previous_routes:
        connection.execute(
            "UPDATE model_routes SET provider=?,upstream_model=?,updated_at=? WHERE id=?",
            (route["provider"], route["upstream_model"], utc_now(), route["id"]),
        )
    connection.execute(
        "UPDATE rag_evaluations SET status='rolled_back',rolled_back_at=? WHERE id=?",
        (utc_now(), evaluation_id),
    )
    connection.commit()
    connection.close()
    return jsonify(ok=True, restored_aliases=[route["requested_model"] for route in previous_routes],
                   evaluation=rag_evaluation_detail(evaluation_id))


@gateway.route("/v1/<path:api_path>", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
def proxy_api(api_path: str):
    if request.method == "OPTIONS":
        return Response(status=204, headers={"Access-Control-Allow-Methods": "GET,POST,PUT,PATCH,DELETE,OPTIONS",
                                             "Access-Control-Allow-Headers": "Authorization,Content-Type,OpenAI-Beta"})
    if not endpoint_allowed("v1/" + api_path):
        return jsonify(error={"message": "This API path is not enabled on the parent gateway.", "type": "invalid_request_error"}), 404

    app_row = authenticate_app()
    if app_row is None:
        return jsonify(error={"message": "A valid application gateway key is required.", "type": "authentication_error"}), 401
    body = parse_body()
    requested_model = body.get("model") if isinstance(body, dict) else None
    original_request_body = json.loads(json.dumps(body)) if isinstance(body, (dict, list)) else body
    route = model_route(app_row["id"], str(requested_model) if requested_model is not None else None)
    if route is None:
        message = "No enabled model route matches this app and requested model." if requested_model else "This app has no enabled default model route."
        return jsonify(error={"message": message, "type": "invalid_request_error"}), 400
    base_url, secret, auth_header, _ = provider_config(route["provider"])
    if not base_url or not secret:
        return jsonify(error={"message": "The routed provider is not configured on the parent system.", "type": "configuration_error"}), 503

    path = "v1/" + api_path
    if path == "v1/models":
        connection = connect_db()
        route_rows = connection.execute(
            "SELECT requested_model FROM model_routes WHERE app_id=? AND enabled=1 ORDER BY requested_model",
            (app_row["id"],),
        ).fetchall()
        connection.close()
        return jsonify(object="list", data=[{"id": row["requested_model"], "object": "model", "owned_by": "parent-system"} for row in route_rows])

    outbound_body = request.get_data(cache=True)
    if isinstance(body, dict) and requested_model is not None:
        body["model"] = route["upstream_model"]
        azure_gpt5_chat = (
            api_path == "chat/completions"
            and route["provider"] == "azure"
            and str(route["upstream_model"]).lower().startswith("gpt-5")
        )
        if azure_gpt5_chat:
            # Azure GPT-5 Chat Completions requires max_completion_tokens. Older
            # child SDKs may still send max_tokens, so adapt only this parameter.
            legacy_limit = body.pop("max_tokens", None)
            if legacy_limit is not None and body.get("max_completion_tokens") is None:
                body["max_completion_tokens"] = legacy_limit
        if api_path == "chat/completions" and route["provider"] == "azure" and body.get("stream"):
            # Azure emits token usage in a final SSE chunk only when requested.
            stream_options = body.get("stream_options")
            if stream_options is None:
                stream_options = {}
                body["stream_options"] = stream_options
            if isinstance(stream_options, dict) and "include_usage" not in stream_options:
                stream_options["include_usage"] = True
        max_output_tokens = route["max_output_tokens"]
        if max_output_tokens and api_path in {"responses", "chat/completions"}:
            fields = (["max_output_tokens"] if api_path == "responses" else
                      ["max_completion_tokens"] if azure_gpt5_chat else
                      ["max_completion_tokens", "max_tokens"])
            present = False
            for field in fields:
                requested_limit = body.get(field)
                if requested_limit is None:
                    continue
                present = True
                try:
                    body[field] = min(int(requested_limit), int(max_output_tokens))
                except (TypeError, ValueError):
                    continue
            if not present:
                default_limit = ("max_output_tokens" if api_path == "responses" else
                                 "max_completion_tokens" if azure_gpt5_chat else "max_tokens")
                body[default_limit] = int(max_output_tokens)
        outbound_body = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    url = upstream_url(base_url, path)
    headers = safe_upstream_headers(route["provider"], secret, auth_header)
    request_id = "gw_" + secrets.token_hex(12)
    started = perf_counter()
    is_model_call = api_path in {"chat/completions", "responses", "embeddings"}
    evaluation_capture = (not _INTERNAL_EVALUATION.get() and capture_enabled(app_row["id"])
                          and api_path in {"chat/completions", "responses"})
    context_factory = lambda: telemetry_context(app_row["name"], request_id, route, body, api_path) if is_model_call else nullcontext(None)
    try:
        upstream = requests.request(
            method=request.method, url=url, params=request.args, data=outbound_body or None,
            headers=headers, timeout=HTTP_TIMEOUT, stream=bool(isinstance(body, dict) and body.get("stream")),
        )
        elapsed_ms = (perf_counter() - started) * 1000
        if isinstance(body, dict) and body.get("stream") and upstream.ok:
            langfuse_capture = os.getenv("LANGFUSE_CAPTURE_CONTENT", "false").strip().lower() in {"1", "true", "yes"}
            captured = bytearray()
            parser_buffer = bytearray()
            stream_usage = {}
            stream_error = None

            @stream_with_context
            def relay():
                nonlocal parser_buffer
                nonlocal stream_error
                with context_factory() as observation:
                    try:
                        for chunk in upstream.iter_content(chunk_size=8192):
                            if not chunk:
                                continue
                            parser_buffer.extend(chunk)
                            while b"\n" in parser_buffer:
                                line, _, remainder = parser_buffer.partition(b"\n")
                                parser_buffer = bytearray(remainder)
                                line = line.strip()
                                if line.startswith(b"data:"):
                                    event_data = line[5:].strip()
                                    if event_data and event_data != b"[DONE]":
                                        try:
                                            parsed_event = json.loads(event_data.decode("utf-8"))
                                            if isinstance(parsed_event, dict):
                                                event_usage = parsed_event.get("usage")
                                                if not isinstance(event_usage, dict):
                                                    response_event = parsed_event.get("response")
                                                    if isinstance(response_event, dict):
                                                        event_usage = response_event.get("usage")
                                                if isinstance(event_usage, dict):
                                                    stream_usage.update(event_usage)
                                        except (UnicodeDecodeError, json.JSONDecodeError):
                                            pass
                            if len(parser_buffer) > 16_384:
                                del parser_buffer[:-8192]
                            if (langfuse_capture or evaluation_capture) and len(captured) < MAX_TELEMETRY_CONTENT_CHARS:
                                captured.extend(chunk[:MAX_TELEMETRY_CONTENT_CHARS - len(captured)])
                            yield chunk
                        final_line = bytes(parser_buffer).strip()
                        if final_line.startswith(b"data:"):
                            event_data = final_line[5:].strip()
                            if event_data and event_data != b"[DONE]":
                                try:
                                    parsed_event = json.loads(event_data.decode("utf-8"))
                                    if isinstance(parsed_event, dict):
                                        event_usage = parsed_event.get("usage")
                                        if not isinstance(event_usage, dict):
                                            response_event = parsed_event.get("response")
                                            if isinstance(response_event, dict):
                                                event_usage = response_event.get("usage")
                                        if isinstance(event_usage, dict):
                                            stream_usage.update(event_usage)
                                except (UnicodeDecodeError, json.JSONDecodeError):
                                    pass
                    except requests.RequestException:
                        stream_error = "upstream_stream_error"
                        yield b'data: {"error":{"message":"The provider stream was interrupted.","type":"upstream_error"}}\n\n'
                    finally:
                        final_ms = (perf_counter() - started) * 1000
                        raw_stream = bytes(captured)
                        output = raw_stream.decode("utf-8", errors="replace") if langfuse_capture else {"streamed": True, "content_capture": False}
                        input_tokens, output_tokens, cost = extract_usage({"usage": stream_usage})
                        usage_details = {}
                        if input_tokens is not None:
                            usage_details["input"] = input_tokens
                        if output_tokens is not None:
                            usage_details["output"] = output_tokens
                        try:
                            if observation is not None:
                                observation.update(output=output, usage_details=usage_details or None,
                                                   cost_details={"total": cost} if cost is not None else None,
                                                   level="ERROR" if stream_error else "DEFAULT",
                                                   status_message="The provider stream was interrupted." if stream_error else None,
                                                   metadata={"status_code": upstream.status_code,
                                                             "latency_ms": round(final_ms, 2),
                                                             "request_id": request_id})
                        except Exception:
                            pass
                        record_request(request_id, app_row["id"], str(requested_model) if requested_model else None,
                                       route, api_path, upstream.status_code, final_ms,
                                       {"usage": stream_usage} if stream_usage else None, stream_error)
                        if evaluation_capture:
                            store_capture(request_id, app_row["id"], str(requested_model), route, api_path,
                                          original_request_body, {"streamed": True},
                                          response_text_from_stream(raw_stream), upstream.status_code, final_ms,
                                          {"usage": stream_usage})
                        upstream.close()

            return Response(relay(), status=upstream.status_code, headers=response_headers(upstream))

        with context_factory() as observation:
            response_content = upstream.content
            parsed_response = None
            try:
                parsed_response = json.loads(response_content.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                pass
            if observation is not None:
                capture = os.getenv("LANGFUSE_CAPTURE_CONTENT", "false").strip().lower() in {"1", "true", "yes"}
                output = parsed_response if capture else {"status_code": upstream.status_code, "content_capture": False}
                usage = parsed_response.get("usage", {}) if isinstance(parsed_response, dict) else {}
                token_usage = {}
                input_tokens, output_tokens, cost = extract_usage(parsed_response)
                if input_tokens is not None:
                    token_usage["input"] = input_tokens
                if output_tokens is not None:
                    token_usage["output"] = output_tokens
                cost_details = {"total": cost} if cost is not None else None
                try:
                    observation.update(output=output, usage_details=token_usage or None,
                                       cost_details=cost_details,
                                       level="ERROR" if not upstream.ok else "DEFAULT",
                                       status_message=None if upstream.ok else f"Provider returned HTTP {upstream.status_code}",
                                       metadata={"status_code": upstream.status_code, "latency_ms": round(elapsed_ms, 2),
                                                 "request_id": request_id})
                except Exception:
                    pass
            record_request(request_id, app_row["id"], str(requested_model) if requested_model else None,
                           route, api_path, upstream.status_code, elapsed_ms, parsed_response,
                           None if upstream.ok else f"upstream_http_{upstream.status_code}")
            if evaluation_capture:
                store_capture(request_id, app_row["id"], str(requested_model), route, api_path,
                              original_request_body, parsed_response, response_output_text(parsed_response),
                              upstream.status_code, elapsed_ms, parsed_response)
            return Response(response_content, status=upstream.status_code, headers=response_headers(upstream))
    except requests.Timeout:
        elapsed_ms = (perf_counter() - started) * 1000
        record_request(request_id, app_row["id"], str(requested_model) if requested_model else None,
                       route, api_path, 504, elapsed_ms, None, "upstream_timeout")
        return jsonify(error={"message": "The model provider timed out.", "type": "upstream_timeout", "request_id": request_id}), 504
    except requests.RequestException as exc:
        elapsed_ms = (perf_counter() - started) * 1000
        record_request(request_id, app_row["id"], str(requested_model) if requested_model else None,
                       route, api_path, 502, elapsed_ms, None, "upstream_connection_error")
        return jsonify(error={"message": "The parent system could not reach the configured model provider.",
                              "type": "upstream_connection_error", "request_id": request_id}), 502


def run_gateway_replay(*, app_id: str, requested_model: str, endpoint: str,
                       request_body: Dict[str, Any], route: Dict[str, Any],
                       metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Replay one saved child request through the same gateway proxy handler."""
    if endpoint not in {"responses", "chat/completions"}:
        raise ValueError("Only Responses and Chat Completions requests can be replayed.")
    body = json.loads(json.dumps(request_body))
    body["model"] = requested_model
    evaluation = {"app_id": app_id, "requested_model": requested_model, "route": route, **metadata}
    token = _INTERNAL_EVALUATION.set(evaluation)
    started = perf_counter()
    try:
        flask_app = current_app._get_current_object()
        with flask_app.test_request_context(
            "/v1/" + endpoint, method="POST", json=body,
            headers={"Authorization": "Bearer internal-parent-evaluation"},
            environ_base={"REMOTE_ADDR": "127.0.0.1"},
        ):
            response = proxy_api(endpoint)
            raw = response.get_data()
            status_code = response.status_code
    finally:
        _INTERNAL_EVALUATION.reset(token)
    parsed = None
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        pass
    streamed = isinstance(body, dict) and bool(body.get("stream"))
    output_text = response_text_from_stream(raw) if streamed else response_output_text(parsed)
    if not output_text and isinstance(parsed, dict) and isinstance(parsed.get("error"), dict):
        output_text = str(parsed["error"].get("message", ""))
    usage = parsed if isinstance(parsed, dict) else None
    if streamed:
        usage_payload = {}
        for line in raw.decode("utf-8", errors="replace").splitlines():
            if not line.startswith("data:"):
                continue
            try:
                event = json.loads(line[5:].strip())
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            current_usage = event.get("usage")
            if not isinstance(current_usage, dict) and isinstance(event.get("response"), dict):
                current_usage = event["response"].get("usage")
            if isinstance(current_usage, dict):
                usage_payload.update(current_usage)
        usage = {"usage": usage_payload}
    input_tokens, output_tokens, cost = extract_usage(usage)
    return {
        "status_code": status_code,
        "output_text": output_text,
        "latency_ms": round((perf_counter() - started) * 1000, 2),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": cost,
    }


def register_gateway(app) -> None:
    init_gateway_database()
    app.register_blueprint(gateway)

