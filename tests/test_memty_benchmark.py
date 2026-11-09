"""Benchmark reports must separate estimates, payload coverage and live usage."""
import json
import unittest
from unittest.mock import patch

from benchmarks.token_burn import run


class BenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture, cls.digest = run.load_fixture()
        cls.payloads = run.build_payloads(cls.fixture)

    def test_offline_report_is_reproducible_and_labels_its_limits(self):
        first = run.offline_report(self.fixture, self.digest, self.payloads)
        second = run.offline_report(self.fixture, self.digest, run.build_payloads(self.fixture))
        self.assertEqual(first, second)
        self.assertEqual(first["mode"], "offline_payload_simulation")
        self.assertIn("not assistant recall", first["continuity_metric"])
        self.assertIn("not a real RAG or MCP product", first["retrieval_baseline"])
        self.assertEqual(first["results"]["memty_selected_context"]["expected_values_present"], 10)
        self.assertEqual(len(first["results"]["memty_selected_context"]["turns"]), 5)

    def test_missing_context_values_reduce_coverage(self):
        modified = {key: list(value) for key, value in self.payloads.items()}
        modified["memty_selected_context"][4] = modified["memty_selected_context"][4].replace("HashiCorp Vault", "missing")
        report = run.offline_report(self.fixture, self.digest, modified)
        result = report["results"]["memty_selected_context"]
        self.assertEqual(result["expected_values_present"], 9)
        self.assertEqual(result["turns"][4]["missing_slots"], ["secrets_manager"])

    def test_live_mode_requires_both_keys_before_any_network_request(self):
        with patch.object(run, "_provider_response") as call:
            with self.assertRaisesRegex(ValueError, "both provider"):
                run.live_report(self.fixture, self.digest, self.payloads,
                                {"claude": "model-a", "perplexity": "model-b"}, {"claude": "secret"})
        call.assert_not_called()

    def test_live_mode_records_real_usage_fields_and_alternating_handoffs(self):
        values = {fact["slot"]: fact["value"] for fact in self.fixture["facts"]}
        calls = []

        def response(provider, model, key, prompt):
            calls.append((provider, prompt))
            requested = prompt.rsplit("Requested keys: ", 1)[1].split(", ")
            return json.dumps({slot: values[slot] for slot in requested}), {"input_tokens": 123, "output_tokens": 17}, model

        with patch.object(run, "_provider_response", side_effect=response):
            report = run.live_report(self.fixture, self.digest, self.payloads,
                {"claude": "claude-model", "perplexity": "provider/model"},
                {"claude": "secret-a", "perplexity": "secret-b"})
        self.assertEqual(len(calls), 15)
        self.assertEqual([provider for provider, _ in calls[:5]], ["claude", "perplexity", "claude", "perplexity", "claude"])
        self.assertIn("Assistant:", calls[1][1])
        for result in report["results"].values():
            self.assertEqual((result["input_tokens"], result["output_tokens"]), (615, 85))
            self.assertEqual(result["exact_values_returned"], 10)
        self.assertNotIn("secret-a", json.dumps(report))
        self.assertNotIn("secret-b", json.dumps(report))


if __name__ == "__main__":
    unittest.main()
