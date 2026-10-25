#!/usr/bin/env python
"""Model-free tests for the RunPod backend (backends/_runpod.py, backends/runpod_qwen_image21.py), no network.

    .venv/bin/python test_remote.py
"""
from __future__ import annotations

import base64
import io
import os
import sys
import tempfile
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from backends import _runpod, get_backend  # noqa: E402
import backends.runpod_qwen_image21 as rq  # noqa: E402


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


def _run(api, payload=None, **kw):
    return _runpod.run(payload or {"prompt": "p"}, "ep", key="k", request=api, sleep=lambda s: None, **kw)


def test_completed_job() -> None:
    api = FakeApi(["IN_QUEUE", "IN_PROGRESS", "COMPLETED"], {"images": [{"png_base64": "aGk=", "meta": {"seed": 3}}]})
    out, job = _run(api, {"prompt": "p", "seed": 3})
    assert out["images"][0]["meta"] == {"seed": 3}
    assert job == {"job": "job1", "delay_ms": 5, "execution_ms": 7}
    assert api.calls[0] == ("ep/run", {"input": {"prompt": "p", "seed": 3}})
    assert [c[0] for c in api.calls[1:]] == ["ep/status/job1"] * 3


def test_failures() -> None:
    for statuses, output, needle in ((["FAILED"], None, "FAILED"),
                                     (["COMPLETED"], {"error": "boom"}, "worker error")):
        try:
            _run(FakeApi(statuses, output))
        except RuntimeError as e:
            assert needle in str(e)
        else:
            raise AssertionError("must fail")
    api = FakeApi(["IN_QUEUE"] * 5)
    try:
        _run(api, timeout_s=-1)
    except RuntimeError as e:
        assert "cancelled" in str(e) and api.calls[-1][0] == "ep/cancel/job1"
    else:
        raise AssertionError("must time out")
    try:
        _run(FakeApi([]), {"prompt": "x" * (11 * 1024 * 1024)})
    except RuntimeError as e:
        assert "too large" in str(e)
    else:
        raise AssertionError("must refuse")


def _png_b64(color) -> str:
    buf = io.BytesIO()
    Image.new("RGBA", (8, 4), color).save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def test_backend_payload_and_stats() -> None:
    seen = {}

    def fake_run(payload, endpoint, timeout_s=0):
        seen.update(payload=payload, endpoint=endpoint)
        imgs = [{"png_base64": _png_b64((i, 2, 3, 255)), "meta": {"seed": payload["seed"] + i, "gpu": "G", "image_s": 1.5}}
                for i in range(payload["n"])]
        return {"images": imgs}, {"job": "j", "delay_ms": 1, "execution_ms": 2}

    old_run, old_env = rq._runpod.run, dict(os.environ)
    rq._runpod.run = fake_run
    os.environ.update(RUNPOD_API_KEY="k", ARTGEN_RUNPOD_ENDPOINT="ep1")
    try:
        b = get_backend("runpod_qwen_image21")
        b.load()
        assert b.apply_template("a man") .startswith("Pixel art sprite of a man")
        assert b.apply_template("Picture 1 ...", ref=["x"]) == "Picture 1 ..."
        with tempfile.TemporaryDirectory() as td:
            ref = Path(td) / "r.png"
            Image.new("RGB", (4, 4), "red").save(ref)
            imgs = b.generate("p", width=64, height=32, seed=5, n=2, ref=[str(ref)], ref_res=512)
        p = seen["payload"]
        assert seen["endpoint"] == "ep1" and p["steps"] == 40 and p["true_cfg"] == 4.0 and p["negative"]
        assert p["opts"] == {"ref_res": 512} and len(p["refs"]) == 1 and len(p["refs"][0]["sha256"]) == 64
        assert [im.getpixel((0, 0))[0] for im in imgs] == [0, 1]
        st = b.stats()
        assert st["runpod"]["job"] == "j" and [m["seed"] for m in st["remote"]] == [5, 6] and st["refs"] == 1
        assert st["model"] == "Qwen/Qwen-Image-2.1" and st["last_image_s"] == [1.5, 1.5]
        os.environ.pop("ARTGEN_RUNPOD_ENDPOINT")
        try:
            get_backend("runpod_qwen_image21").load()
        except SystemExit as e:
            assert "ARTGEN_RUNPOD_ENDPOINT" in str(e)
        else:
            raise AssertionError("missing endpoint must fail")
    finally:
        rq._runpod.run = old_run
        os.environ.clear()
        os.environ.update(old_env)


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("ok", t.__name__)
    print(f"{len(tests)} tests passed")
