#!/usr/bin/env python
"""Model-free tests for the RunPod remote runner command (remote/runpod_cmd.py), with a fake HTTP layer.

    .venv/bin/python test_remote.py
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "remote"))

import runpod_cmd  # noqa: E402


class FakeApi:
    def __init__(self, statuses, output=None):
        self.statuses = list(statuses)
        self.output = output
        self.calls = []

    def __call__(self, url, key, body=None):
        self.calls.append((url.split("/v2/")[-1], body))
        assert key == "k"
        if url.endswith("/run"):
            return {"id": "job1", "status": "IN_QUEUE"}
        if "/cancel/" in url:
            return {"status": "CANCELLED"}
        st = self.statuses.pop(0)
        return {"id": "job1", "status": st, "output": self.output if st == "COMPLETED" else None,
                "delayTime": 5, "executionTime": 7}


def test_completed_job_returns_images_with_meta() -> None:
    api = FakeApi(["IN_QUEUE", "IN_PROGRESS", "COMPLETED"],
                  {"images": [{"png_base64": "aGk=", "meta": {"seed": 3}}]})
    items = runpod_cmd.run({"prompt": "p", "seed": 3}, "k", "ep", request=api, sleep=lambda s: None)
    assert items == [{"png_base64": "aGk=", "meta": {"seed": 3, "runpod_job": "job1", "delay_ms": 5,
                                                     "execution_ms": 7}}]
    assert api.calls[0] == ("ep/run", {"input": {"prompt": "p", "seed": 3}})
    assert [c[0] for c in api.calls[1:]] == ["ep/status/job1"] * 3


def test_failed_job_and_worker_error_exit() -> None:
    for statuses, output, needle in ((["FAILED"], None, "FAILED"),
                                     (["COMPLETED"], {"error": "base variant only"}, "worker error")):
        try:
            runpod_cmd.run({"prompt": "p"}, "k", "ep", request=FakeApi(statuses, output), sleep=lambda s: None)
        except SystemExit as e:
            assert needle in str(e)
        else:
            raise AssertionError("must fail")


def test_timeout_cancels() -> None:
    api = FakeApi(["IN_QUEUE"] * 5)
    try:
        runpod_cmd.run({"prompt": "p"}, "k", "ep", timeout_s=-1, request=api, sleep=lambda s: None)
    except SystemExit as e:
        assert "cancelled" in str(e)
    else:
        raise AssertionError("must time out")
    assert api.calls[-1][0] == "ep/cancel/job1"


def test_payload_limit() -> None:
    try:
        runpod_cmd.run({"prompt": "x" * (11 * 1024 * 1024)}, "k", "ep", request=FakeApi([]), sleep=lambda s: None)
    except SystemExit as e:
        assert "too large" in str(e)
    else:
        raise AssertionError("must refuse")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("ok", t.__name__)
    print(f"{len(tests)} tests passed")
