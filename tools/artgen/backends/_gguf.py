"""Workaround for a diffusers GGUF bug: parameters of non-Linear modules stay raw bytes.

``from_single_file(..., quantization_config=GGUFQuantizationConfig)`` wraps every GGUF tensor in a
``GGUFParameter``, but only ``GGUFLinear`` dequantises on use. Params owned by other modules
(``txt_in.text_norm``, every attention ``norm_q`` / ``norm_k``: 65 of them in the Qwen-Image 2.1
Turbo Q8_0 file) stay as the raw uint8 payload, so the first forward fails with a shape error.
``fix_non_linear`` replaces each of them with a plain dequantised parameter.
"""
from __future__ import annotations


def fix_non_linear(model, dtype=None) -> list[str]:
    """Dequantise every GGUFParameter not owned by a GGUFLinear. Idempotent.

    Returns the dotted names that were fixed by this call (a second call returns ``[]``).
    ``dtype`` defaults to bfloat16.
    """
    import torch
    from diffusers.quantizers.gguf.utils import GGUFLinear, GGUFParameter, dequantize_gguf_tensor
    dtype = dtype or torch.bfloat16
    fixed: list[str] = []
    for mname, mod in model.named_modules():
        if isinstance(mod, GGUFLinear):
            continue
        for pname, prm in list(mod.named_parameters(recurse=False)):
            if isinstance(prm, GGUFParameter):
                w = dequantize_gguf_tensor(prm).to(dtype)
                setattr(mod, pname, torch.nn.Parameter(torch.Tensor(w.as_subclass(torch.Tensor)),
                                                       requires_grad=False))
                fixed.append(f"{mname}.{pname}")
    return fixed
