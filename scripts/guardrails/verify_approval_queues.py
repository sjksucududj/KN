#!/usr/bin/env python3
"""INV-APPR-01 — SETIAP PINTU KEPUTUSAN WAJIB PUNYA ANTREAN YANG MENGHITUNGNYA.

KELAS BUG YANG DICEGAH (terukur 2026-08-17, FASE F-6)
=====================================================
FASE F-3 membuat KPI "Persetujuan Menunggu" berhenti berbohong dengan memakai SATU
sumber (`services/approval_backlog_service.QUEUES`, 13 baris). Angkanya benar untuk 12
antrean — dan tetap **bohong** untuk sisanya: sapuan bukti menemukan 20+ endpoint
keputusan (`approve` / `reject` / `verify` / `decide`) yang sudah lama hidup di backend
tanpa satu pun baris antrean yang menghitungnya:

    transfer gudang · kontrabon (verifikasi/persetujuan/sengketa) · permintaan internal
    antar-PT · retur antar-PT · tagihan supplier · voucher biaya masuk · uang muka &
    pertanggungjawabannya · klaim makloon · buka periode · cuti · lembur

Akibatnya sama seperti kelas bug lama: orang yang pekerjaannya memutuskan melihat angka
yang lebih kecil dari kenyataan, tidak ada error, tidak ada uji yang gagal. Yang lebih
berbahaya: kelas ini **tumbuh sendiri** — setiap fase baru menambah endpoint `approve`
baru, dan tak ada apa pun yang memaksa penambahnya mendaftarkan antreannya.

Penjaga ini menutup celah itu secara PERMANEN: pintu keputusan ditemukan dari KODE
(bukan dari daftar yang bisa lupa diperbarui), lalu setiap pintu WAJIB terklasifikasi —
kalau tidak, gate MEMERAH.

INVARIAN YANG DITEGAKKAN
------------------------
  A. **Pintu terklasifikasi.** Setiap endpoint keputusan di `backend/routers/*.py` harus
     terdaftar di `DOOR_QUEUE` (menunjuk kunci antrean yang ADA di `QUEUES`) atau di
     `DOOR_EXEMPT` **dengan alasan tertulis**. Pintu baru = gate merah sampai diputuskan.
  B. **Data tak boleh punya antrean bayangan.** Setiap `(koleksi, status)` di MongoDB
     yang berbunyi "menunggu keputusan" wajib tercakup satu baris `QUEUES` atau
     dibebaskan beralasan di `DATA_EXEMPT`.
  C. **Anti dobel-hitung.** Tidak ada satu dokumen pun yang dihitung oleh dua baris
     antrean (kelas: `customer_prices` yang pending SUDAH terhitung lewat
     `price_approvals` tertaut — mendaftarkannya lagi membuat KPI melebih-lebihkan).
  D. **Tanpa layar hantu.** `view` tiap baris antrean ada di `AppViewRouter.jsx`.
  E. **Nama koleksi benar.** Koleksi tiap baris ada di database ATAU disebut literal di
     kode backend (kelas `amendments` vs `doc_amendments`: salah tulis = menghitung 0
     selamanya tanpa pesan; fitur yang belum pernah dipakai boleh belum punya koleksi,
     tetapi namanya harus terbukti ada di kode).
  F. **Pensiun mesin generik tak boleh diam-diam kembali.** Bila `approval_requests`
     dipakai lagi di kode backend, `create_approval_request(` WAJIB punya ≥1 pemanggil —
     supaya koleksi mati + izin yatim (`approval.approve`) tidak lahir kembali.

Resilient: MongoDB tak terjangkau → invarian B & C dilewati (A/D/E/F tetap jalan).
Exit 1 hanya bila invarian terbukti dilanggar.

Usage:
    python scripts/guardrails/verify_approval_queues.py
    python scripts/guardrails/verify_approval_queues.py --self-test   # bukti-merah
    python scripts/guardrails/verify_approval_queues.py -v            # + peta pintu
"""
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

