## REMOVED Requirements

### Requirement: Cast recipe
**Reason**: `cast` repainted characters with SDXL character LoRAs. The SDXL stack is deleted by `artgen-qwen-image` (user decision 2026-10-15).
**Migration**: `artgen.py edit` with character reference images and `--mask` paste-back, one region per call.
