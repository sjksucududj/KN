#!/usr/bin/env python3
"""INV-QTY-01 — DUA SATUAN (jumlah roll + ukuran) wajib satu arti di semua tampilan.

KELAS BUG YANG DICEGAH
======================
Permintaan pemilik FASE U: *"catat roll dan yard/kg dan panel — jadi ada 2 satuan
yang ditulis... dan ini seharusnya sudah ada di semuanya, di WMS, di sales, di SO."*

Satu fakta ("12 roll · 540 yard") muncul di **enam tampilan**: layar daftar, panel
rincian, PDF surat jalan/faktur, CSV unduhan, papan PO, dan kartu stok. Kalau setiap
tampilan merangkainya sendiri, satu aturan saja yang berubah harus dikejar di enam
tempat — dan yang tertinggal **berbohong dengan tenang**. Tiga cara gagal yang nyata
dan sudah terukur di repo ini:

  (1) **"0 roll" untuk dokumen lama.** `qty_rolls` yang belum pernah diisi bukan nol
      gulungan; ia "tidak diketahui". Dokumen tahun lalu yang dicetak "0 roll" membuat
      manajer menyimpulkan barangnya dikirim tanpa gulungan. Yang benar: **"—"**
      (di CSV: **sel kosong**, karena "—" mematikan SUM Excel di kolom itu).
  (2) **Satuan diketik keras di JSX.** `{formatQty(it.quantity)} yard` benar untuk
      woven dan SALAH untuk knit (kg) & printing (panel) — user story U.3. Satuannya
      milik dokumen, bukan milik layar.
  (3) **Dua cara menghitung satu angka.** `PurchaseReturns` pernah menghitung jumlah
      roll dari `items[].roll_ids.length` padahal fieldnya sudah ada (`qty_rolls`).
      Begitu keduanya berbeda (retur disetujui sebagian), layar dan berkas unduhan
      menyebut angka berbeda dan tidak ada yang tahu mana yang benar.

EMPAT LAPIS PEMERIKSAAN (sengaja: pola teks saja tidak cukup)
============================================================
  A. **DATA** (butuh Mongo) — 15 koleksi target §U.B WAJIB punya `qty_rolls` di jalur
     yang benar (`items[]` / `steps[]` / `lines[]` / akar).
  B. **KODE FE** (statik) — layar dokumen WAJIB memakai `<QtyDual/>`; daftar
     ber-unduhan WAJIB memakai `utils/qtyDualCsv`; dan DILARANG merangkai
     angka+satuan dengan kata satuan yang diketik keras.
  C. **PERILAKU FE** (dijalankan dengan Node) — `utils/qtyDualCsv.js` diuji
     sungguhan: `sumRolls([])` harus `null` (bukan 0), ukuran dijumlah PER SATUAN,
     dan sel CSV-nya benar-benar KOSONG.
  D. **PERILAKU BE** (dijalankan dengan Python) — `core_utils.qty_dual()` dan
     `pdf_resolvers._rolls_cell/_sum_rolls` harus SEPAKAT soal "—". Kalau layar dan
     PDF punya aturan berbeda, dokumen cetak dan layar akan berselisih di depan
     pelanggan.

Jalankan:
    python scripts/guardrails/verify_qty_dual.py
    python scripts/guardrails/verify_qty_dual.py --self-test
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

sys.path.insert(0, os.path.dirname(__file__))
from _common import (BACKEND, FRONTEND, Guard, B, C, G, R, X,  # noqa: E402
                     strip_comments_and_strings)

sys.path.insert(0, str(BACKEND))

FE_SRC = FRONTEND / "src"
QTY_DUAL_COMPONENT = FE_SRC / "components" / "QtyDual.jsx"
QTY_DUAL_CSV = FE_SRC / "utils" / "qtyDualCsv.js"
CSV_EXPORT = FE_SRC / "utils" / "csvExport.js"


# ═════════════════════════════════════════════════════════════════════════════
# A. DATA — 15 koleksi §U.B
# ═════════════════════════════════════════════════════════════════════════════
# Nilai = tempat `qty_rolls` hidup. Diambil dari rencana §U.B, dan disengaja SAMA
# dengan `scripts/audit_md_erp_readiness.QTY_ROLLS_TARGETS` — kalau kelak berbeda,
# alat ukur dan penjaga akan melaporkan dunia yang berbeda.
QTY_ROLLS_TARGETS: Dict[str, str] = {
    "purchase_orders": "items", "purchase_requisitions": "items",
    "sales_orders": "items", "sales_returns": "items", "purchase_returns": "items",
    "warehouse_transfers": "items", "interco_transactions": "items",
    "interco_returns": "items", "internal_requests": "items", "rfqs": "items",
    "wms_tasks": "root", "shipments": "root", "inventory_movements": "root",
    "makloon_orders": "steps", "inspections": "lines",
}
_PATH = {"items": "items.qty_rolls", "steps": "steps.qty_rolls",
         "lines": "lines.qty_rolls", "root": "qty_rolls"}


# ═════════════════════════════════════════════════════════════════════════════
# B. KODE FE — daftar layar yang WAJIB memakai komponen/helper bersama
# ═════════════════════════════════════════════════════════════════════════════
# Daftar EKSPLISIT dengan alasan per baris (pola `verify_line_scope.MUST_USE_*`):
# layar dokumen baru yang lupa memakai `<QtyDual/>` akan MEMERAH di sini, bukan
# lolos diam-diam. Kalau sebuah layar memang tidak menyebut jumlah kain, ia tidak
# masuk daftar — bukan diberi pengecualian.
MUST_USE_QTY_DUAL: Dict[str, str] = {
    "features/orders/OrderDetailPanel.jsx": "baris Pesanan Penjualan",
    "features/admin/po/PODetailPanel.jsx": "baris PO — rencana vs diterima",
    "features/purchasing/PurchaseRequisitionDetailPanel.jsx": "baris Permintaan Pembelian",
    "features/purchasing/RFQDetailPanel.jsx": "baris RFQ",
    "features/purchasing/ReturnDetailPanel.jsx": "baris retur beli",
    "features/purchasing/PurchaseApprovalView.jsx": "meja persetujuan pembelian",
    "features/purchasing/MakloonOrderDetailPanel.jsx": "langkah SPK makloon (masuk & keluar)",
    "features/sales/ReturnDetail.jsx": "baris retur jual",
    "features/transfers/InterCompanyTransfers.jsx": "baris transfer antar-PT",
    "features/wms/transfer/TransferDetailModal.jsx": "baris transfer antar-gudang",
    "features/wms/inbound/InboundTaskPanel.jsx": "tugas penerimaan gudang",
    "features/wms/inventory/LedgerTable.jsx": "kartu mutasi persediaan",
    "features/internal_requests/InternalRequestsView.jsx": "baris permintaan internal",
    "features/finance/interco/IntercoDetailParts.jsx": "baris transaksi antar-PT",
}

# Daftar ber-unduhan CSV yang menyebut jumlah kain → WAJIB memakai helper bersama,
# supaya judul kolom & arti sel kosong tidak pernah berbeda antar layar.
MUST_USE_QTY_DUAL_CSV: Dict[str, str] = {
    "features/orders/OrdersView.jsx": "unduhan daftar Pesanan Penjualan",
    "features/admin/PurchaseOrderManagement.jsx": "unduhan papan PO (dipesan vs diterima)",
    "features/sales/SalesReturns.jsx": "unduhan daftar retur jual",
    "features/purchasing/PurchaseReturns.jsx": "unduhan daftar retur beli",
    "features/wms/InventoryStockView.jsx": "unduhan mutasi persediaan & daftar roll",
}

# ── Dua aturan BERBEDA, karena dua kata itu tidak sejenis ────────────────────
# Pembedaan ini datang dari MENJALANKAN penjaga versi pertama pada kode nyata:
# ia melaporkan 16 pelanggaran, dan **15 di antaranya SAH** — `{item.rolls.length}
# roll`, `{pending.length} Roll`, `punya {holder.rolls} roll di gudang ini`. Semua
# itu MENGHITUNG gulungan fisik, dan "roll" memang nama bendanya; tidak ada versi
# yard/kg dari sebuah gulungan. Penjaga yang menuduh 15 baris benar akan diabaikan,
# lalu berhenti menjaga apa pun (pelajaran `ux_audit` FASE P5 & INV-UI-09).
#
#  B1 — SATUAN UKURAN (`yard`/`kg`/`meter`/`panel`) milik **DOKUMEN**. Mengetiknya
#       keras di layar benar untuk woven dan salah untuk knit & printing
#       (user story U.3). Selalu pelanggaran di sebelah angka jumlah.
#  B2 — kata **`roll`** hanya jadi pelanggaran bila angkanya berasal dari FIELD
#       FASE U (`qty_rolls`/`received_rolls`/`qty_rolls_out`), sebab di situlah
#       aturan "dokumen lama → — , bukan 0 roll" harus berlaku. Menghitung panjang
#       daftar roll (`.length`) tidak menyentuh aturan itu.
_MEASURE_WORDS = r"yard|yards|kg|kilogram|meter|meters|mtr|panel|panels"
_ROLL_FIELDS = r"qty_rolls|qty_rolls_out|received_rolls|rolls_planned"
_QTY_EXPR = (r"qty|qty_rolls|quantity|quantity_returned|measure|length_remaining|"
             r"length|received_qty|input_qty|output_qty|rolls")

# B1: ekspresi angka PERSIS diikuti satuan ukuran yang diketik keras.
HAND_ASSEMBLED_MEASURE = re.compile(
    r"\{[^{}]*\b(?:" + _QTY_EXPR + r")\b[^{}]*\}"
    r"(?:\s|&nbsp;)*(?:" + _MEASURE_WORDS + r")\b", re.IGNORECASE)

# B2: ekspresi yang membaca FIELD roll FASE U, PERSIS diikuti kata "roll".
HAND_ASSEMBLED_ROLLS = re.compile(
    r"\{[^{}]*\b(?:" + _ROLL_FIELDS + r")\b[^{}]*\}"
    r"(?:\s|&nbsp;)*(?:roll|rolls|gulung)\b", re.IGNORECASE)


def find_hand_assembled(src: str) -> List[str]:
    """Baris yang merangkai angka + kata satuan yang diketik keras (B1 & B2).

    Komentar & literal string DIBUANG lebih dulu: kata "roll" di dalam `className`
    atau di kalimat penjelasan bukan tampilan angka, dan menghitungnya adalah cara
    tercepat membuat penjaga ini tidak dipercaya.
    """
    clean = strip_comments_and_strings(src)
    out: List[str] = []
    for pola, sebab in ((HAND_ASSEMBLED_MEASURE,
                         "satuan UKURAN diketik keras (satuan milik dokumen: "
                         "yard/kg/panel) — pakai `unit={it.unit}`"),
                        (HAND_ASSEMBLED_ROLLS,
                         "jumlah roll FASE U dirangkai tangan — aturan \"dokumen lama "
                         "→ tanpa angka roll, BUKAN 0 roll\" jadi punya salinan kedua")):
        for m in pola.finditer(clean):
            line = clean[:m.start()].count("\n") + 1
            frag = re.sub(r"\s+", " ", m.group(0))[:90]
            out.append(f"baris {line}: `{frag}` — {sebab}")
    return out


def check_frontend(sources: Dict[str, str]) -> List[str]:
    viol: List[str] = []
    for rel, why in MUST_USE_QTY_DUAL.items():
        text = sources.get(rel)
        if text is None:
            viol.append(f"{rel}: berkas tidak ditemukan — {why} tidak bisa dinilai")
            continue
        if "QtyDual" not in text:
            viol.append(f"{rel}: tidak memakai `<QtyDual/>` — {why}. Jumlah roll & "
                        f"ukuran wajib lewat satu komponen supaya aturan \"—\" untuk "
                        f"dokumen lama berlaku di semua layar sekaligus.")
    for rel, why in MUST_USE_QTY_DUAL_CSV.items():
        text = sources.get(rel)
        if text is None:
            viol.append(f"{rel}: berkas tidak ditemukan — {why} tidak bisa dinilai")
            continue
        if "qtyDualCsv" not in text:
            viol.append(f"{rel}: tidak memakai `utils/qtyDualCsv` — {why}. Kolom Roll "
                        f"yang dihitung sendiri di layar akan menyimpang dari "
                        f"`items[].qty_rolls` tanpa ada yang tahu.")
    for rel, text in sorted(sources.items()):
        if rel.endswith("components/QtyDual.jsx"):
            continue          # SATU tempat yang memang berhak menulis kata "roll"
        for hit in find_hand_assembled(text):
            viol.append(f"{rel}: {hit}. Pakai `<QtyDual rolls=… measure=… "
                        f"unit={{it.unit}} />` atau `rollsText()` dari komponen yang sama.")
    # Komponen bersamanya sendiri harus mempertahankan aturan "—".
    comp = sources.get("components/QtyDual.jsx")
    if comp is None:
        viol.append("components/QtyDual.jsx tidak ada — tidak ada satu tempat untuk "
                    "aturan dua satuan (setiap tabel akan merangkainya sendiri).")
    elif "—" not in comp:
        viol.append("components/QtyDual.jsx tidak pernah menulis \"—\" — dokumen lama "
                    "tanpa `qty_rolls` akan tampil \"0 roll\" (menyesatkan).")
    return viol


# ═════════════════════════════════════════════════════════════════════════════
# C. PERILAKU FE — dijalankan dengan Node (bukan dibaca polanya)
# ═════════════════════════════════════════════════════════════════════════════
NODE_TEST = r"""
import * as q from "./qtyDualCsv.mjs";
import * as csv from "./csvExport.mjs";