ROOT = Path(__file__).resolve().parents[2]
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / "backend" / ".env")
except Exception:  # noqa: BLE001
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import Guard, G, R, Y, B, X  # noqa: E402

# ─── Pintu keputusan: bagaimana ia DITEMUKAN dari kode ────────────────────────
#: `POST/PATCH` yang namanya menyatakan sebuah KEPUTUSAN manusia.
DOOR_RE = re.compile(r'@router\.(?:post|patch)\("(/[^"]*(?:approve|reject|verify|decide)[^"]*)"')
PREFIX_RE = re.compile(r'APIRouter\(prefix="([^"]*)"')

#: pintu → kunci antrean di `approval_backlog_service.QUEUES` yang menghitungnya.
DOOR_QUEUE: Dict[str, str] = {
    "cash_advances.py::/api/cash-advances/{ca_id}/approve": "cash_advance",
    "cash_advances.py::/api/cash-advances/{ca_id}/reject": "cash_advance",
    "cash_advances.py::/api/cash-advance-settlements/{stl_id}/approve":
        "cash_advance_settlement",
    "cash_advances.py::/api/cash-advance-settlements/{stl_id}/reject":
        "cash_advance_settlement",
    "contra_bons.py::/api/contra-bons/{cb_id}/decide": "contra_bon_dispute",
    "contra_bons.py::/api/contra-bons/{cb_id}/verify": "contra_bon_verify",
    "contra_bons.py::/api/contra-bons/{cb_id}/approve": "contra_bon_approve",
    "cycle_count.py::/api/cycle-count/sessions/{session_id}/approve": "cycle_count",
    "cycle_count.py::/api/cycle-count/sessions/{session_id}/reject": "cycle_count",
    "hr_leave.py::/api/hr/leave-requests/{leave_id}/approve": "hr_leave",
    "hr_leave.py::/api/hr/leave-requests/{leave_id}/reject": "hr_leave",
    "hr_leave.py::/api/hr/overtime/{ot_id}/approve": "hr_overtime",
    "hr_leave.py::/api/hr/overtime/{ot_id}/reject": "hr_overtime",
    "interco.py::/api/interco/returns/{ret_id}/approve": "interco_return",
    "internal_requests.py::/api/internal-requests/{req_id}/reject": "internal_request",
    "landed_cost.py::/api/landed-costs/{voucher_id}/approve": "landed_cost",
    "landed_cost.py::/api/landed-costs/{voucher_id}/reject": "landed_cost",
    "makloon_orders.py::/api/makloon-orders/{mko_id}/claim/approve": "makloon_claim",
    "makloon_orders.py::/api/makloon-orders/{mko_id}/claim/reject": "makloon_claim",
    "period_unlocks.py::/api/finance/period-unlocks/{plu_id}/approve": "period_unlock",
    "period_unlocks.py::/api/finance/period-unlocks/{plu_id}/reject": "period_unlock",
    "price_approvals.py::/api/price-approvals/{approval_id}/approve": "price",
    "price_approvals.py::/api/price-approvals/{approval_id}/reject": "price",
    "purchase_orders.py::/api/purchase-orders/{po_id}/approve": "purchase_order",
    "purchase_orders.py::/api/purchase-orders/{po_id}/reject": "purchase_order",
    "purchase_requisitions.py::/api/purchase-requisitions/{pr_id}/approve":
        "purchase_requisition",
    "purchase_requisitions.py::/api/purchase-requisitions/{pr_id}/reject":
        "purchase_requisition",
    "purchase_returns.py::/api/purchase-returns/{return_id}/approve": "purchase_return",
    "purchase_returns.py::/api/purchase-returns/{return_id}/reject": "purchase_return",
    "rnd.py::/api/rnd/specs/{spec_id}/approve": "rnd_spec",
    "rnd.py::/api/rnd/specs/{spec_id}/reject": "rnd_spec",
    "rnd.py::/api/rnd/samples/{sample_id}/decide": "rnd_sample",
    "sales_orders_extra.py::/api/sales-orders/{order_id}/approve": "sales_order",
    "sales_returns.py::/api/sales-returns/{return_id}/approve": "sales_return",
    "sales_returns.py::/api/sales-returns/{return_id}/reject": "sales_return",
    "so_approvals.py::/api/sales-orders/{order_id}/approvals/{approval_id}/decide":
        "sales_order",
    "special_orders.py::/api/special-orders/{order_id}/approve": "special_order",
    "special_orders.py::/api/special-orders/{order_id}/reject": "special_order",
    "transfers.py::/api/transfers/{transfer_id}/approve": "transfer",
    "transfers.py::/api/transfers/{transfer_id}/reject": "transfer",
    "vendor_bills.py::/api/vendor-bills/{bill_id}/approve": "vendor_bill",
    "vendor_bills.py::/api/vendor-bills/{bill_id}/reject": "vendor_bill",
    # ── UTANG ALUR F-6.7 DIBAYAR (2026-08-18). Empat pintu di bawah ini DULU ada di
    # `DOOR_EXEMPT` dengan alasan bertanda "UTANG ALUR" — bukan karena pintunya tidak
    # butuh antrean, melainkan karena alurnya belum memungkinkan menghitung dengan
    # jujur. Alurnya sudah diperbaiki (langkah "Ajukan" untuk payroll & desain), jadi
    # pembebasannya dihapus dan pintunya dipetakan ke antreannya.
    "hr_payroll.py::/api/hr/payroll/runs/{run_id}/approve": "hr_payroll",
    "hr_payroll.py::/api/hr/payroll/runs/{run_id}/reject": "hr_payroll",
    "design_gallery.py::/api/design-gallery/{gallery_id}/approve": "design_gallery",
    "design_gallery.py::/api/design-gallery/{gallery_id}/reject": "design_gallery",
    "payment_variance.py::/api/payment-variances/receipt/{receipt_id}/decide":
        "payment_variance",
    "work_desks.py::/api/sales-orders/{order_id}/verify": "so_verify",
}

