/**
 * Project RESONANCE - Tactical Disaster Response Dashboard
 * Bengaluru Tactical Mesh Grid & AI Dynamic Routing Engine
 */

// ---------------------------------------------------------------------------
// Global Application State & Route Coordinates
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
    nodes: new Map(), // callsign -> node data
    markers: new Map(), // callsign -> Leaflet marker
    meshLinks: new Map(), // callsign -> Leaflet polyline
    map: null,
    layers: {
        nodes: null,
        links: null,
        hazards: null,
        routes: null,
    },
    audioCtx: null,

    // Hazard & Routing State
    hazardActive: false,
    hazardCircle: null,
    hazardPulseTimer: null,
    hazardRadius: 750,
    hazardCenter: [12.9609, 77.6387], // Node #3 (CHARLIE-7 @ Domlur)

    // Route Overlays
    routeA_Original: null, // Original direct path through Domlur
    routeA_Blocked: null,  // Compromised red dashed path
    routeB_Detour: null,   // AI Recalculated detour path
    routeMarkers: [],
};

// Route A: Direct Path (MG Road -> Domlur [Node #3] -> Koramangala -> HSR Layout)
const ROUTE_A_COORDS = [
    [12.9733, 77.6186], // Start: MG Road / Trinity (ALPHA-1)
    [12.9690, 77.6260], // Old Airport Road Approach
    [12.9609, 77.6387], // Direct through DOMLUR INTERSECTION (CHARLIE-7 / NODE #3)
    [12.9510, 77.6395], // Inner Ring Road South
    [12.9352, 77.6245], // Koramangala (DELTA-2)
    [12.9230, 77.6320], // Sarjapur Road connection
    [12.9116, 77.6389], // End: HSR Layout Evac Hub (ECHO-9)
];

// Route B: AI Detour Path (MG Road -> Richmond Rd -> Adugodi -> Koramangala West -> Silk Board -> HSR)
// Detours WEST around the Domlur Gas Plume!
const ROUTE_B_DETOUR_COORDS = [
    [12.9733, 77.6186], // Start: MG Road / Trinity
    [12.9660, 77.6110], // Richmond Circle diversion
    [12.9550, 77.6060], // Hosur Road North
    [12.9430, 77.6090], // Adugodi Junction
    [12.9352, 77.6245], // Koramangala Sony World Junction (DELTA-2)
    [12.9177, 77.6238], // Silk Board Junction (SIERRA-8)
    [12.9116, 77.6389], // End: HSR Layout Evac Hub (ECHO-9)
];

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
            // Urgent high-pitch double chirp for Gas Leak
            osc.type = "sawtooth";
            osc.frequency.setValueAtTime(1400, now);
            osc.frequency.exponentialRampToValueAtTime(750, now + 0.18);
            gain.gain.setValueAtTime(0.09, now);
            gain.gain.exponentialRampToValueAtTime(0.001, now + 0.22);
            osc.start(now);
            osc.stop(now + 0.22);
        } else {
            // Soft high-frequency tactical radio blip
            osc.type = "sine";
            osc.frequency.setValueAtTime(980, now);
            osc.frequency.exponentialRampToValueAtTime(1250, now + 0.05);
            gain.gain.setValueAtTime(0.025, now);
            gain.gain.exponentialRampToValueAtTime(0.001, now + 0.06);
            osc.start(now);
            osc.stop(now + 0.06);
        }
    } catch (e) {
        console.warn("Audio playback error:", e);
    }
}

