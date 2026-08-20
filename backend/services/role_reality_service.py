"""**CEK KENYATAAN PERAN** — utang migrasi (ii) FASE E-8/E-6.

KENAPA BERKAS INI ADA
=====================
FASE E-8 menambah dua peran (`sales_admin`, `finance`) karena sebelumnya orang yang
mengurus alur pesanan **harus** dijadikan `manager` — satu-satunya peran yang bisa
Konfirmasi SO. Akibatnya orang itu ikut menerima kuasa manajer yang tidak pernah ia
butuhkan: **tutup buku · payroll · bayar tagihan supplier · hapus master data**.

Peran barunya sudah ada, tetapi **akun lamanya masih `manager`**. `plan.md` §8 mencatat
ini sebagai utang yang sengaja ditunda dengan kalimat: *"daftar akun `manager` yang
sebenarnya Admin Sales/Finance dan perlu diubah perannya"*. Membuat daftar itu **dengan
tangan** adalah tebakan; di sistem yang sudah berjalan tebakan soal wewenang berbahaya
dua arah (mencabut hak orang yang benar-benar manajer, atau membiarkan kuasa berlebih).

Berkas ini membuat daftar itu **dari jejak nyata**, bukan dari asumsi.

CARA KERJANYA — TIGA LANGKAH, SEMUANYA BERBASIS BUKTI
=====================================================
1. **Kumpulkan jejak.** Dua sumber, keduanya data nyata:
   · `audit_logs` (`user_id` + `user_name` + `action` + `resource`) — paling kuat, ada
     tanggalnya; · **field pembuat dokumen** (`created_by`, `approved_by`, `issued_by`, …)
   pada 20 koleksi bisnis. Sumber kedua penting karena banyak dokumen lama dibuat sebelum
   jejak audit selengkap sekarang.
2. **Terjemahkan tiap jejak menjadi (module, action) izin** lewat `ACTIVITIES` di bawah —
   pasangan yang **sama** dengan yang dipakai `require_permission()` di router. Jadi
   pertanyaannya bukan "menurut saya ini pekerjaan siapa" melainkan
   **"izin apa yang secara teknis dibutuhkan untuk melakukan ini"**.
3. **Cari peran TERENDAH yang masih bisa melakukan SEMUA jejak itu**, dibaca langsung dari
   `permissions_config.DEFAULT_PERMISSIONS` + peringkat dari `role_registry`. Tidak ada
   tabel kedua yang bisa bercabang dari matriks izin sungguhan.

EMPAT KESIMPULAN YANG MUNGKIN
-----------------------------
| Kesimpulan | Arti | Tindakan yang ditawarkan |
|---|---|---|
| `kuasa_berlebih` | peran sekarang **lebih tinggi** dari yang dibutuhkan kenyataan | turunkan ke peran usulan |
| `pisah_tugas` | jejaknya mencakup dua domain yang **sengaja dipisah** (alur pesanan ↔ uang & pajak) sehingga TIDAK ADA satu peran non-manajer yang menampungnya | **dua akun**, bukan satu — SD2 |
| `di_luar_peran` | ia pernah melakukan hal yang peran sekarang **tidak** boleh (dokumen lama sebelum izin diperketat, atau lubang izin) | tinjau: naikkan peran atau akui sebagai riwayat |
| `sesuai` / `tanpa_jejak` | peran cocok · atau belum ada jejak sama sekali | **tidak menebak** |

ATURAN YANG SENGAJA DIPEGANG
---------------------------
* **Tanpa jejak = tanpa usulan.** Akun baru tidak boleh diturunkan hanya karena belum
  dipakai. `tanpa_jejak` bukan temuan.
* **Jejak sistem dibuang.** `seed`, `system`, `Sistem Seed`, `Admin` (literal lama) bukan
  orang; ikut dihitung berarti menuduh akun yang salah.
* **`admin` tidak diusulkan turun.** Ia memang penjaga sistem; menurunkannya berdasar
  aktivitas berarti sistem bisa kehilangan admin terakhir.
* **Kegiatan yang belum dipetakan DILAPORKAN** (`unmapped`), tidak dibuang diam-diam —
  supaya cakupan tidak pernah terlihat lebih lengkap dari kenyataannya.
"""
from typing import Any, Dict, List, Optional, Set, Tuple

from db import db
from permissions_config import DEFAULT_PERMISSIONS
from role_registry import ROLES, rank_of, role_label

