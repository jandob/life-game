"""On-disk cache of text/image-conditioned prompt encodings (the slow step of Qwen-Image).

Location: ``~/.cache/artgen/enc/<namespace>/`` (override the root with ``ARTGEN_ENC_CACHE``).
The key hashes everything that changes an encoding: the prompt, the *resized* condition
image pixels (what the encoder really sees), ``ref_res``, the encoder id (repo + revision)
and ``PREPROC_VERSION`` (bump it when the preprocessing code changes). Values are tuples of
tensors or None, saved with ``torch.save`` and read back with ``weights_only=True``.
"""
from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path

PREPROC_VERSION = "1"


def cache_dir(namespace: str = "qwen21") -> Path:
    root = os.environ.get("ARTGEN_ENC_CACHE")
    base = Path(root) if root else Path.home() / ".cache" / "artgen" / "enc"
    return base / namespace


def key(prompt: str, images, ref_res: int, encoder_id: str) -> str:
    """sha256 hex over prompt, resized condition images (mode, size, bytes; in order), ref_res, encoder id."""
    h = hashlib.sha256()

    def part(b: bytes) -> None:
        h.update(len(b).to_bytes(8, "big"))   # length prefix: no ambiguity between fields
        h.update(b)

    part(PREPROC_VERSION.encode())
    part(prompt.encode("utf-8"))
    part(str(int(ref_res)).encode())
    part(encoder_id.encode("utf-8"))
    for im in images or []:
        part(f"{im.mode}|{im.size[0]}x{im.size[1]}".encode())
        part(im.tobytes())
    return h.hexdigest()


def _path(k: str, namespace: str) -> Path:
    return cache_dir(namespace) / f"{k}.pt"


def get(k: str, namespace: str = "qwen21"):
    """Cached tuple (tensors / None) or None on a miss. A corrupt entry counts as a miss."""
    import torch
    p = _path(k, namespace)
    if not p.exists():
        return None
    try:
        data = torch.load(p, map_location="cpu", weights_only=True)
    except Exception:
        return None
    os.utime(p)   # mark as recently used for prune(older_than_days=...)
    return tuple(data)


def put(k: str, tensors, namespace: str = "qwen21") -> Path:
    """Store a tuple of tensors / None atomically (temp file + rename)."""
    import torch
    p = _path(k, namespace)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    torch.save(list(tensors), tmp)
    tmp.replace(p)
    return p


def _entries(namespace: str):
    d = cache_dir(namespace)
    return [p for p in d.glob("*.pt")] if d.is_dir() else []


def stats(namespace: str = "qwen21") -> dict:
    es = _entries(namespace)
    return {"count": len(es), "bytes": sum(p.stat().st_size for p in es), "dir": str(cache_dir(namespace))}


def prune(older_than_days: float | None = None, max_bytes: int | None = None,
          namespace: str = "qwen21") -> int:
    """Delete entries not used for ``older_than_days``, then oldest-first until the total is
    <= ``max_bytes``. Returns the number removed."""
    removed = 0
    es = sorted(((p.stat().st_mtime, p.stat().st_size, p) for p in _entries(namespace)), key=lambda t: t[0])
    keep = []
    cutoff = time.time() - older_than_days * 86400 if older_than_days is not None else None
    for mt, size, p in es:
        if cutoff is not None and mt < cutoff:
            p.unlink(missing_ok=True)
            removed += 1
        else:
            keep.append((mt, size, p))
    if max_bytes is not None:
        total = sum(s for _, s, _ in keep)
        for _, size, p in keep:   # oldest first
            if total <= max_bytes:
                break
            p.unlink(missing_ok=True)
            total -= size
            removed += 1
    return removed
