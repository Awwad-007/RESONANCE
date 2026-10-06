/**
 * Project RESONANCE - Tactical Disaster Response Dashboard
 * Frontend Core: Leaflet Dark Matter Map, WebSocket Client, Live Telemetry Terminal
 */

// ---------------------------------------------------------------------------
// Global Application State
// ---------------------------------------------------------------------------
const state = {
    ws: null,
    wsConnected: false,
    pingInterval: null,
    lastPingTimestamp: 0,
    latencyMs: 0,
    autoScroll: true,
    audioEnabled: false,
    totalPackets: 0,
    packetRate: 0,
    lastPacketTime: Date.now(),
    nodes: new Map(), // callsign -> node data
    markers: new Map(), // callsign -> Leaflet marker
    meshLinks: new Map(), // callsign -> Leaflet polyline
    map: null,
    layers: {
        nodes: null,
        links: null,
        hazards: null,
        corridors: null,
    },
    audioCtx: null,
};

// ---------------------------------------------------------------------------
// Audio Synthesizer (Zero External Dependencies)
// ---------------------------------------------------------------------------
function playTacticalBeep(type = "normal") {
    if (!state.audioEnabled) return;

    try {
        if (!state.audioCtx) {
            const AudioContext = window.AudioContext || window.webkitAudioContext;
            state.audioCtx = new AudioContext();
        }

        if (state.audioCtx.state === "suspended") {
            state.audioCtx.resume();
        }

        const ctx = state.audioCtx;
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();

        osc.connect(gain);
        gain.connect(ctx.destination);

        const now = ctx.currentTime;

        if (type === "critical") {
            // High-pitched urgent double chirp
            osc.type = "sawtooth";
            osc.frequency.setValueAtTime(1400, now);
            osc.frequency.exponentialRampToValueAtTime(800, now + 0.15);
            gain.gain.setValueAtTime(0.08, now);
            gain.gain.exponentialRampToValueAtTime(0.001, now + 0.18);
            osc.start(now);
            osc.stop(now + 0.18);
        } else {
            // Subtle soft high-frequency tactical radio blip
            osc.type = "sine";
            osc.frequency.setValueAtTime(950, now);
            osc.frequency.exponentialRampToValueAtTime(1200, now + 0.05);
            gain.gain.setValueAtTime(0.03, now);
            gain.gain.exponentialRampToValueAtTime(0.001, now + 0.06);
            osc.start(now);
            osc.stop(now + 0.06);
        }
    } catch (e) {
        console.warn("Audio playback error:", e);
    }
}

// ---------------------------------------------------------------------------
// Leaflet Map Initialization
// ---------------------------------------------------------------------------
function initMap() {
    const defaultCenter = [37.7800, -122.4100];
    const defaultZoom = 14;

    state.map = L.map("tactical-map", {
        center: defaultCenter,
        zoom: defaultZoom,
        zoomControl: false,
        attributionControl: false,
    });

    // Add custom zoom control at bottom right
    L.control.zoom({ position: "bottomright" }).addTo(state.map);

    // Tactical Military Dark Mode Map Tiles (Esri World Dark Gray Canvas - Dark Grey & Black Streets, Zero Watermark)
    const darkMapUrl = "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}";
    L.tileLayer(darkMapUrl, {
        maxZoom: 19,
        maxNativeZoom: 16,
        attribution: '&copy; <a href="https://www.esri.com/">Esri</a>, HERE, Garmin, &copy; OpenStreetMap contributors',
        className: "tactical-dark-tiles",
    }).addTo(state.map);

    // Reference labels overlay
    const darkRefUrl = "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}";
    L.tileLayer(darkRefUrl, {
        maxZoom: 19,
        maxNativeZoom: 16,
        opacity: 0.8,
        className: "tactical-dark-labels",
    }).addTo(state.map);

    // Initialize Layer Groups
    state.layers.hazards = L.layerGroup().addTo(state.map);
    state.layers.corridors = L.layerGroup().addTo(state.map);
    state.layers.links = L.layerGroup().addTo(state.map);
    state.layers.nodes = L.layerGroup().addTo(state.map);

    // Add Disaster Overlays (Flood Zone & Seismic Hotspot)
    setupDisasterOverlays();

    // Map Crosshair Coordinate Tracker
    state.map.on("mousemove", (e) => {
        const crosshair = document.getElementById("crosshair-coords");
        if (crosshair) {
            crosshair.textContent = `LAT: ${e.latlng.lat.toFixed(4)}° N | LON: ${e.latlng.lng.toFixed(4)}° W`;
        }
    });
}

