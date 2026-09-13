from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from prepare_demo import DEFAULT_CASES, selected_cases


class CaseSelectionTests(unittest.TestCase):
    def test_default_keeps_reviewed_pair(self):
        with tempfile.TemporaryDirectory() as temp:
            self.assertEqual(selected_cases(Path(temp), None, False), list(DEFAULT_CASES))

    def test_all_cases_is_sorted_and_ignores_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "UCSF-PDGM-0007").mkdir()
            (root / "UCSF-PDGM-0004").mkdir()
            (root / "notes.txt").write_text("ignored")
            self.assertEqual(selected_cases(root, None, True),
                             ["UCSF-PDGM-0004", "UCSF-PDGM-0007"])

    def test_selection_modes_are_exclusive(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):
                selected_cases(Path(temp), ["UCSF-PDGM-0004"], True)


if __name__ == "__main__":
    unittest.main()
