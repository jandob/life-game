# Mock-up renderer for the SUPERSEDED scale-1/3 draft (superseded_size_options_720p.png). Usage: python -I mock.py DIR,
# where DIR/post/ holds 96x192 cells from `artgen.py post ... --cell 96x192 --feet-row 157`.
import sys, numpy as np
from PIL import Image, ImageDraw
R='/Users/janosch/repos/life-game/'
S=sys.argv[1]
m3=np.array(Image.open(R+'tools/scenekit/out/renders/route1_flat.png').convert('RGBA'))
world=m3[1::3,1::3]  # 1x world px, Tiled coords (y down)
def cell(path,idx,cw,ch):
    a=np.array(Image.open(path).convert('RGBA')); c,r=idx%10,idx//10
    return a[r*ch:(r+1)*ch, c*cw:(c+1)*cw]
old_p=cell(R+'assets/library/characters/player/player.png',0,64,128)
old_s=cell(R+'assets/library/characters/samantha/samantha.png',0,64,128)
new_p=np.array(Image.open(S+'/post/player_front_s12_px.png').convert('RGBA'))
new_s=np.array(Image.open(S+'/post/sam_front_s13_px.png').convert('RGBA'))
def render(vp, sprites, cam=(176,262), W=1280, H=720, dpr=1):
    W*=dpr; H*=dpr; r=H/vp
    ys,xs=np.mgrid[0:H,0:W]
    wx=cam[0]+(xs+0.5-W/2)/r; wy=cam[1]+(ys+0.5-H/2)/r
    out=np.zeros((H,W,4),np.uint8); out[...,3]=255
    ix=np.floor(wx).astype(int); iy=np.floor(wy).astype(int)
    ok=(ix>=0)&(iy>=0)&(ix<world.shape[1])&(iy<world.shape[0])
    out[ok]=world[iy[ok],ix[ok]]
    for spr,s,feet_row,fx,fy in sprites:
        ch,cw=spr.shape[:2]
        left=fx-cw*s/2; top=fy-(feet_row+1)*s
        tx=np.floor((wx-left)/s).astype(int); ty=np.floor((wy-top)/s).astype(int)
        ok=(tx>=0)&(ty>=0)&(tx<cw)&(ty<ch)
        px=np.zeros_like(out); px[ok]=spr[ty[ok],tx[ok]]
        a=px[...,3:4].astype(float)/255
        out[...,:3]=(out[...,:3]*(1-a)+px[...,:3]*a).astype(np.uint8)
    return Image.fromarray(out)
fp=(150,292); fs=(196,296)
cfg={
 'cur_64x128_s0.5_vp250':(250,[(old_p,0.5,105,*fp),(old_s,0.5,105,*fs)]),
 'A_96x192_s0.333_vp240':(240,[(new_p,1/3,157,*fp),(new_s,1/3,157,*fs)]),
 'B_96x192_s0.333_vp180':(180,[(new_p,1/3,157,*fp),(new_s,1/3,157,*fs)]),
 'C_96x192_s0.5_vp250':(250,[(new_p,0.5,157,*fp),(new_s,0.5,157,*fs)]),
}
for k,(vp,spr) in cfg.items():
    im=render(vp,spr); im.save(f'{S}/mock_{k}.png')
    # 4x zoom crop of the faces at 720p
    r=720/vp; cx=640+(173-176)*r; cy=360+(250-262)*r
    im.crop((int(cx-120),int(cy-60),int(cx+120),int(cy+60))).resize((960,480),Image.NEAREST).save(f'{S}/face_{k}.png')
    im2=render(vp,spr,dpr=2); im2.save(f'{S}/mock2x_{k}.png')
