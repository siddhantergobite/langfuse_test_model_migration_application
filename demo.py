"""Local parent model gateway, control dashboard, and Langfuse evaluation workspace."""

from dotenv import load_dotenv
load_dotenv()

import json
import os
import re
import sqlite3
import unicodedata
from datetime import datetime
from pathlib import Path
from time import perf_counter, sleep
from typing import Any, Optional

from flask import Flask, Response, abort, jsonify, request
from langfuse import Evaluation, get_client
from openai import OpenAI
from parent_gateway import register_gateway

OPENROUTER_URL = "https://openrouter.ai/api/v1"
BASELINE = os.getenv("BASELINE_MODEL", os.getenv("AZURE_OPENAI_MODEL", "gpt-5-mini"))
CANDIDATE = os.getenv("CANDIDATE_MODEL", os.getenv("AZURE_OPENAI_MODEL", "gpt-5-mini"))
BASELINE_PROVIDER = os.getenv("BASELINE_PROVIDER", "azure").strip().lower()
CANDIDATE_PROVIDER = os.getenv("CANDIDATE_PROVIDER", "azure").strip().lower()
DATA_DIR = Path(os.getenv("LOCALAPPDATA", str(Path.home() / ".local" / "share"))) / "ModelTransitionLab"
DB_PATH = DATA_DIR / "evaluation.sqlite3"
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = int(os.getenv("PARENT_MAX_REQUEST_BYTES", str(25 * 1024 * 1024)))
register_gateway(app)

SEEDS = [
    ("Extract a profile", "Return only JSON with name, age, role, and company: Alice Example, 30, Engineer at Example Corp.", {"name": "Alice Example", "age": 30, "role": "Engineer", "company": "Example Corp"}),
    ("Calculate a result", "Calculate 17 * 19 + 4. Return only a JSON number.", 327),
    ("Sort names", "Sort alphabetically and return only a JSON array: Mira, David, Asha.", ["Asha", "David", "Mira"]),
    ("Classify sentiment", "Return one JSON string, positive, neutral, or negative: The support team solved my issue quickly and kindly.", "positive"),
]

def db():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(DB_PATH), timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def initialize_database():
    connection = db()
    connection.executescript("""
      CREATE TABLE IF NOT EXISTS test_cases (
        id INTEGER PRIMARY KEY, name TEXT NOT NULL, prompt TEXT NOT NULL,
        expected_output TEXT NOT NULL, created_at TEXT NOT NULL
      );
      CREATE TABLE IF NOT EXISTS evaluation_runs (
        id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, baseline_model TEXT NOT NULL,
        candidate_model TEXT NOT NULL, system_prompt TEXT NOT NULL,
        examples_json TEXT NOT NULL, tools_json TEXT NOT NULL, temperature REAL NOT NULL,
        max_tokens INTEGER NOT NULL, case_count INTEGER NOT NULL, status TEXT NOT NULL
      );
      CREATE TABLE IF NOT EXISTS model_results (
        id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL REFERENCES evaluation_runs(id),
        case_id INTEGER NOT NULL REFERENCES test_cases(id), condition TEXT NOT NULL,
        model TEXT NOT NULL, answer TEXT, tool_calls_json TEXT NOT NULL DEFAULT '[]',
        request_success INTEGER, valid_json INTEGER, reference_match INTEGER,
        normalized_match INTEGER, latency_ms REAL, input_tokens INTEGER,
        output_tokens INTEGER, cost_usd REAL, error TEXT, trace_id TEXT,
        UNIQUE(run_id, case_id, condition)
      );
    """)
    if connection.execute("SELECT COUNT(*) FROM test_cases").fetchone()[0] == 0:
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        connection.executemany(
            "INSERT INTO test_cases(name,prompt,expected_output,created_at) VALUES(?,?,?,?)",
            [(name, prompt, json.dumps(expected), now) for name, prompt, expected in SEEDS],
        )
    connection.commit()
    connection.close()


def parse_json(text: str):
    text = (text or "").strip()
    match = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.I | re.S)
    if match:
        text = match.group(1)
    try:
        return True, json.loads(text)
    except json.JSONDecodeError:
        return False, None


def norm(value):
    if isinstance(value, dict):
        return {key: norm(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [norm(item) for item in value]
    if isinstance(value, str):
        return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value).casefold()).strip().strip(" .,;:!?\"'")
    return value


