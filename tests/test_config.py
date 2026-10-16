import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.config import Settings
from configure import configure


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        env = patch.dict(os.environ, {}, clear=True)
        env.start()
        self.addCleanup(env.stop)

    def test_environment_overrides_local_config(self):
        (self.root / ".env").write_text(
            'QQ_APP_ID=123\nQQ_APP_SECRET=local-secret\nDEEPSEEK_API_KEY=local-key\n'
            'BOT_NAME=本地名字\nHISTORY_TURNS=2\nQQ_ALLOWED_GROUPS=group-a, group-b,,\n', encoding="utf-8"
        )
        os.environ["QQ_APP_SECRET"] = "environment-secret"
        os.environ["BOT_NAME"] = "  自定义鲸鲸  "
        with patch("app.config.ROOT", self.root):
            settings = Settings.load()
        settings.validate_qq()
        self.assertEqual(settings.qq_app_secret, "environment-secret")
        self.assertEqual(settings.allowed_groups, frozenset({"group-a", "group-b"}))
        self.assertEqual(settings.history_turns, 2)
        self.assertEqual(settings.bot_name, "自定义鲸鲸")

    def test_status_and_repr_do_not_expose_secrets(self):
        settings = Settings(qq_app_id="123", qq_app_secret="fake-qq-secret", deepseek_api_key="fake-api-key", llm_api_key="generic-key")
        visible = str(settings.status()) + repr(settings)
        self.assertNotIn("fake-qq-secret", visible)
        self.assertNotIn("fake-api-key", visible)
        self.assertNotIn("generic-key", visible)

    def test_invalid_numeric_config_has_safe_message(self):
        for name, value in (("HISTORY_TURNS", "accidental-secret"), ("HISTORY_TURNS", "11"),
                            ("COOLDOWN_SECONDS", "nan"), ("COOLDOWN_SECONDS", "-1"),
                            ("LLM_MAX_TOKENS", "0"), ("LLM_MAX_TOKENS", "32769")):
            with self.subTest(name=name, value=value), patch.dict(os.environ, {name: value}, clear=True):
                with patch("app.config.ROOT", self.root), self.assertRaises(ValueError) as error:
                    Settings.load()
                self.assertNotIn("accidental-secret", str(error.exception))

    def test_configure_preserves_existing_values_and_masks_output(self):
        path = self.root / ".env"
        path.write_text('BOT_NAME=已有名字\nQQ_APP_ID=123\nQQ_APP_SECRET=kept-secret\nDEEPSEEK_API_KEY=kept-key\nHISTORY_TURNS=2\n', encoding="utf-8")
        output = io.StringIO()
        with patch("configure.ROOT", self.root), patch("builtins.input", return_value=""), \
                patch("configure.getpass", return_value=""), contextlib.redirect_stdout(output):
            self.assertEqual(configure(), 0)
        with patch("app.config.ROOT", self.root):
            settings = Settings.load()
        self.assertEqual(settings.qq_app_secret, "kept-secret")
        self.assertEqual(settings.resolve_llm().api_key, "kept-key")
        self.assertEqual(settings.history_turns, 2)
        self.assertEqual(settings.bot_name, "已有名字")
        self.assertNotIn("kept-secret", output.getvalue())
        self.assertNotIn("kept-key", output.getvalue())

    def test_invalid_configuration_does_not_replace_existing_file(self):
        path = self.root / ".env"
        original = "# keep this file\nQQ_APP_ID=invalid\n"
        path.write_text(original, encoding="utf-8")
        with patch("configure.ROOT", self.root), patch("builtins.input", return_value=""), \
                patch("configure.getpass", return_value=""), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(configure(), 2)
        self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_new_configuration_overrides_legacy_deepseek_values(self):
        with patch.dict(os.environ, {
            "DEEPSEEK_API_KEY": "legacy-key", "DEEPSEEK_MODEL": "legacy-model",
            "LLM_API_KEY": "new-key", "LLM_MODEL": "new-model",
        }):
            with patch("app.config.ROOT", self.root):
                config = Settings.load().resolve_llm()
        self.assertEqual((config.api_key, config.model), ("new-key", "new-model"))

    def test_other_services_never_inherit_legacy_deepseek_key(self):
        for provider in ("compatible", "ollama", "openai", "anthropic", "gemini", "deepseek"):
            with self.subTest(provider=provider):
                config = Settings(
                    llm_provider=provider, llm_base_url="https://another-service.example/v1",
                    llm_model="chosen-model", deepseek_api_key="legacy-private-key",
                ).resolve_llm()
                self.assertEqual(config.api_key, "")

    def test_invalid_provider_urls_and_parameters_fail_without_echoing_values(self):
        cases = [
            {"llm_provider": "unsupported"},
            {"llm_provider": "compatible", "llm_model": "model"},
            {"llm_provider": "openai"},
            {"llm_base_url": "https://user:private-secret@api.example"},
            {"llm_base_url": "https://api.example?key=private-secret"},
            {"llm_base_url": "https://api.example:bad-port"},
            {"llm_base_url": "file:///private-secret"},
            {"llm_extra_body": []},
            {"llm_extra_body": {"messages": "private-secret"}},
            {"llm_extra_body": {"generationConfig": "private-secret"}},
        ]
        for case in cases:
            with self.subTest(case=case), self.assertRaises(ValueError) as error:
                Settings(**case).resolve_llm()
            self.assertNotIn("private-secret", str(error.exception))

    def test_invalid_extra_json_has_safe_message(self):
        with patch.dict(os.environ, {"LLM_EXTRA_BODY": "private-secret"}):
            with patch("app.config.ROOT", self.root), self.assertRaises(ValueError) as error:
                Settings.load()
        self.assertNotIn("private-secret", str(error.exception))

    def test_wizard_switch_clears_old_key_and_specific_parameters(self):
        path = self.root / ".env"
        cases = [
            ("deepseek", "compatible", "https://api.deepseek.com"),
            ("compatible", "compatible", "https://old-service.example/v1"),
            ("deepseek", "deepseek", "https://api.deepseek.com"),
        ]
        for old_provider, provider, old_url in cases:
            with self.subTest(old=old_provider, new=provider), patch.dict(os.environ, {}, clear=True):
                path.write_text(
                    f'QQ_APP_ID=123\nQQ_APP_SECRET=qq-secret\nLLM_PROVIDER={old_provider}\n'
                    f'LLM_BASE_URL={old_url}\nLLM_MODEL=old-model\nLLM_API_KEY=old-private-key\n'
                    'DEEPSEEK_API_KEY=legacy-private-key\nLLM_EXTRA_BODY={"thinking":{"type":"disabled"}}\n',
                    encoding="utf-8",
                )
                inputs = ["", provider, "https://new-service.example/v1", "new-model"]
                with patch("configure.ROOT", self.root), patch("builtins.input", side_effect=inputs), \
                        patch("configure.getpass", return_value=""), contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(configure(), 0)
                with patch("app.config.ROOT", self.root):
                    settings = Settings.load()
                self.assertEqual(settings.resolve_llm().api_key, "")
                self.assertEqual(settings.llm_extra_body, {})
                self.assertNotIn("DEEPSEEK_API_KEY", path.read_text(encoding="utf-8"))
