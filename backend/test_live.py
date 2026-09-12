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
        self.token = "worker-control-token-that-is-long-enough"
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
            "/api/live/jobs", headers=csrf,
            files={"bundle": ("input.zip", input_payload, "application/zip")},
        )
        self.assertEqual(created.status_code, 202, created.text)
        job_id = created.json()["jobId"]

        claim = await self.control.post(
            "/internal/jobs/claim", headers=self.worker_headers,
            json={"capabilities": ["imaging"]},
        )
        self.assertEqual(claim.status_code, 200, claim.text)
        self.assertEqual(claim.json()["job"]["jobId"], job_id)
        downloaded_input = await self.control.get(f"/internal/jobs/{job_id}/input", headers=self.worker_headers)
        self.assertEqual(downloaded_input.content, input_payload)

        self.assertEqual(
            (await self.control.post(f"/internal/jobs/{job_id}/lease", headers=self.worker_headers)).status_code, 200
        )
        completed = await self.control.post(
            f"/internal/jobs/{job_id}/result", headers=self.worker_headers,
            files={"bundle": ("result.zip", imaging_result(job_id), "application/zip")},
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
            "/api/live/jobs", headers=csrf,
            files={"bundle": ("unsafe.zip", unsafe, "application/zip")},
        )
        self.assertEqual(response.status_code, 422)

        created = await self.public.post(
            "/api/live/jobs", headers=csrf,
            files={"bundle": ("input.zip", imaging_input(), "application/zip")},
        )
        job_id = created.json()["jobId"]
        await self.control.post("/internal/jobs/claim", headers=self.worker_headers, json={"capabilities": ["imaging"]})
        with self.store.connect() as db:
            db.execute("UPDATE jobs SET lease_until=0 WHERE id=?", (job_id,))
        self.assertEqual(self.store.cleanup()["staleJobs"], 1)
        with self.store.connect() as db:
            self.assertEqual(db.execute("SELECT status FROM jobs WHERE id=?", (job_id,)).fetchone()[0], "queued")

    async def test_worker_authentication_is_required(self):
        self.assertEqual((await self.control.get("/internal/health")).status_code, 401)
        self.assertEqual((await self.control.get("/internal/health", headers=self.worker_headers)).status_code, 200)
        heartbeat = await self.control.post(
            "/internal/workers/heartbeat", headers=self.worker_headers,
            json={"capabilities": ["imaging", "genomics"]},
        )
        self.assertEqual(heartbeat.status_code, 200)
        self.assertEqual(self.store.available_capabilities(), ["genomics", "imaging"])

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
        for name in ("imaging-input.v1.example.json", "genomics-input.v1.example.json"):
            parsed = InputManifest.model_validate_json((examples / name).read_bytes())
            self.assertEqual(parsed.schemaVersion, 1)
        profiles = await self.public.get("/api/live/profiles")
        self.assertEqual(profiles.status_code, 200)
        self.assertEqual({item["disease"] for item in profiles.json()["profiles"]},
                         {"glioma", "glioma-variant-pathogenicity"})

    async def test_only_one_job_can_be_claimed_globally(self):
        first = self.store.create_session()
        second = self.store.create_session()
        self.store.create_job(first["id"], "imaging", "glioma", "a" * 64)
        self.store.create_job(second["id"], "genomics", "glioma-variant-pathogenicity", "b" * 64)
        self.assertIsNotNone(self.store.claim("gpu-primary", ["imaging", "genomics"]))
        self.assertIsNone(self.store.claim("gpu-standby", ["imaging", "genomics"]))


if __name__ == "__main__":
    unittest.main()
