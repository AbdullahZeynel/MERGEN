from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from mergen_executor.model_smoke import main


class ModelSmokeTests(unittest.TestCase):
    def test_missing_fixture_is_generic_and_leaks_no_path(self):
        with tempfile.TemporaryDirectory(prefix="mergen-sensitive-name-") as temporary:
            secret_path = Path(temporary) / "patient-name"
            stdout = io.StringIO()
            argv = ["model_smoke", "--model-root", "/model", "--imaging-venv", "/venv",
                    "--fixture", str(secret_path)]
            with patch("sys.argv", argv), redirect_stdout(stdout):
                self.assertEqual(main(), 2)
            self.assertNotIn(str(secret_path), stdout.getvalue())
            self.assertNotIn("patient-name", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
