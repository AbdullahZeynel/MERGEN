"""Dispatcher configuration and log redaction.
Run: python -m unittest discover -s mergen_dispatcher -t ."""
import io
import ipaddress
import logging
import subprocess
import sys
import unittest
from pathlib import Path

from mergen_dispatcher.config import ConfigError, DispatcherConfig
from mergen_dispatcher.logs import redacting_handler
from mergen_dispatcher.test_support import TOKEN, WORKER_ID

REPO = Path(__file__).resolve().parents[1]
# Built from the range so no address literal sits in the repository.
TAILSCALE_HOST = str(ipaddress.ip_network("100.64.0.0/10")[1])


def env(**overrides):
    values = {"MERGEN_CONTROL_URL": f"http://{TAILSCALE_HOST}:9100",
              "MERGEN_WORKER_TOKEN": TOKEN, "MERGEN_WORKER_ID": WORKER_ID}
    values.update(overrides)
    return {key: value for key, value in values.items() if value is not None}


class Configuration(unittest.TestCase):
    def test_defaults_are_safe_and_complete(self):
        config = DispatcherConfig.from_env(env())
        self.assertEqual(config.control_url, f"http://{TAILSCALE_HOST}:9100")
        self.assertEqual(config.runtime_root, Path("/var/lib/mergen/runtime"))
        self.assertEqual((config.poll_seconds, config.lease_renew_seconds,
                          config.request_timeout_seconds), (15, 60, 30))
        self.assertEqual(config.max_input_bytes, 2 * 1024**3)
        self.assertNotIn(TOKEN, repr(config))

    def test_missing_required_values_name_the_variable(self):
        for name in ("MERGEN_CONTROL_URL", "MERGEN_WORKER_TOKEN", "MERGEN_WORKER_ID"):
            with self.subTest(missing=name), self.assertRaisesRegex(ConfigError, name):
                DispatcherConfig.from_env(env(**{name: None}))

    def test_url_is_an_http_or_https_origin_only(self):
        accepted = (f"http://{TAILSCALE_HOST}:9100", "http://127.0.0.1:9100",
                    "http://localhost:9100", "http://[fd7a:115c:a1e0::1]:9100",
                    "https://control.example.org", f"http://{TAILSCALE_HOST}:9100/")
        for url in accepted:
            with self.subTest(url=url):
                self.assertEqual(DispatcherConfig.from_env(env(MERGEN_CONTROL_URL=url)).control_url,
                                 url.rstrip("/"))
        rejected = ("ftp://control.example.org", "control.example.org:9100",
                    "http://control.example.org:9100", "http://node.tailnet.ts" + ".net:9100",
                    f"http://{TAILSCALE_HOST}:9100/internal", f"http://{TAILSCALE_HOST}:9100/?a=1",
                    f"http://user:pw@{TAILSCALE_HOST}:9100", f"http://{TAILSCALE_HOST}:99999",
                    "http://192.0.2.10:9100")
        for url in rejected:
            with self.subTest(url=url), self.assertRaisesRegex(ConfigError, "MERGEN_CONTROL_URL"):
                DispatcherConfig.from_env(env(MERGEN_CONTROL_URL=url))

    def test_token_rules_never_echo_the_token(self):
        for token in ("short", "x" * 31, "has space " + "x" * 30, "tab\t" + "x" * 30):
            with self.subTest(length=len(token)):
                with self.assertRaises(ConfigError) as caught:
                    DispatcherConfig.from_env(env(MERGEN_WORKER_TOKEN=token))
                self.assertFalse(token in str(caught.exception), "the error echoed the token")

    def test_worker_id_and_runtime_root_are_constrained(self):
        for value in ("GPU", "a", "gpu_primary", "-gpu"):
            with self.subTest(worker=value), self.assertRaises(ConfigError):
                DispatcherConfig.from_env(env(MERGEN_WORKER_ID=value))
        for value in ("relative/runtime", "/var/lib/../runtime", ""):
            with self.subTest(root=value), self.assertRaisesRegex(ConfigError, "MERGEN_RUNTIME_ROOT"):
                DispatcherConfig.from_env(env(MERGEN_RUNTIME_ROOT=value))

    def test_numbers_are_bounded_and_named(self):
        cases = {"MERGEN_POLL_INTERVAL_SECONDS": ("0", "301", "soon", "nan", ""),
                 "MERGEN_LEASE_RENEW_SECONDS": ("4", "601"),
                 "MERGEN_REQUEST_TIMEOUT_SECONDS": ("0.5",),
                 "MERGEN_MAX_INPUT_BYTES": ("0", "1.5", str(65 * 1024**3))}
        for name, values in cases.items():
            for value in values:
                with self.subTest(name=name, value=value), self.assertRaisesRegex(ConfigError, name):
                    DispatcherConfig.from_env(env(**{name: value}))

    def test_service_exits_2_on_a_configuration_error_without_values(self):
        result = subprocess.run(
            [sys.executable, "-m", "mergen_dispatcher"], cwd=REPO, capture_output=True, text=True,
            env={"MERGEN_CONTROL_URL": "http://control.example.org:9100",
                 "MERGEN_WORKER_TOKEN": TOKEN, "MERGEN_WORKER_ID": WORKER_ID}, timeout=60)
        self.assertEqual(result.returncode, 2)
        self.assertIn("MERGEN_CONTROL_URL", result.stderr)
        self.assertFalse(TOKEN in result.stderr + result.stdout, "the token reached the output")


class Redaction(unittest.TestCase):
    def test_token_address_and_bearer_are_removed_from_messages_and_tracebacks(self):
        config = DispatcherConfig.from_env(env())
        stream = io.StringIO()
        logger = logging.getLogger("mergen.test.redaction")
        logger.propagate = False
        logger.addHandler(redacting_handler(config, stream))
        self.addCleanup(logger.removeHandler, logger.handlers[-1])
        logger.error("request to %s with Bearer %s", config.control_url, TOKEN)
        try:
            raise RuntimeError(f"failed talking to {TAILSCALE_HOST}")
        except RuntimeError:
            logger.exception("third-party failure")
        text = stream.getvalue()
        for secret in (TOKEN, TAILSCALE_HOST, config.control_url):
            self.assertFalse(secret in text, "a redacted value reached the log")
        self.assertIn("[redacted]", text)


if __name__ == "__main__":
    unittest.main()
