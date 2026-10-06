"""
Project RESONANCE - Mesh Network Hardware Telemetry Simulator
Generates 16-byte hex packets mimicking LoRa/mesh field hardware and sends them to the FastAPI server.
"""

import argparse
import datetime
import math
import random
import struct
import sys
import time
from typing import Dict, List, Optional

import requests

# ---------------------------------------------------------------------------
# Simulator Configuration & Constants
# ---------------------------------------------------------------------------
DEFAULT_ENDPOINT = "http://127.0.0.1:8000/api/telemetry"
DEFAULT_INTERVAL_SEC = 2.0

# 16-Byte Binary Format:
#   >HBBiibbBB -> NodeID(2B), MsgType(1B), Battery(1B), Lat(4B), Lon(4B), RSSI(1B), SNR(1B), Hops(1B), Seq(1B)
PACKET_STRUCT_FORMAT = ">HBBiibbBB"

# ANSI Color codes for clean terminal logging
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
MAGENTA = "\033[95m"
BLUE = "\033[94m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"

# ---------------------------------------------------------------------------
# Simulated Mesh Field Nodes
# ---------------------------------------------------------------------------
NODES_CONFIG = [
    {
        "node_id": 0xA101,
        "callsign": "ALPHA-1",
        "role": "Search & Rescue Lead",
        "base_lat": 37.7885,
        "base_lon": -122.4015,
        "is_mobile": True,
        "battery": 88,
        "preferred_types": [1, 2, 5],  # SOS, Medical, Beacon
        "notes": [
            "SAR Unit Alpha deployed inside Sector 4 rubble",
            "Thermal scanner detected 2 survivors in basement",
            "Heavy debris blocking secondary exit corridor",
            "Extraction route secured via North stairwell",
        ],
    },
    {
        "node_id": 0xB204,
        "callsign": "BRAVO-4",
        "role": "Medical Field Triage",
        "base_lat": 37.7785,
        "base_lon": -122.4178,
        "is_mobile": False,
        "battery": 94,
        "preferred_types": [2, 4, 5],  # Medical, Resources, Beacon
        "notes": [
            "Triage Alpha: 14 patients treated, 3 critical",
            "Urgent request: O-negative blood & trauma kits",
            "Field generator operating at 100% capacity",
            "Med-Evac landing zone designated and clear",
        ],
    },
    {
        "node_id": 0xC307,
        "callsign": "CHARLIE-7",
        "role": "Structural Seismic Sensor",
        "base_lat": 37.7940,
        "base_lon": -122.3960,
        "is_mobile": False,
        "battery": 76,
        "preferred_types": [3, 5],  # Hazard, Beacon
        "notes": [
            "Micro-tremor amplitude 2.8 recorded at Pier support",
            "Structural resonance vibration within safety envelope",
            "Crack displacement sensor delta: +1.4mm",
            "Tilt sensor nominal at 0.04 deg offset",
        ],
    },
    {
        "node_id": 0xD402,
        "callsign": "DELTA-2",
        "role": "Airborne Recon Drone",
        "base_lat": 37.7820,
        "base_lon": -122.4100,
        "is_mobile": True,
        "battery": 62,
        "preferred_types": [3, 4, 5],  # Hazard, Status, Beacon
        "notes": [
            "Aerial FLIR survey of Sector 2 perimeter complete",
            "Access road 101 clear for emergency vehicles",
            "Identified unmapped structural fire at warehouse 7",
            "Mesh relay link active at altitude 120m AGL",
        ],
    },
    {
        "node_id": 0xE509,
        "callsign": "ECHO-9",
        "role": "Civilian Evacuation Shelter",
        "base_lat": 37.7840,
        "base_lon": -122.4010,
        "is_mobile": False,
        "battery": 99,
        "preferred_types": [4, 5],  # Resources, Beacon
        "notes": [
            "Moscone Shelter census: 284 registered civilians",
            "Potable water reserves at 4,200 liters",
            "Satellite emergency internet uplink active",
            "Distribution of emergency ration kits underway",
        ],
    },
    {
        "node_id": 0xF603,
        "callsign": "FOXTROT-3",
        "role": "Hydrological Flood Monitor",
        "base_lat": 37.7980,
        "base_lon": -122.3920,
        "is_mobile": False,
        "battery": 82,
        "preferred_types": [3, 5],  # Hazard, Beacon
        "notes": [
            "Water level sensor: +0.65m surge above baseline",
            "Storm drain flow velocity exceeding 3.2 m/s",
            "Pumping station 4 operating at full capacity",
            "Embarcadero roadway surface water pooling detected",
        ],
    },
    {
        "node_id": 0x0001,
        "callsign": "RELAY-01",
        "role": "Twin Peaks High-Gain Gateway",
        "base_lat": 37.7544,
        "base_lon": -122.4477,
        "is_mobile": False,
        "battery": 100,
        "preferred_types": [5, 4],  # Beacon, Status
        "notes": [
            "Master LoRa mesh gateway repeater online",
            "Connected nodes in range: 6 field transceivers",
            "Radio channel 915.0 MHz noise floor: -118 dBm",
            "Backhaul fiber connection operational",
        ],
    },
]


