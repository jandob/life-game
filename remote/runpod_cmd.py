#!/usr/bin/env python
"""Local side of the RunPod remote runner: JobSpec JSON on stdin -> RunPod Serverless -> images on stdout.

    export ARTGEN_REMOTE_RUNPOD_CMD="python remote/runpod_cmd.py"   # from the artgen dir
    artgen.py generate --backend qwen_image21 --opt runner=remote:runpod --opt variant=base ...

Needs ``RUNPOD_API_KEY`` and ``ARTGEN_RUNPOD_ENDPOINT`` (the endpoint id) in the environment.
Prints ``[{png_base64, meta}, ...]`` (what ``runner.RemoteRunner`` expects); errors go to stderr, exit 1.
Standard library only.
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
        raise SystemExit(f"runpod: HTTP {e.code} for {url.split('/v2/')[-1]}: {e.read()[:300]!r}") from None


def run(spec: dict, key: str, endpoint: str, timeout_s: float = 1800, poll_s: float = 3.0,
        request=_request, sleep=time.sleep) -> list[dict]:
    payload = {"input": spec}
    if len(json.dumps(payload)) > MAX_INPUT_BYTES:
        raise SystemExit("runpod: job too large for /run (10 MB); use fewer or smaller references")
    job = request(f"{API}/{endpoint}/run", key, payload)
    job_id = job["id"]
    print(f"runpod: job {job_id} queued", file=sys.stderr, flush=True)
    t0 = time.monotonic()
    while True:
        st = request(f"{API}/{endpoint}/status/{job_id}", key)
        if st.get("status") in DONE:
            break
        if time.monotonic() - t0 > timeout_s:
            request(f"{API}/{endpoint}/cancel/{job_id}", key, {})
            raise SystemExit(f"runpod: job {job_id} cancelled after {timeout_s:.0f}s ({st.get('status')})")
        sleep(poll_s)
    if st["status"] != "COMPLETED":
        raise SystemExit(f"runpod: job {job_id} {st['status']}: {str(st.get('error') or st.get('output'))[:500]}")
    out = st.get("output") or {}
    if out.get("error"):
        raise SystemExit(f"runpod: worker error: {out['error']}")
    items = out.get("images") or []
    for it in items:
        it.setdefault("meta", {}).update(runpod_job=job_id, delay_ms=st.get("delayTime"),
                                         execution_ms=st.get("executionTime"))
    return items


def main() -> None:
    key = os.environ.get("RUNPOD_API_KEY")
    endpoint = os.environ.get("ARTGEN_RUNPOD_ENDPOINT")
    if not key or not endpoint:
        raise SystemExit("runpod: set RUNPOD_API_KEY and ARTGEN_RUNPOD_ENDPOINT")
    spec = json.loads(sys.stdin.read())
    timeout = float(os.environ.get("ARTGEN_RUNPOD_TIMEOUT", "1800"))
    print(json.dumps(run(spec, key, endpoint, timeout_s=timeout)))


if __name__ == "__main__":
    main()
