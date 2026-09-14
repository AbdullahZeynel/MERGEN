"""The spool directory contract the dispatcher enforces before it starts.
Run: python -m unittest discover -s mergen_dispatcher -t ."""
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mergen_dispatcher.spool import Spool, SpoolLayoutError
from mergen_dispatcher.test_support import TOKEN, WORKER_ID, make_runtime
from mergen_spool import contract

REPO = Path(__file__).resolve().parents[1]
EXPECTED = {"staging": contract.STAGING_MODE, "jobs": contract.JOBS_MODE, "trash": contract.TRASH_MODE}


def with_ids(info: os.stat_result, uid: int | None = None, gid: int | None = None) -> os.stat_result:
    values = list(info[:10])
    values[4] = info.st_uid if uid is None else uid
    values[5] = info.st_gid if gid is None else gid
    return os.stat_result(values)


def foreign_directory(target: Path, **ids):
    """os.lstat, except that `target` reports other ids. Real chown needs root;
    the check under test only reads what lstat returns."""
    real, wanted = os.lstat, os.fspath(target)

    def lstat(path, *args, **kwargs):
        info = real(path, *args, **kwargs)
        return with_ids(info, **ids) if os.fspath(path) == wanted else info

    return patch("os.lstat", side_effect=lstat)


class SubdirectoryContract(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="mergen-layout-test-")
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.root = make_runtime(self.base)
        self.spool = Spool(self.root, 1024)

    def test_created_directories_follow_the_contract_exactly(self):
        self.spool.prepare()
        group = os.lstat(self.root).st_gid
        for name, mode in EXPECTED.items():
            info = os.lstat(self.root / name)
            with self.subTest(directory=name):
                self.assertEqual(stat.S_IMODE(info.st_mode), mode)
                self.assertEqual((info.st_uid, info.st_gid), (os.geteuid(), group))
        self.spool.prepare()  # a restart accepts the layout it created

    def test_existing_directories_outside_the_contract_stop_the_service(self):
        self.spool.prepare()
        for name, mode in EXPECTED.items():
            for wrong in (mode | 0o004, mode | 0o007, mode | 0o070, mode & ~stat.S_ISGID):
                with self.subTest(directory=name, mode=f"{wrong:04o}"):
                    os.chmod(self.root / name, wrong)
                    try:
                        with self.assertRaisesRegex(SpoolLayoutError, f"{name}/ has mode {wrong:04o}"):
                            self.spool.prepare()
                    finally:
                        os.chmod(self.root / name, mode)

    def test_a_link_or_a_file_in_place_of_a_directory_stops_the_service(self):
        outside = self.base / "outside"
        outside.mkdir()
        (self.root / "staging").symlink_to(outside)
        (self.root / "jobs").write_text("not a directory", encoding="utf-8")
        with self.assertRaisesRegex(SpoolLayoutError, "staging/ is not a real directory"):
            self.spool.prepare()
        (self.root / "staging").unlink()
        with self.assertRaisesRegex(SpoolLayoutError, "jobs/ is not a real directory"):
            self.spool.prepare()
        self.assertEqual(list(outside.iterdir()), [], "the link was written through")
        self.assertEqual(stat.S_IMODE(os.lstat(outside).st_mode) & 0o7000, 0)

    def test_a_foreign_owner_or_group_stops_the_service(self):
        self.spool.prepare()
        target = self.root / "jobs"
        info = os.lstat(target)
        with foreign_directory(target, gid=info.st_gid + 1), \
                self.assertRaisesRegex(SpoolLayoutError, "jobs/ does not belong to the runtime root's group"):
            self.spool.prepare()
        with foreign_directory(target, uid=info.st_uid + 1), \
                self.assertRaisesRegex(SpoolLayoutError, "jobs/ is not owned by the dispatcher"):
            self.spool.prepare()

    def test_a_root_group_the_dispatcher_is_not_in_stops_the_service(self):
        stranger = max({os.getegid(), *os.getgroups()}) + 1000
        real = os.lstat

        def lstat(path, *args, **kwargs):
            info = real(path, *args, **kwargs)
            return with_ids(info, gid=stranger) if os.fspath(path) == str(self.root) else info

        with patch("os.lstat", side_effect=lstat), \
                self.assertRaisesRegex(SpoolLayoutError, "not a member of the runtime root's group"):
            self.spool.prepare()

    def test_the_service_exits_2_on_an_unsafe_spool(self):
        self.spool.prepare()
        os.chmod(self.root / "jobs", 0o2757)
        result = subprocess.run(
            [sys.executable, "-m", "mergen_dispatcher"], cwd=REPO, capture_output=True, text=True,
            timeout=60, env={"MERGEN_CONTROL_URL": "http://127.0.0.1:9", "MERGEN_WORKER_TOKEN": TOKEN,
                             "MERGEN_WORKER_ID": WORKER_ID, "MERGEN_RUNTIME_ROOT": str(self.root)})
        self.assertEqual(result.returncode, 2, result.stderr[-300:])
        self.assertIn("jobs/ has mode 2757", result.stderr)
        self.assertFalse(TOKEN in result.stdout + result.stderr, "the token reached the output")


if __name__ == "__main__":
    unittest.main()
