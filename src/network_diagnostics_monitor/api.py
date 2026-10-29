"""Monitoring REST API and responsive local dashboard."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from . import __version__
from .database import create_schema, make_engine, make_session_factory
from .incidents import acknowledge_incident, incident_duration_seconds, resolve_incident
from .models import Device, Incident, Metric
from .recommendations import recommendations_as_dicts
from .reports import build_report, render_csv, render_json, render_markdown


class AcknowledgeRequest(BaseModel):
    """Payload used to acknowledge an incident."""

    acknowledged_by: str = Field(default="technician", min_length=1, max_length=100)


DASHBOARD_HTML = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Network Diagnostics Monitor</title>
<style>
:root{color-scheme:light dark;--bg:#f4f7fb;--panel:#fff;--ink:#172033;--muted:#64748b;--line:#dce3ed;--accent:#2459d3;--danger:#b42318;--warn:#9a6700;--good:#067647}
@media(prefers-color-scheme:dark){:root{--bg:#101722;--panel:#182230;--ink:#e7edf7;--muted:#a5b2c5;--line:#334155;--accent:#8ab4ff;--danger:#ff9b91;--warn:#f4c76b;--good:#6ce0a5}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}header{padding:26px max(20px,calc((100% - 1180px)/2));background:var(--panel);border-bottom:1px solid var(--line)}h1{margin:0;font-size:clamp(1.45rem,3vw,2rem)}header p{margin:.35rem 0 0;color:var(--muted)}main{max-width:1180px;margin:24px auto;padding:0 20px}.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}.card,section{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:18px}.label{color:var(--muted);font-size:.85rem}.value{font-size:1.8rem;font-weight:700}.layout{display:grid;grid-template-columns:1.2fr 1fr;gap:16px;margin-top:16px}section h2{font-size:1.1rem;margin:0 0 14px}.toolbar{display:flex;gap:10px;flex-wrap:wrap;margin:18px 0}button,select{font:inherit;border:1px solid var(--line);border-radius:8px;padding:8px 12px;background:var(--panel);color:var(--ink)}button{cursor:pointer}button.primary{background:var(--accent);color:white;border-color:var(--accent)}button:disabled{opacity:.5;cursor:not-allowed}.table-wrap{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:.9rem}th,td{text-align:left;padding:10px 8px;border-bottom:1px solid var(--line);vertical-align:top}th{color:var(--muted);font-weight:600}.pill{display:inline-block;border-radius:99px;padding:2px 8px;font-size:.78rem;background:var(--bg);border:1px solid var(--line)}.critical,.major{color:var(--danger)}.warning{color:var(--warn)}.resolved{color:var(--good)}.muted{color:var(--muted)}.error{color:var(--danger);white-space:pre-wrap}footer{padding:20px 0;color:var(--muted);font-size:.85rem}@media(max-width:800px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}.layout{grid-template-columns:1fr}}@media(max-width:430px){.grid{grid-template-columns:1fr 1fr}.card{padding:12px}.value{font-size:1.5rem}}
</style></head>
<body><header><h1>Network Diagnostics Monitor</h1><p>Monitoring overview · simulated-first portfolio demo</p></header>
<main><div id="message" role="status" aria-live="polite" class="muted">Loading monitoring data…</div>
<div class="grid" aria-label="Monitoring summary"><div class="card"><div class="label">Devices</div><div id="devices" class="value">—</div></div><div class="card"><div class="label">Metrics recorded</div><div id="metrics" class="value">—</div></div><div class="card"><div class="label">Active incidents</div><div id="active" class="value">—</div></div><div class="card"><div class="label">Critical incidents</div><div id="critical-count" class="value">—</div></div></div>
<div class="toolbar"><button class="primary" id="refresh">Refresh data</button><label for="status-filter" class="muted">Incident status</label><select id="status-filter"><option value="">All statuses</option><option value="open">Open</option><option value="acknowledged">Acknowledged</option><option value="resolved">Resolved</option></select><a href="/docs" style="align-self:center;color:var(--accent)">API documentation</a></div>
<div class="layout"><section><h2>Device inventory</h2><div class="table-wrap"><table><thead><tr><th>Device</th><th>Type</th><th>Hostname</th><th>Mode</th></tr></thead><tbody id="device-rows"><tr><td colspan="4">Loading…</td></tr></tbody></table></div></section>
<section><h2>Incident queue</h2><div class="table-wrap"><table><thead><tr><th>Incident</th><th>Severity</th><th>Status</th><th>Actions</th></tr></thead><tbody id="incident-rows"><tr><td colspan="4">Loading…</td></tr></tbody></table></div></section></div>
<section style="margin-top:16px"><h2>Latest measurements</h2><div class="table-wrap"><table><thead><tr><th>Recorded at (UTC)</th><th>Device</th><th>Metric</th><th>Value</th><th>Status</th><th>Source</th></tr></thead><tbody id="metric-rows"><tr><td colspan="6">Loading…</td></tr></tbody></table></div></section>
<footer>Data is read from the configured local database. This dashboard does not initiate network probes or apply device changes. Synthetic measurements are not production evidence.</footer></main>
<script>
const $=id=>document.getElementById(id);const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function get(path){const r=await fetch(path,{headers:{Accept:'application/json'}});if(!r.ok)throw new Error(`${r.status} ${r.statusText}: ${await r.text()}`);return r.json()}
async function load(){ $('message').textContent='Loading monitoring data…';try{const [summary,devices,metrics]=await Promise.all([get('/api/summary'),get('/api/devices'),get('/api/metrics?limit=20')]);const status=$('status-filter').value;const incidents=await get('/api/incidents'+(status?'?status='+encodeURIComponent(status):''));$('devices').textContent=summary.device_count;$('metrics').textContent=summary.metric_count;$('active').textContent=summary.active_incident_count;$('critical-count').textContent=summary.severity_counts?.critical||0;
$('device-rows').innerHTML=devices.length?devices.map(d=>`<tr><td>${esc(d.name)}</td><td>${esc(d.device_type)}</td><td>${esc(d.hostname)}</td><td><span class="pill">${d.is_simulated?'Simulated':'Live'}</span></td></tr>`).join(''):'<tr><td colspan="4">No devices recorded. Run the seed CLI command to create demo data.</td></tr>';
$('incident-rows').innerHTML=incidents.length?incidents.map(i=>`<tr><td><strong>#${i.id} ${esc(i.title)}</strong><br><span class="muted">${esc(i.device_name)} · ${esc(i.kind)}</span>${i.is_flapping?' <span class="pill">Flapping</span>':''}</td><td class="${esc(i.severity)}">${esc(i.severity)}</td><td><span class="pill ${esc(i.status)}">${esc(i.status)}</span></td><td>${i.status!=='resolved'?`<button data-ack="${i.id}" ${i.status==='acknowledged'?'disabled':''}>Acknowledge</button> <button data-resolve="${i.id}">Resolve</button>`:'—'} <button data-rec="${i.id}">Guidance</button></td></tr>`).join(''):'<tr><td colspan="4">No incidents match this filter.</td></tr>';
$('metric-rows').innerHTML=metrics.length?metrics.map(m=>`<tr><td>${esc(m.recorded_at)}</td><td>${esc(m.device_name)}</td><td>${esc(m.name)}</td><td>${esc(m.value)} ${esc(m.unit)}</td><td>${esc(m.status)}</td><td>${esc(m.source)}</td></tr>`).join(''):'<tr><td colspan="6">No metrics recorded.</td></tr>';$('message').textContent='Data refreshed successfully.';
}catch(e){$('message').innerHTML='<span class="error">Unable to load dashboard data: '+esc(e.message)+'</span>'}}
async function action(url,body){const r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body||{})});if(!r.ok)throw new Error(await r.text());return r.json()}
document.addEventListener('click',async e=>{const b=e.target.closest('button');if(!b)return;try{if(b.dataset.ack)await action(`/api/incidents/${b.dataset.ack}/acknowledge`,{acknowledged_by:'dashboard technician'});else if(b.dataset.resolve)await action(`/api/incidents/${b.dataset.resolve}/resolve`);else if(b.dataset.rec){const d=await get(`/api/incidents/${b.dataset.rec}/recommendations`);alert(d.recommendations.map((r,n)=>`${n+1}. ${r.action}\nWhy: ${r.rationale}\nVerify: ${r.verification}`).join('\n\n'));return}else if(b.id==='refresh'){}await load()}catch(err){alert('Action failed: '+err.message)}});
$('refresh').addEventListener('click',load);$('status-filter').addEventListener('change',load);load();
</script></body></html>'''


def _device_dict(device: Device) -> dict[str, Any]:
    return {
        "id": device.id,
        "name": device.name,
        "device_type": device.device_type,
        "hostname": device.hostname,
        "location": device.location,
        "description": device.description,
        "is_simulated": device.is_simulated,
        "created_at": _iso(device.created_at),
    }


def _incident_dict(incident: Incident, now: datetime | None = None) -> dict[str, Any]:
    return {
        "id": incident.id,
        "device_id": incident.device_id,
        "device_name": incident.device.name,
        "kind": incident.kind,
        "title": incident.title,
        "description": incident.description,
        "severity": incident.severity,
        "status": incident.status,
        "started_at": _iso(incident.started_at),
        "acknowledged_at": _iso(incident.acknowledged_at),
        "acknowledged_by": incident.acknowledged_by,
        "resolved_at": _iso(incident.resolved_at),
        "duration_seconds": round(incident_duration_seconds(incident, now=now), 2),
        "occurrence_count": incident.occurrence_count,
        "last_observed_at": _iso(incident.last_observed_at),
        "is_flapping": incident.is_flapping,
    }


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def get_session(request: Request):
    """Yield a database session tied to this app instance."""
    session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()


SessionDep = Annotated[Session, Depends(get_session)]


def create_app(database_url: str | None = None) -> FastAPI:
    """Create the API and dashboard app; database URL override is useful for tests."""
    engine = make_engine(database_url)
    create_schema(engine)
    session_factory = make_session_factory(engine)
    api = FastAPI(
        title="Network Diagnostics Monitor API",
        version=__version__,
        description=(
            "Read-only monitoring inventory, metrics, incidents, recommendations, and reports. "
            "Incident lifecycle actions are available; network probes are not exposed through this API."
        ),
    )
    api.state.engine = engine
    api.state.session_factory = session_factory

    @api.get("/api/health", tags=["system"])
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "network-diagnostics-monitor", "mode": "read-only-monitoring"}

    @api.get("/api/summary", tags=["monitoring"])
    def summary(session: SessionDep) -> dict[str, Any]:
        devices = session.scalar(select(func.count(Device.id))) or 0
        simulated = session.scalar(select(func.count(Device.id)).where(Device.is_simulated.is_(True))) or 0
        metrics = session.scalar(select(func.count(Metric.id))) or 0
        incidents = session.scalars(select(Incident)).all()
        statuses = Counter(item.status for item in incidents)
        severities = Counter(item.severity for item in incidents)
        return {
            "device_count": devices,
            "simulated_device_count": simulated,
            "metric_count": metrics,
            "incident_count": len(incidents),
            "active_incident_count": sum(item.status in {"open", "acknowledged"} for item in incidents),
            "status_counts": dict(sorted(statuses.items())),
            "severity_counts": dict(sorted(severities.items())),
        }

    @api.get("/api/devices", tags=["monitoring"])
    def list_devices(session: SessionDep) -> list[dict[str, Any]]:
        return [_device_dict(item) for item in session.scalars(select(Device).order_by(Device.name)).all()]

    @api.get("/api/devices/{device_id}", tags=["monitoring"])
    def get_device(device_id: int, session: SessionDep) -> dict[str, Any]:
        device = session.get(Device, device_id)
        if device is None:
            raise HTTPException(status_code=404, detail="Device not found")
        return _device_dict(device)

    @api.get("/api/devices/{device_id}/metrics", tags=["monitoring"])
    def device_metrics(
        device_id: int,
        session: SessionDep,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
        name: str | None = None,
    ) -> list[dict[str, Any]]:
        if session.get(Device, device_id) is None:
            raise HTTPException(status_code=404, detail="Device not found")
        query = select(Metric).where(Metric.device_id == device_id).order_by(Metric.recorded_at.desc(), Metric.id.desc())
        if name:
            query = query.where(Metric.name == name)
        rows = session.scalars(query.limit(limit)).all()
        return [_metric_dict(item) for item in rows]

    @api.get("/api/metrics", tags=["monitoring"])
    def list_metrics(
        session: SessionDep,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
        device_id: int | None = None,
        name: str | None = None,
    ) -> list[dict[str, Any]]:
        query = select(Metric).options(joinedload(Metric.device)).order_by(Metric.recorded_at.desc(), Metric.id.desc())
        if device_id is not None:
            query = query.where(Metric.device_id == device_id)
        if name:
            query = query.where(Metric.name == name)
        return [_metric_dict(item) for item in session.scalars(query.limit(limit)).all()]

    @api.get("/api/incidents", tags=["incidents"])
    def list_incidents(
        session: SessionDep,
        status: Literal["open", "acknowledged", "resolved"] | None = None,
        severity: Literal["info", "warning", "major", "critical"] | None = None,
        device_id: int | None = None,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
    ) -> list[dict[str, Any]]:
        query = select(Incident).options(joinedload(Incident.device)).order_by(Incident.started_at.desc(), Incident.id.desc())
        if status:
            query = query.where(Incident.status == status)
        if severity:
            query = query.where(Incident.severity == severity)
        if device_id is not None:
            query = query.where(Incident.device_id == device_id)
        now = datetime.now(UTC)
        return [_incident_dict(item, now) for item in session.scalars(query.limit(limit)).unique().all()]

    @api.get("/api/incidents/{incident_id}", tags=["incidents"])
    def get_incident(incident_id: int, session: SessionDep) -> dict[str, Any]:
        incident = session.scalar(select(Incident).options(joinedload(Incident.device)).where(Incident.id == incident_id))
        if incident is None:
            raise HTTPException(status_code=404, detail="Incident not found")
        return _incident_dict(incident)

    @api.post("/api/incidents/{incident_id}/acknowledge", tags=["incidents"])
    def acknowledge(incident_id: int, payload: AcknowledgeRequest, session: SessionDep) -> dict[str, Any]:
        try:
            incident = acknowledge_incident(session, incident_id, payload.acknowledged_by)
            session.commit()
            session.refresh(incident)
        except ValueError as exc:
            session.rollback()
            status_code = 404 if "not found" in str(exc).lower() else 409
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc
        incident = session.scalar(select(Incident).options(joinedload(Incident.device)).where(Incident.id == incident_id))
        assert incident is not None
        return _incident_dict(incident)

    @api.post("/api/incidents/{incident_id}/resolve", tags=["incidents"])
    def resolve(incident_id: int, session: SessionDep) -> dict[str, Any]:
        try:
            incident = resolve_incident(session, incident_id)
            session.commit()
        except ValueError as exc:
            session.rollback()
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        incident = session.scalar(select(Incident).options(joinedload(Incident.device)).where(Incident.id == incident_id))
        assert incident is not None
        return _incident_dict(incident)

    @api.get("/api/incidents/{incident_id}/recommendations", tags=["incidents"])
    def incident_recommendations(incident_id: int, session: SessionDep) -> dict[str, Any]:
        incident = session.get(Incident, incident_id)
        if incident is None:
            raise HTTPException(status_code=404, detail="Incident not found")
        return {"incident_id": incident.id, "recommendations": recommendations_as_dicts(incident)}

    @api.get("/api/reports/{report_format}", tags=["reports"])
    def report(report_format: Literal["json", "markdown", "csv"], session: SessionDep) -> Response:
        report_data = build_report(session)
        if report_format == "json":
            return Response(render_json(report_data), media_type="application/json")
        if report_format == "markdown":
            return Response(render_markdown(report_data), media_type="text/markdown; charset=utf-8")
        return Response(render_csv(report_data), media_type="text/csv; charset=utf-8")

    @api.get("/", response_class=HTMLResponse, include_in_schema=False)
    def dashboard() -> str:
        return DASHBOARD_HTML

    @api.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
    def dashboard_alias() -> str:
        return DASHBOARD_HTML

    return api


def _metric_dict(metric: Metric) -> dict[str, Any]:
    return {
        "id": metric.id,
        "device_id": metric.device_id,
        "device_name": metric.device.name,
        "name": metric.name,
        "value": metric.value,
        "unit": metric.unit,
        "status": metric.status,
        "recorded_at": _iso(metric.recorded_at),
        "source": metric.source,
        "details": metric.details,
    }


app = create_app()
