"""Run a generation job locally or on a remote host.

A job is a serialisable ``JobSpec`` (JSON, reference images as base64 PNG). A ``Runner`` takes
``submit(spec) -> handle`` and ``fetch(handle) -> [(png_bytes, meta), ...]``.

* ``LocalRunner(backend)`` executes through the backend's ``generate`` in this process.
* ``RemoteRunner(name)`` pipes the spec JSON to the command in ``ARTGEN_REMOTE_<NAME>_CMD`` (shell
  words, e.g. ``ssh gpu 'artgen-worker'``) and reads a JSON list of ``{png_base64, meta}`` from its
  stdout. No host is bundled; without the variable it fails with a clear error.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import re
import shlex
import subprocess
import tempfile
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol

KINDS = ("generate", "edit", "sheet")


def ref_from_bytes(png_bytes: bytes) -> dict:
    return {"sha256": hashlib.sha256(png_bytes).hexdigest(),
            "png_bytes": base64.b64encode(png_bytes).decode("ascii")}


def ref_from_path(path) -> dict:
    return ref_from_bytes(Path(path).read_bytes())


@dataclass
class JobSpec:
    kind: str = "generate"                       # generate | edit | sheet
    backend: str = ""
    variant: str | None = None                   # e.g. "turbo" | "base"
    prompt: str = ""
    negative: str | None = None
    refs: list[dict] = field(default_factory=list)   # [{sha256, png_bytes (base64 in JSON)}]
    seed: int = 0
    n: int = 1
    width: int = 512
    height: int = 512
    steps: int | None = None
    sigmas: list[float] | None = None
    true_cfg: float | None = None
    opts: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"kind must be one of {KINDS}, got {self.kind!r}")

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, text: str) -> "JobSpec":
        data = json.loads(text)
        known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**known)

    def ref_bytes(self) -> list[bytes]:
        """Decoded reference PNGs, each checked against its sha256."""
        out = []
        for r in self.refs:
            b = base64.b64decode(r["png_bytes"])
            if r.get("sha256") and hashlib.sha256(b).hexdigest() != r["sha256"]:
                raise ValueError(f"reference sha256 mismatch ({r['sha256'][:12]}...)")
            out.append(b)
        return out


class Runner(Protocol):
    def submit(self, spec: JobSpec) -> Any: ...
    def fetch(self, handle: Any) -> list[tuple[bytes, dict]]: ...


def _png_bytes(im) -> bytes:
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


class LocalRunner:
    """Runs the job synchronously in ``submit``; ``fetch`` returns the stored result."""

    def __init__(self, backend) -> None:
        self.backend = backend
        self._loaded = False
        self._results: dict[str, list[tuple[bytes, dict]]] = {}

    def submit(self, spec: JobSpec) -> str:
        if spec.kind != "generate":
            raise NotImplementedError(f"LocalRunner only runs kind 'generate' so far, got {spec.kind!r}")
        b = self.backend
        opts = dict(spec.opts)
        if not self._loaded:
            b.load(**{k: v for k, v in opts.items() if k in b.load_keys})
            self._loaded = True
        gen = {k: v for k, v in opts.items() if k not in b.load_keys}
        for k, v in (("steps", spec.steps), ("sigmas", spec.sigmas), ("true_cfg", spec.true_cfg), ("variant", spec.variant)):
            if v is not None:
                gen[k] = v
        with tempfile.TemporaryDirectory(prefix="artgen-refs-") as td:
            paths = []
            for i, data in enumerate(spec.ref_bytes()):
                p = Path(td) / f"ref{i}.png"
                p.write_bytes(data)
                paths.append(str(p))
            if paths:
                gen["ref"] = paths
            imgs = b.generate(spec.prompt, negative=spec.negative, width=spec.width, height=spec.height,
                              seed=spec.seed, n=spec.n, **gen)
        stats = b.stats()
        handle = uuid.uuid4().hex
        self._results[handle] = [(_png_bytes(im), {"seed": spec.seed + i, "size": list(im.size), "stats": stats})
                                 for i, im in enumerate(imgs)]
        return handle

    def fetch(self, handle: str) -> list[tuple[bytes, dict]]:
        return self._results.pop(handle)


class RemoteRunner:
    """Pipes the JobSpec JSON to ``ARTGEN_REMOTE_<NAME>_CMD`` and parses ``[{png_base64, meta}]``."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.env_var = f"ARTGEN_REMOTE_{re.sub(r'[^A-Za-z0-9]', '_', name).upper()}_CMD"
        self._results: dict[str, list[tuple[bytes, dict]]] = {}

    def submit(self, spec: JobSpec) -> str:
        cmd = os.environ.get(self.env_var)
        if not cmd:
            raise RuntimeError(f"no remote host configured for runner 'remote:{self.name}' "
                               f"(set {self.env_var} to a command that reads a JobSpec JSON on stdin and "
                               f"prints a JSON list of {{png_base64, meta}})")
        proc = subprocess.run(shlex.split(cmd), input=spec.to_json(), capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(f"remote runner {self.name!r} failed (exit {proc.returncode}): "
                               f"{proc.stderr.strip()[-500:]}")
        try:
            items = json.loads(proc.stdout)
            res = [(base64.b64decode(it["png_base64"]), it.get("meta", {})) for it in items]
        except (ValueError, KeyError, TypeError) as e:
            raise RuntimeError(f"remote runner {self.name!r} returned bad output: {e}") from None
        handle = uuid.uuid4().hex
        self._results[handle] = res
        return handle

    def fetch(self, handle: str) -> list[tuple[bytes, dict]]:
        return self._results.pop(handle)


def get_runner(spec: str, backend=None) -> Runner:
    """``"local"`` or ``"remote:<name>"``."""
    if spec == "local":
        if backend is None:
            raise ValueError("the local runner needs a backend")
        return LocalRunner(backend)
    if spec.startswith("remote:") and spec[7:]:
        return RemoteRunner(spec[7:])
    raise ValueError(f"unknown runner {spec!r}; use 'local' or 'remote:<name>'")


class RunnerBackend:
    """Backend-shaped proxy that sends every ``generate`` call through a Runner (used for ``remote:<name>``).

    artgen's generate/edit/sheet code only needs ``info``, ``apply_template``, ``generate`` and ``stats``,
    so it runs unchanged on top of this. Reference images are read from their paths and sent as base64.
    The local path calls the backend directly (same results as ``LocalRunner``, without a temp-file round
    trip), so reference paths stay in the sidecars.
    """

    def __init__(self, backend_name: str, runner_spec: str, kind: str = "generate", variant: str | None = None):
        from backends import get_backend
        self._real = get_backend(backend_name)          # not loaded: only its template and info
        self.info = self._real.info
        self.load_keys = frozenset()
        self.passthrough_opts = self._real.passthrough_opts
        self.template_flags = getattr(self._real, "template_flags", frozenset())
        self.runner_spec, self.kind, self.variant = runner_spec, kind, variant
        self.runner = get_runner(runner_spec)
        self._stats: dict[str, Any] = {}

    def apply_template(self, subject: str, **fields) -> str:
        return self._real.apply_template(subject, **fields)

    def generate(self, prompt, negative=None, width=512, height=512, seed=0, n=1, ref=None,
                 sigmas=None, steps=None, true_cfg=None, **opts):
        from PIL import Image
        opts.pop("variant", None)
        spec = JobSpec(kind=self.kind, backend=self.info.name, variant=self.variant or opts.pop("variant", None),
                       prompt=prompt, negative=negative, refs=[ref_from_path(p) for p in ref or []],
                       seed=seed, n=n, width=width, height=height, steps=steps, sigmas=sigmas,
                       true_cfg=true_cfg, opts=opts)
        res = self.runner.fetch(self.runner.submit(spec))
        # Per-image meta from the remote side (GPU, timings, job id ...) goes into the sidecar stats as is.
        self._stats = dict(res[0][1].get("stats", {}) if res else {}, runner=self.runner_spec,
                           remote=[{k: v for k, v in m.items() if k != "stats"} for _, m in res])
        return [Image.open(io.BytesIO(b)).convert("RGBA") for b, _ in res]

    def stats(self) -> dict:
        return dict(self._stats)
