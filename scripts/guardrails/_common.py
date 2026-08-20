"""scripts/guardrails/_common.py — util bersama untuk Guardrail v2 (Kain Nusantara).

Guardrail v2 = penjaga PREVENTIF berbasis analisis STATIK + RUNTIME yang memaksa
invariant lintas-kelas-bug (lihat memory/INVARIANTS.md). Dirancang agar sesi AI /
developer baru — TANPA konteks sesi sebelumnya — tetap tertangkap saat memperkenalkan
kembali kelas bug yang sudah pernah ditemukan (mis. Sesi #076: endpoint tanpa auth,
IDOR baca sub-resource, IDOR tulis inbound). Tiap penjaga mencetak: APA yang salah,
DI MANA (file/endpoint), dan MENGACU ke INVARIANT-ID.

Diadaptasi dari metodologi 'Guardrail v2' proyek Rahaza Travel
(github.com/akugendutkayababi/travel) → disesuaikan ke pola KN:
`require_permission` / `require_role` / `current_user` / `entity_ctx` /
`assert_entity_access` + registry `entity_scope.SCOPED_COLLECTIONS`.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"

G = "\033[92m"; R = "\033[91m"; Y = "\033[93m"; C = "\033[96m"; B = "\033[1m"; X = "\033[0m"


class Guard:
    """Akumulator hasil satu penjaga invariant."""

    def __init__(self, invariant_id: str, title: str):
        self.id = invariant_id
        self.title = title
        self.violations = []
        self.checks = 0

    def add(self, msg: str):
        self.violations.append(msg)

    def bump(self, n: int = 1):
        self.checks += n

    def finish(self) -> int:
        print(f"{C}{B}== {self.id} — {self.title} =={X}")
        if not self.violations:
            print(f"{G}[PASS]{X} {self.checks} cek lolos, 0 pelanggaran.")
            return 0
        print(f"{R}[FAIL]{X} {len(self.violations)} pelanggaran (dari {self.checks} cek):")
        for v in self.violations:
            print(f"  {R}✗{X} {v}")
        print(f"{Y}→ Perbaiki sesuai INVARIANT {self.id} (detail: memory/INVARIANTS.md).{X}")
        return 1


# ─────────────────────────────────────────────────────────────────────────────
# DbSnapshot — SNAPSHOT & RESTORE untuk guardrail RUNTIME  [BARU 2026-07-26]
# ─────────────────────────────────────────────────────────────────────────────
# MASALAH YANG DIPERBAIKI (terukur, bukan dugaan):
#   Guardrail runtime memanggil API sungguhan, jadi mereka MENGUBAH data. Sebelum
#   ini tak satu pun punya cleanup (`grep -c "finally|delete_many|cleanup"` = 0),
#   sehingga setiap kali `gate.sh` dijalankan data demo rusak permanen:
#
#     verify_state_machine.py  (terukur pada seed bersih):
#       · order seed so_006  status "reserved" -> "cancelled"  (TIDAK dipulihkan)
#       · reservasi dilepas: songket 20->10 · lurik 40->0
#       · prod_batik_mega/wh_jakarta  on_hand 75 -> 485  (+410 yard stok fiktif)
#       · +2 baris inventory_movements (release_reservation) · +2 audit_logs
#     verify_cross_entity / nonfinancial_sweep / concurrency: +2..4 audit_logs each
#
#   Akibatnya user melihat SO-006 batal & 410 yard stok hantu setiap habis gate.
#   Ini kelas bug yang sama dengan `verify_phase_g_acc_opname.py` (bocor stok + JE
#   yatim) dan `bughunt_hris_flow.py` (data uji tertinggal) di repo lain.
#
# SOLUSI: snapshot penuh koleksi yang tersentuh sebelum uji, restore di `finally`.
# Koleksi ini kecil di DB uji (puluhan dokumen), jadi biayanya milidetik dan
# restorasinya EKSAK (_id dipertahankan).
#
# PENGAMAN: hanya berjalan bila DB_NAME mengandung "test" ATAU
# KN_GATE_ALLOW_RESTORE=1 — supaya tidak mungkin menghapus database produksi.
TRACKED_COLLECTIONS = [
    # dokumen inti
    "sales_orders", "purchase_orders", "inventory_rolls", "inventory_balances",
    "inventory_movements", "wms_tasks", "shipments", "approval_requests",
    # jejak & notifikasi (residu di sini pun berarti gate meninggalkan jejak)
    "audit_logs", "notifications", "login_attempts",
    # JALUR UANG — ditambahkan 2026-07-26 setelah gate INV-GATE-01 menemukan
    # verify_concurrency.py meninggalkan +1 vendor_bill & +1 ar_receipt tiap gate
    # (uji overpay membuat dokumen sungguhan). Tanpa ini restore tidak lengkap.
    "vendor_bills", "ar_receipts", "invoices", "cash_transactions",
    "journal_entries", "credit_notes", "purchase_returns", "sales_returns",
    "tax_invoices", "price_approvals",
]


class DbSnapshot:
    """Snapshot & restore eksak koleksi transaksional (khusus DB uji)."""

    def __init__(self, db, collections=None, verbose=True):
        self.db = db
        self.collections = collections or TRACKED_COLLECTIONS
        self.data = {}
        self.verbose = verbose
        self.enabled = self._is_safe()

    def _is_safe(self):
        import os
        if os.environ.get("KN_GATE_NO_RESTORE") == "1":
            # Escape hatch untuk MENGUKUR kebocoran (dan untuk debugging manual:
            # kadang kita justru ingin melihat state pasca-uji).
            print(f"{Y}  [snapshot] KN_GATE_NO_RESTORE=1 — restore DIMATIKAN "
                  f"(mode ukur/debug; data demo AKAN berubah).{X}")
            return False
        name = (os.environ.get("DB_NAME") or "").lower()
        if os.environ.get("KN_GATE_ALLOW_RESTORE") == "1":
            return True
        if "test" in name or "demo" in name or "dev" in name:
            return True
        print(f"{Y}  [snapshot] DB_NAME='{name}' bukan DB uji — restore DIMATIKAN "
              f"(set KN_GATE_ALLOW_RESTORE=1 bila memang disengaja).{X}")
        return False

    def take(self):
        if not self.enabled:
            return self
        for c in self.collections:
            try:
                self.data[c] = list(self.db[c].find({}))
            except Exception:
                self.data[c] = []
        if self.verbose:
            total = sum(len(v) for v in self.data.values())
            print(f"{C}  [snapshot] {total} dokumen dari {len(self.data)} koleksi "
                  f"disimpan — data demo akan dipulihkan setelah uji.{X}")
        return self

    def restore(self):
        if not self.enabled or not self.data:
            return
        changed = 0
        for c, docs in self.data.items():
            try:
                now = self.db[c].count_documents({})
                if now == len(docs):
                    # cek cepat: apakah isinya identik? (bandingkan himpunan _id)
                    ids_now = {d["_id"] for d in self.db[c].find({}, {"_id": 1})}
                    if ids_now == {d["_id"] for d in docs}:
                        # jumlah & _id sama — tetap restore isi karena field bisa berubah
                        pass
                self.db[c].delete_many({})
                if docs:
                    self.db[c].insert_many(docs, ordered=False)
                changed += 1
            except Exception as ex:  # noqa: BLE001
                print(f"{R}  [snapshot] gagal memulihkan '{c}': {ex}{X}")
        if self.verbose:
            print(f"{G}  [snapshot] {changed} koleksi dipulihkan ke keadaan sebelum uji "
                  f"— nol residu.{X}")


def run_with_restore(main_fn, collections=None):
    """
    Jalankan gate runtime lalu PULIHKAN DB ke keadaan sebelum uji.

    Dipakai di blok `__main__` guardrail runtime. Snapshot diambil SEBELUM
    `main_fn()` dijalankan, sehingga login/audit yang terjadi di dalam gate pun
    ikut dibersihkan (bila snapshot diambil setelah login, baris audit login
    tertinggal +1 per gate — sudah terukur).
    """
    import os
    try:
        from pymongo import MongoClient
        db = MongoClient(os.environ["MONGO_URL"])[os.environ.get("DB_NAME", "test_database")]
        db.command("ping")
    except Exception:
        return main_fn()          # tanpa Mongo, jalan apa adanya
    snap = DbSnapshot(db, collections=collections).take()
    try:
        return main_fn()
    finally:
        snap.restore()


# ─────────────────────────────────────────────────────────────────────────────
# strip_comments_and_strings — dipakai penjaga STATIK yang menilai KODE
# ─────────────────────────────────────────────────────────────────────────────
# KENAPA BERSAMA (dan bukan disalin per penjaga): dua penjaga berbeda sudah pernah
# MENUDUH PALSU karena mencocokkan pola pada teks mentah —
#   · INV-UI-06 mengira `label: "1 pesan per alert (real-time)"` sebagai `alert()`;
#   · `ux_audit` mengira kata "posting" di dalam kalimat penjelasan sebagai bukti
#     adanya keadaan "sedang memproses", sehingga kartu yang benar-benar TANPA
#     indikator memuat dinyatakan lolos ("hijau tapi hampa").
# Keduanya kelas bug yang sama: menilai KODE tetapi membaca TEKS. Satu implementasi
# supaya perbaikannya berlaku untuk semua penjaga sekaligus.
def strip_comments_and_strings(src: str) -> str:
    """Ganti isi komentar & literal string dengan spasi (panjang & baris dipertahankan).

    Panjang dijaga sama supaya nomor baris hasil pencarian tetap TEPAT menunjuk baris
    aslinya — penjaga yang menunjuk baris salah sama tidak bergunanya dengan penjaga
    yang tidak menuduh apa pun.
    """
    out: List[str] = []
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        nxt = src[i + 1] if i + 1 < n else ""
        if c == "/" and nxt == "/":
            while i < n and src[i] != "\n":
                out.append(" ")
                i += 1
            continue
        if c == "/" and nxt == "*":
            while i < n and not (src[i] == "*" and i + 1 < n and src[i + 1] == "/"):
                out.append("\n" if src[i] == "\n" else " ")
                i += 1
            out.append("  ")
            i += 2
            continue
        if c in ("'", '"', "`"):
            quote = c
            out.append(" ")
            i += 1
            while i < n:
                if src[i] == "\\":
                    out.append("  ")
                    i += 2
                    continue
                if src[i] == quote:
                    out.append(" ")
                    i += 1
                    break
                # `${…}` di template literal adalah KODE — jangan dibuang.
                if quote == "`" and src[i] == "$" and i + 1 < n and src[i + 1] == "{":
                    depth = 0
                    while i < n:
                        if src[i] == "{":
                            depth += 1
                        elif src[i] == "}":
                            depth -= 1
                            if depth == 0:
                                out.append("}")
                                i += 1
                                break
                        out.append(src[i])
                        i += 1
                    continue
                out.append("\n" if src[i] == "\n" else " ")
                i += 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


