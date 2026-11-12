import argparse
import csv
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import scenario_gen as app


class NarrationTests(unittest.TestCase):
    def test_sentence_breaks_keep_quotes_and_decimals(self):
        self.assertEqual(app.normalize_sentences('距離は2.5キロです。「迂回してください。」 次は出口です。'),
                         '距離は2.5キロです。\n「迂回してください。」\n次は出口です。\n')

    def test_rewrite_over_budget(self):
        client = Mock()
        client.generate.side_effect = ["長" * 900 + "。", "要点です。"]
        self.assertEqual(app.generate_narration(client, "記事", "https://example.com", 3, 300), "要点です。\n")
        self.assertEqual(client.generate.call_count, 2)

    def test_failure_never_truncates(self):
        client = Mock()
        client.generate.return_value = "長" * 900 + "。"
        with self.assertRaises(ValueError):
            app.generate_narration(client, "記事", "https://example.com", 3, 300)

    def test_unfinished_sentence_rejected(self):
        client = Mock()
        client.generate.return_value = "途中"
        with self.assertRaises(ValueError):
            app.generate_narration(client, "記事", "https://example.com", 3, 300)

    def test_cli_writes_without_api_key_and_protects_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "原稿.txt"
            with patch.dict(os.environ, {}, clear=True), \
                    patch("scenario_gen.find_codex", return_value=["codex"]), \
                    patch("scenario_gen.fetch_article", return_value="記事本文"), \
                    patch("scenario_gen.CodexClient") as client:
                client.return_value.generate.return_value = "工事のお知らせです。迂回してください。"
                args = ["https://example.com/article", "3", "-o", str(target)]
                self.assertEqual(app.main(args), 0)
                self.assertEqual(target.read_text(encoding="utf-8"), "工事のお知らせです。\n迂回してください。\n")
                self.assertEqual(app.main(args), 1)
                self.assertEqual(client.return_value.generate.call_count, 1)

    def test_invalid_minutes(self):
        for value in ("0", "-1", "nan", "inf"):
            with self.assertRaises(argparse.ArgumentTypeError):
                app.positive_number(value)


