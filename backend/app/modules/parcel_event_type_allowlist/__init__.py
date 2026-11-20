"""包裹事件类型允许集。

实现要点：

* 允许集版本化落库：``event_type_allowlist_version`` 存版本，
  ``event_type_allowlist`` 存该版本成员。每次保存只追加新版本，
  历史版本与已物化的占用成员都不被改写。
* 装载入口按“当前允许集”做一次批次快照后分流（fail-closed）：
  集合内事件照既有规则物化；集合外事件只写 ``quarantine``
  （``kind='event_type'``），不写 ``parcel_events``，不改
  ``occupancies`` / ``cells``。
* 只读核证接口返回当前版本、仍被搁置的违规数、搁置键。
"""

import json
import re
from datetime import datetime, timezone

STATUS = "implemented"

DEFAULT_ALLOWED = ("drop", "pickup")
CANDIDATE_TYPES = ("drop", "pickup", "confirm", "reclaim")

_TYPE_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def current_version(conn) -> int | None:
    row = conn.execute("SELECT MAX(version) AS v FROM event_type_allowlist_version").fetchone()
    return row["v"] if row and row["v"] is not None else None


def normalize_types(raw) -> list[str]:
    """校验并规范化允许集；返回排序去重后的列表。"""
    if not isinstance(raw, (list, tuple)):
        raise ValueError("allowed 必须是 event_type 字符串数组")
    out: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            raise ValueError(f"允许集只能包含字符串，收到 {item!r}")
        value = item.strip()
        if not value:
            raise ValueError("允许集不能包含空字符串")
        if not _TYPE_RE.match(value):
            raise ValueError(
                f"非法 event_type：{value!r}（应为小写字母开头，"
                "仅含小写字母/数字/下划线，最长 32 位）"
            )
        if value not in out:
            out.append(value)
    return sorted(out)


def save_allowlist(conn, raw, note: str = "") -> dict:
    """保存一个新版本；集合未变化时不产生新版本。调用方负责 commit。"""
    types = normalize_types(raw)
    version = current_version(conn)
    if version is not None:
        current = allowed_types(conn, version)
        if set(types) == current:
            return {"version": version, "allowed": sorted(current), "changed": False}
    next_version = (version or 0) + 1
    now = utcnow()
    conn.execute(
        "INSERT INTO event_type_allowlist_version(version, created_at, note) VALUES (?,?,?)",
        (next_version, now, note),
    )
    conn.executemany(
        "INSERT INTO event_type_allowlist(version, event_type) VALUES (?,?)",
        [(next_version, event_type) for event_type in types],
    )
    return {"version": next_version, "allowed": types, "changed": True}


def ensure_default(conn) -> int:
    """无任何版本时落地默认允许集（drop/pickup）。"""
    version = current_version(conn)
    if version is not None:
        return version
    return save_allowlist(conn, DEFAULT_ALLOWED, note="初始允许集（drop/pickup）")["version"]


def allowed_types(conn, version: int | None = None) -> set[str]:
    if version is None:
        version = current_version(conn)
    if version is None:
        return set()
    rows = conn.execute(
        "SELECT event_type FROM event_type_allowlist WHERE version=?", (version,)
    ).fetchall()
    return {row["event_type"] for row in rows}


def current(conn) -> dict:
    """当前允许集快照（版本 + 成员 + 元信息）。"""
    version = ensure_default(conn)
    row = conn.execute(
        "SELECT created_at, note FROM event_type_allowlist_version WHERE version=?",
        (version,),
    ).fetchone()
    return {
        "version": version,
        "allowed": sorted(allowed_types(conn, version)),
        "created_at": row["created_at"] if row else None,
        "note": row["note"] if row else "",
    }


