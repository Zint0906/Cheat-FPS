import asyncio, json, math, random, time, uuid
from pathlib import Path
from typing import Dict, List, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="Cheat FPS")
BASE = os.path.dirname(__file__) if False else str(Path(__file__).parent)  # harmless fallback

MAP_W, MAP_H = 32, 20
TICK = 1/30
ROUND_TIME = 120
MAX_HP = 100
WEAPON_DAMAGE = 34
WEAPON_RANGE = 26
FIRE_INTERVAL = 0.13

# 1 = wall, 0 = floor
WORLD = [
"11111111111111111111111111111111",
"10000000000000001000000000000001",
"10111101111111001011111101111101",
"10000101000001001010000101000001",
"10110101011101011010110101011001",
"10000100010100000010010100010001",
"11110111010111101111010111011101",
"10000000010000101000010000000001",
"10111111111110101011111111111101",
"10000000000010101010000000000001",
"10111101111010101010111101111101",
"10000101000010000010000001000001",
"10110101111111101111111101011001",
"10000100000000100000000100010001",
"10111111101110111110111011111001",
"10000000001000000000100000000001",
"10111111111111101111111111111101",
"10000000000000000000000000000001",
"10000000000000000000000000000001",
"11111111111111111111111111111111"
]
SPAWNS = {
    "A":[(2.5,2.5),(2.5,17.5),(5.5,17.5)],
    "B":[(29.5,2.5),(29.5,17.5),(26.5,17.5)]
}

def clamp(v,a,b): return max(a,min(b,v))
def dist(a,b): return math.hypot(a["x"]-b["x"], a["y"]-b["y"])
def wall(x,y):
    ix, iy = int(x), int(y)
    return ix < 0 or iy < 0 or ix >= MAP_W or iy >= MAP_H or WORLD[iy][ix] == "1"
def move_ok(x,y,r=.22):
    return not any(wall(x+dx,y+dy) for dx,dy in [(r,0),(-r,0),(0,r),(0,-r)])
def los(ax,ay,bx,by):
    steps=max(2,int(math.hypot(bx-ax,by-ay)*12))
    for i in range(1,steps):
        t=i/steps
        if wall(ax+(bx-ax)*t, ay+(by-ay)*t): return False
    return True

class Player:
    def __init__(self, pid, team, name, ai=False):
        self.id,self.team,self.name,self.ai=pid,team,name,ai
        self.x,self.y=SPAWNS[team][0]
        self.a=0.0; self.hp=MAX_HP; self.alive=True
        self.kills=self.deaths=0
        self.input={"f":0,"b":0,"l":0,"r":0,"turn":0,"fire":False}
        self.cheats={"aim":False,"esp":False,"norecoil":False,"infinite":False}
        self.last_shot=0.0
        self.ws=None
    def reset(self, slot):
        self.x,self.y=SPAWNS[self.team][slot]
        self.a=0 if self.team=="A" else math.pi
        self.hp=MAX_HP; self.alive=True; self.deaths=0 if self.deaths<0 else self.deaths
        self.input={"f":0,"b":0,"l":0,"r":0,"turn":0,"fire":False}

