# ============================================================
# CHEAT FPS - FastAPI + WebSocket Server
# ============================================================

import asyncio
import json
import math
import os
import random
import time
import uuid

from pathlib import Path
from typing import Dict, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


# ============================================================
# 기본 설정
# ============================================================

BASE = str(Path(__file__).parent)

app = FastAPI(title="Cheat FPS")

app.mount(
    "/static",
    StaticFiles(directory=os.path.join(BASE, "static")),
    name="static"
)


# ============================================================
# 게임 설정
# ============================================================

MAX_PLAYERS = 6
TEAM_SIZE = 3

MAX_ROUNDS = 9
ROUNDS_TO_WIN = 5

MAX_HP = 100

TICK_RATE = 20
TICK_TIME = 1.0 / TICK_RATE

PLAYER_SPEED = 5.0
AI_SPEED = 3.2

SHOT_DAMAGE = 25
SHOT_RANGE = 60.0

SHOT_COOLDOWN = 0.18
AI_SHOT_COOLDOWN = 0.65

MAP_WIDTH = 40.0
MAP_HEIGHT = 30.0

SPAWNS = {
    0: [
        (-15.0, -8.0),
        (-15.0, 0.0),
        (-15.0, 8.0),
    ],
    1: [
        (15.0, -8.0),
        (15.0, 0.0),
        (15.0, 8.0),
    ],
}


# ============================================================
# 전역 상태
# ============================================================

matches: Dict[str, "Match"] = {}


# ============================================================
# 유틸
# ============================================================

def clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


def distance(x1, y1, x2, y2):
    return math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)


def normalize(x, y):
    length = math.sqrt(x * x + y * y)

    if length <= 0.0001:
        return 0.0, 0.0

    return x / length, y / length


def team_alive(players, team):
    return any(
        p.team == team and
        not p.ai and
        p.hp > 0 and
        not p.spectator
        for p in players.values()
    ) or any(
        p.team == team and
        p.ai and
        p.hp > 0
        for p in players.values()
    )


# ============================================================
# Player
# ============================================================

class Player:

    def __init__(
        self,
        player_id: str,
        name: str,
        team: int,
        ai: bool = False,
    ):
        self.id = player_id
        self.name = name
        self.team = team
        self.ai = ai

        self.ws: Optional[WebSocket] = None

        self.x = 0.0
        self.y = 0.0

        self.angle = 0.0

        self.hp = MAX_HP

        self.kills = 0
        self.deaths = 0

        self.spectator = False

        self.last_shot = 0.0

        self.recoil = 0.0

        self.input_x = 0.0
        self.input_y = 0.0

        self.shooting = False

        self.cheats = {
            "aim": False,
            "esp": False,
            "norecoil": False,
            "infinite": False,
        }

    def reset_for_round(self, index: int):

        spawn_list = SPAWNS[self.team]

        spawn = spawn_list[index % len(spawn_list)]

        self.x = spawn[0]
        self.y = spawn[1]

        if self.team == 0:
            self.angle = 0.0
        else:
            self.angle = math.pi

        self.hp = MAX_HP

        self.spectator = False

        self.input_x = 0.0
        self.input_y = 0.0
        self.shooting = False

        self.recoil = 0.0

        self.last_shot = 0.0


# ============================================================
# Match
# ============================================================

