# Pipeline stage by stage

Copy-paste commands for the artgen pipeline. Run from `tools/artgen` with `.venv/bin/python artgen.py ...`
(shortened to `artgen.py` below). Outputs go to the git-ignored `out/`. **One model process at a time** (24 GB Mac).
Setup, memory and timings: [README.md](README.md). Cell sizes, feet row and style words below are the active profile's
(`profiles/life-game.json`, env `ARTGEN_PROFILE`); the project conventions are in the `life-game-art` skill.

Who can do what (also printed by `artgen.py backends`):

| | `qwen_image21` | `flux2_klein_pixel_lora` | `z_image_turbo` |
|---|---|---|---|
| text to image | yes (1024², 55-95 s) | yes (512², 5-11 s) | yes (about 100 s) |
| `--ref` composition | yes | yes (untested for scenes) | no |
| **real alpha** (`--opt rgba=1`) | **only this one** | no, painted background removed in post | no, same |
| `edit`, `sheet` | **only this one** | no | no |
| `refine` (img2img strength), `inpaint` (scenekit map tiles) | no | **only this one** | no |

A command a backend lacks fails with a message naming the backends that support it.

## 1. Initial generation

```sh
# qwen_image21: best quality, 1024x1024 by default. --prompt is the SUBJECT; it is wrapped in
# "Pixel art sprite of <subject>, 16-bit video game asset, crisp hard-edged pixels, flat colours, plain flat white background."
artgen.py generate --backend qwen_image21 --seed 11 --out out/man --name man_front --json \
    --prompt "an adult man in his late twenties, short brown hair, grey hoodie, dark blue jeans, white sneakers, standing, front view facing the viewer, full body, top-down RPG character"
# faster / lighter options (no refs, no alpha, no edit):
artgen.py generate --backend flux2_klein_pixel_lora --seed 11 --n 4 --out out/man --name man_front --prompt "<subject>"
artgen.py generate --backend z_image_turbo --width 768 --height 1152 --seed 11 --out out/z \
    --opt style="detailed hi-res pixel art, limited palette. " --prompt "a young man in a grey hoodie, front view, full body"
```

The first qwen run encodes the prompt in a separate process (about 20 s for text only); more seeds (`--n`, `--seed`) of the
same prompt are free of that cost.

## 2. Props with real transparency

```sh
artgen.py generate --backend qwen_image21 --opt rgba=1 --seed 11 --out out/sofa --name sofa \
    --prompt "a modern grey fabric three-seat sofa, top-down 3/4 view from above, furniture prop for an apartment"
artgen.py post out/sofa/sofa_s11.png --grid auto --colours 16 --outline inner --out out/sofa_px
```

The raw alpha is 1-9 in the background (not exactly 0); `post` binarises it (about 68 % fully transparent for the sofa).
With flux / z_image the background is painted and `post` removes it by flood fill (`--bg auto`).

## 3. Characters and turnarounds

Make a front view (stage 1), then derive the other views with `edit` so identity and outfit carry over (Picture 1 = source):

```sh
artgen.py edit --image out/man/man_front_s11.png --seed 11 --out out/man --name man_back \
    --prompt "Picture 1 shows a young adult man from the front. Draw the same man from behind: back view seen from directly behind, the face is not visible, full body, same pixel art style, same clothes, plain flat white background."
artgen.py edit --image out/man/man_front_s11.png --seed 11 --out out/man --name man_side \
    --prompt "Picture 1 shows a young adult man from the front. Draw the same man in strict side view facing right, full body, same pixel art style, same clothes, plain flat white background."
```

`edit` writes at the source size (rounded to 32 px for generation, resized back). `--ref-res` (default 1024) applies to all
inputs. Other edits (outfit change, expression) work the same way: describe what stays and what changes.

Post-process a character into the game cell (96x192, feet on row 157). Fix `N` (raw px per art pixel) ONCE per character
from the front view and reuse it for every pose, so all frames share one pixel size:

```sh
artgen.py post out/man/man_front_s11.png --grid fit --cell 96x192 --feet-row 157 --shadow --outline inner --colours 24 --keep-largest --out out/man_px   # first look: read the grid scale in the sidecar
artgen.py post out/man/*_s11.png --grid N --cell 96x192 --feet-row 157 --shadow --outline inner --colours 24 --keep-largest --out out/man_px
```

## 4. Portraits

