"""
Project RESONANCE - Tactical Disaster Response Dashboard Backend
FastAPI Nervous System: Mesh Telemetry Ingest & Real-Time WebSocket Broadcaster
City Grid: Bengaluru Tactical Crisis Coordination Matrix
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
    description="Real-time disaster response mesh telemetry backend and WebSocket broadcaster (Bengaluru Grid)",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Mesh Protocol Specifications & Bengaluru Node Mapping
# ---------------------------------------------------------------------------
PACKET_STRUCT_FORMAT = ">HBBiibbBB"
PACKET_BYTE_LENGTH = 16
PACKET_HEX_LENGTH = 32

NODE_CALLSIGNS: Dict[int, Dict[str, str]] = {
    0xA101: {"callsign": "ALPHA-1", "role": "SAR Lead (MG Road)", "team": "SAR Team Red"},
    0xB204: {"callsign": "BRAVO-4", "role": "Medical Triage (Indiranagar)", "team": "Med-Evac Unit"},
    0xC307: {"callsign": "CHARLIE-7", "role": "Toxic Gas & Env Sensor (Domlur)", "team": "Hazard Recon"},
    0xD402: {"callsign": "DELTA-2", "role": "Recon Drone UAV (Koramangala)", "team": "Airborne Relay"},
    0xE509: {"callsign": "ECHO-9", "role": "Civilian Evac Hub (HSR Layout)", "team": "Shelter Comms"},
    0xF603: {"callsign": "FOXTROT-3", "role": "Perimeter Beacon (Marathahalli)", "team": "Perimeter Unit"},
    0x0001: {"callsign": "RELAY-01", "role": "Master Repeater (Vidhana Soudha)", "team": "Backbone Gateway"},
    0x0808: {"callsign": "SIERRA-8", "role": "Logistics Relay (Silk Board)", "team": "Transit Control"},
}

MESSAGE_TYPES: Dict[int, Dict[str, str]] = {
    1: {"name": "CRITICAL_SOS", "severity": "critical", "badge": "SOS", "color": "#ff3344"},
    2: {"name": "MEDICAL_REQ", "severity": "warning", "badge": "MED", "color": "#ffb703"},
    3: {"name": "HAZARD_ALERT", "severity": "critical", "badge": "HAZARD", "color": "#ff3344"},
    4: {"name": "RESOURCE_STATUS", "severity": "info", "badge": "STATUS", "color": "#00ff41"},
    5: {"name": "BEACON_PING", "severity": "normal", "badge": "BEACON", "color": "#00ff41"},
}

DEFAULT_DESCRIPTIONS: Dict[int, List[str]] = {
    1: ["Critical distress packet intercepted", "Immediate structural evacuation required", "Emergency personnel dispatch beacon"],
    2: ["Medical supplies low - emergency trauma kits needed", "Field triage stabilization active", "Casualty transport corridor requested"],
    3: ["Hazardous gas atmospheric anomaly detected", "Air quality safety threshold exceeded", "Toxic plume dispersion vector tracking"],
    4: ["Civilian shelter resources stable", "Auxiliary power generator operating at nominal load", "Mesh uplink synchronization 100%"],
    5: ["Radio mesh node heartbeat synchronization ping", "RF signal propagation nominal across sector", "Relay routing table update verified"],
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
        "role": "Mesh Transceiver",
        "team": "Field Unit",
    })

    # Message type metadata resolution
    msg_type_info = MESSAGE_TYPES.get(msg_type_code, {
        "name": f"UNKNOWN_0x{msg_type_code:02X}",
        "severity": "info",
        "badge": "DATA",
        "color": "#00ff41",
    })

    # LoRa signal metrics
    clamped_rssi = max(-125, min(-45, rssi))
    signal_quality = int(((clamped_rssi - (-125)) / ((-45) - (-125))) * 100)

    if rssi > -70:
        signal_bars = 4
    elif rssi > -85:
        signal_bars = 3
    elif rssi > -105:
        signal_bars = 2
    else:
        signal_bars = 1

    byte_groups = [cleaned_hex[i : i + 2].upper() for i in range(0, len(cleaned_hex), 2)]
    formatted_hex = " ".join(byte_groups)

    timestamp_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    timestamp_local = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]

    # Special detection for Gas Leak on Node #3 (0xC307 / CHARLIE-7)
    is_gas_leak = False
    if node_id == 0xC307 and (msg_type_code in [1, 3] or (custom_note and "gas" in custom_note.lower())):
        is_gas_leak = True

    description = custom_note or DEFAULT_DESCRIPTIONS.get(msg_type_code, ["Standard telemetry frame"])[
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
        "severity": "critical" if is_gas_leak else msg_type_info["severity"],
        "badge": "GAS HAZARD" if is_gas_leak else msg_type_info["badge"],
        "color": "#ff3344" if is_gas_leak else msg_type_info["color"],
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
        "is_gas_leak": is_gas_leak,
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
HAZARD_STATE: Dict[str, Any] = {
    "active": False,
    "hazard_type": None,
    "node_callsign": None,
    "lat": None,
    "lon": None,
    "radius_meters": 750,
    "timestamp": None,
    "reroute_active": False,
}


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------
class TelemetryIngestRequest(BaseModel):
    hex_payload: str = Field(
        ...,
        description="16-byte raw hex payload (32 hex characters)",
        example="c307035500c5c3c004a08fc0b508022a",
    )
    note: Optional[str] = Field(
        default=None,
        description="Optional human-readable field report or sensor alert note",
    )
    gateway_id: Optional[str] = Field(
        default="GW-BENGALURU-CENTRAL",
        description="Identifier of the gateway that picked up the LoRa frame",
    )


class EmergencyBroadcastRequest(BaseModel):
    callsign: str = Field(default="CHARLIE-7", description="Node triggering emergency")
    alert_type: str = Field(default="GAS_LEAK_HAZARD", description="Alert category")
    message: str = Field(..., description="Emergency instructions or broadcast message")
    lat: Optional[float] = Field(default=12.9609, description="Target Latitude")
    lon: Optional[float] = Field(default=77.6387, description="Target Longitude")


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
        "message": "Frontend static file index.html not found.",
    })


@app.get("/api/status")
async def get_system_status():
    """Returns real-time backend operational status and network statistics."""
    uptime_sec = round(time.time() - START_TIME, 1)
    critical_count = sum(1 for node in ACTIVE_NODES.values() if node.get("severity") == "critical")

    return {
        "status": "OPERATIONAL",
        "system": "Project RESONANCE Core (Bengaluru Grid)",
        "uptime_seconds": uptime_sec,
        "total_packets_received": TOTAL_PACKETS_RECEIVED,
        "active_nodes_count": len(ACTIVE_NODES),
        "critical_alerts_count": critical_count,
        "connected_ws_clients": len(manager.active_connections),
        "hazard_state": HAZARD_STATE,
        "frequency": "433.92 MHz LoRa Mesh",
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
            gateway_id=payload.gateway_id or "GW-BENGALURU-CENTRAL",
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

    # Check if this packet triggers or maintains the gas leak hazard state
    if telemetry.get("is_gas_leak"):
        HAZARD_STATE["active"] = True
        HAZARD_STATE["hazard_type"] = "TOXIC_GAS_LEAK"
        HAZARD_STATE["node_callsign"] = callsign
        HAZARD_STATE["lat"] = telemetry["lat"]
        HAZARD_STATE["lon"] = telemetry["lon"]
        HAZARD_STATE["timestamp"] = telemetry["timestamp_local"]
        HAZARD_STATE["reroute_active"] = True

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
        "is_gas_leak": telemetry.get("is_gas_leak", False),
    }

    # Store history
    TELEMETRY_HISTORY.append(telemetry)
    if len(TELEMETRY_HISTORY) > MAX_HISTORY_SIZE:
        TELEMETRY_HISTORY.pop(0)

    # Broadcast event to all WebSocket clients
    broadcast_event = {
        "event": "TELEMETRY_PACKET",
        "data": telemetry,
        "hazard_state": HAZARD_STATE,
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
        "hazard_active": HAZARD_STATE["active"],
        "active_clients_broadcasted": len(manager.active_connections),
    }


@app.post("/api/disaster/gas-leak")
async def trigger_gas_leak_endpoint():
    """Manually triggers the gas leak disaster scenario for demo control."""
    HAZARD_STATE["active"] = True
    HAZARD_STATE["hazard_type"] = "TOXIC_GAS_LEAK"
    HAZARD_STATE["node_callsign"] = "CHARLIE-7"
    HAZARD_STATE["lat"] = 12.9609
    HAZARD_STATE["lon"] = 77.6387
    HAZARD_STATE["timestamp"] = datetime.datetime.now().strftime("%H:%M:%S")
    HAZARD_STATE["reroute_active"] = True

    event = {
        "event": "DISASTER_TRIGGER",
        "data": {
            "hazard_type": "TOXIC_GAS_LEAK",
            "callsign": "CHARLIE-7",
            "lat": 12.9609,
            "lon": 77.6387,
            "radius_meters": 750,
            "message": "CRITICAL TOXIC GAS LEAK DETECTED AT DOMLUR INTERSECTION (850 PPM) - AI RE-ROUTING ENGAGED",
            "timestamp": HAZARD_STATE["timestamp"],
        },
    }
    await manager.broadcast(event)
    return {"status": "TRIGGERED", "hazard": HAZARD_STATE}


@app.post("/api/disaster/reset")
async def reset_disaster_endpoint():
    """Resets the disaster state back to normal operational status."""
    HAZARD_STATE["active"] = False
    HAZARD_STATE["hazard_type"] = None
    HAZARD_STATE["reroute_active"] = False

    event = {
        "event": "DISASTER_RESET",
        "data": {
            "message": "DISASTER STATE CLEARED - ALL HAZARDS MITIGATED. RESTORING DEFAULT CONVOY ROUTE A.",
            "timestamp": datetime.datetime.now().strftime("%H:%M:%S"),
        },
    }
    await manager.broadcast(event)
    return {"status": "RESET_COMPLETE", "hazard": HAZARD_STATE}


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
            "hazard_state": HAZARD_STATE,
            "system_info": {
                "system": "Project RESONANCE (Bengaluru Grid)",
                "total_packets": TOTAL_PACKETS_RECEIVED,
                "uptime": round(time.time() - START_TIME, 1),
                "active_nodes_count": len(ACTIVE_NODES),
            },
        },
    }
    await websocket.send_text(json.dumps(initial_payload))

    try:
        while True:
            raw_data = await websocket.receive_text()
            try:
                msg = json.loads(raw_data)
                if msg.get("action") == "PING":
                    await websocket.send_text(json.dumps({
                        "event": "PONG",
                        "timestamp": datetime.datetime.now().isoformat(),
                    }))
                elif msg.get("action") == "TRIGGER_GAS_LEAK":
                    await trigger_gas_leak_endpoint()
                elif msg.get("action") == "RESET_HAZARD":
                    await reset_disaster_endpoint()
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
    print(" Bengaluru Tactical Mesh Grid starting on http://127.0.0.1:8000")
    print("=" * 70)
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
