"""VPS control-plane lifecycle tests with synthetic transport fixtures."""
from __future__ import annotations

import hashlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import httpx

from backend.api import app as public_app
from backend.control import app as control_app, get_store as get_control_store
from backend.live_api import get_live_store
from backend.live_contracts import InputManifest
from backend.live_store import LiveSettings, LiveStore


def zip_bytes(files: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, payload in files.items():
            archive.writestr(name, payload)
    return output.getvalue()


def imaging_input() -> bytes:
    volumes = {
        "volumes/t1.nii.gz": b"t1",
        "volumes/t1ce.nii.gz": b"t1ce",
        "volumes/t2.nii.gz": b"t2",
        "volumes/flair.nii.gz": b"flair",
    }
    manifest = {
        "schemaVersion": 1,
        "module": "imaging",
        "disease": "glioma",
        "files": [
            {"path": name, "role": "volume", "modality": modality}
            for name, modality in zip(volumes, ("T1", "T1CE", "T2", "FLAIR"))
        ],
    }
    return zip_bytes({"input.json": json.dumps(manifest).encode(), **volumes})


def imaging_result(job_id: str) -> bytes:
    files = {
        "report.json": b'{"status":"synthetic-transport"}',
        "prediction.nii.gz": b"synthetic-prediction-transport",
        "prediction.glb": b"synthetic-glb-transport",
    }
    kinds = {
        "report.json": "report-json",
        "prediction.nii.gz": "prediction-nifti",
        "prediction.glb": "prediction-glb",
    }
    manifest = {
        "schemaVersion": 1,
        "jobId": job_id,
        "module": "imaging",
        "disease": "glioma",
        "modelId": "mergen-imaging",
        "modelVersion": "test-1",
        "hasPrediction": True,
        "hasGroundTruth": False,
        "assets": [{"path": name, "kind": kinds[name],
                    "sha256": hashlib.sha256(payload).hexdigest(), "size": len(payload)}
                   for name, payload in files.items()],
    }
    return zip_bytes({"manifest.json": json.dumps(manifest).encode(), **files})


class LiveControlTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.store = LiveStore(LiveSettings(
            runtime_root=root / "runtime",
            database_path=root / "runtime/control.sqlite3",
            max_sessions=2,
            idle_seconds=180,
            absolute_seconds=1800,
            lease_seconds=60,
            max_attempts=2,
            max_claimed_jobs=1,
            max_upload_bytes=1024 * 1024,
            max_expanded_bytes=4 * 1024 * 1024,
            max_result_bytes=1024 * 1024,
        ))
        async def override_store():
            return self.store
        public_app.dependency_overrides[get_live_store] = override_store
        control_app.dependency_overrides[get_control_store] = override_store
        self.addCleanup(public_app.dependency_overrides.clear)
        self.addCleanup(control_app.dependency_overrides.clear)
        self.public = httpx.AsyncClient(transport=httpx.ASGITransport(app=public_app), base_url="https://testserver")
        self.control = httpx.AsyncClient(transport=httpx.ASGITransport(app=control_app), base_url="https://worker.test")
        self.addAsyncCleanup(self.public.aclose)
        self.addAsyncCleanup(self.control.aclose)
        self.token = "worker-control-token-that-is-long-enough"  # repo-guard: allow (test fixture)
        self.access_code = "presentation-access-code"
        self.worker_headers = {
            "Authorization": f"Bearer {self.token}",
            "X-Mergen-Worker": "gpu-primary",
        }
        self.env = patch.dict("os.environ", {
            "MERGEN_CONTROL_TOKEN": self.token,
            "MERGEN_LIVE_ACCESS_HASH": hashlib.sha256(self.access_code.encode()).hexdigest(),
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        async def inline_to_thread(function, *args, **kwargs):
            return function(*args, **kwargs)
        self.to_thread = patch("asyncio.to_thread", new=inline_to_thread)
        self.to_thread.start()
        self.addCleanup(self.to_thread.stop)

    async def create_session(self):
        response = await self.public.post(
            "/api/live/session", headers={"X-Mergen-Live-Access": self.access_code}
        )
        self.assertEqual(response.status_code, 201, response.text)
        csrf = response.json()["csrfToken"]
        return {"X-Mergen-CSRF": csrf}

    async def test_session_capacity_csrf_and_cleanup(self):
        csrf = await self.create_session()
        self.assertEqual((await self.public.post("/api/live/session/heartbeat")).status_code, 403)
        self.assertEqual((await self.public.post("/api/live/session/heartbeat", headers=csrf)).status_code, 200)

        second = httpx.AsyncClient(transport=httpx.ASGITransport(app=public_app), base_url="https://second.test")
        third = httpx.AsyncClient(transport=httpx.ASGITransport(app=public_app), base_url="https://third.test")
        self.addAsyncCleanup(second.aclose)
        self.addAsyncCleanup(third.aclose)
        access = {"X-Mergen-Live-Access": self.access_code}
        self.assertEqual((await second.post("/api/live/session", headers=access)).status_code, 201)
        self.assertEqual((await third.post("/api/live/session", headers=access)).status_code, 429)

        self.assertEqual((await self.public.delete("/api/live/session", headers=csrf)).status_code, 204)
        self.assertEqual((await self.public.get("/api/live/session")).status_code, 401)
        self.assertEqual((await third.post("/api/live/session", headers=access)).status_code, 201)

    async def test_complete_job_download_and_delete(self):
        csrf = await self.create_session()
        input_payload = imaging_input()
        created = await self.public.post(
            "/api/live/jobs", headers={**csrf, "Content-Type": "application/zip"},
            content=input_payload,
        )
        self.assertEqual(created.status_code, 202, created.text)
        job_id = created.json()["jobId"]

        claim = await self.control.post(
            "/internal/jobs/claim", headers=self.worker_headers,
            json={"capabilities": ["imaging"]},
        )
        self.assertEqual(claim.status_code, 200, claim.text)
        self.assertEqual(claim.json()["job"]["jobId"], job_id)
        wrong_worker = {**self.worker_headers, "X-Mergen-Worker": "gpu-standby"}
        self.assertEqual((await self.control.get(
            f"/internal/jobs/{job_id}/input", headers=wrong_worker
        )).status_code, 404)
        downloaded_input = await self.control.get(f"/internal/jobs/{job_id}/input", headers=self.worker_headers)
        self.assertEqual(downloaded_input.content, input_payload)

        self.assertEqual(
            (await self.control.post(f"/internal/jobs/{job_id}/lease", headers=self.worker_headers)).status_code, 200
        )
        result_bundle = imaging_result(job_id)
        completed = await self.control.post(
            f"/internal/jobs/{job_id}/result",
            headers={**self.worker_headers, "Content-Type": "application/zip",
                     "X-Mergen-Result-Sha256": hashlib.sha256(result_bundle).hexdigest()},
            content=result_bundle,
        )
        self.assertEqual(completed.status_code, 200, completed.text)

        status = await self.public.get(f"/api/live/jobs/{job_id}")
        self.assertEqual(status.json()["status"], "completed")
        self.assertFalse(status.json()["result"]["hasGroundTruth"])
        glb_url = status.json()["assetUrls"]["prediction.glb"]
        glb = await self.public.get(glb_url)
        self.assertEqual(glb.content, b"synthetic-glb-transport")
        self.assertEqual(glb.headers["content-type"], "model/gltf-binary")
        self.assertEqual((await self.public.get(
            f"/api/live/jobs/{job_id}/assets/not-declared"
        )).status_code, 404)
        result = await self.public.get(f"/api/live/jobs/{job_id}/download")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.headers["cache-control"], "no-store")

        session_id = self.store.get_session(self.public.cookies.get("mergen_session"))["id"]
        session_path = self.store.session_directory(session_id)
        self.assertTrue(session_path.exists())
        self.assertEqual((await self.public.delete("/api/live/session", headers=csrf)).status_code, 204)
        self.assertFalse(session_path.exists())
        with self.store.connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0], 0)

    async def test_invalid_archive_and_expired_lease_requeue(self):
        csrf = await self.create_session()
        unsafe = zip_bytes({"input.json": b"{}", "../escape": b"bad"})
        response = await self.public.post(
            "/api/live/jobs", headers={**csrf, "Content-Type": "application/zip"},
            content=unsafe,
        )
        self.assertEqual(response.status_code, 422)

        created = await self.public.post(
            "/api/live/jobs", headers={**csrf, "Content-Type": "application/zip"},
            content=imaging_input(),
        )
        job_id = created.json()["jobId"]
        await self.control.post("/internal/jobs/claim", headers=self.worker_headers, json={"capabilities": ["imaging"]})
        with self.store.connect() as db:
            db.execute("UPDATE jobs SET lease_until=0 WHERE id=?", (job_id,))
        self.assertEqual(self.store.cleanup()["staleJobs"], 1)
        with self.store.connect() as db:
            self.assertEqual(db.execute("SELECT status FROM jobs WHERE id=?", (job_id,)).fetchone()[0], "queued")

    async def test_streaming_upload_limit_removes_partial_file(self):
        csrf = await self.create_session()
        response = await self.public.post(
            "/api/live/jobs",
            headers={**csrf, "Content-Type": "application/zip"},
            content=b"x" * (self.store.settings.max_upload_bytes + 1),
        )
        self.assertEqual(response.status_code, 413)
        session = self.store.get_session(self.public.cookies.get("mergen_session"))
        self.assertEqual(list(self.store.session_directory(session["id"]).glob("*.part")), [])

    async def test_worker_authentication_is_required(self):
        self.assertEqual((await self.control.get("/internal/health")).status_code, 401)
        self.assertEqual((await self.control.get("/internal/health", headers=self.worker_headers)).status_code, 200)
        heartbeat = await self.control.post(
            "/internal/workers/heartbeat", headers=self.worker_headers,
            json={"capabilities": ["imaging"]},
        )
        self.assertEqual(heartbeat.status_code, 200)
        self.assertEqual(self.store.available_capabilities(), ["imaging"])

    async def test_live_access_code_is_required_only_for_new_session(self):
        self.assertEqual((await self.public.post("/api/live/session")).status_code, 401)
        csrf = await self.create_session()
        self.assertEqual((await self.public.post("/api/live/session")).status_code, 201)
        self.assertEqual((await self.public.post("/api/live/session/heartbeat", headers=csrf)).status_code, 200)

    async def test_idle_session_files_and_rows_expire(self):
        await self.create_session()
        token = self.public.cookies.get("mergen_session")
        session = self.store.get_session(token)
        marker = self.store.session_directory(session["id"]) / "marker"
        marker.write_bytes(b"temporary")
        with self.store.connect() as db:
            db.execute("UPDATE sessions SET last_seen=0 WHERE id=?", (session["id"],))
        self.assertEqual(self.store.cleanup()["expiredSessions"], 1)
        self.assertFalse(marker.exists())
        self.assertIsNone(self.store.get_session(token))

    async def test_documented_input_examples_match_contract(self):
        examples = Path(__file__).parents[1] / "docs/contracts"
        for name in ("imaging-input.v1.example.json",):
            parsed = InputManifest.model_validate_json((examples / name).read_bytes())
            self.assertEqual(parsed.schemaVersion, 1)
        profiles = await self.public.get("/api/live/profiles")
        self.assertEqual(profiles.status_code, 200)
        self.assertEqual({item["disease"] for item in profiles.json()["profiles"]}, {"glioma"})

    async def test_only_one_job_can_be_claimed_globally(self):
        first = self.store.create_session()
        second = self.store.create_session()
        self.store.create_job(first["id"], "imaging", "glioma", "a" * 64)
        self.store.create_job(second["id"], "imaging", "glioma", "b" * 64)
        self.assertIsNotNone(self.store.claim("gpu-primary", ["imaging"]))
        self.assertIsNone(self.store.claim("gpu-standby", ["imaging"]))

    async def test_the_vps_completes_only_the_declared_result_digest(self):
        csrf = await self.create_session()
        created = await self.public.post(
            "/api/live/jobs", headers={**csrf, "Content-Type": "application/zip"},
            content=imaging_input(),
        )
        job_id = created.json()["jobId"]
        await self.control.post("/internal/jobs/claim", headers=self.worker_headers,
                                json={"capabilities": ["imaging"]})
        bundle = imaging_result(job_id)
        upload = {**self.worker_headers, "Content-Type": "application/zip"}
        path = f"/internal/jobs/{job_id}/result"
        missing = await self.control.post(path, headers=upload, content=bundle)
        wrong = await self.control.post(
            path, headers={**upload, "X-Mergen-Result-Sha256": "0" * 64}, content=bundle)
        self.assertEqual((missing.status_code, wrong.status_code), (422, 422))
        session = self.store.get_session(self.public.cookies.get("mergen_session"))
        self.assertEqual(self.store.job_for_session(job_id, session["id"])["status"], "claimed")
        self.assertFalse((self.store.job_directory(session["id"], job_id) / "result.zip").exists())
        right = await self.control.post(
            path, headers={**upload, "X-Mergen-Result-Sha256": hashlib.sha256(bundle).hexdigest()},
            content=bundle)
        self.assertEqual(right.status_code, 200)

    async def test_the_vps_accepts_no_result_once_the_lease_has_expired(self):
        csrf = await self.create_session()
        created = await self.public.post(
            "/api/live/jobs", headers={**csrf, "Content-Type": "application/zip"},
            content=imaging_input(),
        )
        job_id = created.json()["jobId"]
        await self.control.post("/internal/jobs/claim", headers=self.worker_headers,
                                json={"capabilities": ["imaging"]})
        with self.store.connect() as db:
            db.execute("UPDATE jobs SET lease_until=0 WHERE id=?", (job_id,))
        bundle = imaging_result(job_id)
        answer = await self.control.post(
            f"/internal/jobs/{job_id}/result",
            headers={**self.worker_headers, "Content-Type": "application/zip",
                     "X-Mergen-Result-Sha256": hashlib.sha256(bundle).hexdigest()},
            content=bundle)
        self.assertEqual(answer.status_code, 409)
        session = self.store.get_session(self.public.cookies.get("mergen_session"))
        self.assertNotEqual(self.store.job_for_session(job_id, session["id"])["status"], "completed")
        self.assertFalse((self.store.job_directory(session["id"], job_id) / "result.zip").exists())
        renewal = await self.control.post(f"/internal/jobs/{job_id}/lease", headers=self.worker_headers)
        self.assertEqual(renewal.status_code, 409)