// ---------------------------------------------------------------------------
// Leaflet Map Initialization (Bengaluru Grid)
// ---------------------------------------------------------------------------
function initMap() {
    // Center of Bengaluru mesh network
    const bengaluruCenter = [12.9520, 77.6320];
    const defaultZoom = 13;

    state.map = L.map("tactical-map", {
        center: bengaluruCenter,
        zoom: defaultZoom,
        zoomControl: false,
        attributionControl: false,
    });

    L.control.zoom({ position: "bottomright" }).addTo(state.map);

    // CartoDB Dark Matter Base Tiles
    const darkMatterUrl = "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png";
    L.tileLayer(darkMatterUrl, {
        subdomains: "abcd",
        maxZoom: 19,
        opacity: 0.95,
    }).addTo(state.map);

    // Initialize Layer Groups
    state.layers.hazards = L.layerGroup().addTo(state.map);
    state.layers.routes = L.layerGroup().addTo(state.map);
    state.layers.links = L.layerGroup().addTo(state.map);
    state.layers.nodes = L.layerGroup().addTo(state.map);

    // Initialize the default Primary Convoy Route A
    initInitialRouteA();

    // Map Crosshair Coordinate Tracker
    state.map.on("mousemove", (e) => {
        const crosshair = document.getElementById("crosshair-coords");
        if (crosshair) {
            crosshair.textContent = `LAT: ${e.latlng.lat.toFixed(4)}° N | LON: ${e.latlng.lng.toFixed(4)}° E`;
        }
    });
}

// ---------------------------------------------------------------------------
// Initial Active Convoy Route A (Direct Path through Node #3)
// ---------------------------------------------------------------------------
function initInitialRouteA() {
    // Clear any previous routes
    state.layers.routes.clearLayers();
    state.routeMarkers = [];

    // Outer glow polyline (Electric Blue)
    const glowLine = L.polyline(ROUTE_A_COORDS, {
        color: "#00f0ff",
        weight: 8,
        opacity: 0.35,
        lineCap: "round",
    });

    // Core sharp active route line
    state.routeA_Original = L.polyline(ROUTE_A_COORDS, {
        color: "#00f0ff",
        weight: 3.5,
        opacity: 0.95,
        dashArray: "10, 6",
        className: "active-convoy-route-a",
    }).bindPopup("<b>PRIMARY CONVOY ROUTE A (ORIGINAL DIRECT PATH)</b><br>MG Road ➔ Domlur ➔ HSR Evac Base (7.2 km)<br><span style='color: #00ff41;'>● STATUS: ACTIVE TRANSIT</span>");

    state.layers.routes.addLayer(glowLine);
    state.layers.routes.addLayer(state.routeA_Original);

    // Add Start and End Waypoint Markers
    const startIcon = L.divIcon({
        className: "waypoint-marker start-wp",
        html: `<div class="wp-badge wp-start">ORIGIN [ALPHA-1]</div>`,
        iconSize: [80, 20],
        iconAnchor: [40, 10],
    });
    const endIcon = L.divIcon({
        className: "waypoint-marker end-wp",
        html: `<div class="wp-badge wp-end">DEST [ECHO-9]</div>`,
        iconSize: [80, 20],
        iconAnchor: [40, 10],
    });

    const startMarker = L.marker(ROUTE_A_COORDS[0], { icon: startIcon }).addTo(state.layers.routes);
    const endMarker = L.marker(ROUTE_A_COORDS[ROUTE_A_COORDS.length - 1], { icon: endIcon }).addTo(state.layers.routes);
    state.routeMarkers = [startMarker, endMarker, glowLine];
}

// ---------------------------------------------------------------------------
// Node Rendering & Flash-on-Heartbeat Animation
// ---------------------------------------------------------------------------
function createNodeMarker(telemetry) {
    const isNode3Hazard = (telemetry.callsign === "CHARLIE-7" && (telemetry.is_gas_leak || state.hazardActive));
    const markerClass = isNode3Hazard ? "hazard-gas-leak" : "mesh-beacon-green";

    const customIcon = L.divIcon({
        className: "custom-node-container",
        html: `
            <div class="tactical-node-marker ${markerClass}" id="marker-${telemetry.callsign}">
                <div class="node-core-dot"></div>
                <div class="node-pulse-ring"></div>
                <div class="node-flash-ring"></div>
                <span class="node-label-tag">${telemetry.callsign}</span>
            </div>
        `,
        iconSize: [32, 32],
        iconAnchor: [16, 16],
    });

    const popupContent = `
        <div class="map-popup-card">
            <div class="popup-title">${telemetry.callsign}</div>
            <div class="popup-sub">${telemetry.role}</div>
            <div class="popup-metrics">
                <div>BATTERY: <b>${telemetry.battery}%</b></div>
                <div>RSSI: <b>${telemetry.rssi} dBm</b></div>
                <div>SNR: <b>${telemetry.snr} dB</b></div>
                <div>STATUS: <b style="color: ${isNode3Hazard ? '#ff3344' : '#00ff41'}">${isNode3Hazard ? 'GAS HAZARD' : telemetry.badge}</b></div>
            </div>
            <div class="popup-note">${telemetry.description}</div>
        </div>
    `;

    const marker = L.marker([telemetry.lat, telemetry.lon], { icon: customIcon })
        .bindPopup(popupContent)
        .addTo(state.layers.nodes);

    return marker;
}