def equal(left, right, normalized=False):
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return left == right
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(equal(left[k], right[k], normalized) for k in left)
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(equal(a, b, normalized) for a, b in zip(left, right))
    if isinstance(left, str) and isinstance(right, str):
        return norm(left) == norm(right) if normalized else left == right
    return type(left) is type(right) and left == right


def messages(item):
    result = []
    system = "\n\n".join(x.strip() for x in (item.get("system_prompt", ""), item.get("instructions", "")) if x and x.strip())
    if system:
        result.append({"role": "system", "content": system})
    for example in item.get("examples", []):
        user = example.get("input", example.get("user", example.get("scenario")))
        answer = example.get("output", example.get("assistant", example.get("expected_output")))
        if user is not None and answer is not None:
            result.extend(({"role": "user", "content": str(user)}, {"role": "assistant", "content": str(answer)}))
    result.append({"role": "user", "content": item["prompt"]})
    return result


def format_tools(tools):
    formatted = []
    for index, tool in enumerate(tools, 1):
        function = tool.get("function") if isinstance(tool.get("function"), dict) else tool
        if "function" in tool and tool.get("type") != "function":
            raise ValueError("Tool %d must have type 'function'." % index)
        name, params = function.get("name"), function.get("parameters")
        if not isinstance(name, str) or not name.strip() or not isinstance(params, dict) or params.get("type") != "object":
            raise ValueError("Tool %d needs a name and object-valued parameters." % index)
        spec = {"name": name.strip(), "parameters": params}
        if function.get("description"):
            spec["description"] = str(function["description"])
        if isinstance(function.get("strict"), bool):
            spec["strict"] = function["strict"]
        formatted.append({"type": "function", "function": spec})
    return formatted


def run_local_tool(name, args):
    if name != "calculate_budget":
        raise ValueError("No local implementation is enabled for tool '%s'." % name)
    if not isinstance(args, dict):
        raise ValueError("calculate_budget arguments must be an object.")
    total, expenses = args.get("total_budget"), args.get("expenses")
    if any(isinstance(x, bool) or not isinstance(x, (int, float)) for x in (total, expenses)):
        raise ValueError("calculate_budget needs numeric total_budget and expenses.")
    return total - expenses


def make_provider_client(provider):
    if provider == "openrouter":
        api_key = os.getenv("OPENROUTER_API_KEY")
        base_url = os.getenv("OPENROUTER_BASE_URL", OPENROUTER_URL)
    elif provider == "azure":
        api_key = os.getenv("AZURE_OPENAI_API_KEY")
        endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "").strip().rstrip("/")
        if not endpoint:
            raise ValueError("AZURE_OPENAI_ENDPOINT is missing from .env.")
        if endpoint.endswith("/openai/v1"):
            base_url = endpoint + "/"
        elif endpoint.endswith("/openai"):
            base_url = endpoint + "/v1/"
        else:
            base_url = endpoint + "/openai/v1/"
    else:
        raise ValueError("Provider must be 'openrouter' or 'azure'.")

    if not api_key:
        variable = "AZURE_OPENAI_API_KEY" if provider == "azure" else "OPENROUTER_API_KEY"
        raise ValueError(f"{variable} is missing from .env.")
    return OpenAI(base_url=base_url, api_key=api_key)


