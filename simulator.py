"""
Project RESONANCE - Mesh Network Hardware Telemetry Simulator
Bengaluru Tactical Mesh Grid & Disaster Trigger Simulator
Simulates 8 LoRa field transceivers across Bengaluru with an automated toxic gas leak trigger on Node #3.
"""

import argparse
import datetime
import math
import random
import struct
import sys
import threading
import time
from typing import Dict, List, Optional

import requests

# ---------------------------------------------------------------------------
# Simulator Configuration & Constants
# ---------------------------------------------------------------------------
DEFAULT_ENDPOINT = "http://127.0.0.1:8000/api/telemetry"
DEFAULT_INTERVAL_SEC = 2.0
TRIGGER_PACKET_COUNT = 6  # Triggers gas leak on packet #6 (~12s after launch)

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
# Simulated Bengaluru Mesh Field Nodes (8 Major Intersections)
# ---------------------------------------------------------------------------
BENGALURU_NODES_CONFIG = [
    {
        "index": 1,
        "node_id": 0xA101,
        "callsign": "ALPHA-1",
        "role": "SAR Lead (MG Road / Trinity)",
        "base_lat": 12.9733,
        "base_lon": 77.6186,
        "is_mobile": True,
        "battery": 92,
        "preferred_types": [5, 4],  # Beacon, Status
        "notes": [
            "SAR Unit Alpha deployed at MG Road metro interchange",
            "Emergency vehicle transit lane established",
            "Grid power stable across Sector 1 corridor",
            "Thermal recon sweep: zero civilian distress detected",
        ],
    },
    {
        "index": 2,
        "node_id": 0xB204,
        "callsign": "BRAVO-4",
        "role": "Medical Triage (Indiranagar)",
        "base_lat": 12.9784,
        "base_lon": 77.6408,
        "is_mobile": False,
        "battery": 88,
        "preferred_types": [5, 2],  # Beacon, Medical
        "notes": [
            "Indiranagar 100ft Field Hospital operational",
            "Triage units prepared for emergency surge",
            "Rapid response ambulance convoy on standby",
            "Medical oxygen & critical supply levels optimal",
        ],
    },
    {
        "index": 3,
        "node_id": 0xC307,
        "callsign": "CHARLIE-7",
        "role": "Toxic Gas & Env Sensor (Domlur Flyover)",
        "base_lat": 12.9609,
        "base_lon": 77.6387,
        "is_mobile": False,
        "battery": 84,
        "preferred_types": [5],  # Normal beacon -> switches to CRITICAL HAZARD on trigger
        "notes": [
            "Atmospheric particulate baseline nominal (AQI 42)",
            "Methane / H2S optical spectrometry sensor calibrated",
            "Domlur intersection traffic flow telemetry linked",
            "Air sample flow rate: 2.4 L/min standard",
        ],
    },
    {
        "index": 4,
        "node_id": 0xD402,
        "callsign": "DELTA-2",
        "role": "Recon Drone UAV (Koramangala)",
        "base_lat": 12.9352,
        "base_lon": 77.6245,
        "is_mobile": True,
        "battery": 68,
        "preferred_types": [5, 4],  # Beacon, Status
        "notes": [
            "UAV altitude 150m AGL - Sony World junction orbit",
            "FLIR infrared sensor scanning transit corridors",
            "Optical telemetry feed synced to mesh repeater",
            "Aerial wind vector: 4.2 km/h North-East",
        ],
    },
    {
        "index": 5,
        "node_id": 0xE509,
        "callsign": "ECHO-9",
        "role": "Civilian Evac Hub (HSR Layout)",
        "base_lat": 12.9116,
        "base_lon": 77.6389,
        "is_mobile": False,
        "battery": 97,
        "preferred_types": [5, 4],  # Beacon, Status
        "notes": [
            "HSR Layout Evac Shelter Base online (Capacity: 500)",
            "Emergency potable water supply: 8,500 L",
            "Satellite emergency data downlink verified",
            "Civilian check-in portal active on local Wi-Fi mesh",
        ],
    },
    {
        "index": 6,
        "node_id": 0xF603,
        "callsign": "FOXTROT-3",
        "role": "Perimeter Beacon (Marathahalli ORR)",
        "base_lat": 12.9562,
        "base_lon": 77.7019,
        "is_mobile": False,
        "battery": 79,
        "preferred_types": [5],  # Beacon
        "notes": [
            "Outer Ring Road perimeter link synchronized",
            "Secondary repeater hops routed through HAL sector",
            "Radio channel noise floor: -116 dBm",
            "Perimeter access checkpoint operational",
        ],
    },
    {
        "index": 7,
        "node_id": 0x0001,
        "callsign": "RELAY-01",
        "role": "Master Gateway (Vidhana Soudha)",
        "base_lat": 12.9797,
        "base_lon": 77.5907,
        "is_mobile": False,
        "battery": 100,
        "preferred_types": [5],  # Beacon
        "notes": [
            "Central Command High-Gain LoRa Gateway active",
            "Full-mesh packet routing tables synchronized",
            "Fiber backhaul uplink bandwidth nominal",
            "Master clock sync pulse broadcasted (UTC)",
        ],
    },
    {
        "index": 8,
        "node_id": 0x0808,
        "callsign": "SIERRA-8",
        "role": "Logistics Relay (Silk Board Junction)",
        "base_lat": 12.9177,
        "base_lon": 77.6238,
        "is_mobile": False,
        "battery": 91,
        "preferred_types": [5, 4],  # Beacon, Status
        "notes": [
            "Silk Board central transit junction link active",
            "Heavy transport emergency corridor clear",
            "RF repeater coverage verified across Hosur Road",
            "Auxiliary solar battery charging active",
        ],
    },
]