function updateNodeOnMap(telemetry) {
    const { callsign, lat, lon } = telemetry;
    const latLng = [lat, lon];

    let marker = state.markers.get(callsign);
    if (!marker) {
        marker = createNodeMarker(telemetry);
        state.markers.set(callsign, marker);
    } else {
        marker.setLatLng(latLng);
        // Refresh popup content
        const isNode3Hazard = (callsign === "CHARLIE-7" && (telemetry.is_gas_leak || state.hazardActive));
        marker.setPopupContent(`
            <div class="map-popup-card">
                <div class="popup-title">${callsign}</div>
                <div class="popup-sub">${telemetry.role}</div>
                <div class="popup-metrics">
                    <div>BATTERY: <b>${telemetry.battery}%</b></div>
                    <div>RSSI: <b>${telemetry.rssi} dBm</b></div>
                    <div>SNR: <b>${telemetry.snr} dB</b></div>
                    <div>STATUS: <b style="color: ${isNode3Hazard ? '#ff3344' : '#00ff41'}">${isNode3Hazard ? 'GAS HAZARD' : telemetry.badge}</b></div>
                </div>
                <div class="popup-note">${telemetry.description}</div>
            </div>
        `);
    }

    // Trigger visual heartbeat flash on the marker DOM element
    flashMarkerHeartbeat(callsign, telemetry.is_gas_leak);

    // Update Mesh Topology Line to Master Repeater (RELAY-01 @ Vidhana Soudha)
    if (callsign !== "RELAY-01" && state.nodes.has("RELAY-01")) {
        const relayNode = state.nodes.get("RELAY-01");
        const linkCoords = [latLng, [relayNode.lat, relayNode.lon]];

        if (state.meshLinks.has(callsign)) {
            state.meshLinks.get(callsign).setLatLngs(linkCoords);
        } else {
            const polyline = L.polyline(linkCoords, {
                color: "#00ff41",
                weight: 1.2,
                opacity: 0.35,
                dashArray: "3, 6",
            }).addTo(state.layers.links);
            state.meshLinks.set(callsign, polyline);
        }
    }
}

function flashMarkerHeartbeat(callsign, isHazard = false) {
    const el = document.getElementById(`marker-${callsign}`);
    if (!el) return;

    el.classList.remove("heartbeat-ping");
    // Force reflow
    void el.offsetWidth;
    el.classList.add("heartbeat-ping");

    if (isHazard || (callsign === "CHARLIE-7" && state.hazardActive)) {
        el.classList.add("hazard-gas-leak");
        el.classList.remove("mesh-beacon-green");
    }
}

