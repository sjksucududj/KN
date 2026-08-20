#!/usr/bin/env python3
"""POC PS-20 (D-14) — MATRIKS PERSETUJUAN DIVISI YANG MENGIKAT.

Membuktikan (terisolasi, lewat HTTP nyata ke backend lokal) bahwa:

  1. GET /api/approvals/matrix          → 4 tahap + tingkat + kebijakan penegakan.
  2. GET /api/approvals/my-queue        → antrean lintas tahap; sales/gudang 403.
  3. ACC Desain  (design_acc)           → sales 403; PENGAJU sendiri 403 (SoD); manager 200.
  4. PR          (purchase_request)     → gudang 403; pengaju 403 (SoD); approver lain 200.
  5. PO Custom   (po_custom)            → 2 TINGKAT: manager → (masih menunggu) → Direksi/admin.
  6. Sakelar retroaktif                 → 'new_only' + tanggal → dokumen lama lolos (SoD dilewati).
  7. Jejak persetujuan                  → GET /api/approvals/matrix-log mencatat keputusan+pelanggaran.
  8. Regresi                            → /api/rnd/divisions & /api/approvals/queue tetap hidup.

JEBAKAN YANG DIHINDARI: `dependencies.extract_token` mengutamakan cookie sesi HttpOnly di
atas header Bearer → setiap peran memakai SESI HTTP TERPISAH (cookie tidak saling menimpa).

Jalankan: python3 /app/test_core_approval_matrix.py
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

import requests

BASE = "http://localhost:8001/api"
ENTITY = "ent_ksc"
PASSWORD = "demo12345"
USERS = {
    "admin": "admin@kainnusantara.id",
    "manager": "manager@kainnusantara.id",
    "sales": "sales@kainnusantara.id",
    "warehouse": "warehouse@kainnusantara.id",
}

PASS: list[str] = []
FAIL: list[str] = []


def ok(msg: str) -> None:
    PASS.append(msg)
    print(f"  ✅ {msg}")


def bad(msg: str) -> None:
    FAIL.append(msg)
    print(f"  ❌ {msg}")


def check(cond: bool, msg: str, extra: str = "") -> bool:
    (ok if cond else bad)(msg + (f" — {extra}" if (extra and not cond) else ""))
    return bool(cond)


class Client:
    """Satu peran = satu sesi (cookie terpisah) supaya uji RBAC tidak salah baca."""

    def __init__(self, role: str) -> None:
        self.role = role
        self.s = requests.Session()
        r = self.s.post(f"{BASE}/auth/login",
                        json={"email": USERS[role], "password": PASSWORD}, timeout=30)
        r.raise_for_status()
        data = r.json()
        self.token = data["token"]
        self.user = data["user"]
        self.s.headers.update({"Authorization": f"Bearer {self.token}",
                               "X-Entity-Id": ENTITY,
                               "Content-Type": "application/json"})

    def req(self, method: str, path: str, **kw) -> requests.Response:
        return self.s.request(method, f"{BASE}{path}", timeout=60, **kw)

    def get(self, path: str, **kw) -> requests.Response:
        return self.req("GET", path, **kw)

    def post(self, path: str, **kw) -> requests.Response:
        return self.req("POST", path, **kw)

    def put(self, path: str, **kw) -> requests.Response:
        return self.req("PUT", path, **kw)


def body(r: requests.Response) -> Any:
    try:
        return r.json()
    except Exception:  # noqa: BLE001
        return r.text[:200]


def detail(r: requests.Response) -> str:
    d = body(r)
    if isinstance(d, dict):
        return str(d.get("detail") or d)[:220]
    return str(d)[:220]


# ─── Pengaturan (Pusat Pengaturan) ───────────────────────────────────────────
def set_setting(cli: Client, key: str, value: Any) -> bool:
    """Tulis lewat Pusat Pengaturan yang sebenarnya: PUT /api/config/values."""
    r = cli.s.put("http://localhost:8001/api/config/values",
                  json={"items": [{"key": key, "value": value, "scope_type": "global",
                                   "reason": "POC PS-20 — uji sakelar retroaktif"}]},
                  timeout=60)
    if r.status_code in (200, 201):
        return True
    print(f"     (set_setting {key} gagal: {r.status_code} {detail(r)})")
    return False


# ═══════════════════════════════════════════════════════════════════════════
def t1_matrix(m: Client) -> Dict[str, Any]:
    print("\n[1] GET /approvals/matrix — matriks + tingkat + kebijakan")
    r = m.get("/approvals/matrix")
    if not check(r.status_code == 200, "matrix 200 untuk manager", f"{r.status_code} {detail(r)}"):
        return {}
    d = body(r)
    stages = {s["stage"]: s for s in d.get("stages") or []}
    check(set(stages) == {"design_acc", "sample_acc", "po_custom", "purchase_request"},
          "4 tahap lengkap", str(list(stages)))
    check(len(stages.get("po_custom", {}).get("levels") or []) == 2,
          "po_custom punya 2 tingkat (Manager + Direksi) pada nilai ≥ ambang",
          json.dumps(stages.get("po_custom", {}).get("levels")))
    for st in ("design_acc", "sample_acc", "purchase_request"):
        check((stages.get(st, {}).get("levels") or [{}])[0].get("roles") == ["manager", "admin"],
              f"{st} tingkat 1 = manager/admin")
    cfg = d.get("config") or {}
    check(cfg.get("mode") == "enforce", "bawaan penegakan = enforce", str(cfg.get("mode")))
    check(cfg.get("scope") == "all_pending",
          "bawaan cakupan = semua dokumen (termasuk yang menunggu)", str(cfg.get("scope")))
    check(cfg.get("sod") is True, "bawaan pemisahan tugas aktif", str(cfg.get("sod")))
    check(float(cfg.get("po_custom_direksi_min") or 0) > 0,
          "ambang Direksi terbaca", str(cfg.get("po_custom_direksi_min")))
    return cfg


def t2_queue(m: Client, s: Client, w: Client) -> None:
    print("\n[2] GET /approvals/my-queue — antrean + RBAC")
    r = m.get("/approvals/my-queue")
    if check(r.status_code == 200, "my-queue 200 untuk manager", f"{r.status_code} {detail(r)}"):
        d = body(r)
        check(isinstance(d.get("items"), list), "items[] ada")
        check(set((d.get("counts") or {})) ==
              {"design_acc", "sample_acc", "po_custom", "purchase_request"},
              "counts per tahap lengkap", str(d.get("counts")))
        for it in d.get("items") or []:
            if not all(k in it for k in ("stage", "can_decide", "required_roles_label",
                                         "days_waiting", "view", "level")):
                bad(f"item antrean tidak lengkap: {list(it)[:8]}")
                break
        else:
            ok("setiap baris antrean membawa stage/level/can_decide/required_roles/view")
    check(s.get("/approvals/my-queue").status_code == 403, "sales 403 di my-queue")
    check(w.get("/approvals/my-queue").status_code == 403, "gudang 403 di my-queue")
    check(s.get("/approvals/matrix").status_code == 403, "sales 403 di matrix")
    r = m.get("/approvals/my-queue", params={"stage": "xxx"})
    check(r.status_code == 400, "tahap tidak dikenal → 400", f"{r.status_code}")


# ─── Tahap 1: ACC Desain (design_acc) ────────────────────────────────────────
def make_spec(cli: Client, title: str) -> Optional[Dict[str, Any]]:
    payload = {"title": title, "sample_type_hint": "labdip",
               "target": {"fabric_type": "woven", "stage": "grey",
                          "gramasi": 120, "lebar": 115},
               "base_unit": "meter", "target_price": 55000,
               "sku_hint": "", "notes": "POC PS-20"}
    r = cli.post("/rnd/specs", json=payload)
    if r.status_code not in (200, 201):
        bad(f"gagal buat spesifikasi: {r.status_code} {detail(r)}")
        return None
    spec = body(r)
    r2 = cli.post(f"/rnd/specs/{spec['id']}/submit", json={})
    if r2.status_code != 200:
        bad(f"gagal submit spesifikasi: {r2.status_code} {detail(r2)}")
        return None
    return body(r2)


def t3_design_acc(a: Client, m: Client, s: Client) -> None:
    print("\n[3] ACC Desain (design_acc) — peran + pemisahan tugas")
    spec = make_spec(m, "POC PS-20 · spesifikasi diajukan MANAGER")
    if not spec:
        return
    sku = f"POC{datetime.now(timezone.utc).strftime('%H%M%S')}"
    r = s.post(f"/rnd/specs/{spec['id']}/approve", json={"sku": sku, "name": "POC Kain"})
    check(r.status_code == 403, "sales tidak boleh ACC desain (403)", f"{r.status_code}")

    r = m.post(f"/rnd/specs/{spec['id']}/approve", json={"sku": sku, "name": "POC Kain"})
    if check(r.status_code == 403,
             "PENGAJU (manager) tidak boleh meng-ACC desainnya sendiri — SoD 403",
             f"{r.status_code} {detail(r)}"):
        check("emisahan tugas" in detail(r), "pesan SoD jelas & berbahasa Indonesia",
              detail(r))

    r = a.post(f"/rnd/specs/{spec['id']}/approve", json={"sku": sku, "name": "POC Kain"})
    check(r.status_code == 200, "Direksi/Admin (bukan pengaju) berhasil ACC (200)",
          f"{r.status_code} {detail(r)}")

    spec2 = make_spec(a, "POC PS-20 · spesifikasi diajukan ADMIN")
    if spec2:
        sku2 = f"POCB{datetime.now(timezone.utc).strftime('%H%M%S')}"
        r = m.post(f"/rnd/specs/{spec2['id']}/approve", json={"sku": sku2, "name": "POC Kain B"})
        check(r.status_code == 200, "Manager berhasil ACC desain yang diajukan orang lain (200)",
              f"{r.status_code} {detail(r)}")


# ─── Tahap 2: PR (purchase_request) ──────────────────────────────────────────
def make_pr(cli: Client, note: str) -> Optional[Dict[str, Any]]:
    # > Rp 50 juta supaya matriks approval_rules memang mewajibkan persetujuan manager
    payload = {"items": [{"description": f"Bahan POC {note}", "quantity": 500,
                          "unit": "meter", "est_price": 200000}],
               "entity_id": ENTITY, "reason": f"POC PS-20 {note}",
               "submit_now": True, "source": "manual"}
    r = cli.post("/purchase-requisitions", json=payload)
    if r.status_code not in (200, 201):
        bad(f"gagal buat PR: {r.status_code} {detail(r)}")
        return None
    return body(r)


def t4_pr(a: Client, m: Client, w: Client) -> Optional[str]:
    print("\n[4] Permintaan Pembelian (purchase_request) — peran + SoD")
    pr_w = make_pr(w, "oleh gudang")
    if pr_w:
        check(pr_w.get("status") == "pending_approval",
              "PR gudang berstatus pending_approval", str(pr_w.get("status")))
        r = w.post(f"/purchase-requisitions/{pr_w['id']}/approve", json={"notes": "coba"})
        check(r.status_code == 403, "gudang tidak boleh menyetujui PR (403)", f"{r.status_code}")
        r = m.post(f"/purchase-requisitions/{pr_w['id']}/approve", json={"notes": "POC"})
        check(r.status_code == 200, "Manager menyetujui PR orang lain (200)",
              f"{r.status_code} {detail(r)}")

    pr_m = make_pr(m, "oleh manager sendiri")
    if not pr_m:
        return None
    r = m.post(f"/purchase-requisitions/{pr_m['id']}/approve", json={"notes": "coba sendiri"})
    check(r.status_code == 403, "PENGAJU PR (manager) ditolak menyetujui sendiri — SoD 403",
          f"{r.status_code} {detail(r)}")
    r = a.post(f"/purchase-requisitions/{pr_m['id']}/approve", json={"notes": "POC admin"})
    check(r.status_code == 200, "Direksi/Admin menyetujui PR manager (200)",
          f"{r.status_code} {detail(r)}")

    # PR ketiga: dipakai uji sakelar retroaktif (tetap menggantung).
    pr_retro = make_pr(m, "untuk uji retroaktif")
    return (pr_retro or {}).get("id")


# ─── Tahap 3: PO Custom (po_custom) 2 tingkat ────────────────────────────────
def first_customer(cli: Client) -> Optional[Dict[str, Any]]:
    r = cli.get("/customers")
    d = body(r)
    rows = d.get("items") if isinstance(d, dict) else d
    return (rows or [None])[0]


def make_special_order(cli: Client, amount_total: float) -> Optional[Dict[str, Any]]:
    cust = first_customer(cli)
    if not cust:
        bad("tidak ada customer untuk membuat pesanan khusus")
        return None
    qty = 100.0
    payload = {"customer_id": cust["id"], "entity_id": ENTITY,
               "custom_item": {"description": "Kain custom POC PS-20",
                               "specifications": {"warna": "indigo"},
                               "quantity": qty, "unit": "meter",
                               "target_price": amount_total / qty,
                               "notes": "POC"},
               "expected_delivery": (date.today() + timedelta(days=30)).isoformat(),
               "notes": "POC PS-20", "submit_for_approval": True}
    r = cli.post("/special-orders", json=payload)
    if r.status_code not in (200, 201):
        bad(f"gagal buat pesanan khusus: {r.status_code} {detail(r)}")
        return None
    return body(r)


def t5_po_custom(a: Client, m: Client, s: Client, cfg: Dict[str, Any]) -> None:
    print("\n[5] PO Custom (po_custom) — 2 tingkat: Manager → Direksi")
    threshold = float(cfg.get("po_custom_direksi_min") or 50_000_000)

    big = make_special_order(s, threshold * 2)
    if big:
        check(big.get("status") == "pending_approval",
              "pesanan besar berstatus pending_approval", str(big.get("status")))
        check(len(big.get("approval_chain") or []) == 2,
              "rantai 2 tingkat tercap sejak dibuat",
              json.dumps(big.get("approval_chain")))
        r = m.post(f"/special-orders/{big['id']}/approve", json={"notes": "tingkat 1"})
        if check(r.status_code == 200, "Manager menyetujui tingkat 1 (200)",
                 f"{r.status_code} {detail(r)}"):
            d = body(r)
            check(d.get("status") == "pending_approval",
                  "status TETAP menunggu setelah tingkat 1", str(d.get("status")))
            check(d.get("approval_level_current") == 2, "tingkat berjalan naik ke 2",
                  str(d.get("approval_level_current")))
        r = m.post(f"/special-orders/{big['id']}/approve", json={"notes": "tingkat 2 oleh manager"})
        check(r.status_code == 403,
              "Manager DITOLAK di tingkat 2 (hanya Direksi/Admin) — 403",
              f"{r.status_code} {detail(r)}")
        r = a.post(f"/special-orders/{big['id']}/approve", json={"notes": "tingkat 2 Direksi"})
        if check(r.status_code == 200, "Direksi/Admin menyetujui tingkat 2 (200)",
                 f"{r.status_code} {detail(r)}"):
            d = body(r)
            check(d.get("status") == "confirmed", "pesanan menjadi confirmed setelah 2 tingkat",
                  str(d.get("status")))

    small = make_special_order(s, threshold / 2)
    if small:
        check(len(small.get("approval_chain") or []) == 1,
              "pesanan di bawah ambang cukup 1 tingkat (cara lama tidak berubah)",
              json.dumps(small.get("approval_chain")))
        r = m.post(f"/special-orders/{small['id']}/approve", json={"notes": "1 tingkat"})
        if check(r.status_code == 200, "Manager langsung menuntaskan pesanan kecil (200)",
                 f"{r.status_code} {detail(r)}"):
            check(body(r).get("status") == "confirmed", "pesanan kecil langsung confirmed",
                  str(body(r).get("status")))


# ─── Tahap 4: sakelar retroaktif ─────────────────────────────────────────────
def t6_retro(a: Client, m: Client, pr_id: Optional[str]) -> None:
    print("\n[6] Sakelar retroaktif (Pusat Pengaturan) — 'hanya dokumen baru'")
    if not pr_id:
        bad("tidak ada PR untuk uji retroaktif")
        return
    besok = (date.today() + timedelta(days=1)).isoformat()
    if not (set_setting(a, "approval.matrix_scope", "new_only")
            and set_setting(a, "approval.matrix_effective_from", besok)):
        bad("gagal mengubah pengaturan cakupan penegakan")
        return
    ok(f"pengaturan diubah: scope=new_only, effective_from={besok}")
    r = m.get("/approvals/matrix")
    check((body(r).get("config") or {}).get("scope") == "new_only",
          "matrix melaporkan cakupan baru")
    r = m.post(f"/purchase-requisitions/{pr_id}/approve", json={"notes": "retro"})
    check(r.status_code == 200,
          "dokumen LAMA lolos penegakan saat 'hanya dokumen baru' (pengaju boleh menyetujui)",
          f"{r.status_code} {detail(r)}")
    set_setting(a, "approval.matrix_scope", "all_pending")
    set_setting(a, "approval.matrix_effective_from", "")
    r = m.get("/approvals/matrix")
    check((body(r).get("config") or {}).get("scope") == "all_pending",
          "pengaturan dikembalikan ke bawaan (semua dokumen)")


def t7_log(m: Client) -> None:
    print("\n[7] Jejak persetujuan — /approvals/matrix-log")
    r = m.get("/approvals/matrix-log", params={"limit": 100})
    if not check(r.status_code == 200, "matrix-log 200", f"{r.status_code} {detail(r)}"):
        return
    rows = body(r).get("items") or []
    check(len(rows) > 0, "jejak terisi", str(len(rows)))
    stages = {x.get("stage") for x in rows}
    check({"design_acc", "purchase_request", "po_custom"} <= stages,
          "jejak mencakup 3 tahap yang diuji", str(stages))
    viol = [x for x in rows if x.get("violation")]
    check(len(viol) > 0, "pelanggaran (percobaan tak berhak) tercatat", str(len(viol)))
    r = m.get("/approvals/matrix-log", params={"only_violations": "true", "limit": 50})
    check(r.status_code == 200 and all(x.get("violation") for x in (body(r).get("items") or [])),
          "filter only_violations bekerja")
    sample = rows[0]
    check(all(k in sample for k in ("stage_label", "actor_name", "actor_role", "level",
                                    "outcome", "created_at", "doc_number")),
          "baris jejak lengkap (siapa · tahap · tingkat · hasil · kapan)", str(list(sample)))


def t8_regression(m: Client) -> None:
    print("\n[8] Regresi — layar & endpoint yang sudah ada tetap hidup")
    r = m.get("/rnd/divisions")
    if check(r.status_code == 200, "GET /rnd/divisions tetap 200"):
        d = body(r)
        check(len(d.get("divisions") or []) == 7, "7 divisi tetap ada")
        check(len(d.get("approver_matrix") or []) == 4, "approver_matrix tetap 4 tahap")
        first = (d.get("approver_matrix") or [{}])[0]
        check(first.get("approvers") == ["Manager"],
              "field `approvers` (dipakai UI PS-17) tidak berubah bentuk", str(first))
    check(m.get("/rnd/divisions/members").status_code == 200, "GET /rnd/divisions/members 200")
    check(m.get("/approvals/queue").status_code == 200, "GET /approvals/queue (inbox SO) 200")
    r = m.get("/rnd/reports/designer-kpi", params={"period": "all"})
    check(r.status_code == 200, "KPI desainer tetap 200")
    check(m.get("/purchase-requisitions").status_code == 200, "daftar PR tetap 200")
    check(m.get("/special-orders").status_code == 200, "daftar pesanan khusus tetap 200")
    r = m.get("/config/registry")
    if r.status_code == 200:
        ok("Pusat Pengaturan (config registry) tetap 200")
    else:
        bad(f"config registry {r.status_code}")


def main() -> int:
    print("=" * 78)
    print("POC PS-20 — PENEGAKAN MATRIKS PERSETUJUAN DIVISI (D-14)")
    print("=" * 78)
    try:
        a, m, s, w = (Client("admin"), Client("manager"), Client("sales"), Client("warehouse"))
    except Exception as exc:  # noqa: BLE001
        print(f"FATAL: login gagal — {exc}")
        return 2
    print(f"  login OK: admin={a.user['name']} · manager={m.user['name']} · "
          f"sales={s.user['name']} · gudang={w.user['name']}")

    cfg = t1_matrix(m)
    t2_queue(m, s, w)
    t3_design_acc(a, m, s)
    pr_retro = t4_pr(a, m, w)
    t5_po_custom(a, m, s, cfg or {})
    t6_retro(a, m, pr_retro)
    t7_log(m)
    t8_regression(m)

    print("\n" + "=" * 78)
    total = len(PASS) + len(FAIL)
    print(f"HASIL: {len(PASS)}/{total} lulus")
    if FAIL:
        print("\nGAGAL:")
        for f in FAIL:
            print(f"  • {f}")
        return 1
    print("SEMUA LULUS ✅ — inti penegakan matriks persetujuan terbukti bekerja.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