def model_task(model, condition, provider, client, langfuse, temperature, max_tokens):
    def task(*, item, **kwargs):
        data = item.get("input", {}) if isinstance(item, dict) else item.input
        chat = messages(data)
        tools = data.get("tools", [])
        model_slug = model.lower().rsplit("/", 1)[-1]
        is_gpt5 = model_slug.startswith("gpt-5")
        is_gpt6 = model_slug.startswith("gpt-6")
        request_data = {"model": model}
        if is_gpt5 or is_gpt6:
            # Keep GPT-5/6 requests on their reasoning-compatible token parameters.
            request_data["max_completion_tokens"] = max_tokens
            model_parameters = {"max_completion_tokens": max_tokens}
            if is_gpt6:
                reasoning_effort = "none" if tools else "medium"
                request_data["reasoning_effort"] = reasoning_effort
                model_parameters["reasoning_effort"] = reasoning_effort
        else:
            request_data.update(temperature=temperature, max_tokens=max_tokens)
            model_parameters = {"temperature": temperature, "max_tokens": max_tokens}
        if provider == "openrouter":
            request_data["extra_body"] = {"usage": {"include": True}}
        if tools:
            request_data["tools"] = tools
        calls, elapsed_total, token_in, token_out, cost_total = [], 0.0, 0, 0, 0.0
        saw_in = saw_out = saw_cost = False
        try:
            for turn in range(2):
                request_data["messages"] = chat
                started = perf_counter()
                with langfuse.start_as_current_observation(
                    as_type="generation", name=f"{condition} model call {turn + 1}", model=model,
                    model_parameters=model_parameters,
                    input={"messages": chat, "tools": tools},
                    metadata={"condition": condition, "provider": provider,
                              "case_id": data["case_id"], "turn": turn + 1},
                ) as generation:
                    try:
                        response = client.chat.completions.create(**request_data)
                        if not getattr(response, "choices", None):
                            generation.update(metadata={"empty_choices_retry": True})
                            sleep(0.25)
                            response = client.chat.completions.create(**request_data)
                    except Exception as exc:
                        generation.update(level="ERROR", status_message=str(exc), output={"error": str(exc)})
                        raise
                    elapsed = (perf_counter() - started) * 1000
                    elapsed_total += elapsed
                    if not response.choices:
                        message_error = "Provider returned no completion choices after one retry."
                        generation.update(level="ERROR", status_message=message_error, output={"error": message_error})
                        raise ValueError(message_error)
                    choice = response.choices[0]
                    if choice.message is None:
                        message_error = "Provider returned an empty completion message."
                        generation.update(level="ERROR", status_message=message_error, output={"error": message_error})
                        raise ValueError(message_error)
                    message = choice.message
                    finish_reason = choice.finish_reason
                    answer = message.content or ""
                    usage = response.usage.model_dump(exclude_none=True) if hasattr(response.usage, "model_dump") else {}
                    used_in = usage.get("prompt_tokens", usage.get("input_tokens"))
                    used_out = usage.get("completion_tokens", usage.get("output_tokens"))
                    used_cost = usage.get("cost")
                    if used_in is not None:
                        token_in += int(used_in); saw_in = True
                    if used_out is not None:
                        token_out += int(used_out); saw_out = True
                    if used_cost is not None:
                        cost_total += float(used_cost); saw_cost = True
                    response_calls = list(message.tool_calls or [])
                    generation.update(output={"answer": answer, "tool_calls": [c.function.name for c in response_calls]},
                                      metadata={"condition": condition, "provider": provider,
                                                "case_id": data["case_id"], "latency_ms": round(elapsed, 2)})
                    if not response_calls and not answer.strip():
                        message_error = "Model returned no text or tool call (finish reason: %s). Increase max output tokens or inspect this trace." % finish_reason
                        generation.update(level="ERROR", status_message=message_error, output={"error": message_error})
                        raise ValueError(message_error)
                if not response_calls:
                    break
                if turn:
                    raise ValueError("Only one round of local tool execution is supported.")
                assistant_calls, tool_messages = [], []
                for call in response_calls:
                    args = json.loads(call.function.arguments)
                    with langfuse.start_as_current_observation(as_type="tool", name=call.function.name, input=args) as observation:
                        result = run_local_tool(call.function.name, args)
                        observation.update(output=result)
                    calls.append({"name": call.function.name, "arguments": args, "result": result})
                    assistant_calls.append({"id": call.id, "type": "function", "function": {"name": call.function.name, "arguments": call.function.arguments}})
                    tool_messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(result)})
                chat.append({"role": "assistant", "content": answer or None, "tool_calls": assistant_calls})
                chat.extend(tool_messages)
            return {"answer": answer, "tool_calls": calls, "latency_ms": round(elapsed_total, 2),
                    "input_tokens": token_in if saw_in else None, "output_tokens": token_out if saw_out else None,
                    "cost_usd": cost_total if saw_cost else None}
        except Exception as exc:
            return {"error": str(exc), "tool_calls": calls, "latency_ms": round(elapsed_total, 2),
                    "input_tokens": token_in if saw_in else None, "output_tokens": token_out if saw_out else None,
                    "cost_usd": cost_total if saw_cost else None}
    return task