class Match:

    def __init__(self, match_id: str, mode: str):

        self.id = match_id

        self.mode = mode

        self.players: Dict[str, Player] = {}

        self.phase = "lobby"

        self.round_number = 0

        self.team_round_wins = {
            0: 0,
            1: 0,
        }

        self.round_timer = 0.0

        self.round_winner: Optional[int] = None

        self.match_winner: Optional[int] = None

        self.created_at = time.time()

        self.lock = asyncio.Lock()

    # --------------------------------------------------------
    # 플레이어 수
    # --------------------------------------------------------

    def human_count(self):

        return sum(
            1 for p in self.players.values()
            if not p.ai
        )

    def ai_count(self):

        return sum(
            1 for p in self.players.values()
            if p.ai
        )

    # --------------------------------------------------------
    # 팀별 플레이어
    # --------------------------------------------------------

    def team_players(self, team):

        return [
            p for p in self.players.values()
            if p.team == team
        ]

    # --------------------------------------------------------
    # 빈 팀 찾기
    # --------------------------------------------------------

    def get_team(self):

        team0 = len(self.team_players(0))
        team1 = len(self.team_players(1))

        if team0 < TEAM_SIZE:
            return 0

        if team1 < TEAM_SIZE:
            return 1

        return None

    # --------------------------------------------------------
    # AI 생성
    # --------------------------------------------------------

    def create_ai_team(self, team):

        while len(self.team_players(team)) < TEAM_SIZE:

            index = len(self.team_players(team))

            ai_id = f"ai_{uuid.uuid4().hex[:8]}"

            ai = Player(
                player_id=ai_id,
                name=f"AI {index + 1}",
                team=team,
                ai=True,
            )

            self.players[ai.id] = ai

    # --------------------------------------------------------
    # AI 매치 구성
    # --------------------------------------------------------

    def setup_ai_match(self):

        self.create_ai_team(0)
        self.create_ai_team(1)

    # --------------------------------------------------------
    # 라운드 시작
    # --------------------------------------------------------

    def start_round(self):

        self.round_number += 1

        self.phase = "playing"

        self.round_winner = None

        self.round_timer = 0.0

        for team in (0, 1):

            team_members = self.team_players(team)

            for index, player in enumerate(team_members):

                player.reset_for_round(index)

    # --------------------------------------------------------
    # 다음 라운드
    # --------------------------------------------------------

    def finish_round(self, winner):

        if self.phase != "playing":
            return

        self.round_winner = winner

        self.team_round_wins[winner] += 1

        if self.team_round_wins[winner] >= ROUNDS_TO_WIN:

            self.match_winner = winner

            self.phase = "finished"

            return

        if self.round_number >= MAX_ROUNDS:

            if self.team_round_wins[0] > self.team_round_wins[1]:
                self.match_winner = 0
            elif self.team_round_wins[1] > self.team_round_wins[0]:
                self.match_winner = 1
            else:
                self.match_winner = winner

            self.phase = "finished"

            return

        self.phase = "between"

    # --------------------------------------------------------
    # 모든 인간 플레이어 연결
    # --------------------------------------------------------

    async def broadcast(self, data):

        message = json.dumps(
            data,
            ensure_ascii=False,
            separators=(",", ":"),
        )

        disconnected = []

        for player in list(self.players.values()):

            if player.ws is None:
                continue

            try:
                await player.ws.send_text(message)

            except Exception:
                disconnected.append(player.id)

        for player_id in disconnected:

            if player_id in self.players:

                self.players[player_id].ws = None

    # --------------------------------------------------------
    # 상태
    # --------------------------------------------------------

    def state_for(self, viewer: Optional[Player]):

        players = []

        for p in self.players.values():

            # 죽은 플레이어도 관전 상태로 전송
            item = {
                "id": p.id,
                "name": p.name,
                "team": p.team,
                "ai": p.ai,
                "hp": p.hp,
                "x": round(p.x, 3),
                "y": round(p.y, 3),
                "angle": round(p.angle, 4),
                "spectator": p.spectator,
                "kills": p.kills,
                "deaths": p.deaths,
            }

            # ESP가 꺼져 있으면 적 위치를 제한할 수도 있지만
            # 게임 구현을 단순화하기 위해 기본 위치는 전달한다.
            players.append(item)

        return {
            "type": "state",
            "matchId": self.id,
            "mode": self.mode,
            "phase": self.phase,

            "round": self.round_number,

            "roundWins": {
                "0": self.team_round_wins[0],
                "1": self.team_round_wins[1],
            },

            "roundWinner": self.round_winner,

            "matchWinner": self.match_winner,

            "viewer": (
                {
                    "id": viewer.id,
                    "team": viewer.team,
                    "hp": viewer.hp,
                    "spectator": viewer.spectator,
                    "kills": viewer.kills,
                    "deaths": viewer.deaths,
                }
                if viewer
                else None
            ),

            "players": players,

            "serverTime": time.time(),
        }


