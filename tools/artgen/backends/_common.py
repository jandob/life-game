"""Helpers shared by the diffusers backends that read models.json."""
from __future__ import annotations

import json
import os
from pathlib import Path

REGISTRY_FILE = Path(__file__).resolve().parent.parent / "models.json"


def load_registry() -> dict:
    return json.loads(Path(os.environ.get("ARTGEN_MODELS", REGISTRY_FILE)).read_text())


def hf_file(repo: str, filename: str) -> str:
    """Path of a file in the HF cache; downloads only if it is missing."""
    from huggingface_hub import hf_hub_download
    try:
        return hf_hub_download(repo, filename, local_files_only=True)
    except Exception:  # noqa: BLE001
        return hf_hub_download(repo, filename)


def hf_snapshot(repo: str, patterns: list[str]) -> str:
    from huggingface_hub import snapshot_download
    try:
        return snapshot_download(repo, allow_patterns=patterns, local_files_only=True)
    except Exception:  # noqa: BLE001
        return snapshot_download(repo, allow_patterns=patterns)


def resolve(entry: dict) -> str:
    """models.json entry -> local file path ('path' or ['hf'] = [repo, file])."""
    if "path" in entry:
        p = os.path.expanduser(entry["path"])
        if not os.path.isfile(p):
            raise FileNotFoundError(f"model file missing: {p}")
        return p
    return hf_file(*entry["hf"])


class MemTracker:
    """Peak MPS driver memory and process RSS, like the FLUX backend."""

    def __init__(self, torch, device: str, stats: dict):
        self.torch, self.device, self.stats = torch, device, stats

    def __call__(self, key: str = "peak_mps_gen_gb") -> None:
        if self.device == "mps":
            drv = self.torch.mps.driver_allocated_memory() / 2**30
            self.stats[key] = round(max(self.stats.get(key, 0.0), drv), 2)
        try:
            import resource
            self.stats["peak_rss_gb"] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**30, 2)
        except Exception:  # noqa: BLE001
            pass