def evaluate(*, output, expected_output=None, **kwargs):
    if not isinstance(output, dict) or output.get("error"):
        message = output.get("error", "No model response.") if isinstance(output, dict) else "No model response."
        return [Evaluation(name="request_success", value=False, data_type="BOOLEAN", comment=str(message))]
    valid, parsed = parse_json(str(output.get("answer", "")))
    if valid:
        exact, normalized = equal(parsed, expected_output), equal(parsed, expected_output, normalized=True)
    elif isinstance(expected_output, str):
        exact = str(output.get("answer", "")).strip() == expected_output
        normalized = norm(str(output.get("answer", ""))) == norm(expected_output)
    else:
        exact = normalized = False
    return [
        Evaluation(name="request_success", value=True, data_type="BOOLEAN"),
        Evaluation(name="valid_json", value=valid, data_type="BOOLEAN"),
        Evaluation(name="reference_match", value=exact, data_type="BOOLEAN"),
        Evaluation(name="normalized_match", value=normalized, data_type="BOOLEAN"),
    ]


def save_result(conn, run_id, condition, model, case_id, output, scores, trace_id):
    result = output if isinstance(output, dict) else {}
    error = result.get("error")
    conn.execute("""INSERT OR REPLACE INTO model_results
      (run_id,case_id,condition,model,answer,tool_calls_json,request_success,valid_json,
       reference_match,normalized_match,latency_ms,input_tokens,output_tokens,cost_usd,error,trace_id)
      VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
      (run_id, case_id, condition, model, result.get("answer"), json.dumps(result.get("tool_calls", [])),
       int(not error and "answer" in result), _score(scores.get("valid_json")), _score(scores.get("reference_match")),
       _score(scores.get("normalized_match")), result.get("latency_ms"), result.get("input_tokens"),
       result.get("output_tokens"), result.get("cost_usd"), str(error) if error else None, trace_id))


def _score(value):
    return None if value is None else int(bool(value))


def summary(rows, total):
    good = [r for r in rows if r["request_success"]]
    avg = lambda key: (sum(r[key] for r in good if r[key] is not None) /
                       len([r for r in good if r[key] is not None])) if any(r[key] is not None for r in good) else None
    summed = lambda key: sum(r[key] for r in good if r[key] is not None) if any(r[key] is not None for r in good) else None
    latencies = [r["latency_ms"] for r in good if r["latency_ms"] is not None]
    return {"successes": len(good), "total": total, "exact_rate": avg("reference_match"),
            "normalized_rate": avg("normalized_match"), "json_rate": avg("valid_json"),
            "avg_latency": sum(latencies) / len(latencies) if latencies else None,
            "input_tokens": summed("input_tokens"), "output_tokens": summed("output_tokens"), "cost": summed("cost_usd")}


@app.get("/")
def home():
    return PAGE


@app.get("/app.js")
def frontend():
    return Response(Path(__file__).with_name("app.js").read_text(encoding="utf-8"), mimetype="application/javascript")


@app.get("/styles.css")
def stylesheet():
    return Response(Path(__file__).with_name("styles.css").read_text(encoding="utf-8"), mimetype="text/css")


@app.get("/api/state")
def state():
    conn = db()
    cases = [dict(row) for row in conn.execute("SELECT * FROM test_cases ORDER BY id")]
    runs = [dict(row) for row in conn.execute("SELECT * FROM evaluation_runs ORDER BY id DESC LIMIT 10")]
    conn.close()
    for case in cases:
        case["expected_output"] = json.loads(case["expected_output"])
    project_id = os.getenv("LANGFUSE_PROJECT_ID", "").strip()
    langfuse_host = os.getenv("LANGFUSE_HOST", "http://localhost:3000").rstrip("/")
    trace_url_base = f"{langfuse_host}/project/{project_id}/traces?peek=" if project_id else None
    return jsonify(cases=cases, recent_runs=runs,
                   baseline_model=os.getenv("BASELINE_MODEL", BASELINE),
                   candidate_model=os.getenv("CANDIDATE_MODEL", CANDIDATE),
                   baseline_provider=BASELINE_PROVIDER, candidate_provider=CANDIDATE_PROVIDER,
                   langfuse_trace_url_base=trace_url_base,
                   database_path=str(DB_PATH))


@app.post("/api/cases")
def add_case():
    data = request.get_json(silent=True) or {}
    name, prompt, expected_text = (str(data.get(key, "")).strip() for key in ("name", "prompt", "expected_output"))
    if not name or not prompt or not expected_text:
        return jsonify(error="Enter a case name, prompt, and expected JSON output."), 400
    try:
        expected = json.loads(expected_text)
    except json.JSONDecodeError:
        return jsonify(error="Expected output must be valid JSON."), 400
    conn = db()
    cursor = conn.execute("INSERT INTO test_cases(name,prompt,expected_output,created_at) VALUES(?,?,?,?)",
                          (name, prompt, json.dumps(expected), datetime.now().astimezone().isoformat(timespec="seconds")))
    conn.commit(); case_id = cursor.lastrowid; conn.close()
    return jsonify(id=case_id), 201


@app.post("/api/run")
def run_comparison():
    data = request.get_json(silent=True) or {}
    try:
        ids = sorted({int(x) for x in data.get("case_ids", [])})
        temperature, max_tokens = float(data.get("temperature", 0)), int(data.get("max_tokens", 4096))
    except (TypeError, ValueError):
        return jsonify(error="Invalid case IDs or model parameters."), 400
    examples, tools = data.get("examples", []), data.get("tools", [])
    if not ids:
        return jsonify(error="Select at least one case."), 400
    if not isinstance(examples, list) or any(not isinstance(x, dict) for x in examples):
        return jsonify(error="Examples must be a JSON array of objects."), 400
    if not isinstance(tools, list) or any(not isinstance(x, dict) for x in tools):
        return jsonify(error="Tools must be a JSON array of objects."), 400
    try:
        tools = format_tools(tools)
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    if not 0 <= temperature <= 2 or not 1 <= max_tokens <= 8192:
        return jsonify(error="Temperature must be 0–2 and max tokens 1–8192."), 400
    baseline, candidate = str(data.get("baseline_model", "")).strip(), str(data.get("candidate_model", "")).strip()
    system_prompt = str(data.get("system_prompt", "")).strip()
    if not baseline or not candidate:
        return jsonify(error="Enter both model IDs."), 400
    providers = (BASELINE_PROVIDER, CANDIDATE_PROVIDER)
    if providers[0] == providers[1] and baseline.casefold() == candidate.casefold():
        return jsonify(error=(
            "Baseline and candidate resolve to the same provider model. "
            "Use two distinct Azure deployment names for a model comparison; "
            "a same-model run only measures repeatability."
        )), 400
    if any(provider not in {"openrouter", "azure"} for provider in providers):
        return jsonify(error="Set BASELINE_PROVIDER and CANDIDATE_PROVIDER to 'openrouter' or 'azure' in .env."), 400
    required = ["LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"]
    if "openrouter" in providers:
        required.append("OPENROUTER_API_KEY")
    if "azure" in providers:
        required.extend(("AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_KEY"))
    missing = [key for key in required if not os.getenv(key)]
    if missing:
        return jsonify(error="Missing required .env settings: " + ", ".join(missing)), 400

    conn = db()
    marks = ",".join("?" for _ in ids)
    cases = conn.execute(f"SELECT * FROM test_cases WHERE id IN ({marks}) ORDER BY id", ids).fetchall()
    if not cases:
        conn.close(); return jsonify(error="Selected cases were not found."), 404
    cursor = conn.execute("""INSERT INTO evaluation_runs
      (created_at,baseline_model,candidate_model,system_prompt,examples_json,tools_json,temperature,max_tokens,case_count,status)
      VALUES(?,?,?,?,?,?,?,?,?,'running')""",
      (datetime.now().astimezone().isoformat(timespec="seconds"), baseline, candidate, system_prompt,
       json.dumps(examples), json.dumps(tools), temperature, max_tokens, len(cases)))
    run_id = cursor.lastrowid; conn.commit()
    items = [{"input": {"case_id": str(c["id"]), "prompt": c["prompt"], "system_prompt": system_prompt,
                         "examples": examples, "tools": tools},
              "expected_output": json.loads(c["expected_output"]),
              "metadata": {"case_id": c["id"], "case_name": c["name"]}} for c in cases]
    try:
        langfuse = get_client()
        failures = []
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        for condition, model, provider in (("baseline", baseline, BASELINE_PROVIDER),
                                           ("candidate", candidate, CANDIDATE_PROVIDER)):
            try:
                client = make_provider_client(provider)
                experiment = langfuse.run_experiment(
                    name="Model migration comparison", run_name=f"{condition} - {provider} - {model} - {stamp}",
                    description="Same local test cases and settings compared across models.", data=items,
                    task=model_task(model, condition, provider, client, langfuse, temperature, max_tokens),
                    evaluators=[evaluate], max_concurrency=1,
                    metadata={"condition": condition, "provider": provider,
                              "model": model, "local_run_id": run_id})
                for result in experiment.item_results:
                    item = result.item.get("input", {}) if isinstance(result.item, dict) else result.item.input
                    scores = {s.name: s.value for s in getattr(result, "evaluations", [])}
                    save_result(conn, run_id, condition, model, int(item["case_id"]), result.output, scores, getattr(result, "trace_id", None))
                conn.commit()
            except Exception as exc:
                failures.append(str(exc))
                for case in cases:
                    save_result(conn, run_id, condition, model, case["id"], {"error": str(exc)}, {}, None)
                conn.commit()
        try:
            langfuse.flush()
        except Exception as exc:
            failures.append(str(exc))
        success_count = conn.execute("SELECT COUNT(*) FROM model_results WHERE run_id=? AND request_success=1", (run_id,)).fetchone()[0]
        status = "complete" if success_count == len(cases) * 2 else "partial" if success_count else "failed"
        if failures and success_count == 0:
            status = "failed"
        conn.execute("UPDATE evaluation_runs SET status=? WHERE id=?", (status, run_id)); conn.commit()
    except Exception as exc:
        for condition, model in (("baseline", baseline), ("candidate", candidate)):
            for case in cases:
                save_result(conn, run_id, condition, model, case["id"], {"error": str(exc)}, {}, None)
        conn.execute("UPDATE evaluation_runs SET status='failed' WHERE id=?", (run_id,)); conn.commit()
        status = "failed"
    finally:
        conn.close()
    return jsonify(run_id=run_id, status=status)


@app.get("/api/runs/<int:run_id>")
def run_detail(run_id):
    conn = db()
    run = conn.execute("SELECT * FROM evaluation_runs WHERE id=?", (run_id,)).fetchone()
    if run is None:
        conn.close(); abort(404)
    rows = conn.execute("""SELECT r.*,c.name AS case_name,c.prompt,c.expected_output FROM model_results r
      JOIN test_cases c ON c.id=r.case_id WHERE r.run_id=? ORDER BY c.id,r.condition""", (run_id,)).fetchall()
    conn.close()
    groups = {}
    for row in rows:
        case_id = row["case_id"]
        groups.setdefault(case_id, {"case_id": case_id, "name": row["case_name"], "prompt": row["prompt"],
                                    "expected": json.loads(row["expected_output"]), "baseline": None, "candidate": None})
        result = dict(row)
        try:
            result["tool_calls"] = json.loads(result.pop("tool_calls_json"))
        except (TypeError, json.JSONDecodeError):
            result["tool_calls"] = []
        groups[case_id][row["condition"]] = result
    baseline = [r for r in rows if r["condition"] == "baseline"]
    candidate = [r for r in rows if r["condition"] == "candidate"]
    return jsonify(run=dict(run), groups=list(groups.values()),
                   baseline_summary=summary(baseline, run["case_count"]),
                   candidate_summary=summary(candidate, run["case_count"]))


@app.errorhandler(500)
def api_error(error):
    if request.path.startswith("/api/"):
        return jsonify(error="Internal app error. See the PowerShell window running demo.py."), 500
    return error


PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#f4f6f8"><title>Parent System · Model Control Plane</title><link rel="stylesheet" href="/styles.css"></head><body>
<div id="app" aria-live="polite"><div class="boot">Loading Parent System…</div></div><script src="/app.js" defer></script></body></html>"""


if __name__ == "__main__":
    initialize_database()
    port = int(os.getenv("PARENT_PORT", "5001"))
    print("Parent System: http://127.0.0.1:" + str(port))
    print("SQLite database: " + str(DB_PATH))
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)