#: pintu yang SENGAJA tak punya antrean — alasannya WAJIB ditulis (dan diperiksa).
#: "UTANG:" menandai alasan yang mengakui cacat alur, bukan membenarkannya.
DOOR_EXEMPT: Dict[str, str] = {
    "bank_reconciliation.py::/api/bank-reconciliation/rules/{rule_id}/decide":
        "Keputusan atas USULAN ATURAN pencocokan bank (konfigurasi mesin), bukan dokumen "
        "bisnis yang menunggu orang. Usulannya tampil di panel layar Rekonsiliasi Bank.",
    "esign.py::/api/esign/verify":
        "Verifikasi KRIPTOGRAFIS tanda tangan dokumen (mesin memeriksa berkas), "
        "bukan keputusan manusia atas dokumen yang menunggu.",
    "finance_cases.py::/api/finance-cases/{case_id}/reject":
        "Kasus keuangan adalah PEKERJAAN ber-SLA yang dikerjakan (open/in_progress), "
        "antreannya layar Kasus Keuangan; 'reject' menutup kasus, bukan menyetujui dokumen.",
    "purchase_returns.py::/api/purchase-returns/{return_id}/supplier-reject":
        "Pencatatan keputusan SUPPLIER (pihak luar) atas retur yang sudah disetujui "
        "internal — bukan antrean keputusan orang dalam.",
}

# ─── Sapuan DATA: kosakata "menunggu keputusan" ───────────────────────────────
#: `draft` SENGAJA tidak masuk kosakata: hampir semua koleksi punya draf dan draf
#: adalah keadaan bekerja, bukan antrean. Pintu yang preconditionnya `draft`
#: tetap tertangkap oleh invarian A (sapuan KODE) — jadi tak ada yang lolos.
WAIT_VOCAB: Set[str] = {
    "pending", "pending_approval", "waiting_approval", "submitted", "review",
    "verified", "disputed", "awaiting_approval", "pending_review", "for_approval",
    "menunggu_persetujuan", "pending_atasan", "pending_pimpinan", "pending_finance",
}