# ============================================================
# 매치 찾기
# ============================================================

def find_match_for_join(mode: str):

    # --------------------------------------------------------
    # AI 모드
    #
    # AI 모드는 플레이어마다 독립적인 매치 생성.
    # 여러 명이 들어와서 서로 다른 AI 매치에 섞이는 것을 방지.
    # --------------------------------------------------------

    if mode == "ai":
        return None

    # --------------------------------------------------------
    # Local 모드
    #
    # 핵심 수정:
    # 기존 플레이어의 WebSocket이 이미 연결되어 있어도
    # 같은 lobby / playing / between 방을 계속 사용한다.
    # --------------------------------------------------------

    candidates = []

    for match in matches.values():

        if match.mode != "local":
            continue

        if match.phase not in (
            "lobby",
            "playing",
            "between",
        ):
            continue

        if match.human_count() >= MAX_PLAYERS:
            continue

        candidates.append(match)

    if not candidates:
        return None

    candidates.sort(
        key=lambda m: m.created_at
    )

    return candidates[0]


# ============================================================
# 플레이어 추가
# ============================================================

async def create_player(mode: str, name: str):

    match = find_match_for_join(mode)

    if match is None:

        match_id = uuid.uuid4().hex[:8]

        match = Match(
            match_id=match_id,
            mode=mode,
        )

        matches[match_id] = match

    team = match.get_team()

    if team is None:

        return None, None

    player_id = uuid.uuid4().hex[:10]

    player = Player(
        player_id=player_id,
        name=name[:20] if name else "Player",
        team=team,
        ai=False,
    )

    match.players[player.id] = player

    # --------------------------------------------------------
    # AI 모드
    # --------------------------------------------------------

    if mode == "ai":

        match.setup_ai_match()

        if match.phase == "lobby":

            match.start_round()

    # --------------------------------------------------------
    # Local 모드
    # --------------------------------------------------------

    else:

        if match.human_count() >= MAX_PLAYERS:

            if match.phase == "lobby":

                # 팀이 3v3인지 확인
                if (
                    len(match.team_players(0)) >= TEAM_SIZE
                    and
                    len(match.team_players(1)) >= TEAM_SIZE
                ):
                    match.start_round()

    return match, player


# ============================================================
# 이동
# ============================================================

def update_player_movement(player: Player, dt: float):

    if player.hp <= 0:
        return

    if player.spectator:
        return

    dx = player.input_x
    dy = player.input_y

    nx, ny = normalize(dx, dy)

    speed = AI_SPEED if player.ai else PLAYER_SPEED

    player.x += nx * speed * dt
    player.y += ny * speed * dt

    player.x = clamp(
        player.x,
        -MAP_WIDTH / 2,
        MAP_WIDTH / 2,
    )

    player.y = clamp(
        player.y,
        -MAP_HEIGHT / 2,
        MAP_HEIGHT / 2,
    )


# ============================================================
# AI
# ============================================================

def update_ai(match: Match, ai: Player, dt: float):

    if ai.hp <= 0:
        return

    enemies = [
        p for p in match.players.values()
        if p.team != ai.team
        and p.hp > 0
    ]

    if not enemies:
        return

    target = min(
        enemies,
        key=lambda p: distance(
            ai.x,
            ai.y,
            p.x,
            p.y,
        )
    )

    dx = target.x - ai.x
    dy = target.y - ai.y

    dist = math.sqrt(dx * dx + dy * dy)

    if dist > 7:

        ai.input_x = dx
        ai.input_y = dy

    else:

        # 가까우면 좌우로 조금 움직임
        ai.input_x = -dy * 0.3
        ai.input_y = dx * 0.3

    ai.angle = math.atan2(
        dy,
        dx,
    )

    if dist <= SHOT_RANGE:

        ai.shooting = True

    else:

        ai.shooting = False