def history(conn, limit: int = 20) -> list[dict]:
    versions = conn.execute(
        "SELECT version, created_at, note FROM event_type_allowlist_version "
        "ORDER BY version DESC LIMIT ?",
        (limit,),
    ).fetchall()
    members: dict[int, list[str]] = {}
    for row in conn.execute(
        "SELECT version, event_type FROM event_type_allowlist ORDER BY version, event_type"
    ).fetchall():
        members.setdefault(row["version"], []).append(row["event_type"])
    return [
        {
            "version": row["version"],
            "allowed": members.get(row["version"], []),
            "created_at": row["created_at"],
            "note": row["note"],
        }
        for row in versions
    ]


def quarantine_event(conn, event: dict, version: int, allowed: set[str], batch_id: str | None) -> tuple[str, bool]:
    """把类型违规事件写入搁置；返回 (搁置键, 是否新插入)。"""
    raw_type = event.get("event_type")
    raw_type = raw_type.strip() if isinstance(raw_type, str) else ""
    label = raw_type or "(缺失)"
    key = f"QT-{event['id']}"
    allowed_text = ", ".join(sorted(allowed)) if allowed else "空集"
    reason = (
        f"类型违规：event_type={label} 不在允许集 v{version}"
        f"（允许：{allowed_text}）；未入事件账、未改占用与格口"
    )
    member = {
        "id": event["id"],
        "cabinet_id": event.get("cabinet_id"),
        "cell_id": event.get("cell_id"),
        "event_type": event.get("event_type"),
        "event_ts": event.get("event_ts"),
        "tracking_no": event.get("tracking_no"),
        "payload": event.get("payload") or {},
    }
    cursor = conn.execute(
        "INSERT OR IGNORE INTO quarantine"
        "(kind, quarantine_key, batch_id, event_id, event_type, allowlist_version,"
        " reason, member_json, created_at) "
        "VALUES ('event_type',?,?,?,?,?,?,?,?)",
        (
            key,
            batch_id,
            event["id"],
            raw_type or None,
            version,
            reason,
            json.dumps(member, ensure_ascii=False),
            utcnow(),
        ),
    )
    return key, cursor.rowcount > 0


def type_violations(conn) -> list[dict]:
    """仍被搁置的类型违规（事件后来被接收的历史搁置留档但不计入）。"""
    rows = conn.execute(
        "SELECT q.id, q.quarantine_key, q.batch_id, q.event_id, q.event_type,"
        " q.allowlist_version, q.reason, q.created_at,"
        " CASE WHEN EXISTS(SELECT 1 FROM parcel_events pe WHERE pe.id=q.event_id)"
        " THEN 1 ELSE 0 END AS resolved "
        "FROM quarantine q WHERE q.kind='event_type' ORDER BY q.id"
    ).fetchall()
    return [dict(row) for row in rows]


def verification(conn) -> dict:
    """只读核证：版本、违规数、搁置键。"""
    snapshot = current(conn)
    violations = type_violations(conn)
    active = [row for row in violations if not row["resolved"]]
    by_type: dict[str, int] = {}
    for row in active:
        label = row["event_type"] or "(缺失)"
        by_type[label] = by_type.get(label, 0) + 1

    latest = conn.execute(
        "SELECT id, created_at, allowlist_version, report_json FROM ingest_batches "
        "ORDER BY rowid DESC LIMIT 1"
    ).fetchone()
    latest_batch = None
    if latest:
        try:
            report = json.loads(latest["report_json"])
        except (TypeError, ValueError):
            report = {}
        latest_batch = {
            "batch_id": latest["id"],
            "created_at": latest["created_at"],
            "allowlist_version": latest["allowlist_version"],
            "accepted": report.get("accepted"),
            "quarantined": report.get("quarantined"),
            "duplicate": report.get("duplicate"),
            "total": report.get("total"),
        }

    return {
        "version": snapshot["version"],
        "allowed": snapshot["allowed"],
        "allowed_count": len(snapshot["allowed"]),
        "updated_at": snapshot["created_at"],
        "violation_count": len(active),
        "quarantine_keys": [row["quarantine_key"] for row in active],
        "violations_by_type": by_type,
        "archived_violation_count": len(violations) - len(active),
        "latest_batch": latest_batch,
        "checked_at": utcnow(),
    }