class BengaluruMeshNode:
    """Simulates an individual LoRa mesh node in Bengaluru."""

    def __init__(self, config: dict):
        self.index: int = config["index"]
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
        self.is_hazardous: bool = False

    def step(self, force_hazard: bool = False) -> tuple[bytes, str, str, int]:
        """
        Advances the simulation and packs a 16-byte binary payload.
        Returns: (raw_bytes, hex_string, note, msg_type)
        """
        self.seq_num = (self.seq_num + 1) % 256

        # Slow battery degrade
        if random.random() < 0.1 and self.battery > 5:
            self.battery -= 1

        # Mobile nodes wander slightly
        if self.is_mobile:
            self.orbit_angle += 0.15
            radius = 0.0025  # ~250m radius
            self.lat = self.base_lat + (math.sin(self.orbit_angle) * radius)
            self.lon = self.base_lon + (math.cos(self.orbit_angle) * radius * 1.2)
        else:
            self.lat = self.base_lat + random.uniform(-0.00004, 0.00004)
            self.lon = self.base_lon + random.uniform(-0.00004, 0.00004)

        # Handle Hazard State for Node #3
        if force_hazard or self.is_hazardous:
            self.is_hazardous = True
            msg_type = 3  # HAZARD_ALERT
            note = "CRITICAL TOXIC GAS LEAK DETECTED (METHANE/H2S > 850 PPM) AT DOMLUR INTERSECTION - IMMEDIATE EVACUATION ORDER"
            rssi = -64
            snr = 11
        else:
            msg_type = random.choice(self.preferred_types)
            note = random.choice(self.notes)
            rssi = int(random.gauss(-76, 10))
            rssi = max(-120, min(-45, rssi))
            snr = int(random.gauss(7, 3))
            snr = max(-15, min(14, snr))

        lat_scaled = int(round(self.lat * 1_000_000))
        lon_scaled = int(round(self.lon * 1_000_000))
        hops = random.randint(1, 2)

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
        return raw_bytes, hex_payload, note, msg_type


