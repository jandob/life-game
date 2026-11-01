# Route 1 notebook night: scene frames and image prompts

Source: `assets/dialogue/route1_notebook.yarn`, node `Route1NotebookAsk`, after `<<fade_out>>`.
Pipeline: frame 1 with artgen `generate --backend runpod_qwen_image21` (RunPod, about 65 s and 1.5-2 cents per image) (1024x576 wide), refs = bedroom background + the two character keys,
later frames that only change frame 1 slightly use artgen `edit` on the frame 1 pick (see each frame), then `post` to the project pixel grid. Same look as `contact_intimate.png`: side-view cutaway bedroom, night window, dim lamp.

## Frame 1: pillow

Script: before "Pillow under your hips. There."

**Command: `artgen.py generate`** (first frame of the scene, from the three references). Pick: `frame1_pillow_v3_s12.png`.

Prompt (verbatim, as sent):

> Picture 1 is the bedroom background, Picture 2 is the man, Picture 3 is the woman. Keep the room from Picture 1, but zoomed onto the scene on the bed. Keep character desing and clothing from Pictures 2 and 3. Side view of a bedroom at night. The man is on all fours on the bed, knees on the mattress, his chest and shoulders resting low on the mattress, his back arched and his hips raised high with one pillow under them, face turned to the side toward the viewer, shoulders tense. He is not sitting upright. The woman kneels on the floor beside the bed, left of him, one hand resting on the middle of his back. A small bottle on the floor by her knee. Warm bedside lamp, dark window. anime style pixel art, thick dark outlines, flat cel shading with two tones, 16-bit video game scene, side view room cutaway, dim warm lamp light, dark night window, intimate but not explicit, no nudity shown

References (Picture 1, 2, 3):
- `assets/library/rooms/flat3b/background.png`
- `art/characters/player/keys/player_side_idle_s11.png`
- `art/characters/samantha/keys/sam_side_idle_s11.png`

Negative: text, watermark, extra limbs


## Frame 2: "I brought something"

Script: before "I brought something. It's cold for a second."

**Command: `artgen.py edit`, not `generate`.** Only small changes to frame 1, so the frame 1 pick is the source image and the room, camera and characters stay as they are.

- backend `runpod_qwen_image21`, `--image tools/artgen/out/notebook_frames/frame1_pillow_v3_s12.png` (the frame 1 pick), output keeps the source size 1024x576
- `--ref-res 512`, `--seed 11 --n 4`
- `edit` has no `--negative` option, so there is no negative for this frame; the instruction "keep everything else unchanged" is part of the prompt.

Prompt (verbatim, as sent):

> Picture 1 is the scene to edit. Picture 2 is the man, Picture 3 is the woman. Keep everything in Picture 1 exactly as it is: the room, the camera, the lamp light, both characters' designs and clothing, the man staying on all fours on the bed, and the woman staying on her knees on the floor beside the bed. Do not add or remove any person. Change only this: the man on the bed has his pants pulled down to his thighs and his bare ass is exposed. The woman holds the small bottle in one hand and rests her other hand on his ass. He looks back over his shoulder at her, surprised. Warm lamp, dark window.

References (Picture 2, 3; Picture 1 is the `--image`):
- `art/characters/player/keys/player_side_idle_s11.png`
- `art/characters/samantha/keys/sam_side_idle_s11.png`

Pick: `frame2_brought_edit2_s14.png` (edit of `frame1_pillow_v3_s12.png`, seed 14).

## Frame 3: from behind, finger

Script: before "Breathe out."

**Command: `artgen.py generate`.** New camera angle, so no scene or Samantha reference: the room is mostly dark and the mattress and lamp come from the text.

- backend `runpod_qwen_image21`, 1024x576, `--opt ref_res=512`, `--seed 11 --n 4`

Prompt (verbatim, as sent):

> Picture 1 is the man seen from behind. Close-up from directly behind him, the camera at hip height looking at his back. He is on all fours on a single mattress with his hips raised, wearing the green hoodie and jeans from Picture 1, the jeans pulled down to his thighs, his bare ass in the center of the frame. The room is almost black: only the mattress and the warm glow of a bedside lamp are lit. The bottom edge of the frame is her chest seen from her own eyes, with the same camera angle and chest shape as Picture 2, but she wears her teal track jacket. Her right forearm in a teal track jacket sleeve with a white stripe reaches in, her hand on his ass with one finger on his asshole. His ballsack visible. Her face and the rest of her are not visible. anime style pixel art, thick dark outlines, flat cel shading with two tones, 16-bit video game scene

References (Picture 1, 2):
- `art/characters/player/keys/player_back_idle_s11.png`
- `tools/artgen/out/notebook_frames/ref_chest_crop.png` (camera angle and chest shape only)

Negative: text, watermark, extra limbs, a second person, the woman's face, nipples

Pick: `tools/artgen/out/notebook_frames/frame3_finger_v12_s11.png` (seed 11, with the prompt and negative above). Reference for frame 4.

## Frame 4: from behind, knuckle deep

