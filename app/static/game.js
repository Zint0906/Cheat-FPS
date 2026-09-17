// ============================================================
// CHEAT FPS - Client
// ============================================================

const $ = (s) => document.querySelector(s);
const $$ = (s) => document.querySelectorAll(s);

let ws = null;

let myId = null;
let myTeam = null;
let state = null;

let mode = "ai";
let sensitivity = 1;

let keys = {};
let firing = false;

let yaw = 0;
let lastTouchX = null;

let gameStarted = false;
let connectionAttempt = 0;


// ============================================================
// DOM
// ============================================================

const menu = $("#menu");
const lobby = $("#lobby");
const game = $("#game");
const result = $("#result");

const canvas = $("#view");
const ctx = canvas.getContext("2d");


// ============================================================
// 화면
// ============================================================

function show(screen) {
    [menu, lobby, game, result].forEach((el) => {
        if (el) el.classList.add("hidden");
    });

    if (screen) {
        screen.classList.remove("hidden");
    }
}


// ============================================================
// Canvas
// ============================================================

function resize() {
    const dpr = window.devicePixelRatio || 1;

    canvas.width = Math.floor(innerWidth * dpr);
    canvas.height = Math.floor(innerHeight * dpr);

    canvas.style.width = innerWidth + "px";
    canvas.style.height = innerHeight + "px";

    ctx.setTransform(
        dpr,
        0,
        0,
        dpr,
        0,
        0
    );
}

window.addEventListener("resize", resize);
resize();


// ============================================================
// 모드 선택
// ============================================================

$$("[data-mode]").forEach((button) => {

    button.addEventListener("click", () => {

        mode = button.dataset.mode || "ai";

        if (mode === "ai") {
            $("#modeText").textContent =
                "AI전 — 플레이어팀 3명 vs AI팀 3명";
        } else {
            $("#modeText").textContent =
                "로컬 — 최대 6명이 같은 방에서 대전";
        }

        show(lobby);

        resetLobby();

        // 여기서는 연결하지 않는다.
        // 실제 연결은 '전투 참가' 버튼을 눌렀을 때 한다.
    });

});


// ============================================================
// 설정
// ============================================================

if ($("#settingsBtn")) {

    $("#settingsBtn").onclick = () => {
        $("#settings").classList.toggle("hidden");
    };

}

if ($("#sens")) {

    $("#sens").oninput = (e) => {
        sensitivity = Number(e.target.value);
    };

}


// ============================================================
// 뒤로가기
// ============================================================

if ($("#back")) {

    $("#back").onclick = () => {

        disconnect();

        show(menu);

    };

}


// ============================================================
// Lobby 초기화
// ============================================================

function resetLobby() {

    if ($("#teamA")) {
        $("#teamA").innerHTML = "";
    }

    if ($("#teamB")) {
        $("#teamB").innerHTML = "";
    }

    if ($("#ready")) {
        $("#ready").disabled = false;
        $("#ready").textContent = "전투 참가";
    }

}


// ============================================================
// 전투 참가
// ============================================================

if ($("#ready")) {

    $("#ready").onclick = () => {

        if (ws && ws.readyState === WebSocket.OPEN) {
            return;
        }

        $("#ready").disabled = true;
        $("#ready").textContent = "연결 중...";

        connect();

    };

}


// ============================================================
// WebSocket 연결
// ============================================================

