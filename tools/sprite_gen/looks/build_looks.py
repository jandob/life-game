"""Build look strips (idle.png, walk.png, look.ron, walk.gif) from post-processed 128x256 key cells.

openspec/changes/character-looks-and-sprite-format. Input: the *_px.png cells made by
`artgen.py post ... --cell 128x256 --feet-row 245` with ONE fixed N per character.
Idle is 4 rows (down, left, right, up) x 1 frame; left is the mirrored right. Walk is 1 row facing right.

Run: tools/artgen/.venv/bin/python tools/sprite_gen/looks/build_looks.py
"""
from pathlib import Path
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[3]
PX = ROOT / "tools/artgen/out/side_px"
CELL = (128, 256)

LOOKS = {
    # look id: (character, px dir, front, side idle, back idle, walk frames in cycle order)
    "player_main": ("player", "player5", "player5_front_nobag_s41", "player5nb_side_idle_s41", "player5nb_back_idle_s41",
                    ["player5nb_side_contact_s41", "player5nb_side_passing_s41", "player5_side_contactB_s44", "player5_side_passingB_s45"]),
    "sam_casual": ("samantha", "sam1", "sam_look1_front_s31", "sam1_side_idle_s41", "sam1_back_idle_s41",
                   ["sam1_side_contact_s41", "sam1_side_passing_v2_s43", "sam1_side_contactB_s44", "sam1_side_passingB_s45"]),
    "sam_ponytail": ("samantha", "sam2", "sam_look2_front_s31", "sam2_side_idle_s41", "sam2_back_idle_s41",
                     ["sam2_side_contact_s41", "sam2_side_passing_v2_s43", "sam2_side_contactB_s44", "sam2_side_passingB_s45"]),
}

MANIFEST = """Look(
    id: "{id}",
    character: "{character}",
    cell: (128, 256),
    clips: {{
        Idle: (file: "idle.png", frames: 1, rows: [Down, Left, Right, Up], mirror_left: true),
        Walk: (file: "walk.png", frames: {frames}, rows: [Right], mirror_left: true, frame_ms: 140),
    }},
)
"""


def cell(d: str, name: str) -> Image.Image:
    im = Image.open(PX / d / f"{name}_px.png").convert("RGBA")
    assert im.size == CELL, (name, im.size)
    return im


def main() -> None:
    for look, (character, d, front, side, back, walk) in LOOKS.items():
        out = ROOT / "art/characters" / character / "looks" / look
        out.mkdir(parents=True, exist_ok=True)
        right = cell(d, side)
        idle = Image.new("RGBA", (CELL[0], CELL[1] * 4))
        for row, im in enumerate([cell(d, front), ImageOps.mirror(right), right, cell(d, back)]):
            idle.paste(im, (0, row * CELL[1]))
        idle.save(out / "idle.png")
        frames = [cell(d, n) for n in walk]
        strip = Image.new("RGBA", (CELL[0] * len(frames), CELL[1]))
        for i, im in enumerate(frames):
            strip.paste(im, (i * CELL[0], 0))
        strip.save(out / "walk.png")
        gif = [Image.alpha_composite(Image.new("RGBA", CELL, (200, 200, 200, 255)), f).convert("P") for f in frames]
        gif[0].save(out / "walk.gif", save_all=True, append_images=gif[1:], duration=140, loop=0)
        (out / "look.ron").write_text(MANIFEST.format(id=look, character=character, frames=len(frames)))
        print(look, out)


if __name__ == "__main__":
    main()
