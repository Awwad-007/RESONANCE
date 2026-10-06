"""
Project RESONANCE - Tactical Disaster Response Dashboard Backend
FastAPI Nervous System: Mesh Telemetry Ingest & Real-Time WebSocket Broadcaster
"""

import asyncio
import datetime
import json
import logging
import struct
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import uvicorn
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Logging Configuration
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("RESONANCE.Backend")

# ---------------------------------------------------------------------------
# FastAPI Initialization & Static Directories
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title="Project RESONANCE - Mission Control Nervous System",
    description="Real-time disaster response mesh telemetry backend and WebSocket broadcaster",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Mesh Protocol Specifications & Node Mapping
# ---------------------------------------------------------------------------
# 16-byte Packet Layout (Big-Endian):
#   Offset 00-01 (2B, uint16): Node ID
#   Offset 02    (1B, uint8) : Message Type Code
#   Offset 03    (1B, uint8) : Battery Percentage (0-100)
#   Offset 04-07 (4B, int32) : Latitude * 1,000,000
#   Offset 08-11 (4B, int32) : Longitude * 1,000,000
#   Offset 12    (1B, int8)  : RSSI (dBm, signed)
#   Offset 13    (1B, int8)  : SNR (dB, signed)
#   Offset 14    (1B, uint8) : Mesh Hop Count
#   Offset 15    (1B, uint8) : Sequence Number
PACKET_STRUCT_FORMAT = ">HBBiibbBB"
PACKET_BYTE_LENGTH = 16
PACKET_HEX_LENGTH = 32

NODE_CALLSIGNS: Dict[int, Dict[str, str]] = {
    0xA101: {"callsign": "ALPHA-1", "role": "Search & Rescue Lead", "team": "SAR Team Red"},
    0xB204: {"callsign": "BRAVO-4", "role": "Medical Field Triage", "team": "Med-Evac Unit"},
    0xC307: {"callsign": "CHARLIE-7", "role": "Structural Seismic Sensor", "team": "Sensor Array"},
    0xD402: {"callsign": "DELTA-2", "role": "Airborne Recon Drone", "team": "UAV Relay"},
    0xE509: {"callsign": "ECHO-9", "role": "Civilian Evacuation Shelter", "team": "Logistics Hub"},
    0xF603: {"callsign": "FOXTROT-3", "role": "Hydrological Flood Monitor", "team": "Water Recon"},
    0x0001: {"callsign": "RELAY-01", "role": "Hilltop Mesh Gateway", "team": "Comms Relay"},
}

MESSAGE_TYPES: Dict[int, Dict[str, str]] = {
    1: {"name": "CRITICAL_SOS", "severity": "critical", "badge": "SOS", "color": "#ef4444"},
    2: {"name": "MEDICAL_REQ", "severity": "warning", "badge": "MED", "color": "#f97316"},
    3: {"name": "HAZARD_ALERT", "severity": "warning", "badge": "HAZARD", "color": "#eab308"},
    4: {"name": "RESOURCE_STATUS", "severity": "info", "badge": "STATUS", "color": "#3b82f6"},
    5: {"name": "BEACON_PING", "severity": "normal", "badge": "BEACON", "color": "#10b981"},
}

DEFAULT_DESCRIPTIONS: Dict[int, List[str]] = {
    1: ["Trapped civilian detected under rubble", "Immediate structural evacuation ordered", "Rapid distress beacon active"],
    2: ["Medical supplies low - saline & blood needed", "Triage category Red - 2 casualties", "Field surgeon dispatch requested"],
    3: ["Water level +1.2m above safe levy height", "Gas pipeline anomaly detected", "Bridge support hairline fracture recorded"],
    4: ["Shelter capacity at 82% - water supply stable", "Generator fuel level at 45%", "Satellite uplink sync operational"],
    5: ["Routine mesh relay synchronization heartbeat", "Mesh link path optimized via node hops", "Radio RF noise floor nominal"],
}