function connect() {

    disconnect();

    const protocol =
        location.protocol === "https:"
            ? "wss://"
            : "ws://";

    const url =
        protocol +
        location.host +
        "/ws";

    connectionAttempt++;

    try {

        ws = new WebSocket(url);

    } catch (error) {

        showConnectionError(
            "WebSocket을 만들 수 없습니다."
        );

        return;
    }


    // --------------------------------------------------------
    // 연결 성공
    // --------------------------------------------------------

    ws.onopen = () => {

        console.log("[CHEAT FPS] WebSocket connected");

        const joinMessage = {
            type: "join",
            mode: mode,
            name: getPlayerName()
        };

        send(joinMessage);

    };


    // --------------------------------------------------------
    // 메시지
    // --------------------------------------------------------

    ws.onmessage = (event) => {

        let message;

        try {

            message = JSON.parse(event.data);

        } catch (error) {

            console.error(
                "Invalid server message:",
                event.data
            );

            return;
        }


        // ----------------------------------------------------
        // 참가 완료
        // ----------------------------------------------------

        if (message.type === "joined") {

            myId = message.id;
            myTeam = message.team;

            console.log(
                "[CHEAT FPS] Joined:",
                message
            );

            updateTeamInfo();

            // 서버가 보내는 joined에는 state가 없다.
            // 따라서 현재 상태를 기다린다.
            $("#ready").textContent = "전투 참가 완료";

            return;
        }


        // ----------------------------------------------------
        // 플레이어 참가
        // ----------------------------------------------------

        if (message.type === "player_joined") {

            console.log(
                "[CHEAT FPS] Player joined:",
                message
            );

            updateLobbyCount(message.count);

            return;
        }


        // ----------------------------------------------------
        // 게임 상태
        // ----------------------------------------------------

        if (message.type === "state") {

            state = message;

            updateLobby();

            updateHUD();

            handleGamePhase();

            return;
        }


        // ----------------------------------------------------
        // 피격
        // ----------------------------------------------------

        if (
            message.type === "hit" ||
            message.type === "kill"
        ) {

            console.log(
                "[CHEAT FPS]",
                message
            );

            return;
        }


        // ----------------------------------------------------
        // 치트 변경
        // ----------------------------------------------------

        if (message.type === "cheats_updated") {

            console.log(
                "[CHEAT FPS] Cheats:",
                message.cheats
            );

            return;
        }


        // ----------------------------------------------------
        // Pong
        // ----------------------------------------------------

        if (message.type === "pong") {
            return;
        }


        // ----------------------------------------------------
        // 오류
        // ----------------------------------------------------

        if (message.type === "error") {

            showConnectionError(
                message.message ||
                "게임 참가에 실패했습니다."
            );

            return;
        }

    };


    // --------------------------------------------------------
    // 연결 종료
    // --------------------------------------------------------

    ws.onclose = () => {

        console.log(
            "[CHEAT FPS] WebSocket disconnected"
        );

        if (!gameStarted) {

            if ($("#ready")) {

                $("#ready").disabled = false;
                $("#ready").textContent =
                    "전투 참가";

            }

        }

    };


    // --------------------------------------------------------
    // 오류
    // --------------------------------------------------------

    ws.onerror = (error) => {

        console.error(
            "[CHEAT FPS] WebSocket error",
            error
        );

    };

}


// ============================================================
// 플레이어 이름
// ============================================================

function getPlayerName() {

    let name = localStorage.getItem(
        "cheat_fps_name"
    );

    if (!name) {

        name =
            "Player-" +
            Math.floor(
                Math.random() * 9999
            );

        localStorage.setItem(
            "cheat_fps_name",
            name
        );
    }

    return name;
}


// ============================================================
// 연결 종료
// ============================================================

function disconnect() {

    if (ws) {

        try {
            ws.close();
        } catch (error) {
            console.warn(error);
        }

    }

    ws = null;

    gameStarted = false;

}


// ============================================================
// Send
// ============================================================

function send(data) {

    if (
        ws &&
        ws.readyState === WebSocket.OPEN
    ) {

        try {

            ws.send(
                JSON.stringify(data)
            );

        } catch (error) {

            console.error(
                "Send error:",
                error
            );

        }

    }

}


// ============================================================
// Lobby
// ============================================================

function updateLobby() {

    if (!state) return;

    const players = state.players || [];

    const teamA = $("#teamA");
    const teamB = $("#teamB");

    if (teamA) teamA.innerHTML = "";
    if (teamB) teamB.innerHTML = "";

    players.forEach((player) => {

        const div =
            document.createElement("div");

        div.className =
            "player" +
            (
                player.id === myId
                    ? " me"
                    : ""
            );

        div.textContent =
            player.name +
            (
                player.ai
                    ? " [AI]"
                    : ""
            );

        if (player.team === 0) {

            if (teamA) {
                teamA.appendChild(div);
            }

        } else {

            if (teamB) {
                teamB.appendChild(div);
            }

        }

    });

    updateTeamInfo();

}


// ============================================================
// 팀 정보
// ============================================================

function updateTeamInfo() {

    const modeText = $("#modeText");

    if (!modeText) return;

    let text =
        mode === "ai"
            ? "AI전 — 플레이어팀 3명 vs AI팀 3명"
            : "로컬 — 최대 6명이 같은 방에서 대전";

    if (myTeam !== null) {

        text +=
            " | 배정 팀: " +
            (
                myTeam === 0
                    ? "A"
                    : "B"
            );

    }

    modeText.textContent = text;

}