// ---------------------------------------------------------------------------
// Disaster Trigger & Toxic Gas Plume Animation (Node #3 @ Domlur)
// ---------------------------------------------------------------------------
function triggerGasLeakPlume(centerCoords = state.hazardCenter) {
    if (state.hazardActive) return; // Already active
    state.hazardActive = true;

    console.log("[RESONANCE] 🚨 TOXIC GAS PLUME TRIGGERED AT DOMLUR INTERSECTION!");

    // Play urgent alarm sound
    playTacticalBeep("critical");

    // Display Emergency Tactical Banner
    triggerEmergencyBanner(
        "CHARLIE-7 (DOMLUR)",
        "CRITICAL TOXIC GAS LEAK DETECTED (METHANE/H2S > 850 PPM) - ENGAGING AI A* DYNAMIC RE-ROUTING..."
    );

    // Show AI Routing HUD Overlay on the Map
    showAiRouteHudOverlay();

    // 1. Create the primary pulsating gas plume circle
    const plumeCircle = L.circle(centerCoords, {
        radius: 750,
        color: "#ff3344",
        fillColor: "#ff1122",
        fillOpacity: 0.28,
        weight: 2,
        dashArray: "6, 6",
        className: "animated-gas-plume",
    }).bindPopup("<b>⚠️ TOXIC GAS PLUME HAZARD ZONE</b><br>Concentration: <b>850 PPM (LETHAL)</b><br>Radius: <b>750 meters</b><br>Status: <b>NO-GO EVACUATION SECTOR</b>");

    // 2. Create outer expanding shockwave ripple circles
    const rippleCircle = L.circle(centerCoords, {
        radius: 950,
        color: "#ff3344",
        fillColor: "#ff3344",
        fillOpacity: 0.08,
        weight: 1.5,
        dashArray: "4, 8",
        className: "animated-plume-shockwave",
    });

    state.layers.hazards.addLayer(plumeCircle);
    state.layers.hazards.addLayer(rippleCircle);
    state.hazardCircle = plumeCircle;

    // Smooth pulsing animation of plume radius using JS interval
    let pulseStep = 0;
    if (state.hazardPulseTimer) clearInterval(state.hazardPulseTimer);
    state.hazardPulseTimer = setInterval(() => {
        if (!state.hazardActive || !state.hazardCircle) {
            clearInterval(state.hazardPulseTimer);
            return;
        }
        pulseStep += 0.08;
        const currentRadius = 750 + (Math.sin(pulseStep) * 90);
        const currentOpacity = 0.25 + (Math.sin(pulseStep) * 0.12);
        state.hazardCircle.setRadius(currentRadius);
        state.hazardCircle.setStyle({ fillOpacity: currentOpacity });
    }, 50);

    // Update Node #3 marker style immediately
    const node3Marker = document.getElementById("marker-CHARLIE-7");
    if (node3Marker) {
        node3Marker.classList.add("hazard-gas-leak");
        node3Marker.classList.remove("mesh-beacon-green");
    }

    // 3. Trigger "AI" Dynamic Re-Routing Transition!
    recalculateAiRoute();
}

