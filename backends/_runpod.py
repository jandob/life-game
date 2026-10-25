"""RunPod Serverless client shared by the runpod_* backends (standard library only).

``run(payload, endpoint)`` submits ``{"input": payload}`` to ``/run``, polls ``/status`` until the job
ends, cancels it on timeout and returns the worker's ``output``. The API key comes from ``RUNPOD_API_KEY``.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

API = os.environ.get("RUNPOD_API_BASE", "https://api.runpod.ai/v2")
MAX_INPUT_BYTES = 10 * 1024 * 1024          # RunPod's /run payload limit
DONE = {"COMPLETED", "FAILED", "CANCELLED", "TIMED_OUT"}


def _request(url: str, key: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if data else "GET",
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"runpod: HTTP {e.code} for {url.split('/v2/')[-1]}: {e.read()[:300]!r}") from None


def api_key() -> str:
    key = os.environ.get("RUNPOD_API_KEY")
    if not key:
        raise SystemExit("runpod: set RUNPOD_API_KEY (e.g. in a git-ignored mise.local.toml)")
    return key


def run(payload: dict, endpoint: str, *, key: str | None = None, timeout_s: float = 1800, poll_s: float = 3.0,
        request=_request, sleep=time.sleep) -> tuple[dict, dict]:
    """Run one job; returns (output, status) where status has the job id, delayTime and executionTime."""
    key = key or api_key()
    body = {"input": payload}
    if len(json.dumps(body)) > MAX_INPUT_BYTES:
        raise RuntimeError("runpod: job too large for /run (10 MB); use fewer or smaller references")
    job_id = request(f"{API}/{endpoint}/run", key, body)["id"]
    print(f"runpod: job {job_id} queued", file=sys.stderr, flush=True)
    t0 = time.monotonic()
    while True:
        st = request(f"{API}/{endpoint}/status/{job_id}", key)
        if st.get("status") in DONE:
            break
        if time.monotonic() - t0 > timeout_s:
            request(f"{API}/{endpoint}/cancel/{job_id}", key, {})
            raise RuntimeError(f"runpod: job {job_id} cancelled after {timeout_s:.0f}s ({st.get('status')})")
        sleep(poll_s)
    if st["status"] != "COMPLETED":
        raise RuntimeError(f"runpod: job {job_id} {st['status']}: {str(st.get('error') or st.get('output'))[:500]}")
    out = st.get("output") or {}
    if out.get("error"):
        raise RuntimeError(f"runpod: worker error: {out['error']}")
    return out, {"job": job_id, "delay_ms": st.get("delayTime"), "execution_ms": st.get("executionTime")}
