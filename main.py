"""
Project RESONANCE - FastAPI Nervous System & LoRa Binary Ingest
Decodes 16-byte bit-packed struct payloads (<IffBBH) and broadcasts via WebSocket.
"""

import struct
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="RESONANCE Core")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Active WebSocket connections pool
conns = set()

@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    conns.add(ws)
    try:
        while True:
            await ws.receive_text()
    except (WebSocketDisconnect, Exception):
        conns.discard(ws)

async def broadcast(msg: dict):
    dead = []
    for ws in list(conns):
        try:
            await ws.send_json(msg)
        except Exception:
            dead.append(ws)
    for ws in dead:
        conns.discard(ws)

@app.post("/lora")
async def ingest_lora(req: Request):
    """Receives 16-byte raw binary payload: <IffBBH"""
    raw = await req.body()
    if len(raw) != 16:
        return JSONResponse({"err": f"Expected 16 bytes, got {len(raw)}"}, status_code=400)

    # Unpack 16-byte bit-packed binary payload
    n_id, lat, lon, g_lvl, m_stk, chk = struct.unpack('<IffBBH', raw)

    d = {
        "n_id": n_id,
        "lat": round(lat, 5),
        "lon": round(lon, 5),
        "g_lvl": g_lvl,
        "m_stk": m_stk,
        "chk": chk,
        "hex": raw.hex().upper(),
    }

    # Broadcast to all connected WebSockets
    await broadcast(d)
    return {"status": "ok", "data": d}

@app.get("/")
async def serve_index():
    return FileResponse(STATIC_DIR / "index.html")

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

if __name__ == "__main__":
    import uvicorn
    print("=" * 60)
    print(" [RESONANCE] Backend Nervous System on http://127.0.0.1:8000")
    print("=" * 60)
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
