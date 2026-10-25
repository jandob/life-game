#!/bin/sh
# Side-view room backgrounds (stage 3 of openspec/changes/side-view): each placeholder
# from tools/mapgen/side_placeholders.py is repainted by qwen_image21 `edit`, which keeps
# its layout, so the doors, stairs and furniture stay where the map's hotspots and floor
# line expect them. Then `post` snaps the result to the pixel grid at game size.
# Run from tools/artgen: sh ../../art/jobs/10_side_rooms.sh   (one model process at a time)
set -e
PY=.venv/bin/python
OUT=out/side_rooms
ROOMS=../../assets/library/rooms
STYLE="detailed pixel art in the style of the game The Captain and of Gemini Rue, side-on cross-section of a room seen from the front like a stage set, no perspective, flat side elevation, the floor is a strip along the bottom, warm evening lamp light, muted colours, crisp hard-edged pixels"
KEEP="Keep the exact layout of Picture 1: every wall, doorway, window, piece of furniture and the floor line stay at the same position and size. No people, no text."

edit() { # name, description
    $PY artgen.py edit --backend qwen_image21 --image "$ROOMS/$1/background.png" \
        --seed 11 --n 3 --ref-res 1296 --out "$OUT" --name "$1" \
        --prompt "Picture 1 is a rough layout of $2. Repaint it as $STYLE. $KEEP"
}

edit landing "the third floor landing of an old Berlin apartment building: patterned wallpaper above a green painted dado, a staircase with an iron railing going down on the left, two wooden apartment doors (3B and 3A), a cardboard recycling box on the right, worn linoleum floor"
edit flat3b "an empty, just-rented flat: bare white walls, one window, wooden floorboards, a clothes rack, a mattress bed, a chest of drawers and moving boxes, the open front door on the left"
edit flat3a "Samantha's cosy flat: kitchen corner with sink, fridge and cupboards on the left, a dining table with chairs in the middle, the front door, a tall bookshelf on the right, plants and fairy lights, wooden floorboards"
edit shop "a small late-night corner shop (Spaeti): the street door on the left, shelves of wine bottles, a chocolate display, the till counter with the shopkeeper's side of the counter empty, a bucket of flowers on the right, tiled floor, fluorescent light"

# Pixel grid, 32 colours, no outline (backgrounds), at the placeholder's size (1296x576).
for f in "$OUT"/*_s1[1-3].png; do
    $PY artgen.py post "$f" --grid auto --bg none --colours 32 --outline none --cleanup 1 --out "$OUT/px"
done