class LiveSettingsEnvironmentTests(unittest.IsolatedAsyncioTestCase):
    """systemd must never fall back to the checkout-relative runtime default."""

    SYSTEMD = {"INVOCATION_ID": "0" * 32}

    def test_systemd_refuses_the_checkout_default(self):
        with patch.dict("os.environ", self.SYSTEMD, clear=True):
            with self.assertRaisesRegex(ValueError, "MERGEN_RUNTIME_ROOT"):
                LiveSettings.from_env()

    def test_systemd_requires_an_explicit_database_inside_the_runtime(self):
        cases = (
            ({"MERGEN_RUNTIME_ROOT": "/srv/mergen/runtime"}, "MERGEN_DATABASE_PATH"),
            ({"MERGEN_RUNTIME_ROOT": "relative/runtime",
              "MERGEN_DATABASE_PATH": "/srv/mergen/runtime/control.sqlite3"}, "MERGEN_RUNTIME_ROOT"),
            ({"MERGEN_RUNTIME_ROOT": "/srv/mergen/runtime",
              "MERGEN_DATABASE_PATH": "/var/tmp/control.sqlite3"}, "inside"),
        )
        for env, message in cases:
            with self.subTest(expected=message), patch.dict("os.environ", {**self.SYSTEMD, **env}, clear=True):
                with self.assertRaisesRegex(ValueError, message):
                    LiveSettings.from_env()

    def test_systemd_uses_the_explicit_paths(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict("os.environ", {
            **self.SYSTEMD, "MERGEN_RUNTIME_ROOT": tmp,
            "MERGEN_DATABASE_PATH": f"{tmp}/control.sqlite3",
        }, clear=True):
            settings = LiveSettings.from_env()
        self.assertEqual(settings.runtime_root, Path(tmp).resolve())
        self.assertEqual(settings.database_path, Path(tmp).resolve() / "control.sqlite3")

    def test_local_development_keeps_the_checkout_default(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(LiveSettings.from_env().runtime_root, Path(".local/runtime").resolve())

    def test_invalid_number_is_named_without_its_value(self):
        canary = "ten-canary-value"
        with patch.dict("os.environ", {"MERGEN_MAX_ACTIVE_SESSIONS": canary}, clear=True):
            with self.assertRaises(ValueError) as caught:
                LiveSettings.from_env()
        self.assertIn("MERGEN_MAX_ACTIVE_SESSIONS", str(caught.exception))
        self.assertFalse(canary in str(caught.exception), "the error echoed a configured value")

    async def test_misconfigured_live_layer_answers_503(self):
        with patch("backend.live_api._store", None), \
                patch.dict("os.environ", self.SYSTEMD, clear=True):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=public_app),
                                         base_url="https://testserver") as client:
                with self.assertLogs("mergen.live", level="ERROR"):
                    response = await client.get("/api/live/session")
                profiles = await client.get("/api/live/profiles")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(profiles.status_code, 200)


if __name__ == "__main__":
    unittest.main()
