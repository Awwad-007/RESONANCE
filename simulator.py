"""
Project RESONANCE - Minimal 16-Byte LoRa Bit-Packing Simulator
Format: <IffBBH (16 bytes) -> NodeID(4B), Lat(4B), Lon(4B), GasLvl(1B), MeshStack(1B), Checksum(2B)
"""

import random
import struct
import time
import requests

url = "http://127.0.0.1:8000/lora"

# 8 Bengaluru Nodes: (n_id, lat, lon, base_gas)
nodes = [
    (1, 12.9733, 77.6186, 12),  # MG Road (ALPHA-1)
    (2, 12.9784, 77.6408, 15),  # Indiranagar (BRAVO-4)
    (3, 12.9609, 77.6387, 85),  # Domlur (CHARLIE-7 / Gas Sensor)
    (4, 12.9352, 77.6245, 14),  # Koramangala (DELTA-2)
    (5, 12.9116, 77.6389, 10),  # HSR Hub (ECHO-9)
    (6, 12.9562, 77.7019, 18),  # Marathahalli (FOXTROT-3)
    (7, 12.9797, 77.5907, 8),   # Vidhana Soudha (RELAY-01)
    (8, 12.9177, 77.6238, 16),  # Silk Board (SIERRA-8)
]

print("=" * 60)
print(" [RESONANCE] LoRa 16-Byte Hardware Simulator Started")
print(f" Target Endpoint : {url} | Interval: 3.0s")
print("=" * 60)

i = 0
while True:
    n_id, b_lat, b_lon, b_gas = nodes[i % len(nodes)]
    i += 1

    # Add minor jitter
    lat = b_lat + random.uniform(-0.0001, 0.0001)
    lon = b_lon + random.uniform(-0.0001, 0.0001)
    g_lvl = min(255, max(0, int(b_gas + random.uniform(-3, 5))))
    m_stk = random.randint(80, 99) # Battery % / Mesh signal
    chk = random.randint(1000, 65000)

    # 16-byte Little-Endian bit-packing: <IffBBH
    pkt = struct.pack('<IffBBH', n_id, lat, lon, g_lvl, m_stk, chk)

    try:
        t0 = time.time()
        res = requests.post(url, data=pkt, headers={"Content-Type": "application/octet-stream"}, timeout=3)
        ms = int((time.time() - t0) * 1000)
        print(f"[TX] Node {n_id} | Hex: {pkt.hex().upper()} ({len(pkt)}B) | Gas: {g_lvl}ppm | Lat:{lat:.4f} Lon:{lon:.4f} | {res.status_code} ({ms}ms)")
    except Exception as e:
        print(f"[ERR] Failed to send packet for Node {n_id}: {e}")

    time.sleep(3)