// ============================================================
// Lobby 인원
// ============================================================

function updateLobbyCount(count) {

    if (!$("#modeText")) return;

    if (mode === "local") {

        $("#modeText").textContent =
            "로컬 — 참가자 " +
            count +
            "/6";

    }

}


// ============================================================
// Phase 처리
// ============================================================

function handleGamePhase() {

    if (!state) return;

    // --------------------------------------------------------
    // Lobby
    // --------------------------------------------------------

    if (state.phase === "lobby") {

        if (!gameStarted) {
            show(lobby);
        }

        return;
    }


    // --------------------------------------------------------
    // Playing
    // --------------------------------------------------------

    if (state.phase === "playing") {

        if (!gameStarted) {

            gameStarted = true;

            show(game);

            startRenderer();

        }

        return;
    }


    // --------------------------------------------------------
    // Between
    // --------------------------------------------------------

    if (state.phase === "between") {

        if (!gameStarted) {

            gameStarted = true;

            show(game);

            startRenderer();

        }

        return;
    }


    // --------------------------------------------------------
    // Finished
    // --------------------------------------------------------

    if (state.phase === "finished") {

        finishMatch();

    }

}


// ============================================================
// HUD
// ============================================================

function updateHUD() {

    if (!state) return;

    const round = Number(
        state.round || 0
    );

    const winsA =
        Number(
            state.roundWins?.["0"] || 0
        );

    const winsB =
        Number(
            state.roundWins?.["1"] || 0
        );


    if ($("#round")) {

        $("#round").textContent =
            `ROUND ${round}/5`;

    }


    if ($("#score")) {

        $("#score").textContent =
            `${winsA} : ${winsB}`;

    }


    if ($("#timer")) {

        $("#timer").textContent =
            state.phase === "playing"
                ? "LIVE"
                : state.phase.toUpperCase();

    }


    const me =
        getMe();


    if (me) {

        if ($("#hp")) {

            $("#hp").textContent =
                `HP ${me.hp}`;

        }


        if ($("#cheats")) {

            const cheats =
                me.cheats || {};

            const active = [];

            if (cheats.aim) {
                active.push("AIM");
            }

            if (cheats.esp) {
                active.push("ESP");
            }

            if (cheats.norecoil) {
                active.push("NO RECOIL");
            }

            if (cheats.infinite) {
                active.push("INFINITE");
            }

            $("#cheats").textContent =
                active.length
                    ? active.join("  ")
                    : "CHEATS OFF";

        }

    }


    // --------------------------------------------------------
    // 생존자
    // --------------------------------------------------------

    const players =
        state.players || [];

    const aliveA =
        players.filter(
            (p) =>
                p.team === 0 &&
                p.hp > 0
        ).length;

    const aliveB =
        players.filter(
            (p) =>
                p.team === 1 &&
                p.hp > 0
        ).length;


    if ($("#alive")) {

        $("#alive").textContent =
            `A ${aliveA}  —  ${aliveB} B`;

    }

}


// ============================================================
// 내 플레이어
// ============================================================

function getMe() {

    if (!state || !myId) {
        return null;
    }

    return (
        state.players || []
    ).find(
        (p) => p.id === myId
    ) || null;

}


// ============================================================
// 치트
// ============================================================

function sendCheats() {

    const message = {
        type: "cheats"
    };

    $$("[data-cheat]").forEach(
        (element) => {

            const cheat =
                element.dataset.cheat;

            if (!cheat) return;

            if (
                element.tagName === "INPUT"
            ) {

                message[cheat] =
                    element.checked;

            } else if (
                element.tagName === "BUTTON"
            ) {

                message[cheat] =
                    element.classList.contains(
                        "active"
                    );

            }

        }
    );

    send(message);

}


// ============================================================
// 치트 입력
// ============================================================

$$("[data-cheat]").forEach(
    (element) => {

        element.addEventListener(
            "change",
            () => {

                if (
                    element.tagName ===
                    "BUTTON"
                ) {

                    element.classList.toggle(
                        "active"
                    );

                }

                sendCheats();

            }
        );

    }
);


// ============================================================
// PC 키보드
// ============================================================

window.addEventListener(
    "keydown",
    (event) => {

        keys[event.code] = true;

        if (
            event.code === "Space"
        ) {

            firing = true;

        }

    }
);