# ---------------------------------------------------------------------------
# Main Simulation Loop
# ---------------------------------------------------------------------------
def run_simulation(endpoint: str, interval: float, auto_trigger_count: int, immediate_hazard: bool = False):
    """Runs the continuous telemetry transmission loop with automated disaster trigger."""
    nodes = [BengaluruMeshNode(cfg) for cfg in BENGALURU_NODES_CONFIG]
    node_map = {n.callsign: n for n in nodes}

    print(f"\n{BOLD}{GREEN}╔══════════════════════════════════════════════════════════════════════════╗{RESET}")
    print(f"{BOLD}{GREEN}║    PROJECT RESONANCE - BENGALURU TACTICAL MESH SIMULATOR (8 NODES)       ║{RESET}")
    print(f"{BOLD}{GREEN}╚══════════════════════════════════════════════════════════════════════════╝{RESET}")
    print(f"{DIM} Ingest Endpoint        : {endpoint}{RESET}")
    print(f"{DIM} Transmission Interval  : {interval:.1f}s | Active Nodes: {len(nodes)}{RESET}")
    print(f"{DIM} Gas Leak Trigger       : After Packet #{auto_trigger_count} (~{auto_trigger_count * interval:.0f}s) on Node #3 (CHARLIE-7 @ Domlur){RESET}")
    print(f"{DIM} Manual Trigger Key     : Press [ENTER] at any time to instantly trigger Gas Leak{RESET}\n")

    hazard_active = immediate_hazard
    if immediate_hazard:
        node_map["CHARLIE-7"].is_hazardous = True

    # Background thread to listen for manual ENTER key to trigger disaster
    def manual_trigger_listener():
        nonlocal hazard_active
        while True:
            try:
                line = sys.stdin.readline()
                if not hazard_active:
                    hazard_active = True
                    node_map["CHARLIE-7"].is_hazardous = True
                    print(f"\n{BOLD}{RED}🚨 [MANUAL TRIGGER] Gas leak initiated by operator on Node #3 (CHARLIE-7)!{RESET}\n")
            except Exception:
                break

    input_thread = threading.Thread(target=manual_trigger_listener, daemon=True)
    input_thread.start()

    packet_count = 0
    node_index = 0

    try:
        while True:
            # Pick node in round-robin order
            node = nodes[node_index % len(nodes)]
            node_index += 1
            packet_count += 1

            # Auto-trigger gas leak when packet threshold reached
            if packet_count == auto_trigger_count and not hazard_active:
                hazard_active = True
                node_map["CHARLIE-7"].is_hazardous = True
                print(f"\n{BOLD}{RED}╔══════════════════════════════════════════════════════════════════════════╗{RESET}")
                print(f"{BOLD}{RED}║  🚨 [DISASTER TRIGGERED] NODE #3 (CHARLIE-7 @ DOMLUR) DETECTED GAS LEAK  ║{RESET}")
                print(f"{BOLD}{RED}║  Broadcasting Toxic Plume Telemetry & Engaging AI A* Dynamic Detour...   ║{RESET}")
                print(f"{BOLD}{RED}╚══════════════════════════════════════════════════════════════════════════╝{RESET}\n")
                # Immediately transmit Node #3's packet
                node = node_map["CHARLIE-7"]

            # Step node
            raw_bytes, hex_payload, note, msg_type = node.step()

            byte_groups = " ".join([hex_payload[i : i + 2].upper() for i in range(0, len(hex_payload), 2)])

            payload_data = {
                "hex_payload": hex_payload,
                "note": note,
                "gateway_id": "GW-BENGALURU-CENTRAL",
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
                status_badge = f"{RED}[CONN REFUSED - Start main.py first]{RESET}"
            except Exception as e:
                status_badge = f"{RED}[ERR: {e}]{RESET}"

            # Format log line
            ts = datetime.datetime.now().strftime("%H:%M:%S")
            node_color = RED if (node.callsign == "CHARLIE-7" and hazard_active) else CYAN
            type_tag = f"{RED}[GAS HAZARD]{RESET}" if (node.callsign == "CHARLIE-7" and hazard_active) else f"{GREEN}[BEACON]{RESET}"

            print(
                f"{DIM}{ts}{RESET} "
                f"{BOLD}{BLUE}#{packet_count:04d}{RESET} "
                f"{BOLD}{node_color}[{node.callsign:^9}]{RESET} "
                f"{type_tag} "
                f"{YELLOW}{byte_groups}{RESET} "
                f"{status_badge}"
            )
            print(f"  {DIM}└─ Pos: ({node.lat:.4f}, {node.lon:.4f}) | Bat: {node.battery}% | {note}{RESET}")

            time.sleep(interval)

    except KeyboardInterrupt:
        print(f"\n{YELLOW}[!] Simulator terminated by operator. Total frames sent: {packet_count}{RESET}\n")
        sys.exit(0)


# ---------------------------------------------------------------------------
# CLI Argument Parser
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Project RESONANCE Bengaluru Mesh Network Hardware Simulator")
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
        "--trigger-count",
        type=int,
        default=TRIGGER_PACKET_COUNT,
        help=f"Packet count at which Node #3 triggers gas leak (default: {TRIGGER_PACKET_COUNT})",
    )
    parser.add_argument(
        "--hazard-now",
        action="store_true",
        help="Start with gas leak hazard immediately active",
    )
    args = parser.parse_args()

    run_simulation(
        endpoint=args.endpoint,
        interval=args.interval,
        auto_trigger_count=args.trigger_count,
        immediate_hazard=args.hazard_now,
    )