function setupDisasterOverlays() {
    // 1. Coastal Flood Inundation Zone along the Embarcadero
    const floodPolygon = L.polygon([
        [37.8020, -122.3980],
        [37.7950, -122.3910],
        [37.7880, -122.3870],
        [37.7830, -122.3860],
        [37.7850, -122.3920],
        [37.7940, -122.3970],
        [37.8010, -122.4040],
    ], {
        color: "#00ff41",
        fillColor: "#00ff41",
        fillOpacity: 0.15,
        weight: 1.5,
        dashArray: "4, 6",
    }).bindPopup("<b>SECTOR 1: FLOOD RISK ZONE</b><br>Surge warning: +1.2m tidal inundation.");
    state.layers.hazards.addLayer(floodPolygon);

    // 2. Structural Seismic Tremor Zone near SOMA / Financial District
    const seismicCircle = L.circle([37.7890, -122.4020], {
        radius: 450,
        color: "#ff3344",
        fillColor: "#ff3344",
        fillOpacity: 0.12,
        weight: 1.5,
        dashArray: "6, 6",
    }).bindPopup("<b>SECTOR 4: STRUCTURAL HAZARD AREA</b><br>Unreinforced masonry collapse risk.");
    state.layers.hazards.addLayer(seismicCircle);

    // 3. Evacuation Safe Corridor to Moscone Center Shelter
    const evacRoute = L.polyline([
        [37.7930, -122.4050],
        [37.7880, -122.4030],
        [37.7840, -122.4010], // Moscone Center (ECHO-9)
    ], {
        color: "#00ff41",
        weight: 3,
        opacity: 0.9,
        dashArray: "8, 8",
    }).bindPopup("<b>CIVILIAN EVACUATION CORRIDOR</b><br>Secured path to Moscone Emergency Shelter.");
    state.layers.corridors.addLayer(evacRoute);
}

// ---------------------------------------------------------------------------
// Node Markers & Mesh Topology
// ---------------------------------------------------------------------------
function getMarkerCssClass(severity) {
    switch (severity) {
        case "critical": return "sos";
        case "warning": return "hazard";
        case "info": return "status";
        default: return "beacon";
    }
}

function updateNodeOnMap(telemetry) {
    const { callsign, lat, lon, severity, role, battery, rssi, snr, description, formatted_hex } = telemetry;

    const latLng = [lat, lon];
    const cssClass = getMarkerCssClass(severity);

    // Create custom HTML icon with glowing pulse rings
    const customIcon = L.divIcon({
        className: "custom-map-icon-wrapper",
        html: `
            <div class="custom-node-marker ${cssClass}">
                <div class="node-pin-core"></div>
                <div class="node-pin-ring"></div>
            </div>
        `,
        iconSize: [36, 36],
        iconAnchor: [18, 18],
    });

    const popupContent = `
        <div class="map-popup-card">
            <div class="popup-title">${callsign}</div>
            <div class="popup-sub">${role}</div>
            <div class="popup-metrics">
                <div>BATTERY: <b>${battery}%</b></div>
                <div>RSSI: <b>${rssi} dBm</b></div>
                <div>SNR: <b>${snr} dB</b></div>
                <div>STATUS: <b style="color: ${telemetry.color}">${telemetry.badge}</b></div>
            </div>
            <div class="popup-note">${description}</div>
        </div>
    `;

    if (state.markers.has(callsign)) {
        const marker = state.markers.get(callsign);
        marker.setLatLng(latLng);
        marker.setIcon(customIcon);
        marker.setPopupContent(popupContent);
    } else {
        const marker = L.marker(latLng, { icon: customIcon })
            .bindPopup(popupContent)
            .addTo(state.layers.nodes);
        state.markers.set(callsign, marker);
    }

    // Update Mesh Topology Line to Gateway (RELAY-01 or Hilltop Master)
    if (callsign !== "RELAY-01" && state.nodes.has("RELAY-01")) {
        const relayNode = state.nodes.get("RELAY-01");
        const relayLatLng = [relayNode.lat, relayNode.lon];
        const linkCoords = [latLng, relayLatLng];

        if (state.meshLinks.has(callsign)) {
            state.meshLinks.get(callsign).setLatLngs(linkCoords);
        } else {
            const polyline = L.polyline(linkCoords, {
                color: "#00ff41",
                weight: 1.5,
                opacity: 0.55,
                dashArray: "3, 6",
            }).addTo(state.layers.links);
            state.meshLinks.set(callsign, polyline);
        }
    }
}