# ─── Penanda "bukan orang" ───────────────────────────────────────────────────
#: Nilai yang muncul di field pembuat dokumen tetapi bukan akun manusia. Diambil dari
#: data nyata (`distinct` atas 20 koleksi): seeder & proses otomatis menulis namanya
#: sendiri ke `created_by` karena field itu bertipe teks bebas sejak awal.
SYSTEM_ACTORS = {
    "", "seed", "seeder", "system", "sistem", "sistem seed", "seed data",
    "admin", "administrator", "auto", "scheduler", "migrasi", "migration",
}

#: Kegiatan yang dijalankan SISTEM, bukan orang (pekerjaan latar/otomatis). Dibuang
#: dari penilaian **dan** dari daftar "belum dipetakan" — memetakannya ke izin akan
#: menuduh orang atas hal yang dikerjakan mesin.
SYSTEM_ACTIONS = {
    "g6_ic_elimination_synced", "outbound_tasks_auto_created",
    "backorder_auto_fulfilled", "scheduler_run", "gate_probe",
}

#: Domain untuk BAHASA MANUSIA di layar (bukan dipakai untuk mengambil keputusan —
#: keputusan memakai matriks izin). Urutan = urutan tampil.
DOMAINS: Dict[str, str] = {
    "alur_pesanan": "Alur pesanan (SO, pemenuhan, retur)",
    "uang_pajak": "Uang masuk & pajak keluaran",
    "gudang": "Operasi gudang",
    "pembelian": "Pembelian & hutang supplier",
    "keputusan_manajerial": "Keputusan manajerial (persetujuan, tutup buku)",
    "administrasi_sistem": "Administrasi sistem (akun, badan usaha)",
}

#: Dua domain yang **sengaja dipisah** oleh keputusan pemilik E8.2/E8.10b#2
#: (yang mengurus pesanan tidak boleh menyentuh uang masuk & faktur pajak).
SEGREGATED_PAIR = ("alur_pesanan", "uang_pajak")


def _act(key: str, label: str, module: str, action: str, domain: str,
         audit_actions: Optional[List[str]] = None,
         audit_pairs: Optional[List[Tuple[str, str]]] = None,
         docs: Optional[List[Tuple[str, str, str]]] = None) -> Dict[str, Any]:
    """Satu jenis kegiatan + di mana jejaknya bisa dibaca.

    `docs` = (koleksi, field pelaku, field nomor dokumen).
    """
    return {"key": key, "label": label, "module": module, "action": action,
            "domain": domain, "audit_actions": audit_actions or [],
            "audit_pairs": audit_pairs or [], "docs": docs or []}


