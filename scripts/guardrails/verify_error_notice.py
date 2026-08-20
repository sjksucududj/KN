#!/usr/bin/env python3
"""INV-UI-03 — Kegagalan backend TIDAK BOLEH hilang tanpa jejak di layar.

KELAS BUG YANG DICEGAH — `KN-G9-ERR-SILENT` (P1, ditemukan saat penutupan FASE G-9):
  `components/ErrorNotice.jsx` menerima prop **`message`** dan `return null` bila kosong.
  Dua layar keuangan terbaru menyimpan objek error axios lalu mengirimnya sebagai
  **`error={err}`**:
      frontend/src/features/finance/BankReconciliationView.jsx   (FASE G-8)
      frontend/src/features/finance/cases/FinanceCasesView.jsx   (FASE G-9)
  Akibatnya `message` undefined → bilah error TIDAK PERNAH dirender. Backend menolak
  dengan kalimat yang jelas ("wajib pilih alasan", "wajib lampiran bukti", "kasus sudah
  ada — jangan membuat kasus kembar", 403 "entitas lain"), tetapi di layar **tidak
  terjadi apa pun**: petugas menekan tombol, tidak ada pesan, tidak ada perubahan.
  Uji backend tetap 100% HIJAU karena API-nya memang benar — yang rusak hanya jalur
  penyampaiannya ke manusia. Justru itu yang membuat kelas bug ini berbahaya.

ATURAN (STATIK, tidak butuh backend):
  A. Setiap pemakaian `<ErrorNotice …>` WAJIB memberi prop `message`. Nama prop lain
     (`error=`, `err=`, `text=`) = MERAH: propnya diabaikan diam-diam.
  B. `components/ErrorNotice.jsx` WAJIB menormalkan nilai bukan-string lewat
     `apiErrorText` — supaya objek error yang lolos pun tetap terbaca manusia
     (pertahanan berlapis, bukan pengganti aturan A).
  C. MODAL yang memanggil API WAJIB menampilkan errornya SENDIRI. Bilah error milik
     layar induk berada di BELAKANG lapisan modal, jadi tidak terlihat selama modal
     terbuka: pengguna melihat tombol "tidak melakukan apa-apa". Modal = berkas yang
     merender `modal-overlay` DAN memanggil `axios.post/put/patch/delete`.

Melanggar → MERAH: sebut berkas, nomor baris, dan alasannya.

Pemakaian:
    python scripts/guardrails/verify_error_notice.py
    python scripts/guardrails/verify_error_notice.py --self-test   # bukti-merah
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _common import FRONTEND, Guard  # noqa: E402

SRC = FRONTEND / "src"
COMPONENT = SRC / "components" / "ErrorNotice.jsx"

# <ErrorNotice … /> boleh melintasi beberapa baris. Setelah nama tag WAJIB ada spasi
# (jadi penyebutan dalam prosa/komentar seperti "masuk ke <ErrorNotice>." tidak ikut
# tertangkap), dan isi propnya tidak boleh memuat `<` supaya pencocokan tidak
# melompati elemen lain (`>` tetap boleh: dipakai panah `() =>`).
USE_RX = re.compile(r"<ErrorNotice(\s[^<]*?)/>", re.DOTALL)
# Nama prop yang SERING dipakai keliru (silent no-op).
WRONG_PROPS = ("error", "err", "text", "msg", "children")

# Penanda modal & tulisan ke API.
MODAL_MARKERS = ("modal-overlay", "m-sheet-wrap")
WRITE_RX = re.compile(r"axios\.(post|put|patch|delete)\s*\(")

# Modal yang memang TIDAK menulis lewat axios (murni tampilan/konfirmasi) otomatis lolos.
# Modal yang menulis TAPI sudah punya bilah errornya sendiri juga lolos.
MODAL_SAFE = ("<ErrorNotice", "notice-bar danger", "role=\"alert\"")

# ── BASELINE MIGRASI (aturan C) ────────────────────────────────────────────────
# Modal LAMA yang sudah menulis ke API sebelum INV-UI-03 lahir. Mereka dicatat di sini
# supaya (a) gate tidak memerah karena utang teknis yang bukan bagian fase berjalan, dan
# (b) daftarnya tetap TERLIHAT sebagai pekerjaan yang harus dituntaskan — bukan hilang
# dari ingatan. Pola yang sama dipakai baseline `scripts/ux_audit.py`.
#
# ATURAN DAFTAR INI: hanya boleh MENGECIL. Menambah berkas baru ke sini = MERAH
# (dijaga oleh pemeriksaan "baseline basi" di bawah), sehingga modal BARU wajib benar
# sejak hari pertama.
MODAL_BASELINE = {
    "components/LabelPrinterModal.jsx",
    "features/crm/CustomerFormModal.jsx",
    "features/crm/Customer360Panel.jsx",
    "features/purchasing/LandedCostDetailPanel.jsx",
    "features/purchasing/VendorBillDetailPanel.jsx",
    "features/purchasing/BlanketPOCreateModal.jsx",
    "features/purchasing/CallOffModal.jsx",
    "features/purchasing/InputTaxCreateModal.jsx",
    "features/purchasing/LandedCostCreateModal.jsx",
    "features/purchasing/RFQCreateModal.jsx",
    "features/purchasing/RFQDetailPanel.jsx",
    "features/purchasing/VendorBillCreateModal.jsx",
}


def scan_usage(text: str, rel: str):
    """Aturan A — setiap <ErrorNotice> harus dapat prop `message`."""
    out = []
    for m in USE_RX.finditer(text):
        props = m.group(1)
        line = text[:m.start()].count("\n") + 1
        if re.search(r"\bmessage\s*=", props):
            continue
        wrong = [w for w in WRONG_PROPS if re.search(rf"\b{w}\s*=", props)]
        hint = (f"dipakai prop `{wrong[0]}=` yang TIDAK ADA di kontrak komponen"
                if wrong else "tidak ada prop apa pun yang membawa pesan")
        out.append((rel, line,
                    f"<ErrorNotice> tanpa prop `message` — {hint}. Komponen akan "
                    f"`return null`, sehingga penolakan backend HILANG dari layar "
                    f"(bug KN-G9-ERR-SILENT). Pakai `message={{err}}`."))
    return out


def scan_modal(text: str, rel: str):
    """Aturan C — modal yang menulis ke API harus menampilkan errornya sendiri."""
    if not any(mk in text for mk in MODAL_MARKERS):
        return []
    if not WRITE_RX.search(text):
        return []
    if any(sf in text for sf in MODAL_SAFE):
        return []
    line = 1
    for i, ln in enumerate(text.split("\n"), start=1):
        if any(mk in ln for mk in MODAL_MARKERS):
            line = i
            break
    return [(rel, line,
             "modal ini menulis ke API tetapi tidak punya bilah error sendiri. "
             "Bilah error layar induk tertutup lapisan modal, jadi penolakan backend "
             "tidak terlihat dan tombolnya terasa mati. Tambahkan "
             "<ErrorNotice message={err} testId=\"…-error\" /> DI DALAM modal.")]


def main() -> int:
    g = Guard("INV-UI-03", "Kegagalan backend harus terlihat di layar (anti error senyap)")

    # ── Aturan B — komponen bersama wajib menormalkan nilai bukan-string ──────
    g.bump()
    if not COMPONENT.exists():
        g.add("components/ErrorNotice.jsx — komponen bilah error tidak ditemukan.")
        return g.finish()
    comp = COMPONENT.read_text(encoding="utf-8")
    if "apiErrorText" not in comp:
        g.add("components/ErrorNotice.jsx — tidak memanggil `apiErrorText` "
              "(utils/apiError.js). Objek error axios yang lolos akan dirender jadi "
              "`[object Object]` atau hilang. Normalkan dulu.")

    # ── Aturan A & C — pindai seluruh layar ───────────────────────────────────
    findings = []
    for path in sorted(SRC.rglob("*.jsx")) + sorted(SRC.rglob("*.js")):
        rel = str(path.relative_to(SRC)).replace("\\", "/")
        if rel == "components/ErrorNotice.jsx":
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if "<ErrorNotice" in text:
            g.bump()
            findings += scan_usage(text, rel)
        if any(mk in text for mk in MODAL_MARKERS):
            g.bump()
            findings += scan_modal(text, rel)

    baseline_hit = set()
    for rel, line, msg in findings:
        if rel in MODAL_BASELINE and "modal ini menulis ke API" in msg:
            baseline_hit.add(rel)
            continue
        g.add(f"{rel}:{line} — {msg}")

    # Baseline BASI = modal yang sudah diperbaiki tetapi namanya masih tertinggal di
    # daftar. Dibiarkan, daftar ini pelan-pelan jadi allowlist buta yang menyembunyikan
    # pelanggaran baru. Jadi: wajib dihapus.
    stale = sorted(MODAL_BASELINE - baseline_hit)
    if stale:
        g.add("BASELINE BASI — modal berikut sudah memenuhi INV-UI-03 (atau sudah tidak "
              "ada) tetapi masih terdaftar di MODAL_BASELINE. Hapus dari daftar supaya "
              f"tidak jadi allowlist buta: {', '.join(stale)}")
    elif MODAL_BASELINE:
        print(f"  utang teknis (baseline aturan C): {len(MODAL_BASELINE)} modal lama "
              f"belum punya bilah error sendiri — lihat MODAL_BASELINE.")

    # ── BUKTI-MERAH: guard harus benar-benar bisa memerah ─────────────────────
    if "--self-test" in sys.argv:
        probe_a = '      {err && <ErrorNotice error={err} onDismiss={() => setErr(null)} />}\n'
        if not scan_usage(probe_a, "__probe__.jsx"):
            print("  [FAIL] SELF-TEST A: prop `error=` yang salah TIDAK tertangkap.")
            return 1
        probe_a2 = '      {err && <ErrorNotice\n        message={err} />}\n'
        if scan_usage(probe_a2, "__probe__.jsx"):
            print("  [FAIL] SELF-TEST A2: pemakaian yang BENAR justru dianggap salah.")
            return 1
        probe_c = ('<div className="modal-overlay">\n'
                   '  <button onClick={() => axios.post(url, body)}>Simpan</button>\n'
                   '</div>\n')
        if not scan_modal(probe_c, "__probe__.jsx"):
            print("  [FAIL] SELF-TEST C: modal penulis tanpa bilah error TIDAK tertangkap.")
            return 1
        probe_c2 = ('<div className="modal-overlay">\n'
                    '  <ErrorNotice message={err} testId="x-error" />\n'
                    '  <button onClick={() => axios.post(url, body)}>Simpan</button>\n'
                    '</div>\n')
        if scan_modal(probe_c2, "__probe__.jsx"):
            print("  [FAIL] SELF-TEST C2: modal yang SUDAH benar justru dianggap salah.")
            return 1
        print("  [PASS] SELF-TEST: 2 pelanggaran tertangkap · 2 pemakaian benar "
              "tidak salah-tuduh (bukti-merah sah).")

    return g.finish()


if __name__ == "__main__":
    raise SystemExit(main())