// ---------------------------------------------------------------------------
// Telemetry Terminal UI Feed
// ---------------------------------------------------------------------------
function renderByteGroups(byteGroups) {
    if (!byteGroups || byteGroups.length < 16) {
        return `<span>${byteGroups ? byteGroups.join(" ") : ""}</span>`;
    }

    // 16 bytes: [0-1 Node] [2 Type] [3 Bat] [4-7 Lat] [8-11 Lon] [12 RSSI] [13 SNR] [14 Hops] [15 Seq]
    return `
        <span class="hex-b-node" title="Byte 00-01: Node ID">${byteGroups[0]} ${byteGroups[1]}</span>
        <span class="hex-b-type" title="Byte 02: Message Type">${byteGroups[2]}</span>
        <span class="hex-b-bat" title="Byte 03: Battery %">${byteGroups[3]}</span>
        <span class="hex-b-lat" title="Byte 04-07: Latitude Scaled">${byteGroups[4]} ${byteGroups[5]} ${byteGroups[6]} ${byteGroups[7]}</span>
        <span class="hex-b-lon" title="Byte 08-11: Longitude Scaled">${byteGroups[8]} ${byteGroups[9]} ${byteGroups[10]} ${byteGroups[11]}</span>
        <span class="hex-b-rf" title="Byte 12-13: RSSI & SNR">${byteGroups[12]} ${byteGroups[13]}</span>
        <span class="hex-b-mesh" title="Byte 14-15: Mesh Hops & Seq">${byteGroups[14]} ${byteGroups[15]}</span>
    `;
}

function renderSignalBars(bars) {
    return `
        <div class="signal-bars-ui">
            <span class="s-bar ${bars >= 1 ? 'active' : ''}"></span>
            <span class="s-bar ${bars >= 2 ? 'active' : ''}"></span>
            <span class="s-bar ${bars >= 3 ? 'active' : ''}"></span>
            <span class="s-bar ${bars >= 4 ? 'active' : ''}"></span>
        </div>
    `;
}

function appendTelemetryCard(telemetry) {
    const container = document.getElementById("telemetry-log-stream");
    const placeholder = document.getElementById("terminal-placeholder");
    if (placeholder) placeholder.remove();

    const card = document.createElement("div");
    card.className = `packet-card ${telemetry.severity}`;
    card.id = `card-${telemetry.id}`;
    
    // Quick click handler to focus map on this node
    card.onclick = () => focusNode(telemetry.callsign);

    const severityTagClass = `tag-${telemetry.severity}`;

    card.innerHTML = `
        <div class="packet-header">
            <div class="header-left">
                <span class="packet-time">${telemetry.timestamp_local}</span>
                <span class="node-callsign-badge">${telemetry.callsign}</span>
                <span class="priority-tag ${severityTagClass}">${telemetry.badge}</span>
            </div>
            <span class="packet-time">${telemetry.node_hex}</span>
        </div>

        <div class="packet-hex-display">
            ${renderByteGroups(telemetry.byte_groups)}
        </div>

        <div class="telemetry-grid">
            <div class="telemetry-cell">
                <span class="cell-label">POSITION</span>
                <span class="cell-value">${telemetry.lat.toFixed(4)}, ${telemetry.lon.toFixed(4)}</span>
            </div>
            <div class="telemetry-cell">
                <span class="cell-label">SIGNAL</span>
                <span class="cell-value">${telemetry.rssi} dBm ${renderSignalBars(telemetry.signal_bars)}</span>
            </div>
            <div class="telemetry-cell">
                <span class="cell-label">BATTERY</span>
                <span class="cell-value">${telemetry.battery}%</span>
            </div>
        </div>

        <div class="packet-note">
            <span class="note-bullet">▶</span>
            <span>${telemetry.description}</span>
        </div>
    `;

    container.appendChild(card);

    // Keep terminal buffer manageable (max 80 cards)
    while (container.children.length > 80) {
        container.removeChild(container.firstChild);
    }

    if (state.autoScroll) {
        container.scrollTop = container.scrollHeight;
    }
}