window.addEventListener(
    "keyup",
    (event) => {

        keys[event.code] = false;

        if (
            event.code === "Space"
        ) {

            firing = false;

        }

    }
);


// ============================================================
// PC 마우스
// ============================================================

canvas.addEventListener(
    "mousedown",
    (event) => {

        if (
            event.button === 0
        ) {

            firing = true;

        }

    }
);


window.addEventListener(
    "mouseup",
    () => {

        firing = false;

    }
);


canvas.addEventListener(
    "mousemove",
    (event) => {

        if (
            document.pointerLockElement ===
            canvas
        ) {

            const turn =
                event.movementX *
                0.004 *
                sensitivity;

            yaw += turn;

            send({
                type: "look",
                angle: getServerAngle()
            });

        }

    }
);


canvas.addEventListener(
    "click",
    () => {

        if (
            gameStarted &&
            canvas.requestPointerLock
        ) {

            canvas.requestPointerLock();

        }

    }
);


// ============================================================
// PC 이동
// ============================================================

function inputLoop() {

    if (
        gameStarted &&
        state
    ) {

        let x = 0;
        let y = 0;

        if (keys.KeyW) y += 1;
        if (keys.KeyS) y -= 1;
        if (keys.KeyA) x -= 1;
        if (keys.KeyD) x += 1;


        const length =
            Math.hypot(x, y);

        if (length > 1) {

            x /= length;
            y /= length;

        }


        send({
            type: "input",
            x: x,
            y: y,
            angle: getServerAngle(),
            shooting: firing
        });

    }

    requestAnimationFrame(
        inputLoop
    );

}

inputLoop();


// ============================================================
// 서버 angle
// ============================================================

function getServerAngle() {

    const me = getMe();

    if (me) {

        return me.angle + yaw;

    }

    return yaw;

}


// ============================================================
// 모바일 스틱
// ============================================================

const stick =
    $("#stick");

if (stick) {

    stick.addEventListener(
        "pointerdown",
        (event) => {

            stick.active = true;

            try {
                stick.setPointerCapture(
                    event.pointerId
                );
            } catch (_) {}

        }
    );


    stick.addEventListener(
        "pointermove",
        (event) => {

            if (!stick.active) {
                return;
            }

            const rect =
                stick.getBoundingClientRect();

            let x =
                event.clientX -
                (
                    rect.left +
                    rect.width / 2
                );

            let y =
                event.clientY -
                (
                    rect.top +
                    rect.height / 2
                );


            const max =
                Math.min(
                    45,
                    Math.hypot(x, y)
                );

            const angle =
                Math.atan2(y, x);


            x =
                Math.cos(angle) *
                max;

            y =
                Math.sin(angle) *
                max;


            const knob =
                stick.querySelector("i");

            if (knob) {

                knob.style.transform =
                    `translate(${x}px, ${y}px)`;

            }


            let moveX =
                clamp(
                    x / 45,
                    -1,
                    1
                );

            let moveY =
                clamp(
                    y / 45,
                    -1,
                    1
                );


            send({
                type: "input",
                x: moveX,
                y: -moveY,
                angle: getServerAngle(),
                shooting: firing
            });

        }
    );


    stick.addEventListener(
        "pointerup",
        stopStick
    );

    stick.addEventListener(
        "pointercancel",
        stopStick
    );

}


function stopStick() {

    if (!stick) return;

    stick.active = false;

    const knob =
        stick.querySelector("i");

    if (knob) {

        knob.style.transform = "";

    }

    send({
        type: "input",
        x: 0,
        y: 0,
        angle: getServerAngle(),
        shooting: firing
    });

}


// ============================================================
// 모바일 조준
// ============================================================

const look =
    $("#look");

if (look) {

    look.addEventListener(
        "pointerdown",
        (event) => {

            lastTouchX =
                event.clientX;

            try {

                look.setPointerCapture(
                    event.pointerId
                );

            } catch (_) {}

        }
    );


    look.addEventListener(
        "pointermove",
        (event) => {

            if (
                lastTouchX === null
            ) {
                return;
            }

            const dx =
                event.clientX -
                lastTouchX;

            lastTouchX =
                event.clientX;


            yaw +=
                dx *
                0.01 *
                sensitivity;


            send({
                type: "look",
                angle: getServerAngle()
            });

        }
    );


    look.addEventListener(
        "pointerup",
        () => {

            lastTouchX = null;

        }
    );


    look.addEventListener(
        "pointercancel",
        () => {

            lastTouchX = null;

        }
    );

}


