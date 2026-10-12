#!/bin/sh
# usage: run_train.sh OUTPUT_DIR MAX_STEPS [extra args]   (run from tools/artgen)
OUT="$1"; STEPS="$2"; shift 2
export HF_HUB_OFFLINE=1 PYTORCH_ENABLE_MPS_FALLBACK=1
exec .venv/bin/python train/train_dreambooth_lora_sdxl.py \
  --pretrained_model_name_or_path "$HOME/.cache/artgen/wai_v17_diffusers" \
  --pretrained_vae_model_name_or_path madebyollin/sdxl-vae-fp16-fix \
  --dataset_name "$HOME/.cache/artgen/datasets/lgwoman1" --caption_column text \
  --instance_prompt lgwoman1 --resolution 512 --center_crop \
  --train_batch_size 1 --gradient_accumulation_steps 1 --gradient_checkpointing \
  --rank 16 --learning_rate 1e-4 --lr_scheduler constant --lr_warmup_steps 0 \
  --optimizer AdamW --mixed_precision no --cache_latents \
  --max_train_steps "$STEPS" --checkpointing_steps 500 --seed 42 \
  --report_to tensorboard --output_dir "$OUT" "$@"