// ---------------------------------------------------------------------------
// Fleet Roster View (Tab 2)
// ---------------------------------------------------------------------------
function updateFleetRoster() {
    const rosterList = document.getElementById("fleet-roster-list");
    const fleetCount = document.getElementById("fleet-count");
    if (!rosterList) return;

    if (fleetCount) fleetCount.textContent = state.nodes.size;
    const hudNodeCount = document.getElementById("hud-node-count");
    if (hudNodeCount) hudNodeCount.textContent = `${state.nodes.size}/7`;

    rosterList.innerHTML = "";

    state.nodes.forEach((node) => {
        const card = document.createElement("div");
        card.className = "roster-card";
        card.onclick = () => focusNode(node.callsign);

        const batClass = node.battery < 20 ? "crit" : node.battery < 50 ? "warn" : "";

        card.innerHTML = `
            <div class="roster-top">
                <div>
                    <span class="roster-callsign">${node.callsign}</span>
                    <span class="node-callsign-badge" style="font-size: 9px; margin-left: 6px;">${node.node_hex}</span>
                </div>
                <span class="priority-tag tag-${node.severity}">${node.badge}</span>
            </div>
            <div class="roster-role">${node.role} (${node.team || 'Mesh Unit'})</div>
            
            <div class="telemetry-grid" style="margin-bottom: 0;">
                <div class="telemetry-cell">
                    <span class="cell-label">LAT / LON</span>
                    <span class="cell-value" style="font-size: 10px;">${node.lat.toFixed(4)}, ${node.lon.toFixed(4)}</span>
                </div>
                <div class="telemetry-cell">
                    <span class="cell-label">SIGNAL</span>
                    <span class="cell-value">${node.rssi} dBm</span>
                </div>
                <div class="telemetry-cell">
                    <span class="cell-label">BATTERY</span>
                    <span class="cell-value">${node.battery}%</span>
                </div>
            </div>

            <div class="battery-bar-container">
                <div class="battery-bar-fill ${batClass}" style="width: ${node.battery}%;"></div>
            </div>
        `;

        rosterList.appendChild(card);
    });
}

// ---------------------------------------------------------------------------
// Emergency Banner
// ---------------------------------------------------------------------------
let bannerTimeout = null;
function triggerEmergencyBanner(callsign, message) {
    const banner = document.getElementById("emergency-banner");
    const title = document.getElementById("banner-title");
    const desc = document.getElementById("banner-desc");

    if (!banner) return;

    title.textContent = `CRITICAL ALERT // ${callsign}`;
    desc.textContent = message;
    banner.classList.add("show");

    if (bannerTimeout) clearTimeout(bannerTimeout);
    bannerTimeout = setTimeout(() => {
        dismissEmergencyBanner();
    }, 6000);
}

function dismissEmergencyBanner() {
    const banner = document.getElementById("emergency-banner");
    if (banner) banner.classList.remove("show");
}

// ---------------------------------------------------------------------------
// Map Helper Functions
// ---------------------------------------------------------------------------
function focusNode(callsign) {
    if (state.nodes.has(callsign)) {
        const node = state.nodes.get(callsign);
        state.map.flyTo([node.lat, node.lon], 16, { animate: true, duration: 1 });

        const marker = state.markers.get(callsign);
        if (marker) {
            setTimeout(() => marker.openPopup(), 900);
        }
    }
}