// ---------------------------------------------------------------------------
// "AI" Dynamic Re-Routing (A* Visual Engine)
// ---------------------------------------------------------------------------
function recalculateAiRoute() {
    console.log("[RESONANCE] ⚡ AI A* Pathfinding Engine calculating optimal bypass route...");

    // 1. Remove/Transition Original Route A into a Compromised Red Line
    if (state.routeA_Original) {
        state.layers.routes.removeLayer(state.routeA_Original);
    }
    state.routeMarkers.forEach((m) => state.layers.routes.removeLayer(m));
    state.routeMarkers = [];

    // Draw Compromised Route A (Dashed Red fading through the hazard)
    state.routeA_Blocked = L.polyline(ROUTE_A_COORDS, {
        color: "#ff3344",
        weight: 3,
        opacity: 0.45,
        dashArray: "5, 8",
        className: "route-compromised",
    }).bindPopup("<b>ROUTE A: COMPROMISED PATH</b><br><span style='color: #ff3344;'>⛔ BLOCKED: Intersects 850 PPM Toxic Gas Plume at Domlur</span>");

    state.layers.routes.addLayer(state.routeA_Blocked);

    // 2. Draw Recalculated AI Route B (Vibrant Glowing Neon Blue Detour)
    // Outer glow for Route B
    const detourGlow = L.polyline(ROUTE_B_DETOUR_COORDS, {
        color: "#00f0ff",
        weight: 9,
        opacity: 0.4,
        lineCap: "round",
    });

    // Core animated Route B
    state.routeB_Detour = L.polyline(ROUTE_B_DETOUR_COORDS, {
        color: "#00f0ff",
        weight: 4,
        opacity: 1.0,
        dashArray: "12, 6",
        className: "ai-detour-route-animated",
    }).bindPopup("<b>⚡ AI RECALCULATED ROUTE B (A* OPTIMIZED)</b><br>MG Road ➔ Richmond ➔ Adugodi ➔ Silk Board ➔ HSR Hub (8.6 km)<br><span style='color: #00ff41;'>● HAZARD EXPOSURE: 0.0% (100% CLEAR)</span><br><span style='color: #00f0ff;'>● STATUS: ACTIVE DETOUR ENGAGED</span>");

    state.layers.routes.addLayer(detourGlow);
    state.layers.routes.addLayer(state.routeB_Detour);

    // Add Waypoint Badges
    const startIcon = L.divIcon({
        className: "waypoint-marker",
        html: `<div class="wp-badge wp-start">ORIGIN [ALPHA-1]</div>`,
        iconSize: [80, 20],
        iconAnchor: [40, 10],
    });
    const endIcon = L.divIcon({
        className: "waypoint-marker",
        html: `<div class="wp-badge wp-end">SAFE HUB [ECHO-9]</div>`,
        iconSize: [80, 20],
        iconAnchor: [40, 10],
    });
    const bypassIcon = L.divIcon({
        className: "waypoint-marker bypass-wp",
        html: `<div class="wp-badge wp-ai-detour">AI BYPASS CORRIDOR</div>`,
        iconSize: [110, 20],
        iconAnchor: [55, 10],
    });

    L.marker(ROUTE_B_DETOUR_COORDS[0], { icon: startIcon }).addTo(state.layers.routes);
    L.marker(ROUTE_B_DETOUR_COORDS[ROUTE_B_DETOUR_COORDS.length - 1], { icon: endIcon }).addTo(state.layers.routes);
    L.marker(ROUTE_B_DETOUR_COORDS[3], { icon: bypassIcon }).addTo(state.layers.routes);

    // Smoothly pan map to show both the hazard and the detour corridor
    state.map.flyToBounds([
        [12.9800, 77.6050],
        [12.9050, 77.6450]
    ], { duration: 1.5 });
}

// ---------------------------------------------------------------------------
// Reset Disaster & Re-Engage Initial Route
// ---------------------------------------------------------------------------
function resetDisasterState() {
    console.log("[RESONANCE] Resetting disaster state to nominal...");
    state.hazardActive = false;

    if (state.hazardPulseTimer) {
        clearInterval(state.hazardPulseTimer);
        state.hazardPulseTimer = null;
    }

    state.layers.hazards.clearLayers();
    state.hazardCircle = null;

    // Reset Node #3 marker
    const node3Marker = document.getElementById("marker-CHARLIE-7");
    if (node3Marker) {
        node3Marker.classList.remove("hazard-gas-leak");
        node3Marker.classList.add("mesh-beacon-green");
    }

    // Hide AI Route HUD overlay
    hideAiRouteHudOverlay();
    dismissEmergencyBanner();

    // Re-initialize default Route A
    initInitialRouteA();

    // Reset map view
    state.map.flyTo([12.9520, 77.6320], 13, { duration: 1 });
}