// ============================================================
// FIRE
// ============================================================

const fireButton =
    $("#fire");

if (fireButton) {

    fireButton.addEventListener(
        "pointerdown",
        () => {

            firing = true;

        }
    );


    fireButton.addEventListener(
        "pointerup",
        () => {

            firing = false;

        }
    );


    fireButton.addEventListener(
        "pointercancel",
        () => {

            firing = false;

        }
    );

}


// ============================================================
// 유틸
// ============================================================

function clamp(
    value,
    min,
    max
) {

    return Math.max(
        min,
        Math.min(
            max,
            value
        )
    );

}


// ============================================================
// Renderer
// ============================================================

let rendererStarted = false;

function startRenderer() {

    if (rendererStarted) {
        return;
    }

    rendererStarted = true;

    requestAnimationFrame(
        draw
    );

}


function draw() {

    if (!gameStarted) {

        rendererStarted = false;

        return;

    }


    const width =
        innerWidth;

    const height =
        innerHeight;


    ctx.clearRect(
        0,
        0,
        width,
        height
    );


    const me =
        getMe();


    if (!me || !state) {

        requestAnimationFrame(
            draw
        );

        return;

    }


    // --------------------------------------------------------
    // 천장
    // --------------------------------------------------------

    ctx.fillStyle =
        "#111820";

    ctx.fillRect(
        0,
        0,
        width,
        height / 2
    );


    // --------------------------------------------------------
    // 바닥
    // --------------------------------------------------------

    ctx.fillStyle =
        "#26313b";

    ctx.fillRect(
        0,
        height / 2,
        width,
        height / 2
    );


    // --------------------------------------------------------
    // 벽
    // --------------------------------------------------------

    const fov =
        Math.PI / 2.9;

    const rays =
        Math.min(
            420,
            Math.max(
                120,
                Math.floor(
                    width / 2
                )
            )
        );

    const columnWidth =
        width / rays;


    for (
        let i = 0;
        i < rays;
        i++
    ) {

        const angle =
            getServerAngle() -
            fov / 2 +
            fov *
            (
                i / rays
            );


        const distance =
            castRay(
                me.x,
                me.y,
                angle
            );


        const corrected =
            distance *
            Math.cos(
                angle -
                getServerAngle()
            );


        const wallHeight =
            Math.min(
                height * 1.5,
                height /
                (
                    corrected *
                    0.085 +
                    0.02
                )
            );


        const shade =
            Math.max(
                25,
                Math.min(
                    70,
                    75 -
                    corrected * 2
                )
            );


        ctx.fillStyle =
            `rgb(${shade},${shade + 8},${shade + 18})`;


        ctx.fillRect(
            i * columnWidth,
            (height - wallHeight) / 2,
            columnWidth + 1,
            wallHeight
        );

    }


    // --------------------------------------------------------
    // 플레이어
    // --------------------------------------------------------

    drawPlayers(
        me,
        width,
        height,
        fov
    );


    // --------------------------------------------------------
    // 사망 화면
    // --------------------------------------------------------

    if (
        me.hp <= 0 ||
        me.spectator
    ) {

        ctx.fillStyle =
            "rgba(0,0,0,.55)";

        ctx.fillRect(
            0,
            0,
            width,
            height
        );


        ctx.fillStyle =
            "#ffffff";

        ctx.font =
            "bold 30px Arial";

        ctx.textAlign =
            "center";

        ctx.fillText(
            "KNOCKED OUT",
            width / 2,
            height / 2
        );

        ctx.font =
            "16px Arial";

        ctx.fillText(
            "SPECTATING",
            width / 2,
            height / 2 + 32
        );

        ctx.textAlign =
            "left";

    }


    requestAnimationFrame(
        draw
    );

}


// ============================================================
// 플레이어 렌더링
// ============================================================

