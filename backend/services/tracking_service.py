"""HRD H2 services — Live Field Tracking (WebSocket).

WS-upgrade lewat ingress publik (wss) sudah DIBUKTIKAN di H-POC (scripts/poc_hrd.py).
Manager (admin/manager) subscribe → Live Map; karyawan lapangan (sales) publish posisi.
Koleksi: hr_field_tracks (trk_). Posisi disimpan ter-throttle; cache 'posisi terkini'
untuk snapshot cepat + broadcast realtime.
"""
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Set

from db import db
from core_utils import new_id, now_iso, safe_doc

WIB = timezone(timedelta(hours=7))
STORE_INTERVAL_SEC = 30          # tulis DB maksimum 1×/30 dtk/karyawan (cache tetap realtime)
ONLINE_WINDOW_SEC = 600          # dianggap online bila posisi terakhir < 10 menit

_LIVE_FIELDS = ("employee_id", "employee_name", "lat", "lon", "accuracy",
                "battery", "ts", "entity_id", "source")


class TrackManager:
    """In-memory: subscriber WS + cache posisi terkini per karyawan."""
    def __init__(self) -> None:
        self.subscribers: Set[Any] = set()
        self.latest: Dict[str, Dict[str, Any]] = {}
        self._store_lock = asyncio.Lock()
        self._last_store: Dict[str, datetime] = {}

    def add_subscriber(self, ws: Any) -> None:
        self.subscribers.add(ws)

    def remove_subscriber(self, ws: Any) -> None:
        self.subscribers.discard(ws)

    def snapshot(self) -> List[Dict[str, Any]]:
        return list(self.latest.values())

    async def broadcast(self, msg: Dict[str, Any]) -> None:
        dead = []
        for ws in list(self.subscribers):
            try:
                await ws.send_json(msg)
            except Exception:  # noqa: BLE001 — koneksi mati, bersihkan
                dead.append(ws)
        for ws in dead:
            self.subscribers.discard(ws)

    async def update_position(self, pos: Dict[str, Any]) -> None:
        self.latest[pos["employee_id"]] = pos
        await self.broadcast({"type": "position", "data": pos})


manager = TrackManager()


async def auth_ws_token(token: str) -> Optional[Dict[str, Any]]:
    """Validasi token sesi (query param) untuk WebSocket. Return user atau None."""
    if not token:
        return None
    session = await db.sessions.find_one({"token": token.strip()}, {"_id": 0})
    if not session:
        return None
    user = await db.users.find_one(
        {"id": session["user_id"], "status": "active"}, {"_id": 0, "password_hash": 0})
    return safe_doc(user) if user else None


async def employee_for_user(user_id: str) -> Optional[Dict[str, Any]]:
    return safe_doc(await db.hr_employees.find_one({"user_id": user_id}, {"_id": 0}))


async def store_track(emp: Dict[str, Any], lat: float, lon: float,
                      accuracy: float = 0, battery: Optional[float] = None,
                      source: str = "ws") -> Dict[str, Any]:
    """Update cache + broadcast (selalu) lalu tulis DB ter-throttle."""
    now = datetime.now(WIB)
    pos = {
        "employee_id": emp["id"], "employee_name": emp.get("name", ""),
        "lat": float(lat), "lon": float(lon), "accuracy": float(accuracy or 0),
        "battery": battery, "ts": now.isoformat(),
        "entity_id": emp.get("entity_id", ""), "source": source,
    }
    await manager.update_position(pos)
    last = manager._last_store.get(emp["id"])
    if not last or (now - last).total_seconds() >= STORE_INTERVAL_SEC:
        manager._last_store[emp["id"]] = now
        await db.hr_field_tracks.insert_one(
            {**pos, "id": new_id("trk"), "created_at": now_iso()})
    return pos


async def hydrate_latest() -> None:
    """Muat posisi terakhir per karyawan ke cache saat startup."""
    try:
        pipeline = [
            {"$sort": {"ts": -1}},
            {"$group": {"_id": "$employee_id", "doc": {"$first": "$$ROOT"}}},
        ]
        async for row in db.hr_field_tracks.aggregate(pipeline):
            d = safe_doc(row["doc"])
            manager.latest[d["employee_id"]] = {k: d.get(k) for k in _LIVE_FIELDS}
    except Exception:  # noqa: BLE001 — jangan gagalkan startup
        pass


def is_online(ts_iso: str) -> bool:
    try:
        ts = datetime.fromisoformat(ts_iso)
        return (datetime.now(WIB) - ts).total_seconds() <= ONLINE_WINDOW_SEC
    except (ValueError, TypeError):
        return False