Script: before "Still yes?"

**Command: `artgen.py edit`, not `generate`.** Only a small change to the frame 3 pick.

- backend `runpod_qwen_image21`, `--image tools/artgen/out/notebook_frames/frame3_finger_v12_s11.png` (the frame 3 pick), `--ref-res 512`, `--seed 11 --n 4`
- no references and no negative.

Prompt (verbatim, as sent):

> Picture 1 shows the scene to keep exactly. Only change: Her finger enters him.

Pick: `tools/artgen/out/notebook_frames/frame4_edit3_s11.png` (seed 11, prompt above). Reference for frame 5.

## Frame 5: from behind, fully

Script: before "Oh. There it is."

**Command: `artgen.py edit`.** Small change to the frame 4 pick.

- backend `runpod_qwen_image21`, `--image tools/artgen/out/notebook_frames/frame4_edit3_s11.png` (the frame 4 pick), `--ref-res 512`, `--seed 11 --n 4`
- no references and no negative.

Prompt (verbatim, as sent):

> Picture 1 shows the scene to keep. Changes: The mans pants are further down. Her right hand is still in his ass. Her left hand is closed around his penis which is hanging down.

### Frame 5, second pass: put the finger back

`artgen.py edit` on `tools/artgen/out/notebook_frames/frame5_edit2_s11.png` (the take with her left hand around his penis), `--ref-res 512`, `--seed 11 --n 4`, no references, no negative.

Prompt (verbatim, as sent):

> Picture 1 shows the scene to keep. Only change: Her right hand is in his ass, one finger is inside him, her hand is closed around nothing else. Her left hand stays closed around his penis.

### Frame 5, third pass: combine two takes

`artgen.py edit` with `--image tools/artgen/out/notebook_frames/frame4_edit3_s11.png` (Picture 1, the frame 4 pick, her right hand's finger inside him) and `--ref tools/artgen/out/notebook_frames/frame5_edit2_s11.png` (Picture 2, her right hand around his penis), `--ref-res 512`, `--seed 11 --n 4`, no negative.

Prompt (verbatim, as sent):

> Picture 1 shows the scene to keep, with her right hand in his ass and one finger inside him. Picture 2 shows her right hand closed around his penis. Combine both: keep Picture 1 exactly as it is and add her left hand closed around his penis as in Picture 2. Both of her hands are visible at the same time.

Pick: `tools/artgen/out/notebook_frames/frame5_edit5_s12.png` (seed 12 of the third pass). 

## Frame 6: "I'm close"

Script: before "I'm close."

**Command: `artgen.py generate`.** The camera and pose change a lot from the frame 5 pick, so the frame 2 pick is only a reference.

- backend `runpod_qwen_image21`, 1024x576, `--opt ref_res=512`, `--seed 11 --n 4`
- no negative.

Prompt (verbatim, as sent):

> Keep the characters and room from Picture 1. The man from Picture 1 is still on all fours on the bed. His cock hangs down under his belly, and one of her hands is closed around it, jerking him off. Her other hand has one finger in his ass.

References (Picture 1):
- `tools/artgen/out/notebook_frames/frame2_brought_edit2_s14.png`

Run 2 (as sent above, `--name frame6_v2`, out `tools/artgen/out/notebook_frames/`, contact sheet `frame6_v2_contact.png`):
- s11: her hand around the cock, other hand at his ass, pants kept at his knees like frame 2. Cleanest. Pick.
- s12: bare legs, hand at his ass, cock held out at the knee, not under the belly.
- s13: bare legs, both hands in place, cock a bit far back.
- s14: she holds the lube bottle in one hand, background noisy.
Pick so far: frame6_v2_s11 (cock hangs under the hips, not quite under the belly).

Run 3 (same prompt and settings, `--seed 21 --n 4`, `--name frame6_v3`, contact sheet `frame6_v3_contact.png`):
- s21: cock angled back along her forearm, not hanging.
- s22: cock hangs under the hips, but her hand is at his ass and the other holds the lube bottle, nothing around the cock.
- s23: cock hangs under the hips with her hand at it, pants at his knees. Pick.
- s24: bare legs, cock hangs, her hands close to it, a little crowded.
Final pick (Janosch): frame6_v3_s23 (`tools/artgen/out/notebook_frames/frame6_v3_s23.png`).


## Frame 7: climax

Script: before "Breathe. I've got you."

PLACEHOLDER. Plain drawn image `tools/artgen/out/notebook_frames/frame7_placeholder.png` (not generated). Prompt to be written and run later.

## Frame 8: aftermath

Script: before "Get some water. I'm going to write."

PLACEHOLDER. Plain drawn image `tools/artgen/out/notebook_frames/frame8_placeholder.png` (not generated). The earlier side-view prompt was dropped as outdated; to be rewritten and run later.

## Notes

- Fix the typo `${samantha_name}: That was you, finding out.` in the yarn file (stray `$`).
- Take count: 4 seeds per frame for a first batch, pick one, then `post` with the same grid scale for all frames.
