# Framing mock-ups for the texel-unit world: world px = 1 art pixel; the old 16 px map is upscaled 3x
# (placeholder tiles: their pixels are 3x the characters', unlike the final 48 px tiles).
import sys, numpy as np
from PIL import Image, ImageDraw
R='/Users/janosch/repos/life-game/'; S=sys.argv[1]
m3=np.array(Image.open(R+'tools/scenekit/out/renders/route1_flat.png').convert('RGBA'))
world=m3[1::3,1::3]; world=np.repeat(np.repeat(world,3,0),3,1)
P=np.array(Image.open(S+'/post2/player_front_s12_px.png').convert('RGBA'))
Sm=np.array(Image.open(S+'/post2/sam_front_s13_px.png').convert('RGBA'))
def render(vp,cam,sprites,W=1280,H=720):
    r=H/vp; ys,xs=np.mgrid[0:H,0:W]
    wx=cam[0]+(xs+0.5-W/2)/r; wy=cam[1]+(ys+0.5-H/2)/r
    out=np.zeros((H,W,4),np.uint8); out[...,3]=255
    ix=np.floor(wx).astype(int); iy=np.floor(wy).astype(int)
    ok=(ix>=0)&(iy>=0)&(ix<world.shape[1])&(iy<world.shape[0]); out[ok]=world[iy[ok],ix[ok]]
    for spr,fx,fy in sprites:
        ch,cw=spr.shape[:2]; left=fx-cw/2; top=fy-158
        tx=np.floor(wx-left).astype(int); ty=np.floor(wy-top).astype(int)
        ok=(tx>=0)&(ty>=0)&(tx<cw)&(ty<ch); px=np.zeros_like(out); px[ok]=spr[ty[ok],tx[ok]]
        a=px[...,3:4]/255; out[...,:3]=(out[...,:3]*(1-a)+px[...,:3]*a).astype(np.uint8)
    return Image.fromarray(out)
spr=[(P,150*3,292*3),(Sm,196*3,296*3)]
cam=(176*3,262*3)
panels=[(720,'view 720 texels: t=1 at 720p (head ~19 px)'),(540,'view 540: t=1.33 at 720p, 2 at 1080p'),(480,'view 480: t=1.5 at 720p, 3 at DPR 2'),(360,'view 360: t=2 at 720p, 3 at 1080p')]
out=Image.new('RGB',(1280*2+10,750*2),(40,40,40)); d=ImageDraw.Draw(out)
for i,(vp,t) in enumerate(panels):
    im=render(vp,cam,spr); im.save(f'{S}/frame_{vp}.png')
    x=(i%2)*1290; y=(i//2)*750; out.paste(im.convert('RGB'),(x,y+30)); d.text((x+8,y+8),t+' - 1280x720, DPR 1; tiles = old art upscaled 3x (placeholder)',fill=(255,255,255))
out.save(f'{S}/framing_options_720p.png')
# room-scale view of the flat interior at 480
render(480,(240*3,150*3),[(P,160*3,176*3),(Sm,200*3,180*3)]).save(f'{S}/frame_480_room.png')