class MeshNodeSimulator:
    """Simulates an individual LoRa field node with dynamic state."""

    def __init__(self, config: dict):
        self.node_id: int = config["node_id"]
        self.callsign: str = config["callsign"]
        self.role: str = config["role"]
        self.lat: float = config["base_lat"]
        self.lon: float = config["base_lon"]
        self.base_lat: float = config["base_lat"]
        self.base_lon: float = config["base_lon"]
        self.is_mobile: bool = config["is_mobile"]
        self.battery: int = config["battery"]
        self.preferred_types: List[int] = config["preferred_types"]
        self.notes: List[str] = config["notes"]
        self.seq_num: int = random.randint(0, 50)
        self.orbit_angle: float = random.uniform(0, 2 * math.pi)

    def step(self) -> tuple[bytes, str, str]:
        """
        Advances the node simulation state and packs a 16-byte binary payload.
        Returns: (raw_bytes, hex_string, note_description)
        """
        self.seq_num = (self.seq_num + 1) % 256

        # Slowly degrade battery
        if random.random() < 0.15 and self.battery > 5:
            self.battery -= 1

        # Mobile nodes wander slightly
        if self.is_mobile:
            self.orbit_angle += 0.12
            radius = 0.0035  # ~350 meters radius
            self.lat = self.base_lat + (math.sin(self.orbit_angle) * radius)
            self.lon = self.base_lon + (math.cos(self.orbit_angle) * radius * 1.2)
        else:
            # Stationary nodes experience tiny GPS jitter (±5 meters)
            self.lat = self.base_lat + random.uniform(-0.00005, 0.00005)
            self.lon = self.base_lon + random.uniform(-0.00005, 0.00005)

        # Pick message type
        msg_type = random.choice(self.preferred_types)

        # Scale coordinates to signed 32-bit integers
        lat_scaled = int(round(self.lat * 1_000_000))
        lon_scaled = int(round(self.lon * 1_000_000))

        # Radio metrics
        rssi = int(random.gauss(-78, 12))
        rssi = max(-120, min(-45, rssi))

        snr = int(random.gauss(6, 4))
        snr = max(-15, min(14, snr))

        hops = random.randint(1, 3)

        # 16-byte binary pack
        raw_bytes = struct.pack(
            PACKET_STRUCT_FORMAT,
            self.node_id,
            msg_type,
            self.battery,
            lat_scaled,
            lon_scaled,
            rssi,
            snr,
            hops,
            self.seq_num,
        )

        hex_payload = raw_bytes.hex()
        note = random.choice(self.notes)

        return raw_bytes, hex_payload, note


