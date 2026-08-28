"""Integration test: the volunteer hub survives a process restart and recovers state.

Proves the durability contract: a submission made before a process kill is still
visible after a restart when both processes share the same lease-store path.
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx
import pytest
import uvicorn
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from bernstein.core.volunteer.hub_app import build_hub_app
from bernstein.core.volunteer.lease_store import LeaseStore

pytestmark = [pytest.mark.integration, pytest.mark.slow]

# Reasonable timeout for hub startup + first health check
HUB_START_TIMEOUT = 15.0


def _make_keypair() -> tuple[Ed25519PrivateKey, bytes]:
    private = Ed25519PrivateKey.generate()
    public = private.public_key()
    pem = public.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private, pem


def _enroll(client: httpx.Client, pubkey_pem: bytes) -> str:
    resp = client.post(
        "/volunteer/enroll",
        json={"public_key_pem": pubkey_pem.decode("ascii")},
    )
    assert resp.status_code == 201, f"enroll failed: {resp.text}"
    return resp.json()["worker_id"]


def _claim(client: httpx.Client, task_id: str, worker_id: str, ttl: int = 300) -> None:
    resp = client.post(
        f"/volunteer/tasks/{task_id}/claim",
        json={"worker_id": worker_id, "ttl_seconds": ttl},
    )
    assert resp.status_code == 201, f"claim failed: {resp.text}"


def _submit(
    client: httpx.Client,
    task_id: str,
    worker_id: str,
    bundle_digest: str = "sha256:testdigest",
    location: str = "https://example.com/bundle.tar.gz",
) -> None:
    resp = client.post(
        f"/volunteer/tasks/{task_id}/submit",
        json={
            "worker_id": worker_id,
            "bundle_digest": bundle_digest,
            "location": location,
        },
    )
    assert resp.status_code == 200, f"submit failed: {resp.text}"


def _hub_is_ready(url: str, timeout: float = HUB_START_TIMEOUT) -> bool:
    deadline = time.monotonic() + timeout
    with httpx.Client(timeout=3.0) as client:
        while time.monotonic() < deadline:
            try:
                resp = client.get(f"{url}/healthz")
                if resp.status_code == 200:
                    return True
            except (httpx.ConnectError, httpx.RemoteProtocolError, OSError):
                pass
            time.sleep(0.2)
    return False


class TestHubDurability:
    """Hub process lifecycle — restart survival."""

    def test_restart_survives_submission(self, tmp_path: Path) -> None:
        """A submission made before a kill is still present after restart.

        Sequence:
        1. Start hub with a temp lease store path.
        2. Enroll, claim, submit task t-restart-durable.
        3. Kill hub.
        4. Restart hub pointing at the same lease store.
        5. Assert the submission is still visible.
        """
        lease_store_path = tmp_path / "leases.jsonl"
        url = "http://127.0.0.1:18765"

        # Use the hub as a library (no subprocess needed for the first phase).
        # This exercises the same code path as the CLI.
        store = LeaseStore(lease_store_path)
        app = build_hub_app(store)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        server = uvicorn.Server(
            config=uvicorn.Config(app, host="127.0.0.1", port=18765, log_level="error"),
        )

        def _run_server() -> None:
            loop.run_until_complete(server.serve())

        thread = threading.Thread(target=_run_server, daemon=True)
        thread.start()

        # Wait for hub to be ready
        assert _hub_is_ready(url), "hub failed to start"

        try:
            with httpx.Client(base_url=url, timeout=10.0) as client:
                _, pubkey_pem = _make_keypair()
                worker_id = _enroll(client, pubkey_pem)
                _claim(client, "t-restart-durable", worker_id)
                _submit(client, "t-restart-durable", worker_id)
        finally:
            loop.call_soon_threadsafe(server.force_exit)
            thread.join(timeout=10)
            loop.close()

        # The hub is dead. Verify the lease store file was written.
        assert lease_store_path.exists(), "lease store file was not created"

        # Restart with a fresh in-memory state that replays the log.
        store2 = LeaseStore(lease_store_path)
        app2 = build_hub_app(store2)
        server2 = uvicorn.Server(
            config=uvicorn.Config(app2, host="127.0.0.1", port=18765, log_level="error"),
        )
        loop2 = asyncio.new_event_loop()
        asyncio.set_event_loop(loop2)

        def _run_server2() -> None:
            loop2.run_until_complete(server2.serve())

        thread2 = threading.Thread(target=_run_server2, daemon=True)
        thread2.start()

        assert _hub_is_ready(url), "hub failed to restart"

        try:
            # Verify the submission survived: query the lease directly from the
            # replayed store without needing another HTTP round-trip.
            lease = store2.lease_for("t-restart-durable")
            assert lease is not None, "task lease not found after restart"
            assert lease.submission is not None, "submission was lost after restart"
            assert lease.submission.bundle_digest == "sha256:testdigest"
            assert lease.submission.location == "https://example.com/bundle.tar.gz"
            assert lease.worker_id == worker_id
        finally:
            loop2.call_soon_threadsafe(server2.force_exit)
            thread2.join(timeout=10)
            loop2.close()