def decode_16byte_packet(raw_hex: str, custom_note: Optional[str] = None, gateway_id: str = "GW-CENTRAL") -> Dict[str, Any]:
    """Decodes a 16-byte hex payload into structured telemetry."""
    cleaned_hex = raw_hex.strip().replace(" ", "").replace("0x", "").lower()
    if len(cleaned_hex) != PACKET_HEX_LENGTH:
        raise ValueError(f"Payload must be exactly 16 bytes (32 hex characters). Got {len(cleaned_hex)} chars.")

    raw_bytes = bytes.fromhex(cleaned_hex)
    node_id, msg_type_code, battery, lat_scaled, lon_scaled, rssi, snr, hops, seq_num = struct.unpack(
        PACKET_STRUCT_FORMAT, raw_bytes
    )

    lat = lat_scaled / 1_000_000.0
    lon = lon_scaled / 1_000_000.0

    # Node metadata resolution
    node_info = NODE_CALLSIGNS.get(node_id, {
        "callsign": f"NODE-{node_id:04X}",
        "role": "Mesh Node",
        "team": "Field Unit",
    })

    # Message type metadata resolution
    msg_type_info = MESSAGE_TYPES.get(msg_type_code, {
        "name": f"UNKNOWN_0x{msg_type_code:02X}",
        "severity": "info",
        "badge": "DATA",
        "color": "#94a3b8",
    })

    # Calculate signal quality (0 - 100%)
    # Standard LoRa RSSI ranges between -120 dBm (poor) and -50 dBm (excellent)
    clamped_rssi = max(-125, min(-45, rssi))
    signal_quality = int(((clamped_rssi - (-125)) / ((-45) - (-125))) * 100)

    # Signal bar representation (1-4 bars)
    if rssi > -70:
        signal_bars = 4
    elif rssi > -85:
        signal_bars = 3
    elif rssi > -105:
        signal_bars = 2
    else:
        signal_bars = 1

    # Formatted byte breakdown for UI hex inspector
    byte_groups = [cleaned_hex[i : i + 2].upper() for i in range(0, len(cleaned_hex), 2)]
    formatted_hex = " ".join(byte_groups)

    timestamp_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    timestamp_local = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]

    # Use custom note if provided, else assign a default based on msg_type
    description = custom_note or DEFAULT_DESCRIPTIONS.get(msg_type_code, ["Standard telemetry packet received"])[
        seq_num % len(DEFAULT_DESCRIPTIONS.get(msg_type_code, ["Telemetry frame"]))
    ]

    return {
        "id": f"PKT-{int(time.time() * 1000)}-{seq_num:03d}",
        "timestamp_iso": timestamp_iso,
        "timestamp_local": timestamp_local,
        "gateway_id": gateway_id,
        "raw_hex": cleaned_hex,
        "formatted_hex": formatted_hex,
        "byte_groups": byte_groups,
        "node_id": node_id,
        "node_hex": f"0x{node_id:04X}",
        "callsign": node_info["callsign"],
        "role": node_info["role"],
        "team": node_info["team"],
        "msg_type_code": msg_type_code,
        "msg_type": msg_type_info["name"],
        "severity": msg_type_info["severity"],
        "badge": msg_type_info["badge"],
        "color": msg_type_info["color"],
        "battery": battery,
        "lat": round(lat, 6),
        "lon": round(lon, 6),
        "rssi": rssi,
        "snr": snr,
        "hops": hops,
        "seq_num": seq_num,
        "signal_quality": signal_quality,
        "signal_bars": signal_bars,
        "description": description,
    }


# ---------------------------------------------------------------------------
# Global State & Connection Manager
# ---------------------------------------------------------------------------
class ConnectionManager:
    """Manages real-time WebSocket client connections and broadcasting."""

    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        async with self._lock:
            self.active_connections.add(websocket)
        logger.info(f"WebSocket client connected. Total clients: {len(self.active_connections)}")

    async def disconnect(self, websocket: WebSocket):
        async with self._lock:
            self.active_connections.discard(websocket)
        logger.info(f"WebSocket client disconnected. Total clients: {len(self.active_connections)}")

    async def broadcast(self, message: Dict[str, Any]):
        """Broadcasts a JSON payload to all active clients safely."""
        if not self.active_connections:
            return

        payload = json.dumps(message)
        dead_connections = []

        for ws in list(self.active_connections):
            try:
                await ws.send_text(payload)
            except Exception:
                dead_connections.append(ws)

        if dead_connections:
            async with self._lock:
                for ws in dead_connections:
                    self.active_connections.discard(ws)


