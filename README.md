# Project RESONANCE 🌐⚡
> **Tactical Disaster Response Mesh Telemetry & Mission Control System**
> High-fidelity, real-time smoke-and-mirrors MVP built for rapid crisis coordination.

---

## 🧭 System Overview

**Project RESONANCE** simulates a decentralized disaster response mesh network (e.g., LoRa 433/915 MHz transceivers). Field units, search-and-rescue teams, and sensor beacons transmit 16-byte raw hex packets over RF mesh. The backend acts as the central nervous system, decoding packets in real-time and streaming them via WebSockets to a dark-mode tactical operations dashboard.

```
┌──────────────────────────────┐
│        simulator.py          │ (Simulates LoRa field transceivers)
│   • Generates 16-byte hex    │
│   • Packed struct telemetry  │
└──────────────┬───────────────┘
               │ HTTP POST /api/telemetry (Every 2s)
               ▼
┌──────────────────────────────┐
│           main.py            │ (FastAPI Nervous System)
│   • 16-byte hex decoder      │
│   • State & Ring Buffer      │
│   • WebSocket Broadcaster    │
└──────────────┬───────────────┘
               │ WebSocket /ws (JSON Real-Time Broadcast)
               ▼
┌──────────────────────────────┐
│     Mission Control UI       │ (HTML5 / CSS3 / Leaflet.js)
│   • Dark Matter Tactical Map │
│   • Live Telemetry Terminal  │
│   • Node Fleet Roster & HUD  │
└──────────────────────────────┘
```

---

## 📦 16-Byte Hex Packet Specification

Every mesh frame consists of exactly **16 bytes (32 hex characters)** packed in Big-Endian binary format (`>HBBiibbBB`):

| Offset | Length | Type | Name | Description & Scaling |
|---|---|---|---|---|
| `00 - 01` | 2 Bytes | `uint16` | `Node ID` | Transceiver hardware ID (e.g., `0xA101` = ALPHA-1, `0xB204` = BRAVO-4) |
| `02` | 1 Byte | `uint8` | `Msg Type` | `0x01`=SOS, `0x02`=Medical, `0x03`=Hazard, `0x04`=Status, `0x05`=Beacon |
| `03` | 1 Byte | `uint8` | `Battery %` | Battery level remaining `0 - 100%` |
| `04 - 07` | 4 Bytes | `int32` | `Latitude` | Scaled GPS latitude (`Lat * 1,000,000`) |
| `08 - 11` | 4 Bytes | `int32` | `Longitude` | Scaled GPS longitude (`Lon * 1,000,000`) |
| `12` | 1 Byte | `int8` | `RSSI` | Radio Signal Strength Indication (`-120` to `-45 dBm`) |
| `13` | 1 Byte | `int8` | `SNR` | Signal-to-Noise Ratio (`-15` to `+14 dB`) |
| `14` | 1 Byte | `uint8` | `Mesh Hops` | Number of mesh hops taken across repeaters |
| `15` | 1 Byte | `uint8` | `Seq Num` | Rolling sequence counter (`0 - 255`) |

---

## 🚀 Quick Start Guide

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Launch the Backend Nervous System
```bash
python main.py
```
- Mission Control UI: **[http://127.0.0.1:8000](http://127.0.0.1:8000)**
- API Docs: **[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)**
- WebSocket Endpoint: `ws://127.0.0.1:8000/ws`

### 3. Start the Hardware Mesh Simulator
In a second terminal window:
```bash
python simulator.py
```

Optional flags:
- `--interval 1.0`: Faster 1-second transmission rate
- `--burst`: Rapid randomized packet bursts for load testing

---

## 🎨 Dashboard Features

1. **CartoDB Dark Matter Tactical Map**:
   - Live pulsating node markers color-coded by priority (SOS Red, Hazard Yellow, Medical Orange, Beacon Green).
   - Real-time mesh topology links connecting field nodes to relay gateways.
   - Disaster zone overlays: Flood risk coastal polygon, seismic tremor radius, and evacuation route.
   - Click-to-focus and interactive node inspection cards.

2. **Live Radio Telemetry Scrolling Terminal**:
   - Real-time auto-scrolling terminal with pause toggle and buffer management.
   - Syntax-highlighted 16-byte raw hex representation split by protocol field chips.
   - Decoded telemetry breakdown: Coordinates, RSSI signal bars, SNR, Battery gauge, and field notes.

3. **Tactical Audio & Emergency Alerts**:
   - Web Audio API synthesizer for realistic radio chirps and high-priority distress alarms (zero external audio assets required).
   - Global emergency broadcast overlay on `CRITICAL_SOS` packet interception.