# ---------------------------------------------------------------------------
# Main Simulation Loop
# ---------------------------------------------------------------------------
def run_simulation(endpoint: str, interval: float, burst_mode: bool = False):
    """Runs the continuous telemetry transmission loop."""
    nodes = [MeshNodeSimulator(cfg) for cfg in NODES_CONFIG]

    print(f"\n{BOLD}{CYAN}╔══════════════════════════════════════════════════════════════════╗{RESET}")
    print(f"{BOLD}{CYAN}║     PROJECT RESONANCE - HARDWARE MESH SIMULATOR (LoRa 433MHz)    ║{RESET}")
    print(f"{BOLD}{CYAN}╚══════════════════════════════════════════════════════════════════╝{RESET}")
    print(f"{DIM} Target Ingest Endpoint : {endpoint}{RESET}")
    print(f"{DIM} Transmission Interval  : {interval:.1f}s | Nodes Active: {len(nodes)}{RESET}")
    print(f"{DIM} Payload Size           : 16 Bytes (32 Hex Chars){RESET}\n")

    packet_count = 0
    node_index = 0

    try:
        while True:
            # Round-robin selection of field nodes or random transmission
            node = nodes[node_index % len(nodes)]
            node_index += 1

            raw_bytes, hex_payload, note = node.step()
            packet_count += 1

            # Format byte groups for terminal output: e.g. "A1 01 01 55 02 40 ..."
            byte_groups = " ".join([hex_payload[i : i + 2].upper() for i in range(0, len(hex_payload), 2)])

            payload_data = {
                "hex_payload": hex_payload,
                "note": note,
                "gateway_id": "GW-CENTRAL-01",
            }

            send_start = time.time()
            try:
                response = requests.post(endpoint, json=payload_data, timeout=3.0)
                latency_ms = int((time.time() - send_start) * 1000)

                if response.status_code == 200:
                    status_badge = f"{GREEN}[200 OK - {latency_ms}ms]{RESET}"
                else:
                    status_badge = f"{RED}[{response.status_code} ERR]{RESET}"
            except requests.exceptions.ConnectionError:
                status_badge = f"{RED}[CONN REFUSED - Backend not running?]{RESET}"
            except Exception as e:
                status_badge = f"{RED}[ERR: {e}]{RESET}"

            # Styled console log
            ts = datetime.datetime.now().strftime("%H:%M:%S")
            print(
                f"{DIM}{ts}{RESET} "
                f"{BOLD}{BLUE}#{packet_count:04d}{RESET} "
                f"{BOLD}{MAGENTA}[{node.callsign:^8}]{RESET} "
                f"{YELLOW}{byte_groups}{RESET} "
                f"{status_badge}"
            )
            print(f"  {DIM}└─ Pos: ({node.lat:.4f}, {node.lon:.4f}) | Bat: {node.battery}% | Note: {note}{RESET}")

            # Wait for next transmission interval
            sleep_time = interval if not burst_mode else random.uniform(0.5, 1.5)
            time.sleep(sleep_time)

    except KeyboardInterrupt:
        print(f"\n{YELLOW}[!] Simulator halted by operator. Total packets generated: {packet_count}{RESET}\n")
        sys.exit(0)


# ---------------------------------------------------------------------------
# CLI Argument Parser
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Project RESONANCE Hardware Mesh Packet Simulator")
    parser.add_argument(
        "--endpoint",
        type=str,
        default=DEFAULT_ENDPOINT,
        help=f"Backend telemetry API endpoint (default: {DEFAULT_ENDPOINT})",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=DEFAULT_INTERVAL_SEC,
        help=f"Transmission interval in seconds (default: {DEFAULT_INTERVAL_SEC}s)",
    )
    parser.add_argument(
        "--burst",
        action="store_true",
        help="Enable rapid random burst mode for load testing",
    )
    args = parser.parse_args()

    run_simulation(endpoint=args.endpoint, interval=args.interval, burst_mode=args.burst)