function drawPlayers(
    me,
    width,
    height,
    fov
) {

    const players =
        state.players || [];


    for (
        const player of players
    ) {

        if (
            player.id === me.id
        ) {
            continue;
        }

        if (
            player.hp <= 0
        ) {
            continue;
        }


        const dx =
            player.x -
            me.x;

        const dy =
            player.y -
            me.y;

        const dist =
            Math.hypot(
                dx,
                dy
            );


        if (dist > 35) {
            continue;
        }


        let relative =
            Math.atan2(
                dy,
                dx
            ) -
            getServerAngle();


        relative =
            Math.atan2(
                Math.sin(relative),
                Math.cos(relative)
            );


        if (
            Math.abs(relative) >
            fov / 2
        ) {

            continue;

        }


        const screenX =
            width / 2 +
            (
                Math.tan(relative) /
                Math.tan(fov / 2)
            ) *
            (
                width / 2
            );


        const size =
            Math.max(
                8,
                Math.min(
                    160,
                    180 / (dist + 0.5)
                )
            );


        const color =
            player.team === me.team
                ? "#5ac8ff"
                : "#ff5b5b";


        // 적 위치 표시
        // ESP가 켜져 있으면 벽 뒤에서도 표시
        const esp =
            me.cheats &&
            me.cheats.esp;


        if (
            !esp &&
            !isPotentiallyVisible(
                me,
                player
            )
        ) {

            continue;

        }


        ctx.fillStyle =
            color;


        ctx.fillRect(
            screenX - size / 2,
            height / 2 - size,
            size,
            size
        );


        ctx.fillStyle =
            "#ffffff";

        ctx.font =
            "12px Arial";

        ctx.textAlign =
            "center";


        ctx.fillText(
            `${player.name} ${player.hp}`,
            screenX,
            height / 2 -
            size -
            8
        );


        ctx.textAlign =
            "left";

    }

}


// ============================================================
// 간단 시야 체크
// ============================================================

function isPotentiallyVisible(
    me,
    player
) {

    // 같은 팀은 표시
    if (
        me.team === player.team
    ) {
        return true;
    }

    // 기본적으로 게임 서버 위치를 사용한다.
    // 실제 벽 판정은 렌더링 단계에서 제한한다.
    return true;

}


// ============================================================
// Raycast
// ============================================================

function castRay(
    x,
    y,
    angle
) {

    const dx =
        Math.cos(angle);

    const dy =
        Math.sin(angle);

    let distance = 0;

    while (
        distance < 40
    ) {

        distance += 0.05;

        const px =
            x +
            dx *
            distance;

        const py =
            y +
            dy *
            distance;


        if (
            wallAt(
                px,
                py
            )
        ) {

            break;

        }

    }

    return distance;

}


// ============================================================
// 맵
// ============================================================

const stateMap = [
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
].map(
    row => [...row]
);


function wallAt(
    x,
    y
) {

    // 서버 좌표계를 맵 중앙에 맞춤
    const mx =
        Math.floor(
            x +
            stateMap[0].length / 2
        );

    const my =
        Math.floor(
            y +
            stateMap.length / 2
        );


    if (
        my < 0 ||
        my >= stateMap.length ||
        mx < 0 ||
        mx >= stateMap[0].length
    ) {

        return true;

    }


    return (
        stateMap[my][mx] === "1"
    );

}


// ============================================================
// 결과
// ============================================================

function finishMatch() {

    if (!state) return;

    show(result);


    const me =
        getMe();


    const winsA =
        Number(
            state.roundWins?.["0"] || 0
        );

    const winsB =
        Number(
            state.roundWins?.["1"] || 0
        );


    const winner =
        state.matchWinner;


    let title =
        "MATCH COMPLETE";


    if (
        winner !== null &&
        winner !== undefined
    ) {

        if (
            winner === myTeam
        ) {

            title =
                "VICTORY";

        } else {

            title =
                "DEFEAT";

        }

    }


    if ($("#resultTitle")) {

        $("#resultTitle").textContent =
            title;

    }


    if ($("#resultStats")) {

        $("#resultStats").innerHTML =
            `
            최종 스코어
            <b>${winsA}:${winsB}</b>
            <br>
            킬 ${me?.kills || 0}
            /
            데스 ${me?.deaths || 0}
            `;

    }


    gameStarted = false;

}


// ============================================================
// 다시하기
// ============================================================

if ($("#again")) {

    $("#again").onclick = () => {

        location.reload();

    };

}


if ($("#home")) {

    $("#home").onclick = () => {

        location.reload();

    };

}


// ============================================================
// 연결 오류
// ============================================================

function showConnectionError(
    message
) {

    console.error(
        "[CHEAT FPS]",
        message
    );


    if ($("#ready")) {

        $("#ready").disabled = false;

        $("#ready").textContent =
            "다시 전투 참가";

    }


    if ($("#modeText")) {

        $("#modeText").textContent =
            message;

    }

}


// ============================================================
// 초기 상태
// ============================================================

show(menu);