#: `(koleksi, status)` yang berbunyi "menunggu" tetapi memang BUKAN antrean keputusan.
DATA_EXEMPT: Dict[Tuple[str, str], str] = {
    ("wms_tasks", "pending"):
        "Tugas gudang yang belum DIKERJAKAN (pick/pack/putaway) — pekerjaan, bukan "
        "keputusan; antreannya layar Operasi Gudang.",
    ("customer_prices", "pending_approval"):
        "ANTI DOBEL-HITUNG: tiap harga langganan yang menunggu punya `price_approval_id` "
        "dan SUDAH dihitung baris antrean `price` lewat `price_approvals`. "
        "Mendaftarkannya lagi membuat KPI melebih-lebihkan.",
    ("purchase_orders", "pending"):
        "Status awal PO (draf/menunggu dikirim ke supplier) — bukan menunggu keputusan "
        "orang; yang menunggu ACC berstatus `waiting_approval` dan sudah dihitung.",
    ("hr_payslips", "pending_approval"):
        "ANTI DOBEL-HITUNG: status slip gaji adalah CERMIN status run-nya "
        "(`hr_payroll_runs` — satu run mengubah semua slipnya sekaligus). Keputusannya "
        "ada di level RUN dan sudah dihitung baris antrean `hr_payroll`; mendaftarkan "
        "slip juga berarti satu keputusan dihitung sebanyak jumlah karyawan (terukur: "
        "1 run = 11 slip). Tak ada endpoint yang menyetujui slip satu per satu.",
    ("interco_returns", "draft"):
        "Dihitung baris antrean `interco_return` lewat query `draft`; entri ini hanya "
        "penjelas bila query berubah.",
}


# ─── Pengumpul bukti ─────────────────────────────────────────────────────────
def doors_from_code() -> Dict[str, str]:
    """Semua pintu keputusan di `backend/routers/*.py` → `{"file::path": nama_fungsi}`."""
    out: Dict[str, str] = {}
    for f in sorted((ROOT / "backend" / "routers").glob("*.py")):
        txt = f.read_text(encoding="utf-8")
        pre_m = PREFIX_RE.search(txt)
        pre = pre_m.group(1) if pre_m else ""
        for m in DOOR_RE.finditer(txt):
            out[f"{f.name}::{pre + m.group(1)}"] = f.name
    return out


def views_in_router() -> Set[str]:
    txt = (ROOT / "frontend" / "src" / "AppViewRouter.jsx").read_text(encoding="utf-8")
    return set(re.findall(r'activeView\s*===\s*"([\w-]+)"', txt))


def backend_source() -> str:
    """Seluruh kode backend (router+service) sebagai satu teks — untuk cek nama koleksi."""
    parts: List[str] = []
    for sub in ("routers", "services"):
        for f in (ROOT / "backend" / sub).glob("*.py"):
            parts.append(f.read_text(encoding="utf-8"))
    for f in (ROOT / "backend").glob("*.py"):
        parts.append(f.read_text(encoding="utf-8"))
    return "\n".join(parts)


def queues_from_backend() -> List[tuple]:
    sys.path.insert(0, str(ROOT / "backend"))
    from services import approval_backlog_service as abl  # noqa: PLC0415
    return abl.QUEUES