# ============================================================
# 조준 보정
# ============================================================

def apply_aim_assist(
    shooter: Player,
    target_candidates,
):

    if not target_candidates:
        return None

    best = None
    best_angle = 999999

    for target in target_candidates:

        dx = target.x - shooter.x
        dy = target.y - shooter.y

        target_angle = math.atan2(
            dy,
            dx,
        )

        diff = abs(
            math.atan2(
                math.sin(target_angle - shooter.angle),
                math.cos(target_angle - shooter.angle),
            )
        )

        if diff < best_angle:

            best_angle = diff
            best = target

    # 스냅 허용각
    if best is not None and best_angle <= math.radians(25):

        return best

    return None


# ============================================================
# 사격
# ============================================================

def shoot(match: Match, shooter: Player):

    if shooter.hp <= 0:
        return None

    now = time.time()

    cooldown = (
        AI_SHOT_COOLDOWN
        if shooter.ai
        else SHOT_COOLDOWN
    )

    if now - shooter.last_shot < cooldown:

        return None

    shooter.last_shot = now

    enemies = [
        p for p in match.players.values()
        if p.team != shooter.team
        and p.hp > 0
    ]

    if not enemies:
        return None

    target = None

    # --------------------------------------------------------
    # Aim Assist
    # --------------------------------------------------------

    if shooter.cheats.get("aim"):

        target = apply_aim_assist(
            shooter,
            enemies,
        )

    # --------------------------------------------------------
    # AI 기본 사격
    # --------------------------------------------------------

    elif shooter.ai:

        target = min(
            enemies,
            key=lambda p: distance(
                shooter.x,
                shooter.y,
                p.x,
                p.y,
            )
        )

    # --------------------------------------------------------
    # 일반 사격
    # --------------------------------------------------------

    else:

        # 조준 방향에 가장 가까운 적 검색
        best_diff = math.radians(10)

        for enemy in enemies:

            dx = enemy.x - shooter.x
            dy = enemy.y - shooter.y

            dist = math.sqrt(dx * dx + dy * dy)

            if dist > SHOT_RANGE:
                continue

            target_angle = math.atan2(
                dy,
                dx,
            )

            diff = abs(
                math.atan2(
                    math.sin(
                        target_angle - shooter.angle
                    ),
                    math.cos(
                        target_angle - shooter.angle
                    ),
                )
            )

            if diff < best_diff:

                best_diff = diff
                target = enemy

    if target is None:
        return None

    target_distance = distance(
        shooter.x,
        shooter.y,
        target.x,
        target.y,
    )

    if target_distance > SHOT_RANGE:

        return None

    # --------------------------------------------------------
    # No Recoil
    # --------------------------------------------------------

    if not shooter.cheats.get("norecoil"):

        recoil_amount = 0.035

        shooter.recoil += recoil_amount

        shooter.angle += random.uniform(
            -recoil_amount,
            recoil_amount,
        )

    # --------------------------------------------------------
    # 데미지
    # --------------------------------------------------------

    target.hp -= SHOT_DAMAGE

    if target.hp <= 0:

        target.hp = 0

        target.spectator = True

        target.deaths += 1

        shooter.kills += 1

        return {
            "type": "kill",
            "killer": shooter.id,
            "victim": target.id,
        }

    return {
        "type": "hit",
        "killer": shooter.id,
        "victim": target.id,
        "damage": SHOT_DAMAGE,
    }


# ============================================================
# 라운드 종료 체크
# ============================================================

def check_round_end(match: Match):

    if match.phase != "playing":
        return

    team0_alive = any(
        p.team == 0 and p.hp > 0
        for p in match.players.values()
    )

    team1_alive = any(
        p.team == 1 and p.hp > 0
        for p in match.players.values()
    )

    if not team0_alive:

        match.finish_round(1)

    elif not team1_alive:

        match.finish_round(0)


# ============================================================
# 매치 업데이트
# ============================================================