class Match:
    def __init__(self, mode):
        self.id=str(uuid.uuid4())[:8]; self.mode=mode
        self.players: Dict[str,Player]={}
        self.scores={"A":0,"B":0}; self.round=1
        self.round_wins={"A":[],"B":[]}
        self.started=False; self.phase="lobby"; self.round_end=0
        self.events=[]
        self.last=time.time()
        self.lock=asyncio.Lock()
    def add_human(self, team=None):
        pid=str(uuid.uuid4())[:8]
        counts={t:sum(p.team==t and not p.ai for p in self.players.values()) for t in ["A","B"]}
        team=team or ("A" if counts["A"]<=counts["B"] else "B")
        if counts[team]>=3: return None
        p=Player(pid,team,f"Player-{pid[:4]}")
        p.ws=None; self.players[pid]=p; return p
    def add_ai(self, team, slot):
        pid=f"ai-{team}-{slot}-{uuid.uuid4().hex[:4]}"
        p=Player(pid,team,f"AI-{team}{slot+1}",True); self.players[pid]=p; return p
    def setup_ai(self):
        for t in ["A","B"]:
            existing=sum(p.team==t for p in self.players.values())
            for s in range(existing,3): self.add_ai(t,s)
    def start_round(self):
        self.phase="playing"; self.round_end=time.time()+ROUND_TIME
        for t in ["A","B"]:
            ps=[p for p in self.players.values() if p.team==t]
            for i,p in enumerate(ps): p.reset(i%3)
        self.events.append({"type":"round","round":self.round,"text":f"Round {self.round} 시작"})
    def living(self,t): return [p for p in self.players.values() if p.team==t and p.alive]
    def shoot(self,p, now):
        if not p.alive or now-p.last_shot<FIRE_INTERVAL: return
        p.last_shot=now
        angle=p.a
        targets=[q for q in self.players.values() if q.team!=p.team and q.alive]
        if not targets:return
        target=None; best=999
        # aim cheat: snap to closest visible target inside a wide cone
        if p.cheats["aim"]:
            for q in targets:
                d=dist(p.__dict__,q.__dict__)
                if d<best and d<=WEAPON_RANGE and los(p.x,p.y,q.x,q.y):
                    best=d; target=q
            if target: angle=math.atan2(target.y-p.y,target.x-p.x)
        # normal hitscan: closest target near crosshair
        candidates=[]
        for q in targets:
            d=dist(p.__dict__,q.__dict__)
            if d>WEAPON_RANGE or not los(p.x,p.y,q.x,q.y): continue
            da=abs((math.atan2(q.y-p.y,q.x-p.x)-angle+math.pi)%(2*math.pi)-math.pi)
            if da < (0.10 if p.cheats["aim"] else 0.075):
                candidates.append((da,d,q))
        if candidates:
            candidates.sort(key=lambda x:(x[0],x[1]))
            q=candidates[0][2]
            q.hp-=WEAPON_DAMAGE
            self.events.append({"type":"hit","text":f"{p.name} → {q.name} -{WEAPON_DAMAGE}"})
            if q.hp<=0:
                q.hp=0;q.alive=False;q.deaths+=1;p.kills+=1
                self.events.append({"type":"kill","text":f"{p.name} 처치 → {q.name}"})
    def ai_step(self,p,dt,now):
        if not p.alive:return
        enemies=[q for q in self.players.values() if q.team!=p.team and q.alive]
        if not enemies:return
        q=min(enemies,key=lambda e:dist(p.__dict__,e.__dict__))
        desired=math.atan2(q.y-p.y,q.x-p.x)
        delta=(desired-p.a+math.pi)%(2*math.pi)-math.pi
        p.a += clamp(delta,-2.2*dt,2.2*dt)
        d=dist(p.__dict__,q.__dict__)
        if d>8:
            nx=p.x+math.cos(p.a)*2.2*dt; ny=p.y+math.sin(p.a)*2.2*dt
            if move_ok(nx,p.y):p.x=nx
            if move_ok(p.x,ny):p.y=ny
        p.input["fire"]=d<18 and los(p.x,p.y,q.x,q.y)
        if p.input["fire"]: self.shoot(p,now)
    def update(self,dt):
        now=time.time()
        if self.phase=="between":
            if now>=self.round_end: self.start_round()
            return
        if self.phase!="playing": return
        for p in self.players.values():
            if p.ai:self.ai_step(p,dt,now)
            elif p.alive:
                inp=p.input
                speed=4.4*dt
                dx=(inp["f"]-inp["b"])*math.cos(p.a)+(inp["r"]-inp["l"])*math.cos(p.a+math.pi/2)
                dy=(inp["f"]-inp["b"])*math.sin(p.a)+(inp["r"]-inp["l"])*math.sin(p.a+math.pi/2)
                length=math.hypot(dx,dy)
                if length: dx,dy=dx/length*speed,dy/length*speed
                nx,ny=p.x+dx,p.y+dy
                if move_ok(nx,p.y):p.x=nx
                if move_ok(p.x,ny):p.y=ny
                p.a += inp["turn"]*dt*2.7
                if inp["fire"]:self.shoot(p,now)
        if not self.living("A") or not self.living("B") or now>=self.round_end:
            winner="A" if len(self.living("A"))>len(self.living("B")) else "B"
            if not self.living("A"):winner="B"
            if not self.living("B"):winner="A"
            self.scores[winner]+=1; self.round_wins[winner].append(self.round)
            self.events.append({"type":"round_end","winner":winner,"round":self.round})
            if self.scores[winner]>=3 or self.round>=5:
                self.phase="finished"
            else:
                self.round+=1; self.phase="between"; self.round_end=now+4
        elif self.phase=="finished": pass
    def state(self, viewer=None):
        now=time.time()
        ps=[]
        for p in self.players.values():
            item={"id":p.id,"team":p.team,"name":p.name,"x":p.x,"y":p.y,"a":p.a,
                  "hp":p.hp,"alive":p.alive,"kills":p.kills,"deaths":p.deaths,"ai":p.ai}
            if viewer and viewer.cheats["esp"] or (viewer and viewer.team==p.team) or p.id==(viewer.id if viewer else ""):
                item["visible"]=True
            else:item["visible"]=los(viewer.x,viewer.y,p.x,p.y) if viewer else False
            ps.append(item)
        return {"id":self.id,"mode":self.mode,"phase":self.phase,"round":self.round,
                "scores":self.scores,"time":max(0,int(self.round_end-now)) if self.phase=="playing" else 0,
                "players":ps,"events":self.events[-8:]}