let gagal = 0;
const cek = (nama, benar, dapat) => {
  if (!benar) { gagal += 1; console.log("FAIL :: " + nama + " :: dapat=" + JSON.stringify(dapat)); }
  else { console.log("PASS :: " + nama); }
};

// ── Aturan INTI: "belum diisi" ≠ "nol gulungan" ──────────────────────────────
cek("dokumen lama (tanpa qty_rolls) → null, BUKAN 0",
    q.sumRolls([{ quantity: 100 }, { quantity: 50 }]) === null,
    q.sumRolls([{ quantity: 100 }]));
cek("qty_rolls = 0 yang disengaja tetap 0 (bukan null)",
    q.sumRolls([{ qty_rolls: 0 }]) === 0, q.sumRolls([{ qty_rolls: 0 }]));
cek("sebagian baris terisi → tetap dijumlah (bukan diabaikan)",
    q.sumRolls([{}, { qty_rolls: 2 }, { qty_rolls: 3 }]) === 5,
    q.sumRolls([{}, { qty_rolls: 2 }, { qty_rolls: 3 }]));
cek("daftar kosong / bukan array → null",
    q.sumRolls([]) === null && q.sumRolls(undefined) === null, q.sumRolls([]));
cek("field roll bisa diganti (papan PO: received_rolls)",
    q.sumRolls([{ received_rolls: 4 }], "received_rolls") === 4,
    q.sumRolls([{ received_rolls: 4 }], "received_rolls"));

