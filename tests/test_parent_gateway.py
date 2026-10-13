import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask

import parent_gateway as gateway


class FakeResponse:
    def __init__(self, payload=None, chunks=None, status_code=200, headers=None):
        self.status_code = status_code
        self.headers = headers or {"Content-Type": "application/json", "X-Request-Id": "upstream-test"}
        self.content = payload if isinstance(payload, bytes) else json.dumps(payload or {}).encode("utf-8")
        self._chunks = chunks
        self.closed = False
        self.ok = 200 <= status_code < 400

    def iter_content(self, chunk_size=8192):
        yield from (self._chunks or [self.content])

    def close(self):
        self.closed = True


class ParentGatewayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tempdir = tempfile.TemporaryDirectory()
        cls.data_dir_patch = patch.object(gateway, "DATA_DIR", Path(cls.tempdir.name))
        cls.db_path_patch = patch.object(gateway, "DB_PATH", Path(cls.tempdir.name) / "test.sqlite3")
        cls.env_patch = patch.dict(os.environ, {
            "CANDIDATE_PROVIDER": "openrouter",
            "CANDIDATE_MODEL": "vendor/target-model",
            "OPENROUTER_API_KEY": "unit-test-upstream-key",
            "OPENROUTER_BASE_URL": "https://provider.example/v1",
            "AZURE_OPENAI_ENDPOINT": "https://azure.example",
            "AZURE_OPENAI_API_KEY": "unit-test-azure-key",
            "LANGFUSE_PUBLIC_KEY": "",
            "LANGFUSE_SECRET_KEY": "",
            "LANGFUSE_CAPTURE_CONTENT": "true",
        })
        cls.data_dir_patch.start()
        cls.db_path_patch.start()
        cls.env_patch.start()

    @classmethod
    def tearDownClass(cls):
        cls.env_patch.stop()
        cls.db_path_patch.stop()
        cls.data_dir_patch.stop()
        cls.tempdir.cleanup()

    def setUp(self):
        app = Flask(__name__)
        app.config["TESTING"] = True
        gateway.register_gateway(app)
        self.client = app.test_client()
        connection = gateway.connect_db()
        connection.execute("DELETE FROM gateway_requests")
        connection.execute("DELETE FROM rag_evaluations")
        connection.execute("DELETE FROM gateway_captures")
        connection.execute("DELETE FROM gateway_capture_settings")
        connection.execute("DELETE FROM model_routes WHERE requested_model='gpt-4.1-mini'")
        connection.execute(
            """UPDATE model_routes SET provider='openrouter',upstream_model='vendor/target-model',
               max_output_tokens=NULL WHERE app_id='support-agent' AND requested_model='gpt-5.2'"""
        )
        connection.commit()
        connection.close()
        result = self.client.post("/api/control/apps/support-agent/key")
        self.assertEqual(result.status_code, 201)
        self.app_key = result.get_json()["api_key"]
        self.auth = {"Authorization": "Bearer " + self.app_key}

    def test_chat_request_only_rewrites_model_and_keeps_instructions_and_tools(self):
        request_body = {
            "model": "gpt-5.2",
            "instructions": "Do not change this instruction.",
            "input": [{"role": "user", "content": "test prompt"}],
            "tools": [{"type": "function", "name": "lookup", "parameters": {"type": "object"}}],
            "temperature": 0,
            "stream": False,
        }
        upstream_payload = {"id": "resp_test", "object": "response", "usage": {"input_tokens": 7, "output_tokens": 4}}
        client_headers = dict(self.auth, Cookie="session=child-secret", Referer="https://child.example")
        with patch.object(gateway.requests, "request", return_value=FakeResponse(upstream_payload)) as relay:
            response = self.client.post("/v1/responses", headers=client_headers, json=request_body)

        self.assertEqual(response.status_code, 200)
        call = relay.call_args.kwargs
        self.assertEqual(call["url"], "https://provider.example/v1/responses")
        self.assertEqual(call["headers"]["Authorization"], "Bearer unit-test-upstream-key")
        self.assertNotIn("Cookie", call["headers"])
        self.assertNotIn("Referer", call["headers"])
        forwarded = json.loads(call["data"].decode("utf-8"))
        self.assertEqual(forwarded["model"], "vendor/target-model")
        request_body["model"] = "vendor/target-model"
        self.assertEqual(forwarded, request_body)
        self.assertEqual(response.get_json(), upstream_payload)
        connection = gateway.connect_db()
        row = connection.execute("SELECT * FROM gateway_requests ORDER BY id DESC LIMIT 1").fetchone()
        connection.close()
        self.assertEqual(row["input_tokens"], 7)
        self.assertEqual(row["output_tokens"], 4)
        self.assertNotIn("test prompt", dict(row).values())

    def test_configured_output_limit_caps_provider_budget_without_changing_instructions(self):
        route = {
            "requested_model": "gpt-5.2",
            "provider": "openrouter",
            "upstream_model": "vendor/target-model",
            "enabled": True,
            "max_output_tokens": 512,
        }
        configured = self.client.put(
            "/api/control/apps/support-agent/route", json=route
        )
        self.assertEqual(configured.status_code, 200)

        request_body = {
            "model": "gpt-5.2",
            "instructions": "Keep this instruction exactly.",
            "input": "test prompt",
            "max_output_tokens": 65536,
        }
        with patch.object(
            gateway.requests,
            "request",
            return_value=FakeResponse({"id": "resp_test", "usage": {}}),
        ) as relay:
            response = self.client.post(
                "/v1/responses", headers=self.auth, json=request_body
            )

        self.assertEqual(response.status_code, 200)
        forwarded = json.loads(relay.call_args.kwargs["data"].decode("utf-8"))
        self.assertEqual(forwarded["max_output_tokens"], 512)
        self.assertEqual(forwarded["instructions"], request_body["instructions"])
        self.assertEqual(forwarded["input"], request_body["input"])

    def test_azure_gpt5_chat_maps_legacy_max_tokens_to_max_completion_tokens(self):
        route = {
            "requested_model": "gpt-5.2",
            "provider": "azure",
            "upstream_model": "gpt-5-mini",
            "enabled": True,
            "max_output_tokens": 512,
        }
        configured = self.client.put(
            "/api/control/apps/support-agent/route", json=route
        )
        self.assertEqual(configured.status_code, 200)

        request_body = {
            "model": "gpt-5.2",
            "messages": [{"role": "user", "content": "Extract this."}],
            "max_tokens": 4096,
        }
        with patch.object(
            gateway.requests,
            "request",
            return_value=FakeResponse({"id": "chatcmpl_test", "usage": {}}),
        ) as relay:
            response = self.client.post(
                "/v1/chat/completions", headers=self.auth, json=request_body
            )

        self.assertEqual(response.status_code, 200)
        forwarded = json.loads(relay.call_args.kwargs["data"].decode("utf-8"))
        self.assertEqual(forwarded["model"], "gpt-5-mini")
        self.assertEqual(forwarded["max_completion_tokens"], 512)
        self.assertNotIn("max_tokens", forwarded)

    def test_invalid_output_limit_is_rejected(self):
        response = self.client.put(
            "/api/control/apps/support-agent/route",
            json={
                "requested_model": "gpt-5.2",
                "provider": "openrouter",
                "upstream_model": "vendor/target-model",
                "max_output_tokens": 0,
            },
        )
        self.assertEqual(response.status_code, 400)

    def test_rejects_missing_app_key_without_calling_provider(self):
        with patch.object(gateway.requests, "request") as relay:
            response = self.client.post("/v1/chat/completions", json={"model": "gpt-5.2", "messages": []})
        self.assertEqual(response.status_code, 401)
        relay.assert_not_called()

    def test_rejects_unmapped_model_without_calling_provider(self):
        with patch.object(gateway.requests, "request") as relay:
            response = self.client.post("/v1/chat/completions", headers=self.auth,
                                       json={"model": "not-configured", "messages": []})
        self.assertEqual(response.status_code, 400)
        relay.assert_not_called()

    def test_propagates_provider_rate_limit_and_records_it(self):
        provider_error = {"error": {"message": "Rate limited.", "type": "rate_limit_error"}}
        with patch.object(
            gateway.requests,
            "request",
            return_value=FakeResponse(provider_error, status_code=429),
        ):
            response = self.client.post(
                "/v1/responses", headers=self.auth,
                json={"model": "gpt-5.2", "input": "test"},
            )

        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.get_json(), provider_error)
        connection = gateway.connect_db()
        row = connection.execute("SELECT * FROM gateway_requests ORDER BY id DESC LIMIT 1").fetchone()
        connection.close()
        self.assertEqual(row["status_code"], 429)
        self.assertEqual(row["success"], 0)
        self.assertEqual(row["error_code"], "upstream_http_429")

    def test_provider_timeout_returns_gateway_error_and_records_timeout(self):
        with patch.object(
            gateway.requests, "request", side_effect=gateway.requests.Timeout
        ):
            response = self.client.post(
                "/v1/responses", headers=self.auth,
                json={"model": "gpt-5.2", "input": "test"},
            )

        self.assertEqual(response.status_code, 504)
        self.assertEqual(response.get_json()["error"]["type"], "upstream_timeout")
        self.assertTrue(response.get_json()["error"].get("request_id"))
        connection = gateway.connect_db()
        row = connection.execute("SELECT * FROM gateway_requests ORDER BY id DESC LIMIT 1").fetchone()
        connection.close()
        self.assertEqual(row["status_code"], 504)
        self.assertEqual(row["success"], 0)
        self.assertEqual(row["error_code"], "upstream_timeout")

    def test_additional_model_alias_can_be_added_and_used(self):
        result = self.client.post("/api/control/apps/support-agent/routes", json={
            "requested_model": "gpt-4.1-mini",
            "provider": "openrouter",
            "upstream_model": "vendor/other-target",
        })
        self.assertEqual(result.status_code, 201)
        duplicate = self.client.post("/api/control/apps/support-agent/routes", json={
            "requested_model": "gpt-4.1-mini",
            "provider": "openrouter",
            "upstream_model": "vendor/other-target",
        })
        self.assertEqual(duplicate.status_code, 409)

        with patch.object(gateway.requests, "request", return_value=FakeResponse({"ok": True})) as relay:
            response = self.client.post("/v1/chat/completions", headers=self.auth,
                                        json={"model": "gpt-4.1-mini", "messages": []})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(relay.call_args.kwargs["data"])["model"], "vendor/other-target")

    def test_multipart_file_body_is_forwarded_byte_for_byte(self):
        boundary = "test-boundary-0123"
        raw = ("--" + boundary + "\r\nContent-Disposition: form-data; name=\"purpose\"\r\n\r\nassistants\r\n"
               "--" + boundary + "\r\nContent-Disposition: form-data; name=\"file\"; filename=\"a.txt\"\r\n"
               "Content-Type: text/plain\r\n\r\nhello\r\n--" + boundary + "--\r\n").encode("utf-8")
        with patch.object(gateway.requests, "request", return_value=FakeResponse({"id": "file_test"})) as relay:
            response = self.client.post("/v1/files", headers=self.auth, data=raw,
                                        content_type="multipart/form-data; boundary=" + boundary)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(relay.call_args.kwargs["data"], raw)
        self.assertEqual(relay.call_args.kwargs["headers"]["Content-Type"],
                         "multipart/form-data; boundary=" + boundary)

    def test_streaming_body_is_unchanged_and_usage_is_logged(self):
        event_1 = b'data: {"choices":[{"delta":{"content":"Hello"}}]}\n\n'
        event_2 = b'data: {"usage":{"prompt_tokens":5,"completion_tokens":3,"cost":0.00007}}\n\n'
        event_3 = b"data: [DONE]\n\n"
        raw = event_1 + event_2 + event_3
        chunks = [raw[:17], raw[17:58], raw[58:]]
        fake = FakeResponse(chunks=chunks, headers={"Content-Type": "text/event-stream"})
        with patch.object(gateway.requests, "request", return_value=fake):
            response = self.client.post("/v1/chat/completions", headers=self.auth,
                                        json={"model": "gpt-5.2", "messages": [], "stream": True,
                                              "stream_options": {"include_usage": True}})
            streamed = response.get_data()
        self.assertEqual(streamed, raw)
        self.assertTrue(fake.closed)
        connection = gateway.connect_db()
        row = connection.execute("SELECT * FROM gateway_requests ORDER BY id DESC LIMIT 1").fetchone()
        connection.close()
        self.assertEqual(row["input_tokens"], 5)
        self.assertEqual(row["output_tokens"], 3)
        self.assertAlmostEqual(row["cost_usd"], 0.00007)

    def test_responses_stream_captures_nested_completion_usage(self):
        raw = (
            b'data: {"type":"response.completed","response":{"usage":'
            b'{"input_tokens":9,"output_tokens":6,"total_tokens":15}}}\n\n'
            b"data: [DONE]\n\n"
        )
        fake = FakeResponse(chunks=[raw], headers={"Content-Type": "text/event-stream"})
        with patch.object(gateway.requests, "request", return_value=fake):
            response = self.client.post(
                "/v1/responses", headers=self.auth,
                json={"model": "gpt-5.2", "input": "test", "stream": True},
            )
            self.assertEqual(response.get_data(), raw)

        connection = gateway.connect_db()
        row = connection.execute("SELECT * FROM gateway_requests ORDER BY id DESC LIMIT 1").fetchone()
        connection.close()
        self.assertEqual(row["input_tokens"], 9)
        self.assertEqual(row["output_tokens"], 6)

    def test_azure_chat_stream_requests_and_records_provider_usage(self):
        route = {
            "requested_model": "gpt-5.2",
            "provider": "azure",
            "upstream_model": "gpt-5-mini",
            "enabled": True,
        }
        configured = self.client.put(
            "/api/control/apps/support-agent/route", json=route
        )
        self.assertEqual(configured.status_code, 200)
        raw = (
            b'data: {"choices":[{"delta":{"content":"ok"}}]}\n\n'
            b'data: {"usage":{"prompt_tokens":4,"completion_tokens":7}}\n\n'
            b"data: [DONE]\n\n"
        )
        fake = FakeResponse(chunks=[raw], headers={"Content-Type": "text/event-stream"})
        with patch.object(gateway.requests, "request", return_value=fake) as relay:
            response = self.client.post(
                "/v1/chat/completions", headers=self.auth,
                json={"model": "gpt-5.2", "messages": [], "stream": True},
            )
            self.assertEqual(response.get_data(), raw)

        forwarded = json.loads(relay.call_args.kwargs["data"].decode("utf-8"))
        self.assertTrue(forwarded["stream_options"]["include_usage"])
        connection = gateway.connect_db()
        row = connection.execute("SELECT * FROM gateway_requests ORDER BY id DESC LIMIT 1").fetchone()
        connection.close()
        self.assertEqual(row["input_tokens"], 4)
        self.assertEqual(row["output_tokens"], 7)

    def test_unknown_cost_is_reported_as_unknown_not_zero(self):
        overview = self.client.get("/api/control/overview").get_json()
        self.assertIsNone(overview["cost_today_usd"])
        self.assertEqual(overview["cost_samples_today"], 0)

    def test_provider_status_does_not_expose_url_userinfo_or_query_secrets(self):
        with patch.dict(os.environ, {
            "GATEWAY_CUSTOM_BASE_URL": "https://user:password@custom.example/v1?api_key=url-secret",
            "GATEWAY_CUSTOM_API_KEY": "server-secret",
        }):
            result = self.client.get("/api/control/health").get_json()
        custom = next(item for item in result["providers"] if item["id"] == "custom")
        self.assertEqual(custom["base_url"], "https://custom.example/v1")
        self.assertNotIn("password", json.dumps(result))
        self.assertNotIn("url-secret", json.dumps(result))
        self.assertNotIn("server-secret", json.dumps(result))

    def test_rag_capture_is_opt_in_and_keeps_actual_tool_context_private_from_activity(self):
        key = self.client.post("/api/control/apps/rag-knowledge-retrieval/key").get_json()["api_key"]
        auth = {"Authorization": "Bearer " + key}
        payload = {
            "id": "resp_baseline",
            "output_text": "Meera has seven years of AI engineering experience.",
            "usage": {"input_tokens": 84, "output_tokens": 12, "cost": 0.0005},
        }
        request_body = {
            "model": "gpt-5",
            "instructions": "Use only retrieved resume evidence.",
            "input": [
                {"role": "user", "content": "Summarize Meera's experience."},
                {"type": "function_call_output", "call_id": "call_1",
                 "output": "Meera Nair: AI Engineer with 7 years of experience."},
            ],
            "tools": [{"type": "function", "name": "retrieve_context"}],
            "stream": False,
        }
        fake = FakeResponse(payload)
        with patch.object(gateway.requests, "request", return_value=fake):
            response = self.client.post("/v1/responses", headers=auth, json=request_body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/api/control/rag").get_json()["captures"], [])

        enabled = self.client.put("/api/control/rag/capture", json={"enabled": True})
        self.assertEqual(enabled.status_code, 200)
        with patch.object(gateway.requests, "request", return_value=FakeResponse(payload)):
            response = self.client.post("/v1/responses", headers=auth, json=request_body)
        self.assertEqual(response.status_code, 200)

        workspace = self.client.get("/api/control/rag").get_json()
        self.assertEqual(len(workspace["captures"]), 1)
        capture = workspace["captures"][0]
        self.assertTrue(capture["includes_tool_result"])
        self.assertEqual(capture["input_tokens"], 84)
        detail = self.client.get("/api/control/rag/captures/%s" % capture["id"]).get_json()["capture"]
        self.assertEqual(detail["request"]["instructions"], request_body["instructions"])
        self.assertIn("Meera Nair", detail["request"]["input"][1]["output"])
        activity = self.client.get("/api/control/requests").get_json()["requests"]
        self.assertNotIn("Meera Nair", json.dumps(activity))

    def test_rag_candidate_replays_via_gateway_and_gates_promotion_with_rollback(self):
        key = self.client.post("/api/control/apps/rag-knowledge-retrieval/key").get_json()["api_key"]
        auth = {"Authorization": "Bearer " + key}
        self.client.put("/api/control/rag/capture", json={"enabled": True})
        baseline_payload = {
            "id": "resp_baseline", "output_text": "Meera Nair has seven years of AI experience.",
            "usage": {"input_tokens": 90, "output_tokens": 12, "cost": 0.0005},
        }
        body = {
            "model": "gpt-5",
            "instructions": "Answer from the retrieved resume context and cite the source.",
            "input": [
                {"role": "user", "content": "Summarize Meera's experience."},
                {"type": "function_call_output", "call_id": "call_1",
                 "output": "Meera Nair is an AI Engineer with seven years of experience."},
            ],
            "tools": [{"type": "function", "name": "retrieve_context"}],
            "stream": False,
        }
        with patch.object(gateway.requests, "request", return_value=FakeResponse(baseline_payload)):
            response = self.client.post("/v1/responses", headers=auth, json=body)
        self.assertEqual(response.status_code, 200)
        capture_id = self.client.get("/api/control/rag").get_json()["captures"][0]["id"]
        candidate_payload = {
            "id": "resp_candidate", "output_text": "Meera Nair is an AI Engineer with seven years of experience.",
            "usage": {"input_tokens": 90, "output_tokens": 13, "cost": 0.0004},
        }
        with patch.object(gateway.requests, "request", return_value=FakeResponse(candidate_payload)) as relay:
            comparison = self.client.post("/api/control/rag/evaluations", json={
                "capture_id": capture_id, "candidate_provider": "azure", "candidate_model": "gpt-5-mini",
            })
        self.assertEqual(comparison.status_code, 201, comparison.get_data(as_text=True))
        evaluation = comparison.get_json()["evaluation"]
        self.assertEqual(evaluation["status"], "pending_review")
        forwarded = json.loads(relay.call_args.kwargs["data"].decode("utf-8"))
        self.assertEqual(forwarded["model"], "gpt-5-mini")
        self.assertEqual(forwarded["instructions"], body["instructions"])
        self.assertEqual(forwarded["input"], body["input"])
        self.assertEqual(forwarded["tools"], body["tools"])
        self.assertNotEqual(forwarded["model"], body["model"])

        # Mocked provider calls have near-zero timings, so pin values to exercise
        # the configured gate rather than the test machine's scheduler jitter.
        connection = gateway.connect_db()
        connection.execute(
            "UPDATE rag_evaluations SET baseline_latency_ms=1000,candidate_latency_ms=900 WHERE id=?",
            (evaluation["id"],),
        )
        connection.commit()
        connection.close()

        self.client.put("/api/control/rag/policy", json={
            "minimum_quality_score": 4, "max_quality_drop": 0,
            "max_latency_regression_pct": 25, "max_cost_regression_pct": 25,
        })
        reviewed = self.client.post("/api/control/rag/evaluations/%s/review" % evaluation["id"], json={
            "baseline_quality_score": 4.5, "candidate_quality_score": 4.5,
        })
        self.assertEqual(reviewed.status_code, 200)
        self.assertEqual(reviewed.get_json()["evaluation"]["status"], "approved",
                         reviewed.get_json()["evaluation"]["recommendation"])
        promoted = self.client.post("/api/control/rag/evaluations/%s/promote" % evaluation["id"])
        self.assertEqual(promoted.status_code, 200, promoted.get_data(as_text=True))
        updated = self.client.get("/api/control/apps").get_json()["apps"]
        rag_routes = next(app["routes"] for app in updated if app["id"] == "rag-knowledge-retrieval")
        self.assertTrue(all(route["upstream_model"] == "gpt-5-mini" for route in rag_routes
                            if route["enabled"] and route["provider"] == "azure"
                            and not route["requested_model"].startswith("text-embedding")))
        rollback = self.client.post("/api/control/rag/evaluations/%s/rollback" % evaluation["id"])
        self.assertEqual(rollback.status_code, 200, rollback.get_data(as_text=True))
        restored = self.client.get("/api/control/apps").get_json()["apps"]
        rag_routes = next(app["routes"] for app in restored if app["id"] == "rag-knowledge-retrieval")
        self.assertEqual(next(route["upstream_model"] for route in rag_routes if route["requested_model"] == "gpt-5"), "vendor/target-model")

    def test_rag_replay_handles_streamed_responses_api_turns(self):
        key = self.client.post("/api/control/apps/rag-knowledge-retrieval/key").get_json()["api_key"]
        auth = {"Authorization": "Bearer " + key}
        self.client.put("/api/control/rag/capture", json={"enabled": True})
        baseline_stream = (
            b'data: {"type":"response.output_text.delta","delta":"Baseline grounded answer."}\n\n'
            b'data: {"type":"response.completed","response":{"usage":{"input_tokens":20,"output_tokens":5,"cost":0.0002}}}\n\n'
            b"data: [DONE]\n\n"
        )
        body = {
            "model": "gpt-5", "instructions": "Keep the existing system rule.",
            "input": [{"role": "user", "content": "Question"},
                      {"type": "function_call_output", "call_id": "r1", "output": "Retrieved evidence"}],
            "tools": [{"type": "function", "name": "retrieve_context"}], "stream": True,
        }
        fake = FakeResponse(chunks=[baseline_stream], headers={"Content-Type": "text/event-stream"})
        with patch.object(gateway.requests, "request", return_value=fake):
            response = self.client.post("/v1/responses", headers=auth, json=body)
            self.assertIn(b"Baseline grounded answer.", response.get_data())
        captures = self.client.get("/api/control/rag").get_json()["captures"]
        capture = next(item for item in captures if item["requested_model"] == "gpt-5")
        self.assertEqual(capture["output_preview"], "Baseline grounded answer.")
        self.assertEqual(capture["input_tokens"], 20)

        candidate_stream = (
            b'data: {"type":"response.output_text.delta","delta":"Candidate grounded answer."}\n\n'
            b'data: {"type":"response.completed","response":{"usage":{"input_tokens":20,"output_tokens":6,"cost":0.0001}}}\n\n'
            b"data: [DONE]\n\n"
        )
        fake_candidate = FakeResponse(chunks=[candidate_stream], headers={"Content-Type": "text/event-stream"})
        with patch.object(gateway.requests, "request", return_value=fake_candidate) as relay:
            comparison = self.client.post("/api/control/rag/evaluations", json={
                "capture_id": capture["id"], "candidate_provider": "azure", "candidate_model": "gpt-5-mini",
            })
        self.assertEqual(comparison.status_code, 201, comparison.get_data(as_text=True))
        evaluation = comparison.get_json()["evaluation"]
        self.assertEqual(evaluation["candidate_output"], "Candidate grounded answer.")
        self.assertEqual(evaluation["candidate_input_tokens"], 20)
        self.assertTrue(relay.call_args.kwargs["stream"])


if __name__ == "__main__":
    unittest.main()
