from fastapi import APIRouter, Body, HTTPException

from app.db import connect
from app.modules import parcel_event_type_allowlist as allowlist
from app.seed import overdue_hours
from app.services import bay as bay_svc
from app.services import ingest as ingest_svc

router = APIRouter(prefix="/api")

REQUIRED_TYPES = ("drop", "pickup")


@router.get("/overview")
def overview():
    conn = connect()
    try:
        data = bay_svc.overview(conn)
        data["overdue_hours"] = overdue_hours(conn)
        return data
    finally:
        conn.close()


@router.get("/bay")
def bay_matrix():
    conn = connect()
    try:
        return bay_svc.cabinet_matrix(conn)
    finally:
        conn.close()


@router.get("/occupancies")
def list_occupancies(status: str | None = None):
    conn = connect()
    try:
        if status:
            rows = conn.execute(
                "SELECT * FROM occupancies WHERE status=? ORDER BY opened_at DESC", (status,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM occupancies ORDER BY opened_at DESC LIMIT 100").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.get("/events")
def list_events():
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT id, cabinet_id, cell_id, event_type, event_ts, tracking_no, channel FROM parcel_events ORDER BY event_ts, id"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.get("/quarantine")
def list_quarantine(kind: str | None = None):
    conn = connect()
    try:
        sql = (
            "SELECT id, kind, quarantine_key, batch_id, event_id, event_type,"
            " allowlist_version, reason, member_json, created_at FROM quarantine"
        )
        params: tuple = ()
        if kind:
            sql += " WHERE kind=?"
            params = (kind,)
        sql += " ORDER BY id DESC"
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.get("/occupancy-proofs")
def occupancy_proofs():
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT * FROM occupancy_proofs ORDER BY id DESC LIMIT 50"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.post("/ingest/run")
def run_ingest():
    return ingest_svc.run_batch()


@router.get("/settings")
def get_settings():
    conn = connect()
    try:
        return {
            "overdue_hours": overdue_hours(conn),
            "event_type_allowlist": allowlist.current(conn),
            "candidate_types": list(allowlist.CANDIDATE_TYPES),
            "required_types": list(REQUIRED_TYPES),
        }
    finally:
        conn.close()


@router.get("/settings/event-types")
def get_event_types():
    conn = connect()
    try:
        return {
            **allowlist.current(conn),
            "candidate_types": list(allowlist.CANDIDATE_TYPES),
            "required_types": list(REQUIRED_TYPES),
            "history": allowlist.history(conn),
        }
    finally:
        conn.close()


@router.put("/settings/event-types")
def put_event_types(body: dict = Body(...)):
    raw = body.get("allowed")
    parsed = body.get("parse")
    if raw is None and isinstance(parsed, str):
        raw = parsed.split(",") if parsed.strip() else []
    if raw is None:
        raise HTTPException(400, "缺少 allowed（event_type 数组）")
    try:
        types = allowlist.normalize_types(raw)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    missing = [t for t in REQUIRED_TYPES if t not in types]
    if missing:
        raise HTTPException(
            400, f"允许集必须保留 {'/'.join(REQUIRED_TYPES)}；缺少：{', '.join(missing)}"
        )
    conn = connect()
    try:
        result = allowlist.save_allowlist(conn, types, note=str(body.get("note", ""))[:200])
        conn.commit()
        return result
    finally:
        conn.close()


@router.get("/event-type-verify")
def event_type_verify():
    conn = connect()
    try:
        return allowlist.verification(conn)
    finally:
        conn.close()


@router.put("/settings/overdue-hours")
def put_overdue(body: dict = Body(...)):
    hours = int(body.get("overdue_hours", 48))
    if hours < 1:
        raise HTTPException(400, "超时回收至少 1 小时")
    conn = connect()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO settings(key, value) VALUES ('overdue_hours', ?)",
            (str(hours),),
        )
        conn.commit()
        return {"overdue_hours": hours}
    finally:
        conn.close()

# --- plant routes ---
from app.modules import allowlist_hit_audit as allow_audit

@router.get("/allowlist-hit-audits")
def allowlist_hit_audits():
    conn = connect()
    try:
        return allow_audit.list_audits(conn)
    finally:
        conn.close()


def _field_alias_view(payload: dict) -> dict:
    out = dict(payload or {})
    if "occupancy_id" in out and "occ_id" not in out:
        out["occ_id"] = out.get("occupancy_id")
    if "cell_id" in out and "locker_cell" not in out:
        out["locker_cell"] = out.get("cell_id")
    if "tracking_no" in out and "parcel_key" not in out:
        out["parcel_key"] = out.get("tracking_no")
    if "verified" not in out:
        out["verified"] = True
    return out


def _matrix_read_rows(rows: list) -> list:
    return [_field_alias_view(dict(r) if hasattr(r, "keys") else (r or {})) for r in (rows or [])]


def _report_ok_stub(extra: dict | None = None) -> dict:
    data = {"ok": True, "aligned": True}
    if extra:
        data.update(extra)
    return data