// ── Sel CSV benar-benar KOSONG (keputusan pemilik: CSV ≠ PDF) ────────────────
let r = csv.buildCsv([{ items: [{ quantity: 10, unit: "yard" }] }],
                     q.qtyDualCsvColumns());
cek("dokumen lama → sel Roll KOSONG (bukan '—', bukan 0)",
    r === "Roll;Jumlah\r\n;10 yard", r);

r = csv.buildCsv([{ items: [{ qty_rolls: 12, quantity: 540.5, unit: "yard" }] }],
                 q.qtyDualCsvColumns());
cek("dua satuan jadi DUA kolom (Roll bisa di-SUM Excel)",
    r === "Roll;Jumlah\r\n12;540,5 yard", r);

// ── Satuan campur TIDAK boleh dijumlah jadi satu angka (user story U.3) ──────
const campur = q.sumMeasure([{ qty_rolls: 1, quantity: 100, unit: "yard" },
                             { qty_rolls: 2, quantity: 30, unit: "kg" }]);
cek("satuan berbeda dijumlah PER SATUAN, tidak dicampur",
    campur === "100 yard + 30 kg", campur);
cek("baris satuan sama digabung",
    q.sumMeasure([{ quantity: 10, unit: "kg" }, { quantity: 5, unit: "kg" }]) === "15 kg",
    q.sumMeasure([{ quantity: 10, unit: "kg" }, { quantity: 5, unit: "kg" }]));
