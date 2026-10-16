#!/usr/bin/env python3
"""
platform_api.py — Chapter 13, Listing 13-5
AIOps platform REST API and WebSocket event stream.

Author : Balaramakrishna Alti
GitHub : https://github.com/balaramaa/ansible-aiops-playbook

Usage:
    pip3 install fastapi uvicorn[standard] redis pydantic
    uvicorn platform_api:app --host 0.0.0.0 --port 8080 --reload

    # API documentation: http://localhost:8080/docs
    # Health check:      curl http://localhost:8080/health
    # Publish event:     curl -X POST http://localhost:8080/api/v1/events -d '...'
    # Fleet status:      curl http://localhost:8080/api/v1/fleet/status
"""

import asyncio, json, logging, os, subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, WebSocket, HTTPException, BackgroundTasks, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from event_bus import EventBus

log = logging.getLogger(__name__)

# ── App setup ─────────────────────────────────────────────────────────────────
app = FastAPI(
    title       = "AIOps Platform API",
    description = (
        "Unified REST API for the Ansible AIOps platform. "
        "Provides event publishing, remediation triggering, fleet status, "
        "and real-time event streaming via WebSocket."
    ),
    version  = "1.0.0",
    docs_url = "/docs",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize event bus (mock if Redis unavailable)
bus = EventBus()


# ── Request/Response models ───────────────────────────────────────────────────
class EventRequest(BaseModel):
    event_type:     str   = Field(..., example="alert")
    hostname:       str   = Field(..., example="node01.company.com")
    severity:       str   = Field("medium", example="critical")
    payload:        dict  = Field({}, example={"alert_name": "HighMemoryUsage"})
    source:         str   = Field("api", example="prometheus")
    environment:    str   = Field("unknown", example="production")
    auto_remediate: bool  = Field(True)


class RemediationRequest(BaseModel):
    hostname:   str  = Field(..., example="node01")
    playbook:   str  = Field(..., example="playbooks/remediate_memory.yml")
    extra_vars: dict = Field({})
    dry_run:    bool = Field(True)


class EventResponse(BaseModel):
    event_id: str
    status:   str = "published"


# ── Health endpoint ───────────────────────────────────────────────────────────
@app.get("/health", tags=["Platform"])
async def health():
    """Platform health check — returns status and event bus metrics."""
    return {
        "status":         "healthy",
        "version":        "1.0.0",
        "timestamp":      datetime.now(timezone.utc).isoformat(),
        "event_bus":      "connected" if not bus.mock else "mock",
        "pending_events": bus.get_pending_count(),
        "stream_length":  bus.stream_length(),
    }


# ── Events ────────────────────────────────────────────────────────────────────
@app.post("/api/v1/events", response_model=EventResponse, tags=["Events"])
async def publish_event(event: EventRequest):
    """
    Publish an event to the AIOps event bus.
    The AI decision engine will process and respond to the event.
    """
    event_id = bus.publish(
        event_type=     event.event_type,
        hostname=       event.hostname,
        severity=       event.severity,
        payload=        event.payload,
        source=         event.source,
        environment=    event.environment,
        auto_remediate= event.auto_remediate,
    )
    return {"event_id": event_id, "status": "published"}


@app.get("/api/v1/events/pending", tags=["Events"])
async def pending_events():
    """Return count of unprocessed events waiting in the event bus."""
    return {
        "pending": bus.get_pending_count(),
        "total":   bus.stream_length(),
    }


# ── Remediation ───────────────────────────────────────────────────────────────
@app.post("/api/v1/remediate", tags=["Remediation"])
async def trigger_remediation(
        request:          RemediationRequest,
        background_tasks: BackgroundTasks):
    """
    Trigger an Ansible remediation playbook directly via the platform.
    Runs asynchronously in the background. Use dry_run=true to preview.
    """
    cmd = [
        "ansible-playbook",
        "-i", os.environ.get("ANSIBLE_INVENTORY", "inventory/"),
        "--limit", request.hostname,
        "-e", json.dumps(request.extra_vars),
        request.playbook,
    ]
    if request.dry_run:
        cmd += ["--check", "--diff"]

    background_tasks.add_task(_run_async, cmd)
    return {
        "status":   "triggered",
        "playbook": request.playbook,
        "hostname": request.hostname,
        "dry_run":  request.dry_run,
        "command":  " ".join(cmd),
    }


# ── Fleet status ──────────────────────────────────────────────────────────────
@app.get("/api/v1/fleet/status", tags=["Fleet"])
async def fleet_status():
    """Return current fleet health summary from audit logs."""
    today     = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    audit_log = Path("/var/log/self_healing_audit.log")
    healed = escalated = 0

    if audit_log.exists():
        for line in audit_log.read_text().splitlines():
            if today not in line:
                continue
            if "SUCCESS" in line:  healed    += 1
            if "ESCALAT" in line:  escalated += 1

    total = healed + escalated
    return {
        "date":               today,
        "auto_healed_today":  healed,
        "escalated_today":    escalated,
        "auto_resolve_rate":  f"{healed/max(total,1)*100:.1f}%",
        "pending_events":     bus.get_pending_count(),
        "platform_status":    "operational",
    }


@app.get("/api/v1/fleet/compliance", tags=["Fleet"])
async def fleet_compliance():
    """Return latest compliance scores from OpenSCAP reports."""
    import glob, xml.etree.ElementTree as ET

    scores   = {}
    scan_dir = Path("/var/log/compliance")
    if not scan_dir.exists():
        return {"message": "No compliance data found", "scores": {}}

    for report_file in sorted(scan_dir.glob("results-*.xml"))[-20:]:
        try:
            tree = ET.parse(report_file)
            root = tree.getroot()
            ns   = {"x": "http://checklists.nist.gov/xccdf/1.2"}
            hostname_el = root.find(".//x:target", ns)
            score_el    = root.find(".//x:score", ns)
            if hostname_el is not None and score_el is not None:
                scores[hostname_el.text] = round(float(score_el.text), 2)
        except Exception:
            continue

    avg = sum(scores.values()) / max(len(scores), 1) if scores else 0
    return {
        "host_count":      len(scores),
        "average_score":   round(avg, 2),
        "below_90pct":     sum(1 for s in scores.values() if s < 90),
        "below_95pct":     sum(1 for s in scores.values() if s < 95),
        "scores":          scores,
    }


# ── Platform metrics ──────────────────────────────────────────────────────────
@app.get("/api/v1/metrics", tags=["Platform"])
async def platform_metrics(days: int = Query(30, ge=1, le=365)):
    """Return platform-wide AIOps operational intelligence metrics."""
    from platform_metrics import compute_platform_metrics
    return compute_platform_metrics(days=days)


# ── WebSocket event stream ─────────────────────────────────────────────────────
@app.websocket("/ws/events")
async def websocket_event_stream(ws: WebSocket):
    """
    Real-time AIOps event stream via WebSocket.
    Streams all platform events as JSON objects.

    Connect with: wscat -c ws://localhost:8080/ws/events
    """
    await ws.accept()
    log.info("WebSocket client connected to event stream")
    try:
        loop = asyncio.get_event_loop()
        for event in bus.subscribe("ws-stream-client", block_ms=1000):
            await ws.send_json(event)
            await asyncio.sleep(0)  # Yield to event loop
    except Exception as e:
        log.info(f"WebSocket client disconnected: {e}")
    finally:
        try:
            await ws.close()
        except Exception:
            pass


# ── Background task helper ─────────────────────────────────────────────────────
async def _run_async(cmd: list) -> None:
    """Run a subprocess command asynchronously."""
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        log.error(f"Background task failed (rc={proc.returncode}): "
                  f"{stderr.decode()[:300]}")
    else:
        log.info(f"Background task completed: {cmd[1]}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "platform_api:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8080)),
        reload=True,
        log_level="info",
    )
