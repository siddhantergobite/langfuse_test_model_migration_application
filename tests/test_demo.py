import unittest

import demo


class EvaluationGuardTests(unittest.TestCase):
    def test_model_comparison_rejects_same_provider_and_deployment(self):
        response = demo.app.test_client().post("/api/run", json={
            "case_ids": [1],
            "baseline_model": "gpt-5-mini",
            "candidate_model": "GPT-5-MINI",
            "system_prompt": "",
            "examples": [],
            "tools": [],
            "temperature": 0,
            "max_tokens": 128,
        })

        self.assertEqual(response.status_code, 400)
        self.assertIn("same provider model", response.get_json()["error"])


if __name__ == "__main__":
    unittest.main()
