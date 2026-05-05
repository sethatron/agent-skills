"""Regression tests for nlm_runner JSON parsing.

Run: python -m pytest tests/test_nlm_runner.py
or:  python tests/test_nlm_runner.py
"""

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR / "scripts"))

from nlm_runner import NLMRunner, NLMResult, NLMError, NLMQueryResult


NESTED_VALUE_RESPONSE = json.dumps({
    "value": {
        "answer": "The 3 most impactful improvements this week are: 1. Fix claude PATH. 2. Knowledge Capture. 3. Investigation Workflow.",
        "sources_used": [
            "6efde5ad-4bb5-44f4-984c-0c547690c006",
            "d98b03c3-134e-4acf-bc89-a43ebad7ab4c",
        ],
        "citations": {"1": "6efde5ad-4bb5-44f4-984c-0c547690c006"},
        "conversation_id": "0b72e1d8-503d-4252-ab4e-21ba3bf8255b",
    }
})

FLAT_RESPONSE = json.dumps({
    "answer": "Direct flat answer (older nlm format).",
    "sources_used": ["src-1"],
})

EMPTY_VALUE_RESPONSE = json.dumps({
    "value": {
        "answer": "",
        "sources_used": [],
    }
})

NO_ANSWER_RESPONSE = json.dumps({"value": {"sources_used": []}})


def _stub(stdout: str) -> NLMResult:
    return NLMResult(returncode=0, stdout=stdout, stderr="", success=True)


class NLMRunnerJSONParsingTest(unittest.TestCase):
    def setUp(self):
        self.runner = NLMRunner()

    def test_unwraps_nested_value_field(self):
        with patch.object(self.runner, "_run_with_network_retry", return_value=_stub(NESTED_VALUE_RESPONSE)):
            res = self.runner.notebook_query("dispatch", "test?")
        self.assertIsInstance(res, NLMQueryResult)
        self.assertIn("Fix claude PATH", res.answer)
        self.assertEqual(len(res.sources_used), 2)

    def test_flat_format_still_works(self):
        with patch.object(self.runner, "_run_with_network_retry", return_value=_stub(FLAT_RESPONSE)):
            res = self.runner.notebook_query("dispatch", "test?")
        self.assertIn("Direct flat answer", res.answer)
        self.assertEqual(res.sources_used, ["src-1"])

    def test_empty_answer_raises_loud_error(self):
        with patch.object(self.runner, "_run_with_network_retry", return_value=_stub(EMPTY_VALUE_RESPONSE)):
            with self.assertRaises(NLMError) as ctx:
                self.runner.notebook_query("dispatch", "test?")
        self.assertIn("no answer field", str(ctx.exception))

    def test_missing_answer_key_raises(self):
        with patch.object(self.runner, "_run_with_network_retry", return_value=_stub(NO_ANSWER_RESPONSE)):
            with self.assertRaises(NLMError):
                self.runner.notebook_query("dispatch", "test?")

    def test_empty_stdout_raises(self):
        with patch.object(self.runner, "_run_with_network_retry", return_value=_stub("")):
            with self.assertRaises(NLMError) as ctx:
                self.runner.notebook_query("dispatch", "test?")
        self.assertIn("empty stdout", str(ctx.exception))

    def test_non_json_stdout_returns_text(self):
        with patch.object(self.runner, "_run_with_network_retry", return_value=_stub("plain text answer")):
            res = self.runner.notebook_query("dispatch", "test?")
        self.assertEqual(res.answer, "plain text answer")


if __name__ == "__main__":
    unittest.main(verbosity=2)