# ─── REGISTRY KEGIATAN ───────────────────────────────────────────────────────
# Setiap baris = jejak nyata → (module, action) yang dipakai `require_permission`.
ACTIVITIES: List[Dict[str, Any]] = [
    # ── Alur pesanan ────────────────────────────────────────────────────────
    _act("order_create", "Membuat pesanan penjualan", "order", "create", "alur_pesanan",
         audit_actions=["order_created"], audit_pairs=[("CREATE", "sales_order")],
         docs=[("sales_orders", "created_by", "number")]),
    _act("order_confirm", "Mengonfirmasi pesanan", "order", "confirm", "alur_pesanan",
         audit_actions=["order_confirmed"],
         docs=[("sales_orders", "confirmed_by", "number")]),
    _act("order_verify", "Verifikasi administratif pesanan", "order", "verify",
         "alur_pesanan", audit_actions=["order_verified"],
         docs=[("sales_orders", "verified_by", "number")]),
    _act("order_deliver", "Menandai pesanan terkirim", "order", "deliver", "alur_pesanan",
         audit_actions=["order_delivered", "order_marked_delivered"],
         docs=[("sales_orders", "delivered_by", "number")]),
    _act("sales_return_create", "Mengajukan retur pelanggan", "sales_return", "create",
         "alur_pesanan", audit_actions=["sales_return_created"],
         docs=[("sales_returns", "created_by", "number")]),
    _act("sales_return_process", "Memproses retur (periksa, karantina, selesaikan)",
         "sales_return", "update", "alur_pesanan",
         audit_actions=["sales_return_inspect_started", "sales_return_inspected",
                        "sales_return_quarantine_released", "sales_return_settled"]),
    _act("interco_create", "Membuat transaksi antar-badan-usaha", "interco", "create",
         "alur_pesanan",
         audit_actions=["interco_transaction_created", "interco_return_created"],
         docs=[("interco_transactions", "created_by", "number"),
               ("interco_returns", "created_by", "number")]),
    _act("interco_invoice", "Menagihkan transaksi antar-badan-usaha", "interco", "invoice",
         "alur_pesanan", audit_actions=["interco_transaction_invoiced"]),
    _act("internal_request_create", "Membuat permintaan internal",
         "internal_request", "create", "alur_pesanan",
         audit_actions=["internal_request_created"],
         docs=[("internal_requests", "created_by", "number")]),
    _act("internal_request_convert", "Memutus permintaan internal jadi transaksi",
         "internal_request", "convert", "alur_pesanan",
         audit_actions=["internal_request_converted"],
         docs=[("internal_requests", "decided_by", "number")]),
    _act("transfer_create", "Membuat transfer gudang", "transfer", "create",
         "alur_pesanan", audit_actions=["transfer_created"],
         docs=[("warehouse_transfers", "created_by", "number")]),
    _act("pr_create", "Mengajukan pembelian (PR)", "purchase_requisition", "create",
         "alur_pesanan", audit_actions=["purchase_requisition_created"],
         docs=[("purchase_requisitions", "created_by", "number")]),
    _act("price_approval_request", "Mengajukan harga khusus", "price_approval", "create",
         "alur_pesanan", audit_actions=["price_approval_requested"],
         docs=[("price_approvals", "requested_by", "number")]),

    # ── Uang masuk & pajak keluaran (domain `finance`) ──────────────────────
    _act("ar_receipt_create", "Mencatat uang masuk (kwitansi AR)", "ar_receipt", "create",
         "uang_pajak", audit_actions=["ar_receipt_created", "ar_receipt_posted"],
         docs=[("ar_receipts", "created_by", "number")]),
    _act("tax_invoice_create", "Menerbitkan faktur pajak keluaran", "tax_invoice",
         "create", "uang_pajak",
         audit_actions=["tax_invoice_issued", "interco_tax_invoice_issued"],
         docs=[("tax_invoices", "created_by", "number")]),
    _act("payment_variance_decide", "Memutus selisih pembayaran", "payment_variance",
         "decide", "uang_pajak", audit_actions=["payment_variance_decided"]),
    _act("penalty_issue", "Menerbitkan denda", "penalty", "issue", "uang_pajak",
         audit_actions=["penalty_issued"],
         docs=[("penalties", "issued_by", "number")]),
    _act("cash_create", "Mencatat kas", "cash", "create", "uang_pajak",
         audit_actions=["cash_transaction_created"],
         docs=[("cash_transactions", "created_by", "number")]),
    _act("payment_plan_create", "Membuat rencana pembayaran", "payment_plan", "create",
         "uang_pajak", audit_actions=["payment_plan_created"],
         docs=[("payment_plans", "created_by", "number")]),

    # ── Operasi gudang ──────────────────────────────────────────────────────
    _act("wms_receive", "Menerima barang di gudang", "wms", "update", "gudang",
         audit_actions=["inbound_completed", "inbound_scan_receive"],
         audit_pairs=[("COMPLETE", "inbound_task")]),
    _act("wms_dispatch", "Mengirim barang dari gudang", "wms", "dispatch", "gudang",
         audit_actions=["outbound_dispatched", "outbound_shipped"]),
    _act("qc_decide", "Keputusan QC", "wms", "update", "gudang",
         audit_actions=["qc_decision"]),

    # ── Pembelian & hutang supplier ─────────────────────────────────────────
    _act("po_create", "Membuat pesanan pembelian (PO)", "purchase_order", "create",
         "pembelian", audit_actions=["po_created"],
         audit_pairs=[("CREATE", "purchase_order")],
         docs=[("purchase_orders", "created_by", "number")]),
    _act("purchase_return_create", "Membuat retur ke supplier", "purchase_return",
         "create", "pembelian", audit_actions=["purchase_return_created"],
         docs=[("purchase_returns", "created_by", "number")]),
    _act("vendor_bill_create", "Mencatat tagihan supplier", "vendor_bill", "create",
         "pembelian", audit_actions=["vendor_bill_created", "vendor_bill_posted"],
         docs=[("vendor_bills", "created_by", "number")]),
    _act("supplier_contract_create", "Membuat kontrak supplier", "supplier_contract",
         "create", "pembelian", audit_actions=["supplier_contract_created"]),

    # ── Keputusan manajerial ────────────────────────────────────────────────
    _act("order_approve", "Menyetujui pesanan (nilai/kredit)", "order", "approve",
         "keputusan_manajerial", audit_actions=["order_approved"],
         audit_pairs=[("APPROVE", "sales_order")],
         docs=[("sales_orders", "approved_by", "number")]),
    _act("sales_return_approve", "Menyetujui retur pelanggan", "sales_return", "approve",
         "keputusan_manajerial", audit_actions=["sales_return_approved"],
         docs=[("sales_returns", "approved_by", "number")]),
    _act("price_approval_decide", "Menyetujui harga khusus", "price_approval", "approve",
         "keputusan_manajerial", audit_actions=["price_approval_approved"],
         docs=[("price_approvals", "approved_by", "number")]),
    _act("po_approve", "Menyetujui PO", "purchase_order", "approve",
         "keputusan_manajerial", audit_actions=["po_approved"],
         docs=[("purchase_orders", "approved_by", "number")]),
    _act("pr_approve", "Menyetujui PR", "purchase_requisition", "approve",
         "keputusan_manajerial", audit_actions=["purchase_requisition_approved"],
         docs=[("purchase_requisitions", "approved_by", "number")]),
    _act("vendor_bill_pay", "Membayar tagihan supplier", "vendor_bill", "pay",
         "keputusan_manajerial", audit_actions=["vendor_bill_payment"]),
    _act("contra_bon_pay", "Membayar kontrabon", "contra_bon", "pay",
         "keputusan_manajerial", audit_actions=["contra_bon_paid"]),
    _act("contra_bon_approve", "Menyetujui kontrabon", "contra_bon", "approve",
         "keputusan_manajerial", audit_actions=["contra_bon_approved"],
         docs=[("contra_bons", "approved_by", "number")]),
    _act("contra_bon_verify", "Verifikasi kontrabon", "contra_bon", "verify",
         "keputusan_manajerial", audit_actions=["contra_bon_verified"],
         docs=[("contra_bons", "verified_by", "number")]),
    _act("interco_settle", "Menyelesaikan saldo antar-badan-usaha", "interco", "settle",
         "keputusan_manajerial", audit_actions=["interco_settlement_created"]),
    _act("accounting_post", "Membuat jurnal akuntansi", "accounting", "create",
         "keputusan_manajerial", audit_actions=["journal_entry_created", "gl_posted"],
         docs=[("journal_entries", "created_by", "number")]),
    _act("accounting_close", "Tutup buku periode", "accounting", "manage",
         "keputusan_manajerial",
         audit_actions=["period_closed", "closing_created", "period_reclosed"]),
    _act("transfer_approve", "Menyetujui transfer gudang", "transfer", "approve",
         "keputusan_manajerial", audit_actions=["transfer_approved"],
         docs=[("warehouse_transfers", "approved_by", "number")]),

    # ── Administrasi sistem ─────────────────────────────────────────────────
    _act("user_manage", "Mengelola akun & hak akses", "user", "update",
         "administrasi_sistem",
         audit_actions=["user_created", "user_updated", "user_deactivated",
                        "user_reactivated", "user_password_reset",
                        "user_sessions_revoked", "role_reclassified"]),
    _act("entity_manage", "Mengelola badan usaha", "entity", "update",
         "administrasi_sistem",
         audit_actions=["entity_created", "entity_updated", "entity_archived",
                        "entity_reactivated"]),

    # ── Tambahan cakupan (semula muncul di `unmapped_actions`) ──────────────
    # Dipetakan setelah membaca SIAPA yang benar-benar melakukannya di data nyata,
    # supaya pemetaan tidak melahirkan temuan palsu.
    _act("order_submit", "Mengajukan pesanan untuk persetujuan", "order", "create",
         "alur_pesanan", audit_actions=["order_submitted"]),
    _act("interco_ship_receive", "Menjalankan kirim/terima antar-badan-usaha",
         "interco", "receive", "alur_pesanan",
         audit_actions=["inter_company_transfer_executed"]),
    _act("interco_task", "Membuat tugas gudang antar-badan-usaha", "interco", "ship",
         "alur_pesanan", audit_actions=["interco_warehouse_task_created",
                                        "interco_return_task_created"]),
    _act("interco_return_approve", "Menyetujui retur antar-badan-usaha", "interco",
         "return", "keputusan_manajerial", audit_actions=["interco_return_approved"]),
    _act("contra_bon_create", "Membuat kontrabon", "contra_bon", "create", "pembelian",
         audit_actions=["contra_bon_created"],
         docs=[("contra_bons", "created_by", "number")]),
    _act("contra_bon_update", "Mengurus kontrabon (ajukan, jadwalkan, potong)",
         "contra_bon", "update", "pembelian",
         audit_actions=["contra_bon_submitted", "contra_bon_scheduled",
                        "contra_bon_deduction_added", "supplier_invoice_exchange_set"]),
    _act("wms_escalate", "Menaikkan masalah penerimaan (eskalasi)", "wms", "update",
         "gudang", audit_actions=["ESCALATE"]),
    _act("wms_escalation_resolve", "Memutus eskalasi penerimaan", "wms", "approve",
         "keputusan_manajerial", audit_actions=["RESOLVE_ESCALATION"]),
]