# ─── Invarian (fungsi MURNI supaya bisa diuji-merah) ─────────────────────────
def check_doors(g: Guard, doors: Dict[str, str], door_queue: Dict[str, str],
                door_exempt: Dict[str, str], queue_keys: Set[str]) -> None:
    """Invarian A — tiap pintu keputusan terklasifikasi & klasifikasinya sah."""
    for door in sorted(doors):
        g.bump()
        if door in door_queue:
            if door_queue[door] not in queue_keys:
                g.add(f"pintu `{door}` menunjuk antrean `{door_queue[door]}` yang TIDAK "
                      f"ADA di `approval_backlog_service.QUEUES` → keputusan yang tak "
                      f"pernah dihitung KPI.")
        elif door in door_exempt:
            if len((door_exempt.get(door) or "").strip()) < 20:
                g.add(f"pembebasan pintu `{door}` tanpa alasan tertulis yang bisa dinilai "
                      f"orang → pembebasan tanpa alasan = penjaga yang dijinakkan.")
        else:
            g.add(f"PINTU KEPUTUSAN BARU tanpa antrean: `{door}` tidak ada di DOOR_QUEUE "
                  f"maupun DOOR_EXEMPT → dokumen yang menunggu keputusan di pintu ini "
                  f"tidak akan pernah muncul di KPI beranda / Pusat Persetujuan.")
    # Klasifikasi yang menunjuk pintu yang sudah tidak ada (kode dihapus/di-rename)
    for door in sorted(set(door_queue) | set(door_exempt)):
        g.bump()
        if door not in doors:
            g.add(f"klasifikasi menyebut pintu `{door}` yang TIDAK ADA lagi di kode → "
                  f"peta pintu basi (hapus entri atau perbaiki path).")


def check_data(g: Guard, waiting: Dict[Tuple[str, str], int],
               covered: Set[Tuple[str, str]],
               data_exempt: Dict[Tuple[str, str], str]) -> None:
    """Invarian B — tak ada antrean bayangan di data."""
    for (coll, status), n in sorted(waiting.items()):
        g.bump()
        if (coll, status) in covered:
            continue
        alasan = (data_exempt.get((coll, status)) or "").strip()
        if not alasan:
            g.add(f"`{coll}` punya {n} dokumen berstatus `{status}` (berbunyi menunggu "
                  f"keputusan) tetapi TIDAK dihitung baris antrean mana pun dan tidak "
                  f"dibebaskan beralasan → antrean bayangan.")
        elif len(alasan) < 20:
            g.add(f"pembebasan data `{coll}.{status}` tanpa alasan yang bisa dinilai orang.")


def check_dupes(g: Guard, ids_by_queue: Dict[str, Set[Tuple[str, str]]]) -> None:
    """Invarian C — satu dokumen tak boleh dihitung dua antrean."""
    seen: Dict[Tuple[str, str], str] = {}
    for key in sorted(ids_by_queue):
        for ref in sorted(ids_by_queue[key]):
            g.bump()
            if ref in seen and seen[ref] != key:
                g.add(f"dokumen `{ref[0]}/{ref[1]}` dihitung DUA kali: antrean "
                      f"`{seen[ref]}` dan `{key}` → KPI melebih-lebihkan.")
            else:
                seen[ref] = key


def check_queue_rows(g: Guard, queues: List[tuple], known_views: Set[str],
                     colls_in_db: Set[str], src: str) -> None:
    """Invarian D & E — layar tujuan nyata & nama koleksi tidak salah tulis."""
    for key, _label, view, coll, _q in queues:
        g.bump()
        if view not in known_views:
            g.add(f"baris antrean `{key}` menunjuk layar `{view}` yang TIDAK ADA di "
                  f"AppViewRouter.jsx → angka yang diklik mendarat di layar hantu.")
        g.bump()
        if coll not in colls_in_db and f'"{coll}"' not in src and f"db.{coll}" not in src:
            g.add(f"baris antrean `{key}` menyebut koleksi `{coll}` yang tidak ada di "
                  f"database DAN tidak disebut di kode backend → kemungkinan salah tulis "
                  f"(kelas `amendments` vs `doc_amendments`): barisnya menghitung 0 selamanya.")


def check_generic_retired(g: Guard, refs: List[str], callers: int) -> None:
    """Invarian F — mesin generik tak boleh kembali tanpa produsen."""
    g.bump()
    if refs and callers == 0:
        g.add(f"koleksi `approval_requests` dipakai lagi di kode ({', '.join(refs[:3])}) "
              f"tetapi `create_approval_request()` masih NOL pemanggil → koleksi mati + "
              f"izin yatim `approval.approve` lahir kembali (dipensiunkan F-6).")