function resetMapView() {
    state.map.flyTo([37.7800, -122.4100], 14, { animate: true, duration: 0.8 });
}

// ---------------------------------------------------------------------------
// WebSocket Nervous System Connection
// ---------------------------------------------------------------------------
function connectWebSocket() {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}/ws`;

    console.log(`[RESONANCE] Connecting WebSocket to ${wsUrl}...`);
    const wsBadge = document.getElementById("ws-status-badge");
    const wsText = document.getElementById("ws-status-text");

    try {
        state.ws = new WebSocket(wsUrl);

        state.ws.onopen = () => {
            state.wsConnected = true;
            if (wsBadge) {
                wsBadge.className = "connection-badge connected";
                wsText.textContent = "WS LIVE";
            }
            console.log("[RESONANCE] WebSocket Connected successfully.");

            // Start latency heartbeat ping every 5 seconds
            if (state.pingInterval) clearInterval(state.pingInterval);
            state.pingInterval = setInterval(() => {
                if (state.ws && state.ws.readyState === WebSocket.OPEN) {
                    state.lastPingTimestamp = performance.now();
                    state.ws.send(JSON.stringify({ action: "PING" }));
                }
            }, 5000);
        };

        state.ws.onmessage = (event) => {
            try {
                const message = JSON.parse(event.data);
                handleWebSocketMessage(message);
            } catch (err) {
                console.error("Failed to parse WebSocket message:", err);
            }
        };

        state.ws.onclose = () => {
            state.wsConnected = false;
            if (wsBadge) {
                wsBadge.className = "connection-badge disconnected";
                wsText.textContent = "DISCONNECTED";
            }
            if (state.pingInterval) clearInterval(state.pingInterval);
            console.warn("[RESONANCE] WebSocket closed. Retrying in 2.5s...");
            setTimeout(connectWebSocket, 2500);
        };

        state.ws.onerror = (err) => {
            console.error("[RESONANCE] WebSocket encountered error:", err);
        };
    } catch (e) {
        console.error("Failed to establish WebSocket:", e);
        setTimeout(connectWebSocket, 3000);
    }
}

function handleWebSocketMessage(msg) {
    if (msg.event === "PONG") {
        const latency = Math.round(performance.now() - state.lastPingTimestamp);
        state.latencyMs = latency;
        const latencyEl = document.getElementById("ws-latency");
        if (latencyEl) latencyEl.textContent = `${latency}ms`;
        return;
    }

    if (msg.event === "INITIAL_STATE") {
        console.log("[RESONANCE] Received initial state handshake:", msg.data);
        if (msg.data.nodes) {
            msg.data.nodes.forEach((node) => {
                state.nodes.set(node.callsign, node);
                updateNodeOnMap(node);
            });
            updateFleetRoster();
        }
        if (msg.data.recent_history) {
            msg.data.recent_history.forEach((pkt) => {
                appendTelemetryCard(pkt);
            });
        }
        return;
    }

    if (msg.event === "TELEMETRY_PACKET") {
        const pkt = msg.data;
        state.totalPackets++;

        // Update HUD Counters
        const packetCountEl = document.getElementById("hud-packet-count");
        if (packetCountEl) {
            packetCountEl.textContent = String(state.totalPackets).padStart(4, "0");
        }

        if (msg.stats) {
            const alertCountEl = document.getElementById("hud-alert-count");
            if (alertCountEl) alertCountEl.textContent = msg.stats.critical_count;
        }

        // Update Node State & Map
        state.nodes.set(pkt.callsign, pkt);
        updateNodeOnMap(pkt);
        appendTelemetryCard(pkt);
        updateFleetRoster();

        // Audio notification & Emergency Trigger
        if (pkt.severity === "critical") {
            playTacticalBeep("critical");
            triggerEmergencyBanner(pkt.callsign, pkt.description);
        } else {
            playTacticalBeep("normal");
        }
    }

    if (msg.event === "EMERGENCY_BROADCAST") {
        playTacticalBeep("critical");
        triggerEmergencyBanner(msg.data.callsign, msg.data.message);
    }
}

// ---------------------------------------------------------------------------
// Controls & Event Listeners
// ---------------------------------------------------------------------------
function switchSidebarTab(tabName) {
    const tabTelemetry = document.getElementById("tab-telemetry-view");
    const tabFleet = document.getElementById("tab-fleet-view");
    const btnTelemetry = document.getElementById("tab-btn-telemetry");
    const btnFleet = document.getElementById("tab-btn-fleet");

    if (tabName === "telemetry") {
        tabTelemetry.classList.add("active");
        tabFleet.classList.remove("active");
        btnTelemetry.classList.add("active");
        btnFleet.classList.remove("active");
    } else {
        tabTelemetry.classList.remove("active");
        tabFleet.classList.add("active");
        btnTelemetry.classList.remove("active");
        btnFleet.classList.add("active");
        updateFleetRoster();
    }
}

function toggleAutoScroll() {
    state.autoScroll = !state.autoScroll;
    const statusText = document.getElementById("autoscroll-status");
    if (statusText) {
        statusText.textContent = `SCROLL: ${state.autoScroll ? "ON" : "OFF"}`;
    }
}

function clearTelemetryLog() {
    const container = document.getElementById("telemetry-log-stream");
    if (container) {
        container.innerHTML = `
            <div class="terminal-placeholder" id="terminal-placeholder">
                <div class="placeholder-spinner"></div>
                <p class="placeholder-text">Terminal cleared. Awaiting live telemetry frames...</p>
            </div>
        `;
    }
}

function toggleAudio() {
    state.audioEnabled = !state.audioEnabled;
    const icon = document.getElementById("audio-icon");
    const btn = document.getElementById("btn-audio-toggle");

    if (icon) {
        icon.textContent = state.audioEnabled ? "🔊" : "🔇";
    }
    if (btn) {
        btn.classList.toggle("active", state.audioEnabled);
    }

    if (state.audioEnabled) {
        playTacticalBeep("normal");
    }
}

async function triggerManualSos() {
    try {
        await fetch("/api/emergency/alert", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                callsign: "ALPHA-1",
                alert_type: "MANUAL_SOS_BEACON",
                message: "Manual emergency distress beacon triggered from Mission Control HUD!",
                lat: 37.7885,
                lon: -122.4015,
            }),
        });
    } catch (e) {
        console.error("Failed to trigger SOS alert:", e);
    }
}

function setupUiListeners() {
    // Audio button
    document.getElementById("btn-audio-toggle")?.addEventListener("click", toggleAudio);

    // SOS simulation button
    document.getElementById("btn-trigger-sos")?.addEventListener("click", triggerManualSos);

    // Layer toggles
    document.getElementById("toggle-mesh-links")?.addEventListener("change", (e) => {
        if (e.target.checked) state.map.addLayer(state.layers.links);
        else state.map.removeLayer(state.layers.links);
    });

    document.getElementById("toggle-hazard-zones")?.addEventListener("change", (e) => {
        if (e.target.checked) state.map.addLayer(state.layers.hazards);
        else state.map.removeLayer(state.layers.hazards);
    });

    document.getElementById("toggle-safe-corridor")?.addEventListener("change", (e) => {
        if (e.target.checked) state.map.addLayer(state.layers.corridors);
        else state.map.removeLayer(state.layers.corridors);
    });

    // Mission Clock
    setInterval(() => {
        const now = new Date();
        const utcStr = now.toISOString().slice(11, 19) + " UTC";
        const clockEl = document.getElementById("utc-clock");
        if (clockEl) clockEl.textContent = utcStr;
    }, 1000);
}

// ---------------------------------------------------------------------------
// Application Startup
// ---------------------------------------------------------------------------
document.addEventListener("DOMContentLoaded", () => {
    console.log("[RESONANCE] Initializing Mission Control Dashboard...");
    initMap();
    setupUiListeners();
    connectWebSocket();
});