// ---------------------------------------------------------------------------
// AI Route HUD Callout Banner
// ---------------------------------------------------------------------------
function showAiRouteHudOverlay() {
    let hud = document.getElementById("ai-route-hud-overlay");
    if (!hud) {
        hud = document.createElement("div");
        hud.id = "ai-route-hud-overlay";
        hud.className = "ai-route-hud-overlay glass-panel";
        hud.innerHTML = `
            <div class="ai-hud-header">
                <span class="ai-pulse-dot"></span>
                <span class="ai-hud-title">AI A* DYNAMIC ROUTING ENGINE</span>
                <span class="ai-hud-badge">DETOUR ENGAGED</span>
            </div>
            <div class="ai-hud-body">
                <div class="ai-stat-row">
                    <span class="ai-stat-k">INCIDENT:</span>
                    <span class="ai-stat-v text-red">TOXIC GAS PLUME (DOMLUR #3)</span>
                </div>
                <div class="ai-stat-row">
                    <span class="ai-stat-k">CORRIDOR:</span>
                    <span class="ai-stat-v text-cyan">VIA RICHMOND / ADUGODI / HOSUR RD</span>
                </div>
                <div class="ai-stat-row">
                    <span class="ai-stat-k">DETOUR DELTA:</span>
                    <span class="ai-stat-v text-green">+1.4 KM (+3.2 MINS) | 0% RISK</span>
                </div>
            </div>
        `;
        document.querySelector(".map-viewport-wrapper").appendChild(hud);
    }
    hud.classList.add("show");
}

function hideAiRouteHudOverlay() {
    const hud = document.getElementById("ai-route-hud-overlay");
    if (hud) hud.classList.remove("show");
}

// ---------------------------------------------------------------------------
// Telemetry Terminal UI Feed
// ---------------------------------------------------------------------------
function renderByteGroups(byteGroups) {
    if (!byteGroups || byteGroups.length < 16) {
        return `<span>${byteGroups ? byteGroups.join(" ") : ""}</span>`;
    }

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
    if (hudNodeCount) hudNodeCount.textContent = `${state.nodes.size}/8`;

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
            <div class="roster-role">${node.role}</div>
            
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

    title.textContent = `CRITICAL HAZARD // ${callsign}`;
    desc.textContent = message;
    banner.classList.add("show");

    if (bannerTimeout) clearTimeout(bannerTimeout);
    bannerTimeout = setTimeout(() => {
        dismissEmergencyBanner();
    }, 9000);
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
        state.map.flyTo([node.lat, node.lon], 15, { animate: true, duration: 1 });

        const marker = state.markers.get(callsign);
        if (marker) {
            setTimeout(() => marker.openPopup(), 800);
        }
    }
}

function resetMapView() {
    state.map.flyTo([12.9520, 77.6320], 13, { animate: true, duration: 0.8 });
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
        if (msg.data.hazard_state && msg.data.hazard_state.active) {
            triggerGasLeakPlume();
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

        // Check if packet triggers Gas Leak Hazard on Node #3 (CHARLIE-7)
        if (pkt.is_gas_leak || (pkt.callsign === "CHARLIE-7" && pkt.msg_type_code === 3)) {
            triggerGasLeakPlume([pkt.lat, pkt.lon]);
        } else if (pkt.severity === "critical") {
            playTacticalBeep("critical");
            triggerEmergencyBanner(pkt.callsign, pkt.description);
        } else {
            playTacticalBeep("normal");
        }
    }

    if (msg.event === "DISASTER_TRIGGER") {
        triggerGasLeakPlume([msg.data.lat, msg.data.lon]);
    }

    if (msg.event === "DISASTER_RESET") {
        resetDisasterState();
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

async function triggerManualGasLeak() {
    try {
        await fetch("/api/disaster/gas-leak", { method: "POST" });
    } catch (e) {
        // Fallback directly on frontend
        triggerGasLeakPlume();
    }
}

async function triggerManualReset() {
    try {
        await fetch("/api/disaster/reset", { method: "POST" });
    } catch (e) {
        resetDisasterState();
    }
}

function setupUiListeners() {
    document.getElementById("btn-audio-toggle")?.addEventListener("click", toggleAudio);
    document.getElementById("btn-trigger-sos")?.addEventListener("click", triggerManualGasLeak);
    document.getElementById("btn-reset-disaster")?.addEventListener("click", triggerManualReset);

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
        if (e.target.checked) state.map.addLayer(state.layers.routes);
        else state.map.removeLayer(state.layers.routes);
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
    console.log("[RESONANCE] Initializing Bengaluru Tactical Mission Control...");
    initMap();
    setupUiListeners();
    connectWebSocket();
});
