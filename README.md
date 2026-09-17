# Cheat FPS

FastAPI + WebSocket + HTML5 Canvas 기반 3vs3 FPS 프로토타입이 아닌 실행형 프로젝트입니다.

## 기능
- AI전 / 로컬 네트워크 멀티플레이
- 3vs3, 최대 5라운드, 3선승
- 녹아웃 및 관전
- 에임핵 / ESP / 무반동 / 무한탄창 토글
- 서버 권위형 이동/사격 판정
- PC WASD + 마우스
- 모바일 가상 스틱 + 터치 조준/FIRE
- 반응형 UI

## 실행
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
브라우저에서 `http://127.0.0.1:8000`

## 같은 Wi-Fi
서버 PC의 사설 IP를 확인하고 다른 기기에서 `http://서버IP:8000` 접속합니다.
로컬 모드에서 최대 6개의 브라우저 클라이언트를 접속시킬 수 있습니다.

## Render
`render.yaml`을 그대로 사용하거나 Web Service에서:
Build: `pip install -r requirements.txt`
Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