class DialogueTests(unittest.TestCase):
    def test_repeats_speaker_per_sentence_and_preserves_csv_commas(self):
        text = 'jahic-chan-001,いつですか？どこですか？\netc-bouya-001,"対象はA,Bです。確認しましょう。"'
        result = app.normalize_dialogue(text)
        self.assertEqual(list(csv.reader(io.StringIO(result))), [
            [app.LEARNER, "いつですか？"], [app.LEARNER, "どこですか？"],
            [app.TEACHER, "対象はA,Bです。"], [app.TEACHER, "確認しましょう。"],
        ])
        self.assertEqual(app.spoken_character_count(result, True),
                         app.character_count("いつですか？どこですか？対象はA,Bです。確認しましょう。"))

    def test_invalid_dialogue_is_rejected(self):
        for text in ("", "jahic-chan-001,質問です。", "unknown,説明です。",
                     "jahic-chan-001,\netc-bouya-001,説明です。",
                     "jahic-chan-001:質問です。\netc-bouya-001,説明です。",
                     "jahic-chan-001,質問です。\netc-bouya-001,途中",
                     "jahic-chan-001,質問です。\netc-bouya-001,A,Bです。"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                app.normalize_dialogue(text)

    def test_malformed_output_is_rewritten_with_roles_in_prompt(self):
        client = Mock()
        valid = "jahic-chan-001,いつですか？\netc-bouya-001,夜間です。"
        client.generate.side_effect = ["不正な原稿です。", valid]
        result = app.generate_narration(client, "記事", "https://example.com", 3, 300, dialogue=True)
        self.assertEqual(result, valid + "\n")
        self.assertEqual(client.generate.call_count, 2)
        instructions = client.generate.call_args.args[0]
        self.assertIn("教わる役はjahic-chan-001", instructions)
        self.assertIn("教える役はetc-bouya-001", instructions)

    def test_budget_excludes_speaker_names_but_counts_both_speeches(self):
        client = Mock()
        client.generate.return_value = "jahic-chan-001," + "あ" * 400 + "？\netc-bouya-001," + "い" * 408 + "。"
        result = app.generate_narration(client, "記事", "https://example.com", 3, 300, dialogue=True)
        self.assertEqual(app.spoken_character_count(result, True), 810)
        self.assertGreater(app.character_count(result), 810)
        self.assertEqual(client.generate.call_count, 1)
        client.generate.return_value = result.replace("？", "あ？")
        with self.assertRaises(ValueError):
            app.generate_narration(client, "記事", "https://example.com", 3, 300, dialogue=True)

    def test_dialogue_cli_writes_csv_text(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "dialogue.txt"
            raw = "jahic-chan-001,いつですか？\netc-bouya-001,夜間です。"
            with patch("scenario_gen.find_codex", return_value=["codex"]), \
                    patch("scenario_gen.fetch_article", return_value="記事本文"), \
                    patch("scenario_gen.CodexClient") as client:
                client.return_value.generate.return_value = raw
                self.assertEqual(app.main(["https://example.com", "3", "--dialogue", "-o", str(target)]), 0)
                self.assertEqual(target.read_text(encoding="utf-8"), raw + "\n")


class CodexClientTests(unittest.TestCase):
    @patch("scenario_gen.subprocess.run")
    def test_login_accepts_chatgpt(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, "", "Logged in using ChatGPT")
        app.CodexClient(["codex"]).check_login()

    @patch("scenario_gen.subprocess.run")
    def test_login_rejects_api_key_or_missing_login(self, run):
        for code, status in [(0, "Logged in using an API key"), (1, "Not logged in"), (0, "unknown")]:
            run.return_value = subprocess.CompletedProcess([], code, "", status)
            with self.assertRaises(ValueError):
                app.CodexClient(["codex"]).check_login()

    @patch("scenario_gen.subprocess.run")
    def test_timeout_propagates(self, run):
        run.side_effect = subprocess.TimeoutExpired("codex", 1)
        with self.assertRaises(subprocess.TimeoutExpired):
            app.CodexClient(["codex"], timeout=1).generate("指示", "記事")

    @patch("scenario_gen.subprocess.run")
    def test_nonzero_or_missing_output_rejected(self, run):
        for code in (1, 0):
            run.return_value = subprocess.CompletedProcess([], code, "", "")
            with self.assertRaises(ValueError):
                app.CodexClient(["codex"]).generate("指示", "記事")

    def test_subprocess_utf8_stdin_output_and_subscription_flags(self):
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "fake_codex.py"
            script.write_text('''import os, sys
from pathlib import Path
assert "OPENAI_API_KEY" not in os.environ
assert "CODEX_API_KEY" not in os.environ
assert "OPENAI_BASE_URL" not in os.environ
assert 'forced_login_method="chatgpt"' in sys.argv
assert 'model_provider="openai"' in sys.argv
assert sys.argv[sys.argv.index("--sandbox") + 1] == "read-only"
assert sys.argv[sys.argv.index("--model") + 1] == "test-model"
assert sys.stdin.buffer.read().decode("utf-8").replace("\\r\\n", "\\n") == "指示\\n\\n記事 & $(test)"
Path(sys.argv[sys.argv.index("--output-last-message") + 1]).write_text("生成した原稿です。", encoding="utf-8")
''', encoding="utf-8")
            with patch.dict(os.environ, {"OPENAI_API_KEY": "test", "CODEX_API_KEY": "test", "OPENAI_BASE_URL": "test"}):
                client = app.CodexClient([sys.executable, str(script)])
                self.assertEqual(client.generate("指示", "記事 & $(test)", "test-model"), "生成した原稿です。")

    def test_explicit_binary_not_found(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                app.find_codex(str(Path(directory) / "missing.exe"))


if __name__ == "__main__":
    unittest.main()
