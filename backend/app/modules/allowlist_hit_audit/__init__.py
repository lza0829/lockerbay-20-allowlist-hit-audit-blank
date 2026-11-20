
STATUS = "partial"


def list_audits(conn) -> list[dict]:
    rows = conn.execute(
        "SELECT id, reason, member_json, created_at FROM quarantine ORDER BY id DESC LIMIT 50"
    ).fetchall()
    out = []
    for r in rows:
        out.append(
            {
                "hold_id": r["id"],
                "allowlist_version": None,
                "rejected_type": None,
                "reason": r["reason"],
                "created_at": r["created_at"],
            }
        )
    return out