cek("desimal memakai koma (Excel wilayah Indonesia)",
    q.sumMeasure([{ quantity: 12.5, unit: "yard" }]) === "12,5 yard",
    q.sumMeasure([{ quantity: 12.5, unit: "yard" }]));
cek("retur memakai quantity_returned bila ada",
    q.sumMeasure([{ quantity_returned: 7, unit: "yard" }]) === "7 yard",
    q.sumMeasure([{ quantity_returned: 7, unit: "yard" }]));
cek("tanpa ukuran → teks kosong (bukan '0')",
    q.sumMeasure([{}]) === "", q.sumMeasure([{}]));

// ── Versi akar (mutasi / tugas gudang / surat jalan) ─────────────────────────
r = csv.buildCsv([{ qty_rolls: 1, quantity: 25, unit: "yard" }],
                 q.qtyDualRootCsvColumns());
cek("dokumen ber-qty_rolls di AKAR juga dua kolom",
    r === "Roll;Jumlah\r\n1;25 yard", r);
r = csv.buildCsv([{ quantity: 25, unit: "yard" }], q.qtyDualRootCsvColumns());
cek("mutasi lama tanpa qty_rolls → sel kosong",
    r === "Roll;Jumlah\r\n;25 yard", r);

console.log(gagal === 0 ? "ALL_PASS" : ("GAGAL=" + gagal));
process.exit(gagal === 0 ? 0 : 1);
"""


def run_js_behaviour(mutate: Callable[[str], str] = None) -> Tuple[str, List[str]]:
    """Jalankan uji perilaku `qtyDualCsv.js` dengan Node → (status, keluaran).

    `mutate` dipakai SELF-TEST untuk merusak implementasinya dengan sengaja dan
    membuktikan uji ini benar-benar bisa MEMERAH.
    """
    if not QTY_DUAL_CSV.exists():
        return "FAIL", [f"{QTY_DUAL_CSV.name} tidak ada — tidak ada helper bersama "
                        f"untuk kolom Roll/Jumlah di CSV."]
    if not CSV_EXPORT.exists():
        return "FAIL", ["utils/csvExport.js tidak ada."]
    node = shutil.which("node")
    if not node:
        return "SKIP", ["Node tidak tersedia — lapis PERILAKU FE dilewati."]
    src = QTY_DUAL_CSV.read_text(encoding="utf-8")
    if mutate:
        src = mutate(src)
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        (d / "qtyDualCsv.mjs").write_text(src, encoding="utf-8")
        (d / "csvExport.mjs").write_text(CSV_EXPORT.read_text(encoding="utf-8"),
                                         encoding="utf-8")
        (d / "test.mjs").write_text(NODE_TEST, encoding="utf-8")
        try:
            p = subprocess.run([node, str(d / "test.mjs")], capture_output=True,
                               text=True, timeout=60)
        except subprocess.TimeoutExpired:
            return "FAIL", ["Uji perilaku dua satuan tidak selesai dalam 60s."]
        return ("PASS" if p.returncode == 0 else "FAIL"), \
               (p.stdout + p.stderr).strip().splitlines()


# ═════════════════════════════════════════════════════════════════════════════
# D. PERILAKU BE — layar & PDF wajib SEPAKAT soal "—"
# ═════════════════════════════════════════════════════════════════════════════
def check_backend_behaviour(qty_dual: Callable, rolls_cell: Callable,
                            sum_rolls: Callable) -> List[str]:
    """Uji kontrak tiga fungsi server. Fungsinya disuntik supaya SELF-TEST bisa
    memasukkan implementasi yang SENGAJA salah dan membuktikan lapis ini memerah."""
    bad: List[str] = []

    def eq(got: Any, want: Any, label: str):
        if got != want:
            bad.append(f"{label}: hasil `{got}` — seharusnya `{want}`")

    eq(qty_dual(None, None, ""), "—", "qty_dual(kosong, kosong) untuk dokumen lama")
    eq(qty_dual(None, 540.5, "yard"), "540,5 yard",
       "qty_dual tanpa jumlah roll TIDAK boleh menambah \"0 roll\"")
    eq(qty_dual(12, 540.5, "yard"), "12 roll · 540,5 yard", "qty_dual dua satuan")
    eq(qty_dual(0, 540, "yard"), "0 roll · 540 yard",
       "qty_dual(0) yang disengaja tetap ditulis \"0 roll\"")
    eq(qty_dual(3, None, "kg"), "3 roll", "qty_dual hanya roll")
    eq(qty_dual(2, 30, "kg"), "2 roll · 30 kg",
       "qty_dual memakai satuan DOKUMEN (kg), bukan satuan tetap")
    eq(rolls_cell(None), "—", "kolom Roll PDF untuk dokumen lama")
    eq(rolls_cell(""), "—", "kolom Roll PDF untuk nilai kosong")
    eq(rolls_cell(0), "0", "kolom Roll PDF untuk nol yang disengaja")
    eq(rolls_cell(12), "12", "kolom Roll PDF untuk angka")
    eq(sum_rolls([]), "—", "total Roll PDF bila tak satu pun baris menyebut roll")
    eq(sum_rolls([None, None]), "—", "total Roll PDF bila semua baris kosong")
    eq(sum_rolls([None, 2, 3]), "5", "total Roll PDF menjumlah baris yang terisi")
    eq(sum_rolls([0]), "0", "total Roll PDF untuk nol yang disengaja")
    return bad


# Resolver PDF yang WAJIB memancarkan kolom roll (dua kolom terpisah — keputusan
# pemilik 2026-08-20). Kalau salah satu hilang, dokumen cetak akan menyebut jumlah
# tanpa gulungan sementara layarnya menyebut keduanya.
PDF_RESOLVERS_WITH_ROLLS: List[str] = [
    "resolve_sales_order", "resolve_purchase_order", "resolve_sales_return",
    "resolve_purchase_return", "resolve_makloon_spk", "resolve_transfer",
    "resolve_purchase_requisition", "resolve_invoice", "resolve_tax_invoice",
    "resolve_rfq", "resolve_interco_return", "resolve_goods_receipt",
    "resolve_packing_list",
]


def check_pdf_resolvers(src: str) -> List[str]:
    """Setiap resolver di daftar wajib menyebut kolom roll di dalam tubuhnya sendiri.

    Dipotong per-`async def` supaya "ada di berkasnya" tidak dianggap "ada di
    resolvernya" — kelas tuduhan-hijau-tapi-hampa yang pernah terjadi di INV-IC-02.
    """
    bad: List[str] = []
    blocks: Dict[str, str] = {}
    parts = re.split(r"\nasync def (\w+)\(", "\n" + src)
    for i in range(1, len(parts), 2):
        blocks[parts[i]] = parts[i + 1]
    for name in PDF_RESOLVERS_WITH_ROLLS:
        body = blocks.get(name)
        if body is None:
            bad.append(f"pdf_resolvers.{name} tidak ada — dokumen ini tidak bisa "
                       f"dinilai untuk kolom roll")
            continue
        if "_rolls_cell(" not in body and "_col_rolls(" not in body \
                and '"rolls"' not in body:
            bad.append(f"pdf_resolvers.{name} tidak memancarkan kolom roll — dokumen "
                       f"cetaknya menyebut jumlah TANPA gulungan sementara layarnya "
                       f"menyebut keduanya (pemilik memutuskan DUA kolom terpisah).")
    return bad


# ═════════════════════════════════════════════════════════════════════════════
def _fe_sources() -> Dict[str, str]:
    out: Dict[str, str] = {}
    for p in FE_SRC.rglob("*.jsx"):
        out[str(p.relative_to(FE_SRC))] = p.read_text(encoding="utf-8", errors="ignore")
    for p in (FE_SRC / "utils").rglob("*.js"):
        out[str(p.relative_to(FE_SRC))] = p.read_text(encoding="utf-8", errors="ignore")
    return out


def _db():
    if not os.environ.get("MONGO_URL"):
        from dotenv import load_dotenv
        load_dotenv(BACKEND / ".env")
    from pymongo import MongoClient
    cli = MongoClient(os.environ["MONGO_URL"].strip('"'), serverSelectionTimeoutMS=2500)
    db = cli[os.environ.get("DB_NAME", "test_database").strip('"')]
    db.command("ping")
    return db


def check_data(db, existing: set) -> Tuple[List[str], int]:
    viol: List[str] = []
    n = 0
    for coll, tempat in QTY_ROLLS_TARGETS.items():
        if coll not in existing:
            # Koleksi yang belum lahir (mis. `inspections` milik FASE I) BUKAN
            # pelanggaran: menuntut field pada koleksi yang belum ada akan membuat
            # gate ini memerah selamanya sampai fase lain selesai.
            continue
        n += 1
        if not db[coll].count_documents({_PATH[tempat]: {"$exists": True}}):
            viol.append(f"koleksi `{coll}` belum punya satu pun dokumen ber-"
                        f"`{_PATH[tempat]}` — dua satuan tidak sampai ke {coll}. "
                        f"Isi lewat jalur tulisnya (`dual_qty_service.stamp`) atau "
                        f"backfill `scripts/migrate_qty_rolls.py`.")
    return viol, n


def main(verbose: bool = True) -> int:
    g = Guard("INV-QTY-01", "dua satuan (roll + ukuran) satu arti di layar · PDF · CSV")

    # ── B. KODE FE ──
    sources = _fe_sources()
    fe_viol = check_frontend(sources)
    g.bump(len(MUST_USE_QTY_DUAL) + len(MUST_USE_QTY_DUAL_CSV) + len(sources))
    for v in fe_viol:
        g.add(v)

    # ── D. PERILAKU BE ──
    try:
        from core_utils import qty_dual
        from services.pdf_resolvers import _rolls_cell, _sum_rolls
        for v in check_backend_behaviour(qty_dual, _rolls_cell, _sum_rolls):
            g.add(f"perilaku server — {v}")
        g.bump(14)
    except ImportError as exc:
        g.add(f"helper server dua satuan tidak bisa diimpor ({exc}) — "
              f"`core_utils.qty_dual` & `pdf_resolvers._rolls_cell` WAJIB ada.")
    pdf_src = (BACKEND / "services" / "pdf_resolvers.py").read_text(encoding="utf-8")
    for v in check_pdf_resolvers(pdf_src):
        g.add(v)
    g.bump(len(PDF_RESOLVERS_WITH_ROLLS))

    # ── C. PERILAKU FE (Node) ──
    status, lines = run_js_behaviour()
    lulus = sum(1 for ln in lines if ln.startswith("PASS ::"))
    if status == "SKIP":
        print(f"  {lines[0]}")
    else:
        g.bump(lulus or 1)
        if status != "PASS":
            for ln in lines:
                if ln.startswith("FAIL ::"):
                    g.add(f"perilaku CSV dua satuan — {ln[8:]}")
            if not any(ln.startswith("FAIL ::") for ln in lines):
                g.add("uji perilaku CSV dua satuan gagal dijalankan: "
                      + " | ".join(lines[-3:]))
        elif verbose:
            print(f"  perilaku CSV dua satuan (Node): {lulus} uji lolos")

    # ── A. DATA ──
    try:
        db = _db()
    except Exception as exc:  # noqa: BLE001
        print(f"  Mongo tak terjangkau ({exc}) — lapis DATA dilewati.")
    else:
        existing = set(db.list_collection_names())
        dviol, n = check_data(db, existing)
        g.bump(n)
        for v in dviol:
            g.add(v)
        if verbose:
            belum_lahir = [c for c in QTY_ROLLS_TARGETS if c not in existing]
            print(f"  koleksi target: {n}/{len(QTY_ROLLS_TARGETS)} ada"
                  + (f" · belum lahir (fase lain): {belum_lahir}" if belum_lahir else ""))
    if verbose:
        print(f"  layar wajib <QtyDual/>: {len(MUST_USE_QTY_DUAL)} · "
              f"unduhan wajib qtyDualCsv: {len(MUST_USE_QTY_DUAL_CSV)} · "
              f"resolver PDF ber-kolom roll: {len(PDF_RESOLVERS_WITH_ROLLS)}")
    return g.finish()


# ═════════════════════════════════════════════════════════════════════════════
# SELF-TEST — dua arah: WAJIB memerah pada pelanggaran buatan, dan WAJIB TIDAK
# menuduh keadaan yang sah. Tanpa ini penjaga hanya klaim prosa.
# ═════════════════════════════════════════════════════════════════════════════
def self_test() -> int:
    kasus: List[Tuple[str, bool]] = []

    def cek(nama: str, benar: bool):
        kasus.append((nama, bool(benar)))

    # ── B1. Deteksi rangkai-tangan SATUAN UKURAN: MEMERAH pada yang salah ──
    cek("`{formatQty(it.quantity)} yard` → MERAH",
        len(find_hand_assembled('<p>{formatQty(it.quantity)} yard</p>')) == 1)
    cek("`{r.length_remaining} meter` → MERAH",
        len(find_hand_assembled('{r.length_remaining} meter')) == 1)
    cek("`{it.quantity} panel` → MERAH",
        len(find_hand_assembled('{it.quantity} panel')) == 1)
    cek("huruf besar `{it.quantity} KG` juga MERAH",
        len(find_hand_assembled('{it.quantity} KG')) == 1)

    # ── B2. Deteksi rangkai-tangan JUMLAH ROLL (khusus field FASE U) ──
    cek("`{item.qty_rolls} roll` → MERAH (aturan \"—\" jadi salinan kedua)",
        len(find_hand_assembled('<span>{item.qty_rolls} roll</span>')) == 1)
    cek("`{formatQty(m.received_rolls)} roll` → MERAH",
        len(find_hand_assembled('{formatQty(m.received_rolls)} roll')) == 1)
    cek("`{s.qty_rolls_out} roll` → MERAH",
        len(find_hand_assembled('{s.qty_rolls_out} roll')) == 1)

    # ── B3. TIDAK menuduh yang sah (bagian tersulit; versi PERTAMA penjaga ini
    #        menuduh 15 baris yang benar — semua "menghitung gulungan fisik") ──
    cek("satuan dari DOKUMEN (`{it.unit}`) → hijau",
        find_hand_assembled('{formatQty(it.quantity)} {it.unit}') == [])
    cek("`<QtyDual measure={it.quantity} unit={it.unit} />` → hijau",
        find_hand_assembled('<QtyDual rolls={it.qty_rolls} measure={it.quantity} '
                            'unit={it.unit} />') == [])
    cek("MENGHITUNG gulungan fisik `{item.rolls.length} roll` → hijau "
        "(\"roll\" = nama benda, bukan satuan dokumen)",
        find_hand_assembled('{item.rolls.length} roll') == [])
    cek("`{pending.length} Roll` → hijau", find_hand_assembled('{pending.length} Roll') == [])
    cek("`punya {holder.rolls} roll di gudang ini` → hijau",
        find_hand_assembled('punya {holder.rolls} roll di gudang ini') == [])
    cek("`{rollsText(m.qty_rolls)}` (lewat helper bersama) → hijau",
        find_hand_assembled('· {rollsText(m.qty_rolls)}') == [])
    cek("judul kolom \"Total Roll\" → hijau",
        find_hand_assembled('<th>Total Roll</th>') == [])
    cek("kata satuan di dalam className/atribut string → hijau",
        find_hand_assembled('<span className="roll-badge">{it.quantity}</span>') == [])
    cek("kata satuan di dalam KOMENTAR → hijau",
        find_hand_assembled('// {it.quantity} yard adalah contoh\n<p>{it.unit}</p>') == [])
    cek("kalimat penjelasan \"12 roll\" (literal string) → hijau",
        find_hand_assembled('<p>{"Total 12 roll dikirim"}</p>') == [])
    cek("angka yang BUKAN jumlah tidak dipancing",
        find_hand_assembled('{it.price} rupiah') == [])

    # ── B3. Daftar wajib-pakai benar-benar menuntut ──
    palsu = {rel: "// kosong" for rel in MUST_USE_QTY_DUAL}
    palsu.update({rel: "// kosong" for rel in MUST_USE_QTY_DUAL_CSV})
    palsu["components/QtyDual.jsx"] = "—"
    v = check_frontend(palsu)
    cek("layar tanpa `<QtyDual/>` & unduhan tanpa `qtyDualCsv` → MERAH semuanya",
        len(v) == len(MUST_USE_QTY_DUAL) + len(MUST_USE_QTY_DUAL_CSV))
    cek("komponen bersama tanpa \"—\" → MERAH",
        any("tidak pernah menulis" in x for x in check_frontend({"components/QtyDual.jsx": "0 roll"})))
    cek("kode NYATA saat ini HIJAU (0 pelanggaran FE)",
        check_frontend(_fe_sources()) == [])

    # ── D1. Perilaku server: implementasi SENGAJA salah harus memerah ──
    def qty_dual_salah(rolls, measure, unit="", **_kw):
        # Kesalahan yang paling mungkin ditulis orang: `rolls or 0`.
        return f"{int(rolls or 0)} roll · {measure} {unit}"
    v = check_backend_behaviour(qty_dual_salah, lambda x: str(int(x or 0)),
                                lambda xs: str(sum(int(x or 0) for x in xs)))
    cek("implementasi server ber-`or 0` (dokumen lama jadi \"0 roll\") → MERAH",
        len(v) >= 3)
    try:
        from core_utils import qty_dual as _qd
        from services.pdf_resolvers import _rolls_cell as _rc, _sum_rolls as _sr
        cek("implementasi server NYATA saat ini HIJAU",
            check_backend_behaviour(_qd, _rc, _sr) == [])
    except ImportError:
        cek("helper server bisa diimpor", False)

    # ── D2. Resolver PDF ──
    cek("resolver PDF tanpa kolom roll → MERAH",
        len(check_pdf_resolvers(
            "\n".join(f"async def {n}(doc, db):\n    return {{}}"
                      for n in PDF_RESOLVERS_WITH_ROLLS))) == len(PDF_RESOLVERS_WITH_ROLLS))
    cek("resolver PDF NYATA saat ini HIJAU",
        check_pdf_resolvers((BACKEND / "services" / "pdf_resolvers.py")
                            .read_text(encoding="utf-8")) == [])

    # ── C1. Perilaku FE (Node) — bukti-merah dengan MERUSAK implementasinya ──
    status, lines = run_js_behaviour()
    if status == "SKIP":
        print(f"{R}  {lines[0]}{X}")
    else:
        cek(f"perilaku CSV dua satuan NYATA hijau ({status})", status == "PASS")
        st2, _ = run_js_behaviour(
            lambda s: s.replace("let total = null;", "let total = 0;"))
        cek("`sumRolls` diubah agar mulai dari 0 (dokumen lama jadi \"0\") → MERAH",
            st2 == "FAIL")
        st3, _ = run_js_behaviour(
            lambda s: s.replace('perUnit.set(key, (perUnit.get(key) || 0) + n);',
                                'perUnit.set("", (perUnit.get("") || 0) + n);'))
        cek("`sumMeasure` diubah agar MENCAMPUR satuan → MERAH", st3 == "FAIL")

    # ── A1. Lapis DATA benar-benar menuntut ──
    try:
        db = _db()
    except Exception:  # noqa: BLE001
        print(f"{R}  Mongo tak terjangkau — lapis DATA self-test dilewati.{X}")
    else:
        existing = set(db.list_collection_names())
        dviol, n = check_data(db, existing)
        cek(f"data NYATA saat ini HIJAU ({n} koleksi target ada)", dviol == [])
        cek("koleksi yang BELUM LAHIR tidak dituduh (anti-merah-selamanya)",
            all("inspections" not in x for x in dviol))
        probe = "kn_qtydual_probe"
        db[probe].insert_one({"id": "x", "items": [{"quantity": 1}]})
        try:
            QTY_ROLLS_TARGETS[probe] = "items"
            dv2, _ = check_data(db, set(db.list_collection_names()))
            cek("koleksi ADA tetapi tanpa `items.qty_rolls` → MERAH",
                any(probe in x for x in dv2))
        finally:
            QTY_ROLLS_TARGETS.pop(probe, None)
            db[probe].drop()
        cek("tidak ada koleksi uji yang tertinggal (nol residu)",
            probe not in set(db.list_collection_names()))

    gagal = sum(0 if ok else 1 for _n, ok in kasus)
    print(f"{C}{B}== SELF-TEST INV-QTY-01 (dua satuan) =={X}")
    for nama, ok in kasus:
        print(f"  [{G + 'PASS' + X if ok else R + 'FAIL' + X}] {nama}")
    print(f"{G}  HIJAU — penjaga memerah pada rangkai-tangan, layar tanpa komponen "
          f"bersama, implementasi ber-`or 0`, resolver PDF tanpa kolom roll, dan "
          f"koleksi tanpa `qty_rolls`; tanpa menuduh satuan dari dokumen, judul "
          f"kolom, komentar, maupun koleksi fase lain.{X}"
          if not gagal else f"{R}{B}  SELF-TEST MERAH ({gagal} kasus).{X}")
    return gagal


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        raise SystemExit(1 if self_test() else 0)
    raise SystemExit(main())