async def update_match(match: Match):

    dt = TICK_TIME

    # --------------------------------------------------------
    # Between
    # --------------------------------------------------------

    if match.phase == "between":

        # 약간의 대기 후 다음 라운드
        await asyncio.sleep(1.5)

        if match.phase == "between":

            match.start_round()

        return

    # --------------------------------------------------------
    # Playing
    # --------------------------------------------------------

    if match.phase != "playing":
        return

    for player in list(match.players.values()):

        if player.ai:

            update_ai(
                match,
                player,
                dt,
            )

    for player in list(match.players.values()):

        update_player_movement(
            player,
            dt,
        )

    # --------------------------------------------------------
    # Shooting
    # --------------------------------------------------------

    for player in list(match.players.values()):

        if player.hp <= 0:
            continue

        if player.shooting:

            event = shoot(
                match,
                player,
            )

            if event:

                await match.broadcast(event)

    check_round_end(match)


# ============================================================
# 게임 루프
# ============================================================

async def match_loop(match: Match):

    while match.id in matches:

        started = time.time()

        try:

            async with match.lock:

                await update_match(match)

                # 각 플레이어에게 상태 전달
                for player in list(match.players.values()):

                    if player.ws is None:
                        continue

                    try:

                        await player.ws.send_text(
                            json.dumps(
                                match.state_for(player),
                                ensure_ascii=False,
                                separators=(",", ":"),
                            )
                        )

                    except Exception:

                        player.ws = None

        except Exception as e:

            print(
                f"[MATCH ERROR] {match.id}: {e}"
            )

        elapsed = time.time() - started

        await asyncio.sleep(
            max(
                0.01,
                TICK_TIME - elapsed,
            )
        )


# ============================================================
# 매치 루프 시작
# ============================================================

def ensure_match_loop(match: Match):

    task_name = f"_task_{match.id}"

    if hasattr(match, task_name):

        task = getattr(match, task_name)

        if not task.done():
            return

    task = asyncio.create_task(
        match_loop(match)
    )

    setattr(
        match,
        task_name,
        task,
    )


# ============================================================
# HTTP
# ============================================================

@app.get("/")
async def index():

    return FileResponse(
        os.path.join(
            BASE,
            "static",
            "index.html",
        )
    )


@app.get("/health")
async def health():

    return {
        "status": "ok",
        "matches": len(matches),
    }


# ============================================================
# WebSocket
# ============================================================

