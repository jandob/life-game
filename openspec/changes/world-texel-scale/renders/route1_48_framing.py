# 1x framing of the rebuilt 48 px route1_flat at 540 art px visible (960x540, t = 1), with the
# realistic 96x192 stills placed by their feet (cell feet row 158). Same render() as mock_framing.py,
# but the world is the 48 px map at 1 art px per world px (no 3x upscale).
# Usage: python3 route1_48_framing.py STILLS_DIR  (STILLS_DIR holds post2/player_front_s12_px.png, post2/sam_front_s13_px.png)
import sys, numpy as np
from PIL import Image, ImageDraw
R = '/Users/janosch/repos/life-game/'
OUT = R + 'openspec/changes/world-texel-scale/renders/'
S = sys.argv[1]
world = np.array(Image.open(OUT + 'route1_48_1x.png').convert('RGBA'))
P = np.array(Image.open(S + '/post2/player_front_s12_px.png').convert('RGBA'))
Sm = np.array(Image.open(S + '/post2/sam_front_s13_px.png').convert('RGBA'))

def render(vp, cam, sprites, W=960, H=540):
    r = H / vp; ys, xs = np.mgrid[0:H, 0:W]
    wx = cam[0] + (xs + 0.5 - W / 2) / r; wy = cam[1] + (ys + 0.5 - H / 2) / r
    out = np.zeros((H, W, 4), np.uint8); out[..., 3] = 255
    ix = np.floor(wx).astype(int); iy = np.floor(wy).astype(int)
    ok = (ix >= 0) & (iy >= 0) & (ix < world.shape[1]) & (iy < world.shape[0]); out[ok] = world[iy[ok], ix[ok]]
    for spr, fx, fy in sorted(sprites, key=lambda s: s[2]):
        ch, cw = spr.shape[:2]; left = fx - cw // 2; top = fy - 158
        tx = np.floor(wx - left).astype(int); ty = np.floor(wy - top).astype(int)
        ok = (tx >= 0) & (ty >= 0) & (tx < cw) & (ty < ch); px = np.zeros_like(out); px[ok] = spr[ty[ok], tx[ok]]
        a = px[..., 3:4] / 255; out[..., :3] = (out[..., :3] * (1 - a) + px[..., :3] * a).astype(np.uint8)
    return Image.fromarray(out)

# feet positions = Paths end points (map px)
frames = {
    'landing': ((336, 860), [(P, 256, 912), (Sm, 336, 912)], 'landing: player at PlayerKnock, Samantha at the end of SamanthaTo3B'),
    'window': ((300, 330), [(P, 264, 300), (Sm, 176, 288)], 'flat 3B: both at the window (SamanthaToWindow / PlayerToWindow)'),
    'kitchen': ((420, 400), [(P, 576, 552), (Sm, 504, 336)], 'kitchen: SamanthaToKitchen / PlayerToKitchen end points'),
}
for name, (cam, spr, label) in frames.items():
    im = render(540, cam, spr).convert('RGB')
    ImageDraw.Draw(im).text((6, 4), label + ' - 1x, 540 art px visible', fill=(255, 255, 255))
    im.save(OUT + f'route1_48_frame540_{name}.png')
print('ok')