_BY_KEY = {a["key"]: a for a in ACTIVITIES}


# ─── Pembacaan matriks izin (SSOT: permissions_config) ───────────────────────
def _role_allows(role: str, module: str, action: str,
                 matrix: Dict[str, Dict[str, List[str]]]) -> bool:
    allowed = (matrix.get(role) or {}).get(module) or []
    return action in allowed or "*" in allowed


def roles_that_can(pairs: Set[Tuple[str, str]],
                   matrix: Dict[str, Dict[str, List[str]]]) -> List[str]:
    """Peran mana saja yang bisa melakukan SEMUA pasangan izin ini (urut peringkat)."""
    out = [rid for rid in ROLES
           if all(_role_allows(rid, m, a, matrix) for m, a in pairs)]
    return sorted(out, key=lambda r: (rank_of(r), ROLES[r]["order"]))


# ─── Pengumpulan jejak ───────────────────────────────────────────────────────
def _norm(value: Any) -> str:
    return str(value or "").strip()


async def _user_index() -> Tuple[Dict[str, Dict[str, Any]], Dict[str, str]]:
    """(akun per id, peta nama-lowercase → id).

    Peta nama diperlukan karena field pembuat dokumen di repo ini **tidak seragam**:
    sebagian menyimpan `user_id` (`user_sales_01`), sebagian menyimpan nama tampilan
    (`Budi Santoso`). Itu drift nyata (lihat temuan S4 audit sesi #071); di sini
    ditangani, bukan diasumsikan bersih.
    """
    rows = await db.users.find({}, {"_id": 0, "password_hash": 0}).to_list(2000)
    by_id = {r["id"]: r for r in rows}
    by_name: Dict[str, str] = {}
    for r in rows:
        nama = _norm(r.get("name")).lower()
        if nama and nama not in SYSTEM_ACTORS:
            by_name.setdefault(nama, r["id"])
    return by_id, by_name