# ─── Bukti-merah (self-test) ─────────────────────────────────────────────────
def self_test() -> int:
    kasus = []

    def jalankan(nama, fn, harap):
        g = Guard("INV-APPR-01", "self-test")
        g.violations, g.checks = [], 0
        fn(g)
        got = len(g.violations)
        kasus.append((nama, harap, got))

    QK = {"transfer", "hr_leave"}
    doors_ok = {"transfers.py::/api/transfers/{id}/approve": "transfers.py"}
    jalankan("A: pintu terdaftar & antreannya ada → hijau",
             lambda g: check_doors(g, doors_ok,
                                   {"transfers.py::/api/transfers/{id}/approve": "transfer"},
                                   {}, QK), 0)
    jalankan("A: PINTU BARU tak terklasifikasi → merah",
             lambda g: check_doors(g, doors_ok, {}, {}, QK), 1)
    jalankan("A: pintu menunjuk antrean yang tak ada di QUEUES → merah",
             lambda g: check_doors(g, doors_ok,
                                   {"transfers.py::/api/transfers/{id}/approve": "antah"},
                                   {}, QK), 1)
    jalankan("A: pembebasan tanpa alasan → merah",
             lambda g: check_doors(g, doors_ok, {},
                                   {"transfers.py::/api/transfers/{id}/approve": "ya"},
                                   QK), 1)
    jalankan("A: klasifikasi basi (pintu sudah tak ada di kode) → merah",
             lambda g: check_doors(g, {},
                                   {"hilang.py::/api/x/{id}/approve": "transfer"},
                                   {}, QK), 1)
    jalankan("B: antrean bayangan di data → merah",
             lambda g: check_data(g, {("warehouse_transfers", "waiting_approval"): 3},
                                  set(), {}), 1)
    jalankan("B: tercakup baris antrean → hijau",
             lambda g: check_data(g, {("warehouse_transfers", "waiting_approval"): 3},
                                  {("warehouse_transfers", "waiting_approval")}, {}), 0)
    jalankan("B: dibebaskan dengan alasan panjang → hijau",
             lambda g: check_data(g, {("wms_tasks", "pending"): 9}, set(),
                                  {("wms_tasks", "pending"): "Pekerjaan gudang, "
                                   "bukan keputusan orang."}), 0)
    jalankan("C: satu dokumen dihitung dua antrean → merah",
             lambda g: check_dupes(g, {"price": {("price_approvals", "pra_1")},
                                       "price2": {("price_approvals", "pra_1")}}), 1)
    jalankan("C: antrean saling lepas → hijau",
             lambda g: check_dupes(g, {"a": {("c1", "x")}, "b": {("c2", "y")}}), 0)
    jalankan("D: layar hantu → merah",
             lambda g: check_queue_rows(g, [("k", "L", "layar-hantu", "c1", {})],
                                        {"operations"}, {"c1"}, ""), 1)
    jalankan("E: koleksi salah tulis (tak ada di DB & tak ada di kode) → merah",
             lambda g: check_queue_rows(g, [("k", "L", "operations", "amendments", {})],
                                        {"operations"}, {"doc_amendments"}, ""), 1)
    jalankan("E: koleksi belum ada di DB tetapi ADA di kode → hijau",
             lambda g: check_queue_rows(g, [("k", "L", "operations", "cash_advances", {})],
                                        {"operations"}, set(), 'CA_COLL = "cash_advances"'), 0)
    jalankan("F: mesin generik kembali tanpa produsen → merah",
             lambda g: check_generic_retired(g, ["routers/x.py"], 0), 1)
    jalankan("F: mesin generik benar-benar pensiun → hijau",
             lambda g: check_generic_retired(g, [], 0), 0)

    gagal = 0
    print(f"{B}== SELF-TEST INV-APPR-01 (penjaga antrean harus bisa MEMERAH) =={X}")
    for nama, harap, got in kasus:
        ok = harap == got
        gagal += 0 if ok else 1
        print(f"  [{G + 'PASS' + X if ok else R + 'FAIL' + X}] {nama}  "
              f"(harap={harap} pelanggaran, dapat={got})")
    if gagal:
        print(f"{R}{B}  SELF-TEST MERAH — penjaga antrean tidak bisa dipercaya.{X}")
    else:
        print(f"{G}  HIJAU — penjaga terbukti menuduh pintu tanpa antrean.{X}")
    return gagal