@app.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
):

    await websocket.accept()

    player = None
    match = None

    try:

        # ----------------------------------------------------
        # 첫 메시지: join
        # ----------------------------------------------------

        raw = await websocket.receive_text()

        try:
            data = json.loads(raw)
        except Exception:

            await websocket.send_text(
                json.dumps({
                    "type": "error",
                    "message": "잘못된 요청입니다.",
                })
            )

            await websocket.close()

            return

        if data.get("type") != "join":

            await websocket.send_text(
                json.dumps({
                    "type": "error",
                    "message": "먼저 게임에 참가해야 합니다.",
                })
            )

            await websocket.close()

            return

        mode = data.get(
            "mode",
            "ai",
        )

        if mode not in (
            "ai",
            "local",
        ):

            mode = "ai"

        name = str(
            data.get(
                "name",
                "Player",
            )
        ).strip()

        if not name:

            name = "Player"

        # ----------------------------------------------------
        # 플레이어 생성
        # ----------------------------------------------------

        match, player = await create_player(
            mode,
            name,
        )

        if match is None or player is None:

            await websocket.send_text(
                json.dumps({
                    "type": "error",
                    "message": "게임방에 참가할 수 없습니다.",
                })
            )

            await websocket.close()

            return

        player.ws = websocket

        # ----------------------------------------------------
        # 매치 루프 시작
        # ----------------------------------------------------

        ensure_match_loop(match)

        # ----------------------------------------------------
        # 입장 메시지
        # ----------------------------------------------------

        await websocket.send_text(
            json.dumps({
                "type": "joined",
                "id": player.id,
                "matchId": match.id,
                "team": player.team,
                "mode": match.mode,
                "phase": match.phase,
            })
        )

        # 모든 참가자에게 알림
        await match.broadcast({
            "type": "player_joined",
            "name": player.name,
            "team": player.team,
            "count": match.human_count(),
        })

        # 현재 상태
        await websocket.send_text(
            json.dumps(
                match.state_for(player),
                ensure_ascii=False,
            )
        )

        # ----------------------------------------------------
        # 메시지 처리
        # ----------------------------------------------------

        while True:

            raw = await websocket.receive_text()

            try:
                data = json.loads(raw)

            except Exception:

                continue

            msg_type = data.get("type")

            # ------------------------------------------------
            # 입력
            # ------------------------------------------------

            if msg_type == "input":

                player.input_x = float(
                    data.get(
                        "x",
                        0,
                    )
                )

                player.input_y = float(
                    data.get(
                        "y",
                        0,
                    )
                )

                player.input_x = clamp(
                    player.input_x,
                    -1,
                    1,
                )

                player.input_y = clamp(
                    player.input_y,
                    -1,
                    1,
                )

                if "angle" in data:

                    try:

                        player.angle = float(
                            data["angle"]
                        )

                    except Exception:
                        pass

                if "shooting" in data:

                    player.shooting = bool(
                        data["shooting"]
                    )

            # ------------------------------------------------
            # 이동
            # ------------------------------------------------

            elif msg_type == "move":

                try:

                    player.input_x = clamp(
                        float(
                            data.get(
                                "x",
                                0,
                            )
                        ),
                        -1,
                        1,
                    )

                    player.input_y = clamp(
                        float(
                            data.get(
                                "y",
                                0,
                            )
                        ),
                        -1,
                        1,
                    )

                except Exception:
                    pass

            # ------------------------------------------------
            # 조준
            # ------------------------------------------------

            elif msg_type == "look":

                try:

                    player.angle = float(
                        data.get(
                            "angle",
                            player.angle,
                        )
                    )

                except Exception:
                    pass

            # ------------------------------------------------
            # 발사
            # ------------------------------------------------

            elif msg_type == "shoot":

                player.shooting = bool(
                    data.get(
                        "value",
                        True,
                    )
                )

            # ------------------------------------------------
            # 치트
            # ------------------------------------------------

            elif msg_type == "cheats":

                player.cheats["aim"] = bool(
                    data.get(
                        "aim",
                        False,
                    )
                )

                player.cheats["esp"] = bool(
                    data.get(
                        "esp",
                        False,
                    )
                )

                player.cheats["norecoil"] = bool(
                    data.get(
                        "norecoil",
                        False,
                    )
                )

                player.cheats["infinite"] = bool(
                    data.get(
                        "infinite",
                        False,
                    )
                )

                await websocket.send_text(
                    json.dumps({
                        "type": "cheats_updated",
                        "cheats": player.cheats,
                    })
                )

            # ------------------------------------------------
            # Ping
            # ------------------------------------------------

            elif msg_type == "ping":

                await websocket.send_text(
                    json.dumps({
                        "type": "pong",
                        "time": time.time(),
                    })
                )

    except WebSocketDisconnect:

        pass

    except Exception as e:

        print(
            f"[WEBSOCKET ERROR] {e}"
        )

    finally:

        # ----------------------------------------------------
        # 연결 종료
        # ----------------------------------------------------

        if player is not None:

            player.ws = None

            player.input_x = 0
            player.input_y = 0
            player.shooting = False

        # ----------------------------------------------------
        # Local lobby에서 사람이 전부 나갔다면
        # 빈 방 제거
        # ----------------------------------------------------

        if match is not None:

            if match.human_count() == 0:

                # AI는 즉시 제거
                matches.pop(
                    match.id,
                    None,
                )


# ============================================================
# 서버 시작
# ============================================================

if __name__ == "__main__":

    import uvicorn

    port = int(
        os.environ.get(
            "PORT",
            "8000",
        )
    )

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=port,
        reload=False,
    )