def _resolve_actor(raw: Any, by_id: Dict[str, Dict[str, Any]],
                   by_name: Dict[str, str]) -> str:
    token = _norm(raw)
    if not token or token.lower() in SYSTEM_ACTORS:
        return ""
    if token in by_id:
        return token
    return by_name.get(token.lower(), "")


async def _collect_from_audit(by_id, by_name) -> Tuple[Dict[str, Dict[str, Any]],
                                                       Dict[str, int]]:
    """Jejak dari `audit_logs` — sumber terkuat (ada pelaku + waktu).

    **DUA BENTUK BARIS, KEDUANYA WAJIB DIBACA** (drift nyata, bukan teori):
      · bentuk *runtime* dari `dependencies.audit()` → `actor` (NAMA) · `entity_type` ·
        `entity_id` · `after`;
      · bentuk *seed/awal* → `user_id` + `user_name` · `resource` · `resource_id` ·
        `details`.
    Di basis data demo: **88 dari 100 baris memakai bentuk pertama.** Versi pertama
    fungsi ini hanya membaca bentuk kedua sehingga 88 baris jejak hilang tanpa error —
    laporan tetap terlihat "berhasil" padahal nyaris tak melihat apa pun. Kelas cacat
    yang sama dengan `KN-E6-DERIVED-FROM-LIST`: data dibaca dari bentuk yang salah dan
    hasilnya diam-diam kosong.
    """
    hits: Dict[str, Dict[str, Any]] = {}
    unmapped: Dict[str, int] = {}
    action_map: Dict[str, str] = {}
    pair_map: Dict[Tuple[str, str], str] = {}
    for a in ACTIVITIES:
        for name in a["audit_actions"]:
            action_map[name] = a["key"]
        for pair in a["audit_pairs"]:
            pair_map[pair] = a["key"]

    cursor = db.audit_logs.find(
        {}, {"_id": 0, "user_id": 1, "user_name": 1, "actor": 1, "action": 1,
             "resource": 1, "entity_type": 1, "resource_id": 1, "entity_id": 1,
             "timestamp": 1, "details": 1, "after": 1, "scope_entity_id": 1})
    async for row in cursor:
        action = _norm(row.get("action"))
        if action == "login" or action in SYSTEM_ACTIONS:
            continue
        uid = (_resolve_actor(row.get("user_id"), by_id, by_name)
               or _resolve_actor(row.get("user_name"), by_id, by_name)
               or _resolve_actor(row.get("actor"), by_id, by_name))
        jenis = _norm(row.get("resource") or row.get("entity_type"))
        key = action_map.get(action) or pair_map.get((action, jenis))
        if not key:
            if uid:
                unmapped[action] = unmapped.get(action, 0) + 1
            continue
        if not uid:
            continue
        bucket = hits.setdefault(uid, {}).setdefault(
            key, {"count": 0, "last_at": "", "samples": [], "sources": set()})
        bucket["count"] += 1
        bucket["sources"].add("jejak audit")
        ts = _norm(row.get("timestamp"))
        if ts > bucket["last_at"]:
            bucket["last_at"] = ts
        det = row.get("details") or row.get("after") or {}
        if not isinstance(det, dict):
            det = {}
        label = _norm(det.get("number") or det.get("order_number")
                      or det.get("po_number")
                      or row.get("resource_id") or row.get("entity_id"))
        if label and label not in bucket["samples"] and len(bucket["samples"]) < 4:
            bucket["samples"].append(label)
    return hits, unmapped