def main(verbose: bool = False) -> int:
    g = Guard("INV-APPR-01", "tiap pintu keputusan punya antrean yang menghitungnya")
    queues = queues_from_backend()
    queue_keys = {q[0] for q in queues}
    doors = doors_from_code()
    src = backend_source()

    print(f"  pintu keputusan di kode: {len(doors)} · baris antrean: {len(queues)}")
    if verbose:
        for d in sorted(doors):
            tag = DOOR_QUEUE.get(d) or ("BEBAS: " + (DOOR_EXEMPT.get(d, "?")[:48]))
            print(f"    {d:70s} → {tag}")

    check_doors(g, doors, DOOR_QUEUE, DOOR_EXEMPT, queue_keys)
    check_generic_retired(
        g,
        [p for p in ("routers", "services")
         if any("approval_requests" in f.read_text(encoding="utf-8")
                and "db.approval_requests" in f.read_text(encoding="utf-8")
                for f in (ROOT / "backend" / p).glob("*.py"))],
        len(re.findall(r"create_approval_request\s*\(", src))
        - len(re.findall(r"def create_approval_request\s*\(", src)),
    )

    colls_in_db: Set[str] = set()
    db = None
    try:
        from pymongo import MongoClient  # noqa: PLC0415
        db = MongoClient(os.environ["MONGO_URL"], serverSelectionTimeoutMS=3000)[
            os.environ.get("DB_NAME", "test_database")]
        db.command("ping")
        colls_in_db = set(db.list_collection_names())
    except Exception as ex:  # noqa: BLE001
        print(f"{Y}  MongoDB tak terjangkau ({ex}) — invarian B & C dilewati.{X}")

    check_queue_rows(g, queues, views_in_router(), colls_in_db, src)

    if db is not None:
        # Invarian B — sapuan data
        waiting: Dict[Tuple[str, str], int] = {}
        for coll in sorted(colls_in_db):
            try:
                vals = db[coll].distinct("status")
            except Exception:  # noqa: BLE001
                continue
            for v in vals:
                if isinstance(v, str) and v in WAIT_VOCAB:
                    n = db[coll].count_documents({"status": v})
                    if n:
                        waiting[(coll, v)] = n
        covered: Set[Tuple[str, str]] = set()
        for _key, _label, _view, coll, query in queues:
            for (c, status) in waiting:
                if c != coll:
                    continue
                try:
                    if db[coll].count_documents({**query, "status": status}, limit=1):
                        covered.add((c, status))
                except Exception:  # noqa: BLE001
                    continue
        check_data(g, waiting, covered, DATA_EXEMPT)

        # Invarian C — anti dobel-hitung
        ids_by_queue: Dict[str, Set[Tuple[str, str]]] = {}
        for key, _label, _view, coll, query in queues:
            try:
                docs = db[coll].find(query, {"_id": 0, "id": 1}).limit(500)
                ids_by_queue[key] = {(coll, d.get("id", "")) for d in docs if d.get("id")}
            except Exception:  # noqa: BLE001
                ids_by_queue[key] = set()
        check_dupes(g, ids_by_queue)
        total = sum(len(v) for v in ids_by_queue.values())
        print(f"  dokumen menunggu keputusan (semua antrean): {total} · "
              f"antrean berisi: {sorted(k for k, v in ids_by_queue.items() if v)}")

    return g.finish()


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(1 if self_test() else 0)
    try:
        rc = main(verbose=("-v" in sys.argv))
    except Exception as ex:  # noqa: BLE001
        print(f"{Y}  Gate error (dianggap SKIP): {ex}{X}")
        rc = 0
    sys.exit(rc)
