import contextlib
import io
import logging
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nonebot.log import logger

from app.config import Settings
from app.privacy import configure_private_logging
from configure import configure
from scripts.check_privacy import check_project, inspect_text


class PrivacyTests(unittest.TestCase):
    def test_config_diagnostics_hide_identifiers_names_and_private_endpoints(self):
        settings = Settings(
            qq_app_id="test-application-id", qq_app_secret="test-secret",
            bot_name="test-private-name", allowed_groups=frozenset({"test-private-group"}),
            llm_base_url="https://private-gateway.example/v1", llm_model="test-internal-model",
            llm_api_key="test-model-key",
        )
        visible = repr(settings) + repr(settings.resolve_llm()) + str(settings.status())
        for value in (settings.qq_app_id, settings.qq_app_secret, settings.bot_name,
                      settings.llm_base_url, settings.llm_model, settings.llm_api_key, "test-private-group"):
            self.assertNotIn(value, visible)

    def test_framework_logs_do_not_render_message_exception_locals_or_extras(self):
        output = io.StringIO()
        configure_private_logging(output)
        self.addCleanup(configure_private_logging)
        sensitive = "test-sensitive-chat-and-credential"
        logger.bind(user=sensitive).info("User {} says {}", sensitive, sensitive)
        logger.opt(colors=True).info("<green>Private event</green>: {}", sensitive)
        try:
            raise RuntimeError("invalid appid or secret: " + sensitive)
        except RuntimeError:
            logger.exception("QQ | Failed to get gateway info. {}", sensitive)
        logging.getLogger("asyncio").error("Task failed: %s", sensitive)
        visible = output.getvalue()
        self.assertNotIn(sensitive, visible)
        self.assertNotIn("Traceback", visible)
        self.assertNotIn(str(Path(__file__)), visible)
        self.assertIn("QQ 身份验证失败", visible)

    def test_configure_does_not_echo_saved_private_metadata(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / ".env").write_text(
                'QQ_APP_ID=123\nQQ_APP_SECRET=test-secret\nBOT_NAME=test-private-name\n'
                'LLM_PROVIDER=compatible\nLLM_BASE_URL=https://private-gateway.example/v1\n'
                'LLM_MODEL=test-internal-model\nLLM_API_KEY=test-model-key\n', encoding="utf-8",
            )
            prompts = []
            def blank(prompt):
                prompts.append(prompt)
                return ""
            output = io.StringIO()
            with patch("configure.ROOT", root), patch("builtins.input", side_effect=blank), \
                    patch("configure.getpass", side_effect=blank), contextlib.redirect_stdout(output):
                self.assertEqual(configure(), 0)
            visible = output.getvalue() + " ".join(prompts)
            for value in ("test-secret", "test-model-key", "test-private-name", "private-gateway.example", "test-internal-model"):
                self.assertNotIn(value, visible)

    def test_nonempty_example_secret_is_rejected_even_without_a_known_local_value(self):
        value = "not-a-real-credential"
        findings = inspect_text(".env.example", "QQ_APP_SECRET=" + value)
        self.assertTrue(findings)
        self.assertNotIn(value, repr(findings))

    def test_ignored_env_is_excluded_but_force_staged_env_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            def run(*args):
                subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)
            run("init", "-q")
            (root / ".gitignore").write_text(".env\n", encoding="utf-8")
            (root / ".env").write_text("QQ_APP_SECRET=test-local-secret\n", encoding="utf-8")
            (root / ".env.example").write_text("QQ_APP_SECRET=\n", encoding="utf-8")
            findings, _ = check_project(root)
            self.assertFalse(findings)
            run("add", "-f", ".env")
            findings, _ = check_project(root, staged=True)
            self.assertTrue(any(f.path == ".env" for f in findings))
            self.assertNotIn("test-local-secret", repr(findings))

    def test_known_value_and_api_key_formats_are_rejected_in_source(self):
        credential = "sk-" + "a" * 24
        findings = inspect_text("example.py", "value = '" + credential + "'\n", (credential,))
        self.assertTrue(findings)
        self.assertNotIn(credential, repr(findings))