async def _collect_from_docs(by_id, by_name) -> Dict[str, Dict[str, Any]]:
    """Jejak dari field pembuat dokumen — menjangkau dokumen tua tanpa baris audit."""
    hits: Dict[str, Dict[str, Any]] = {}
    existing = set(await db.list_collection_names())
    for a in ACTIVITIES:
        for coll, field, num_field in a["docs"]:
            if coll not in existing:
                continue
            proj = {"_id": 0, field: 1, num_field: 1, "created_at": 1, "updated_at": 1}
            async for row in db[coll].find({field: {"$nin": [None, ""]}}, proj):
                uid = _resolve_actor(row.get(field), by_id, by_name)
                if not uid:
                    continue
                bucket = hits.setdefault(uid, {}).setdefault(
                    a["key"], {"count": 0, "last_at": "", "samples": [],
                               "sources": set()})
                bucket["count"] += 1
                bucket["sources"].add(f"dokumen {coll}")
                ts = _norm(row.get("updated_at") or row.get("created_at"))
                if ts > bucket["last_at"]:
                    bucket["last_at"] = ts
                num = _norm(row.get(num_field))
                if num and num not in bucket["samples"] and len(bucket["samples"]) < 4:
                    bucket["samples"].append(num)
    return hits


def _merge(a: Dict[str, Dict[str, Any]], b: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for src in (a, b):
        for uid, acts in src.items():
            dest = out.setdefault(uid, {})
            for key, ev in acts.items():
                cur = dest.setdefault(key, {"count": 0, "last_at": "", "samples": [],
                                            "sources": set()})
                cur["count"] += ev["count"]
                cur["sources"] |= ev["sources"]
                if ev["last_at"] > cur["last_at"]:
                    cur["last_at"] = ev["last_at"]
                for s in ev["samples"]:
                    if s not in cur["samples"] and len(cur["samples"]) < 4:
                        cur["samples"].append(s)
    return out


# ─── Kesimpulan per akun ─────────────────────────────────────────────────────
#: Peringkat maksimum peran **PELAKSANA** (bukan penyetuju). `sales_admin`/`finance`
#: berperingkat 2; `manager` 3. Dipakai aturan pisah tugas: kalau pekerjaan klerikal
#: seseorang hanya bisa ditampung dengan memberi peran peringkat ≥3, artinya ia
#: memegang kuasa persetujuan hanya demi mengerjakan pekerjaan rutin.
EXECUTOR_MAX_RANK = 2


def executor_roles() -> List[str]:
    return [rid for rid in ROLES if rank_of(rid) <= EXECUTOR_MAX_RANK]


def two_executor_cover(pairs: Set[Tuple[str, str]],
                       matrix: Dict[str, Dict[str, List[str]]]
                       ) -> Optional[Tuple[str, str]]:
    """Bisakah pekerjaan ini dibagi ke **dua akun pelaksana** (tanpa peran manajer)?

    Kalau ya, memberi satu orang peran manajer hanya untuk mengerjakan dua pekerjaan
    rutin adalah kuasa berlebih yang tersembunyi — jalan keluarnya dua akun, sesuai
    keputusan pemilik E8.2/E8.10b#2 (yang mengurus pesanan tidak menyentuh uang masuk
    & faktur pajak).
    """
    execs = executor_roles()
    for i, r1 in enumerate(execs):
        for r2 in execs[i + 1:]:
            if all(_role_allows(r1, m, a, matrix) or _role_allows(r2, m, a, matrix)
                   for m, a in pairs):
                return (r1, r2)
    return None


def _verdict(role: str, keys: List[str],
             matrix: Dict[str, Dict[str, List[str]]]) -> Dict[str, Any]:
    """Bandingkan peran sekarang dengan peran TERENDAH yang cukup untuk jejaknya."""
    if not keys:
        return {"verdict": "tanpa_jejak", "suggested_role": "",
                "headline": "Belum ada jejak kegiatan — peran tidak dinilai.",
                "beyond": [], "split": {}}

    pairs = {(_BY_KEY[k]["module"], _BY_KEY[k]["action"]) for k in keys}
    candidates = roles_that_can(pairs, matrix)

    # Jejak yang peran SEKARANG saja tidak boleh melakukannya.
    beyond = [k for k in keys
              if not _role_allows(role, _BY_KEY[k]["module"], _BY_KEY[k]["action"], matrix)]

    if beyond:
        return {
            "verdict": "di_luar_peran",
            "suggested_role": candidates[0] if candidates else "",
            "headline": (
                f"Ada {len(beyond)} kegiatan yang peran {role_label(role)} "
                f"sekarang TIDAK boleh lakukan — periksa apakah ini dokumen lama "
                f"sebelum izin diperketat, atau peran akunnya kurang."),
            "beyond": beyond, "split": {},
        }
    if role == "admin":
        # Admin tidak diusulkan turun: ia penjaga sistem (dan pagar "admin terakhir").
        return {"verdict": "sesuai", "suggested_role": "",
                "headline": "Admin sistem — peran tidak dinilai dari aktivitas.",
                "beyond": [], "split": {}}

    suggested = candidates[0] if candidates else ""
    cur_rank = rank_of(role)
    if suggested and rank_of(suggested) < cur_rank:
        return {
            "verdict": "kuasa_berlebih", "suggested_role": suggested,
            "headline": (
                f"Seluruh pekerjaannya bisa dilakukan sebagai {role_label(suggested)}. "
                f"Sebagai {role_label(role)} ia ikut memegang kuasa yang tidak pernah "
                f"ia pakai."),
            "beyond": [], "split": {},
        }

    # Tidak ada SATU peran pelaksana yang menampungnya, tetapi DUA akun pelaksana bisa.
    single_exec = [r for r in candidates if rank_of(r) <= EXECUTOR_MAX_RANK]
    pasangan = None if single_exec else two_executor_cover(pairs, matrix)
    if pasangan and cur_rank > EXECUTOR_MAX_RANK:
        groups: Dict[str, List[str]] = {}
        for k in keys:
            groups.setdefault(_BY_KEY[k]["domain"], []).append(k)
        split: Dict[str, Dict[str, Any]] = {}
        for domain, dkeys in groups.items():
            dpairs = {(_BY_KEY[k]["module"], _BY_KEY[k]["action"]) for k in dkeys}
            cocok = [r for r in pasangan
                     if all(_role_allows(r, m, a, matrix) for m, a in dpairs)]
            split[domain] = {"activity_keys": dkeys,
                             "suggested_role": cocok[0] if cocok else ""}
        both = SEGREGATED_PAIR[0] in groups and SEGREGATED_PAIR[1] in groups
        return {
            "verdict": "pisah_tugas", "suggested_role": "",
            "headline": (
                "Akun ini mengerjakan alur pesanan DAN uang/pajak sekaligus. "
                "Keputusan pemilik memisahkan keduanya, jadi jalan keluarnya "
                f"DUA akun ({role_label(pasangan[0])} + {role_label(pasangan[1])}) — "
                f"bukan satu akun {role_label(role)}."
                if both else
                "Pekerjaannya bisa dibagi ke dua akun pelaksana "
                f"({role_label(pasangan[0])} + {role_label(pasangan[1])}); memberi "
                f"peran {role_label(role)} berarti memberi kuasa persetujuan hanya "
                "demi pekerjaan rutin."),
            "beyond": beyond, "split": split,
        }
    if not candidates:
        return {"verdict": "pisah_tugas", "suggested_role": "",
                "headline": ("Jejaknya tidak tertampung oleh satu peran mana pun — "
                             "perlu ditinjau manual."),
                "beyond": beyond, "split": {}}
    return {"verdict": "sesuai", "suggested_role": "",
            "headline": f"Peran {role_label(role)} sudah pas dengan kegiatannya.",
            "beyond": [], "split": {}}


def _entity_names(entities: List[Dict[str, Any]]) -> Dict[str, str]:
    """id → NAMA SINGKAT saja (INV-UI-02: id teknis tak boleh sampai ke layar)."""
    return {e["id"]: (e.get("short_name") or e.get("name") or "—") for e in entities}


async def build_report(entity_id: str = "", role_filter: str = "") -> Dict[str, Any]:
    """Laporan "Cek Kenyataan Peran" — siap dipakai layar & POC."""
    matrix = DEFAULT_PERMISSIONS
    record = await db.permission_settings.find_one({"id": "default"}, {"_id": 0})
    if record and record.get("matrix"):
        # Pemilik boleh menyunting matriks di Pusat Pengaturan; laporan HARUS memakai
        # matriks yang benar-benar berlaku, bukan bawaan kode.
        matrix = record["matrix"]

    by_id, by_name = await _user_index()
    audit_hits, unmapped = await _collect_from_audit(by_id, by_name)
    doc_hits = await _collect_from_docs(by_id, by_name)
    hits = _merge(audit_hits, doc_hits)

    entities = await db.business_entities.find(
        {}, {"_id": 0, "id": 1, "name": 1, "short_name": 1}).to_list(200)
    ent_names = _entity_names(entities)

    rows: List[Dict[str, Any]] = []
    for uid, user in by_id.items():
        if role_filter and user.get("role") != role_filter:
            continue
        allowed = list(user.get("allowed_entity_ids") or [])
        home = user.get("home_entity_id") or ""
        if entity_id and entity_id != "all" and entity_id != home and entity_id not in allowed:
            continue

        acts = hits.get(uid, {})
        keys = sorted(acts, key=lambda k: -acts[k]["count"])
        verdict = _verdict(user.get("role", ""), keys, matrix)

        evidence = []
        for k in keys:
            a, ev = _BY_KEY[k], acts[k]
            evidence.append({
                "key": k, "label": a["label"], "domain": a["domain"],
                "domain_label": DOMAINS.get(a["domain"], a["domain"]),
                "permission": f"{a['module']}.{a['action']}",
                "count": ev["count"], "last_at": ev["last_at"],
                "samples": ev["samples"], "sources": sorted(ev["sources"]),
                "beyond_current_role": k in verdict["beyond"],
            })
        domains = []
        for d in DOMAINS:
            if any(e["domain"] == d for e in evidence):
                domains.append({"key": d, "label": DOMAINS[d]})

        rows.append({
            "user_id": uid,
            "name": user.get("name") or user.get("email") or "—",
            "email": user.get("email") or "",
            "role": user.get("role") or "",
            "role_label": role_label(user.get("role") or ""),
            "status": user.get("status") or "active",
            "home_entity_name": ent_names.get(home, "—"),
            "entity_names": [ent_names[e] for e in allowed if e in ent_names],
            "activity_total": sum(acts[k]["count"] for k in keys),
            "domains": domains,
            "evidence": evidence,
            "verdict": verdict["verdict"],
            "headline": verdict["headline"],
            "suggested_role": verdict["suggested_role"],
            "suggested_role_label": role_label(verdict["suggested_role"])
            if verdict["suggested_role"] else "",
            "split": [
                {"domain": d, "domain_label": DOMAINS.get(d, d),
                 "suggested_role": v["suggested_role"],
                 "suggested_role_label": role_label(v["suggested_role"])
                 if v["suggested_role"] else "",
                 "activities": [_BY_KEY[k]["label"] for k in v["activity_keys"]]}
                for d, v in (verdict["split"] or {}).items()
            ],
        })

    order = {"pisah_tugas": 0, "kuasa_berlebih": 1, "di_luar_peran": 2,
             "sesuai": 3, "tanpa_jejak": 4}
    rows.sort(key=lambda r: (order.get(r["verdict"], 9), -r["activity_total"], r["name"]))

    summary = {
        "accounts": len(rows),
        "perlu_ditinjau": sum(1 for r in rows if r["verdict"] in
                              ("kuasa_berlebih", "pisah_tugas", "di_luar_peran")),
        "kuasa_berlebih": sum(1 for r in rows if r["verdict"] == "kuasa_berlebih"),
        "pisah_tugas": sum(1 for r in rows if r["verdict"] == "pisah_tugas"),
        "di_luar_peran": sum(1 for r in rows if r["verdict"] == "di_luar_peran"),
        "sesuai": sum(1 for r in rows if r["verdict"] == "sesuai"),
        "tanpa_jejak": sum(1 for r in rows if r["verdict"] == "tanpa_jejak"),
    }
    return {
        "rows": rows,
        "summary": summary,
        "activities_mapped": len(ACTIVITIES),
        "unmapped_actions": [{"action": k, "count": v} for k, v in
                             sorted(unmapped.items(), key=lambda kv: -kv[1])],
        "method": (
            "Jejak diambil dari catatan audit dan field pembuat dokumen, lalu setiap "
            "jejak diterjemahkan ke izin yang dibutuhkan. Peran usulan = peran TERENDAH "
            "yang masih bisa melakukan semua jejak itu."),
    }


async def row_for(user_id: str) -> Optional[Dict[str, Any]]:
    """Satu baris laporan (dipakai endpoint terap agar usulannya dihitung ulang)."""
    report = await build_report()
    for r in report["rows"]:
        if r["user_id"] == user_id:
            return r
    return None