manager = ConnectionManager()

# Telemetry in-memory storage
START_TIME = time.time()
TOTAL_PACKETS_RECEIVED = 0
TELEMETRY_HISTORY: List[Dict[str, Any]] = []
MAX_HISTORY_SIZE = 100
ACTIVE_NODES: Dict[str, Dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------
class TelemetryIngestRequest(BaseModel):
    hex_payload: str = Field(
        ...,
        description="16-byte raw hex payload (32 hex characters)",
        example="a101015502406634f8b40738b508022a",
    )
    note: Optional[str] = Field(
        default=None,
        description="Optional human-readable field report or sensor alert note",
    )
    gateway_id: Optional[str] = Field(
        default="GW-CENTRAL",
        description="Identifier of the gateway that picked up the LoRa frame",
    )


class EmergencyBroadcastRequest(BaseModel):
    callsign: str = Field(default="ALPHA-1", description="Node triggering emergency")
    alert_type: str = Field(default="EVACUATION_ORDER", description="Alert category")
    message: str = Field(..., description="Emergency instructions or broadcast message")
    lat: Optional[float] = Field(default=37.7749, description="Target Latitude")
    lon: Optional[float] = Field(default=-122.4194, description="Target Longitude")


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------
@app.get("/")
async def serve_dashboard():
    """Serves the main Project RESONANCE frontend interface."""
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return JSONResponse({
        "status": "online",
        "system": "Project RESONANCE",
        "message": "Frontend static file index.html not found yet. Please ensure static files exist.",
    })


@app.get("/api/status")
async def get_system_status():
    """Returns real-time backend operational status and network statistics."""
    uptime_sec = round(time.time() - START_TIME, 1)
    critical_count = sum(1 for node in ACTIVE_NODES.values() if node.get("severity") == "critical")

    return {
        "status": "OPERATIONAL",
        "system": "Project RESONANCE Core",
        "uptime_seconds": uptime_sec,
        "total_packets_received": TOTAL_PACKETS_RECEIVED,
        "active_nodes_count": len(ACTIVE_NODES),
        "critical_alerts_count": critical_count,
        "connected_ws_clients": len(manager.active_connections),
        "frequency": "433.92 MHz LoRa Mesh",
        "bandwidth": "125 kHz / SF7 / CR 4/5",
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }


@app.get("/api/nodes")
async def get_active_nodes():
    """Returns the latest status table of all active mesh nodes."""
    return {
        "count": len(ACTIVE_NODES),
        "nodes": list(ACTIVE_NODES.values()),
    }


@app.get("/api/history")
async def get_telemetry_history(limit: int = 50):
    """Returns recent telemetry packet history."""
    return {
        "count": min(limit, len(TELEMETRY_HISTORY)),
        "history": TELEMETRY_HISTORY[-limit:],
    }


@app.post("/api/telemetry")
async def ingest_telemetry(payload: TelemetryIngestRequest):
    """
    Ingests a 16-byte raw hex packet from simulator or field mesh gateway,
    decodes telemetry, updates state, and broadcasts immediately via WebSocket.
    """
    global TOTAL_PACKETS_RECEIVED

    try:
        telemetry = decode_16byte_packet(
            raw_hex=payload.hex_payload,
            custom_note=payload.note,
            gateway_id=payload.gateway_id or "GW-CENTRAL",
        )
    except ValueError as err:
        logger.warning(f"Invalid telemetry payload: {err}")
        raise HTTPException(status_code=400, detail=str(err))
    except Exception as err:
        logger.error(f"Error decoding telemetry: {err}")
        raise HTTPException(status_code=500, detail=f"Decoding failure: {err}")

    # Update state
    TOTAL_PACKETS_RECEIVED += 1
    callsign = telemetry["callsign"]

    ACTIVE_NODES[callsign] = {
        "callsign": callsign,
        "node_id": telemetry["node_id"],
        "node_hex": telemetry["node_hex"],
        "role": telemetry["role"],
        "team": telemetry["team"],
        "lat": telemetry["lat"],
        "lon": telemetry["lon"],
        "battery": telemetry["battery"],
        "rssi": telemetry["rssi"],
        "snr": telemetry["snr"],
        "hops": telemetry["hops"],
        "signal_bars": telemetry["signal_bars"],
        "signal_quality": telemetry["signal_quality"],
        "severity": telemetry["severity"],
        "badge": telemetry["badge"],
        "msg_type": telemetry["msg_type"],
        "color": telemetry["color"],
        "last_seen_local": telemetry["timestamp_local"],
        "last_seen_iso": telemetry["timestamp_iso"],
        "last_description": telemetry["description"],
    }

    # Store history
    TELEMETRY_HISTORY.append(telemetry)
    if len(TELEMETRY_HISTORY) > MAX_HISTORY_SIZE:
        TELEMETRY_HISTORY.pop(0)

    # Broadcast event to all WebSocket clients
    broadcast_event = {
        "event": "TELEMETRY_PACKET",
        "data": telemetry,
        "stats": {
            "total_packets": TOTAL_PACKETS_RECEIVED,
            "active_nodes": len(ACTIVE_NODES),
            "critical_count": sum(1 for n in ACTIVE_NODES.values() if n.get("severity") == "critical"),
        },
    }
    await manager.broadcast(broadcast_event)

    return {
        "status": "ACCEPTED",
        "packet_id": telemetry["id"],
        "callsign": callsign,
        "msg_type": telemetry["msg_type"],
        "active_clients_broadcasted": len(manager.active_connections),
    }


@app.post("/api/emergency/alert")
async def trigger_emergency(alert: EmergencyBroadcastRequest):
    """Allows manual trigger of critical tactical alert on the mission map."""
    alert_packet = {
        "event": "EMERGENCY_BROADCAST",
        "data": {
            "id": f"ALERT-{int(time.time())}",
            "timestamp": datetime.datetime.now().strftime("%H:%M:%S"),
            "callsign": alert.callsign,
            "alert_type": alert.alert_type,
            "message": alert.message,
            "lat": alert.lat,
            "lon": alert.lon,
        },
    }
    await manager.broadcast(alert_packet)
    return {"status": "BROADCASTED", "alert": alert_packet}


# ---------------------------------------------------------------------------
# WebSocket Endpoint
# ---------------------------------------------------------------------------
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    Primary WebSocket link connecting the web dashboard to the backend.
    Sends initial handshake with state and streams real-time telemetry frames.
    """
    await manager.connect(websocket)

    # Send initial state handshake to client
    initial_payload = {
        "event": "INITIAL_STATE",
        "data": {
            "nodes": list(ACTIVE_NODES.values()),
            "recent_history": TELEMETRY_HISTORY[-25:],
            "system_info": {
                "system": "Project RESONANCE",
                "total_packets": TOTAL_PACKETS_RECEIVED,
                "uptime": round(time.time() - START_TIME, 1),
                "active_nodes_count": len(ACTIVE_NODES),
            },
        },
    }
    await websocket.send_text(json.dumps(initial_payload))

    try:
        while True:
            # Keep connection alive and listen for client commands / pings
            raw_data = await websocket.receive_text()
            try:
                msg = json.loads(raw_data)
                if msg.get("action") == "PING":
                    await websocket.send_text(json.dumps({
                        "event": "PONG",
                        "timestamp": datetime.datetime.now().isoformat(),
                    }))
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        await manager.disconnect(websocket)
    except Exception as err:
        logger.warning(f"WebSocket error: {err}")
        await manager.disconnect(websocket)


# Mount static assets
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# ---------------------------------------------------------------------------
# Server Entrypoint
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=" * 70)
    print(" [PROJECT RESONANCE] - Disaster Response Mission Control Server")
    print(" WebSocket Nervous System starting on http://127.0.0.1:8000")
    print("=" * 70)
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