```sh
artgen.py generate --backend qwen_image21 --seed 11 --out out/portrait --name man \
    --prompt "dialogue portrait bust of an adult man in his thirties, short dark hair, light stubble, neutral expression, head and shoulders, facing the viewer, visual novel portrait" \
    --opt background="plain flat background"
# a portrait of an existing character:
artgen.py edit --image out/man/man_front_s11.png --seed 11 --out out/portrait --name man_bust \
    --prompt "Picture 1 shows a man standing. Draw a head and shoulders dialogue portrait of the same man, facing the viewer, neutral expression, same pixel art style, plain flat background."
artgen.py post out/portrait/man_s11.png --grid auto --colours 16 --outline inner --out out/portrait_px
```

## 5. Scene composition (room + characters)

`generate --ref` with several references; Picture 1, 2, 3 are the refs in command-line order. With refs the prompt is sent
verbatim (no sprite template), so write the whole prompt.

```sh
artgen.py generate --backend qwen_image21 --seed 11 --width 1024 --height 1024 --opt ref_res=512 --out out/scene --name scene \
    --ref out/room/room_s11.png out/man/man_front_s11.png out/woman/woman_front_s11.png \
    --prompt "Picture 1 is an empty apartment room, Picture 2 is a man, Picture 3 is a woman. Place the man and the woman from Pictures 2 and 3 sitting on the sofa cushions of the room in Picture 1, not on the rug or the coffee table. Keep the room unchanged: same layout, furniture and colours. Keep both characters' faces, hair and clothes. Scale them to the sofa so they look life-size. Same pixel art style."
```

Prompt pattern that worked: name every picture ("Picture 1 is ..."), give explicit placement ("on the sofa cushions, not on
the rug or coffee table"), state scale, and say "keep the room unchanged". A reference costs encode time (about 3 min for
3 refs at 512, once per prompt+refs; extra seeds are free).

## 6. Local fixes (hands, faces)

```sh
artgen.py mask --size 1024x1024 --ellipse 448,300,568,440 --out out/fix/mask.png       # white = take the edit
artgen.py edit --image out/scene/scene_s11.png --mark 508,338,42 --mask out/fix/mask.png --feather 8 \
    --seed 11 --out out/fix --name hand --prompt "Picture 1 has a red circle marking a hand. Redraw that hand correctly with five fingers, same style, same lighting. Remove the circle and change nothing else."
```

`--mark x,y,r` draws a red circle on the source so the model sees where to work; `--mask` pastes only the masked area back
(feathered), so pixels outside the mask equal the source. Check `drift_outside_reach` in the sidecar: it must be 0.0.
The unpasted edit is kept as `hand_s11_raw.png`. A bare `edit` without a mask drifts over the whole image (about 13/255).

## 7. Walk sheets

```sh
artgen.py sheet --ref out/man/man_front_s11.png out/man/man_side_s11.png --poses walk_side --frames 5 --cell 384x768 \
    --ref-res 768 --seed 11 --subject "a young adult man with short messy brown hair, an olive green hoodie, dark blue jeans and brown sneakers" \
    --slice --out out/walk --name walk
```

One generation draws all 5 frames in a row, guided by a skeleton strip (the last reference). `--slice` cuts the frames,
post-processes each with ONE fixed grid (`--grid N`, else fitted on frame 0) into 96x192 cells with feet on row 157, and
writes `walk_f{i}_px.png`, `walk_px_row.png` and `walk.gif`. Encode takes about 8.5 min at `--ref-res 768` (once). Pass
`--prompt-file` to control the whole prompt. Pose words per frame are generated from the walk phase; the strip enforces the
leg positions only roughly (no exact pose control).

## 8. Post-processing settings

| Kind | Command |
|---|---|
| characters (96x192) | `artgen.py post IN --grid N --cell 96x192 --feet-row 157 --shadow --outline inner --colours 24 --keep-largest --out OUT` |
| older 64x128 characters | `--grid fit --cell 64x128 --feet-row 105 --shadow --outline inner --colours 24 --keep-largest` |
| props, portraits | `--grid auto --colours 16 --outline inner` |
| tiles (16x16) | `--tile --cell 16x16 --colours 8` : still weak for every model (not seamless); expect hand touch-up |
| locked palette | `--palette palettes/player_ref.hex` |

Stages and parameters are described in README.md (Post-processing stages).

## 9. Limits

Exact pose control (the skeleton strip is a hint), seamless tiles, and bit-identical reruns across machines are not
available. Edits can drift the whole image: use `--mark` + `--mask` for local changes.
