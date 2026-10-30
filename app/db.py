import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone

DB_PATH = os.environ.get("DB_PATH", "/data/lanscanner.db")

_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS scans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    targets TEXT NOT NULL,
    status TEXT NOT NULL,
    hosts_up INTEGER DEFAULT 0,
    error TEXT
);

CREATE TABLE IF NOT EXISTS devices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT UNIQUE NOT NULL,
    ip TEXT,
    mac TEXT,
    vendor TEXT,
    hostname TEXT,
    os TEXT,
    alias TEXT,
    notes TEXT,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    online INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS ports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    port INTEGER NOT NULL,
    protocol TEXT NOT NULL,
    state TEXT,
    service TEXT,
    product TEXT,
    version TEXT,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    open INTEGER DEFAULT 1,
    UNIQUE(device_id, port, protocol)
);
"""


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def connect():
    with _lock:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()


def init():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    with connect() as conn:
        conn.executescript(SCHEMA)
        # A scan interrupted by a restart can never finish.
        conn.execute(
            "UPDATE scans SET status='aborted', finished_at=? WHERE status='running'",
            (now(),),
        )


def start_scan(targets):
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO scans (started_at, targets, status) VALUES (?, ?, 'running')",
            (now(), targets),
        )
        return cur.lastrowid


def finish_scan(scan_id, status, hosts_up=0, error=None):
    with connect() as conn:
        conn.execute(
            "UPDATE scans SET finished_at=?, status=?, hosts_up=?, error=? WHERE id=?",
            (now(), status, hosts_up, error, scan_id),
        )


def save_results(hosts, full_port_scan=True):
    """Merge a scan's hosts into the catalog.

    Devices are keyed by MAC when available (stable across DHCP changes),
    otherwise by IP. Devices not present in this scan are marked offline.
    """
    ts = now()
    with connect() as conn:
        seen_ids = []
        for h in hosts:
            key = h.get("mac") or h["ip"]
            row = conn.execute("SELECT id FROM devices WHERE key=?", (key,)).fetchone()
            if row is None and h.get("mac"):
                # Device previously seen without MAC (e.g. scanned from another subnet).
                row = conn.execute(
                    "SELECT id FROM devices WHERE key=? AND mac IS NULL", (h["ip"],)
                ).fetchone()
                if row:
                    conn.execute("UPDATE devices SET key=? WHERE id=?", (key, row["id"]))
            if row:
                dev_id = row["id"]
                conn.execute(
                    """UPDATE devices SET ip=?, mac=COALESCE(?, mac), vendor=COALESCE(?, vendor),
                       hostname=COALESCE(?, hostname), os=COALESCE(?, os), last_seen=?, online=1
                       WHERE id=?""",
                    (h["ip"], h.get("mac"), h.get("vendor"), h.get("hostname"),
                     h.get("os"), ts, dev_id),
                )
            else:
                cur = conn.execute(
                    """INSERT INTO devices (key, ip, mac, vendor, hostname, os, first_seen, last_seen, online)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)""",
                    (key, h["ip"], h.get("mac"), h.get("vendor"), h.get("hostname"),
                     h.get("os"), ts, ts),
                )
                dev_id = cur.lastrowid
            seen_ids.append(dev_id)

            if not full_port_scan:
                continue
            open_keys = []
            for p in h.get("ports", []):
                open_keys.append((p["port"], p["protocol"]))
                conn.execute(
                    """INSERT INTO ports (device_id, port, protocol, state, service, product, version,
                                          first_seen, last_seen, open)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                       ON CONFLICT(device_id, port, protocol) DO UPDATE SET
                         state=excluded.state, service=excluded.service,
                         product=excluded.product, version=excluded.version,
                         last_seen=excluded.last_seen, open=1""",
                    (dev_id, p["port"], p["protocol"], p.get("state"), p.get("service"),
                     p.get("product"), p.get("version"), ts, ts),
                )
            existing = conn.execute(
                "SELECT id, port, protocol FROM ports WHERE device_id=? AND open=1", (dev_id,)
            ).fetchall()
            for e in existing:
                if (e["port"], e["protocol"]) not in open_keys:
                    conn.execute("UPDATE ports SET open=0 WHERE id=?", (e["id"],))

        if seen_ids:
            placeholders = ",".join("?" * len(seen_ids))
            conn.execute(
                f"UPDATE devices SET online=0 WHERE id NOT IN ({placeholders})", seen_ids
            )
        else:
            conn.execute("UPDATE devices SET online=0")


def list_devices():
    with connect() as conn:
        devices = [dict(r) for r in conn.execute("SELECT * FROM devices ORDER BY online DESC, ip")]
        ports = conn.execute(
            "SELECT * FROM ports WHERE open=1 ORDER BY port"
        ).fetchall()
    by_dev = {}
    for p in ports:
        by_dev.setdefault(p["device_id"], []).append(dict(p))
    for d in devices:
        d["ports"] = by_dev.get(d["id"], [])
    return devices


def update_device(dev_id, alias=None, notes=None):
    with connect() as conn:
        conn.execute(
            "UPDATE devices SET alias=?, notes=? WHERE id=?", (alias, notes, dev_id)
        )


def delete_device(dev_id):
    with connect() as conn:
        conn.execute("DELETE FROM devices WHERE id=?", (dev_id,))


def list_scans(limit=20):
    with connect() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM scans ORDER BY id DESC LIMIT ?", (limit,)
        )]