matches: Dict[str,Match]={}
clients: Dict[str,WebSocket]={}

@app.get("/")
async def index(): return FileResponse(os.path.join(BASE,"static","index.html"))

@app.on_event("startup")
async def startup():
    asyncio.create_task(game_loop())

async def game_loop():
    while True:
        now=time.time()
        for m in list(matches.values()): m.update(now-m.last); m.last=now
        await asyncio.sleep(TICK)

@app.websocket("/ws")
async def websocket(ws:WebSocket):
    await ws.accept()
    pid=None; match=None
    try:
        while True:
            msg=json.loads(await ws.receive_text())
            typ=msg.get("type")
            if typ=="join":
                mode=msg.get("mode","ai")
                match=next((m for m in matches.values()
                             if m.mode==mode and m.phase in ("lobby","playing","between")
                             and sum(not p.ai for p in m.players.values()) < 6
                             and any(p.ws is None and not p.ai for p in m.players.values())),None)
                if not match:
                    match=Match(mode); matches[match.id]=match
                p=match.add_human(msg.get("team"))
                if not p:
                    await ws.send_json({"type":"error","message":"해당 팀이 가득 찼습니다."}); continue
                pid=p.id;p.ws=ws;clients[pid]=ws
                if mode=="ai":
                    match.setup_ai()
                    if match.phase=="lobby": match.start_round()
                elif sum(not x.ai for x in match.players.values())>=6 and match.phase=="lobby":
                    match.start_round()
                await ws.send_json({"type":"joined","id":pid,"match":match.id,"team":p.team,"state":match.state(p)})
            elif not match or not pid: continue
            elif typ=="input":
                p=match.players.get(pid)
                if p:p.input.update({k:msg.get(k,p.input.get(k)) for k in p.input})
            elif typ=="cheats":
                p=match.players.get(pid)
                if p:
                    for k in p.cheats:
                        if k in msg:p.cheats[k]=bool(msg[k])
            elif typ=="ping": await ws.send_json({"type":"pong"})
            # broadcast after every client command
            if match and pid:
                await broadcast(match)
    except WebSocketDisconnect: pass
    finally:
        if pid:
            clients.pop(pid,None)
            if match and pid in match.players:
                match.players[pid].ws=None

async def broadcast(m):
    dead=[]
    for p in m.players.values():
        if p.ws:
            try: await p.ws.send_json({"type":"state","state":m.state(p)})
            except Exception: dead.append(p.id)
    for x in dead: clients.pop(x,None)

from pathlib import Path
app.mount("/static",StaticFiles(directory=os.path.join(BASE,"static")),name="static")
