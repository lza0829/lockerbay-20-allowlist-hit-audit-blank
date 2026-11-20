import json
from datetime import datetime, timezone
from uuid import uuid4

from app.db import FIXTURES_DIR, connect
from app.modules import parcel_event_type_allowlist as allowlist


def _load_events():
    path = FIXTURES_DIR / "ingest_batch.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("events", [])


def _event_type(ev) -> str:
    raw = ev.get("event_type")
    return raw.strip() if isinstance(raw, str) else ""


def _materialize(conn, ev, event_type):
    """既有物化规则：只在事件首次入账后调用。"""
    if event_type == "drop" and ev.get("cell_id"):
        cell = conn.execute("SELECT status FROM cells WHERE id=?", (ev["cell_id"],)).fetchone()
        if cell and cell["status"] == "free":
            oid = f"OCC-{ev['cell_id']}-{ev['id']}"
            conn.execute(
                "INSERT INTO occupancies(id, cell_id, tracking_no, opened_at, closed_at, status, last_event_id) VALUES (?,?,?,?,?,?,?)",
                (oid, ev["cell_id"], ev["tracking_no"], ev["event_ts"], None, "occupied", ev["id"]),
            )
            conn.execute("UPDATE cells SET status='occupied' WHERE id=?", (ev["cell_id"],))
    elif event_type == "pickup" and ev.get("cell_id"):
        row = conn.execute(
            "SELECT id FROM occupancies WHERE cell_id=? AND status='occupied' ORDER BY opened_at DESC LIMIT 1",
            (ev["cell_id"],),
        ).fetchone()
        if row:
            conn.execute(
                "UPDATE occupancies SET closed_at=?, status='released', last_event_id=? WHERE id=?",
                (ev["event_ts"], ev["id"], row["id"]),
            )
            conn.execute("UPDATE cells SET status='free' WHERE id=?", (ev["cell_id"],))


def run_batch():
    events = _load_events()
    if events is None:
        return {"batch_id": None, "accepted": 0, "message": "无夹具"}
    batch_id = f"B-{uuid4().hex[:8]}"
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn = connect()
    accepted = 0
    quarantined = 0
    duplicate = 0
    decisions = []
    try:
        # 入口按当前允许集分流：批次开始时固定版本，整批按同一快照裁决。
        version = allowlist.ensure_default(conn)
        allowed = allowlist.allowed_types(conn, version)
        for ev in events:
            event_type = _event_type(ev)
            if event_type not in allowed:
                key, is_new = allowlist.quarantine_event(conn, ev, version, allowed, batch_id)
                quarantined += 1
                decisions.append(
                    {
                        "event_id": ev.get("id"),
                        "event_type": ev.get("event_type"),
                        "decision": "quarantined",
                        "quarantine_key": key,
                        "is_new": is_new,
                    }
                )
                continue

            cursor = conn.execute(
                "INSERT OR IGNORE INTO parcel_events(id, cabinet_id, cell_id, event_type, event_ts, tracking_no, payload_json, channel) VALUES (?,?,?,?,?,?,?,?)",
                (
                    ev["id"],
                    ev["cabinet_id"],
                    ev.get("cell_id"),
                    event_type,
                    ev["event_ts"],
                    ev.get("tracking_no"),
                    json.dumps(ev.get("payload", {}), ensure_ascii=False),
                    "primary",
                ),
            )
            inserted = cursor.rowcount > 0
            if inserted:
                accepted += 1
                _materialize(conn, ev, event_type)
            else:
                duplicate += 1
            decisions.append(
                {
                    "event_id": ev["id"],
                    "event_type": event_type,
                    "decision": "accepted" if inserted else "duplicate",
                }
            )

        conn.execute(
            "INSERT INTO ingest_batches(id, created_at, report_json, allowlist_version) VALUES (?,?,?,?)",
            (
                batch_id,
                now,
                json.dumps(
                    {
                        "accepted": accepted,
                        "quarantined": quarantined,
                        "duplicate": duplicate,
                        "total": len(events),
                        "allowlist_version": version,
                        "allowed": sorted(allowed),
                        "decisions": decisions,
                    },
                    ensure_ascii=False,
                ),
                version,
            ),
        )
        conn.commit()
        return {
            "batch_id": batch_id,
            "accepted": accepted,
            "quarantined": quarantined,
            "duplicate": duplicate,
            "total": len(events),
            "allowlist_version": version,
            "allowed": sorted(allowed),
            "decisions": decisions,
        }
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

