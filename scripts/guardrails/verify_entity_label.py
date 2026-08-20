#!/usr/bin/env python3
"""
verify_entity_label.py — GUARDRAIL **INV-UI-02**: id teknis entitas tidak boleh
tampil ke pengguna.
=============================================================================

KELAS BUG NYATA (terlihat di layar, 2026-07-29):
`GET /api/entities` mengembalikan `legal_name` & `short_name`. Ia **TIDAK punya**
`name` maupun `code` — dua field itu hanya ada pada `entity_context.entities`
(respons login). Beberapa layar membaca `entity.name` lalu jatuh ke `entity.id`
sebagai cadangan, sehingga pengguna melihat **`ent_ksc`**:

    features/sales/SalesPortal.jsx      → panel Filter POS: "Entitas: ent_ksc"
    features/settings/config/SettingsHub.jsx → pemilih entitas: "ent_ksc"
    features/crm/IncentiveRatesEditor.jsx    → opsi & kolom: "ent_ksc"
    features/hr/PayrollRunsView.jsx          → label pilihan KOSONG (undefined)
    features/sales/mobile/MobileSalesApp.jsx → header POS mobile: "ent_ksc"

Tidak satu pun gate menangkapnya (semua gate memeriksa kontrak API, bahasa, dan
invarian data — bukan "apakah id teknis tampil di layar"). Skrip ini menutup celah
itu: seluruh tampilan nama entitas WAJIB lewat helper bersama
`frontend/src/utils/entityLabel.js` (`entityShort`/`entityFull`/`*ById`/`entityOptions`)
yang **tidak pernah** mengembalikan id.

CARA PAKAI
    python scripts/guardrails/verify_entity_label.py             # gate (exit 1 bila melanggar)
    python scripts/guardrails/verify_entity_label.py --self-test # bukti-merah: harus MENANGKAP
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SRC = ROOT / "frontend" / "src"
HELPER = SRC / "utils" / "entityLabel.js"
G, Y, R, C, B, X = "\033[92m", "\033[93m", "\033[91m", "\033[96m", "\033[1m", "\033[0m"

# Pola pelanggaran. Setiap entri: (regex, syarat kata pada baris, pesan, cek_cadangan).
# `syarat` membuat cek SEMPIT: hanya baris yang jelas-jelas bicara ENTITAS yang
# diperiksa, supaya `product.name` / `customer.name` tidak ikut tertuduh.
# `cek_cadangan=True` berarti pelanggaran hanya dihitung bila pada baris itu
# **tidak ada** sumber nama manusia sama sekali (`short_name`/`legal_name`/`*name`) —
# jadi pola bertahan `e.legal_name || e.short_name || e.id` TIDAK dianggap salah.
PATTERNS = [
    (re.compile(r"\?\.\s*name\b"), "entities",
     "membaca `.name` dari daftar entitas (field itu TIDAK ADA di /api/entities)", False),
    (re.compile(r"label\s*:\s*\w+\.name\b"), "entities",
     "memakai `.name` sebagai label opsi entitas (label akan tampil KOSONG)", False),
    (re.compile(r"\|\|\s*(?:e|ent|entity)\.id\b"), "entit",
     "nama entitas hanya bersumber dari `id` teknis", True),
    (re.compile(r"entityName\s*\|\|\s*selectedEntity\b"), "",
     "cadangan nama entitas jatuh ke `selectedEntity` (id teknis)", False),
    (re.compile(r"\|\|\s*[\w.]*entity_id\b(?!\s*===)"), "entit",
     "nama entitas hanya bersumber dari `entity_id` teknis", True),
    # FASE P7 — LUBANG YANG DITEMUKAN SAAT PEMERIKSAAN LAYAR:
    # semua pola di atas hanya menangkap `entity_id` yang dipakai sebagai **CADANGAN**
    # (`nama || entity_id`). `entity_id` yang dicetak **LANGSUNG** ke layar tidak
    # tertangkap sama sekali — padahal itu bentuk pelanggaran yang paling telanjang.
    # Terukur: 7 tempat mencetak `ent_ksc` ke layar (Store Credit kolom "Entitas";
    # Transfer Gudang PT Sumber, PT Tujuan, "Pemilik:", + 2 baris jurnal antar-PT;
    # Cycle Count "Pemilik:") — semuanya lolos gate sampai FASE P7.
    # `(?<![=$])` menolak PENERUSAN PROP (`entityId={x.entity_id}`, `key={…}`) dan
    # penyusunan URL (`${API}/…/${acc.from_entity_id}/…`) — dua-duanya bukan teks layar.
    (re.compile(r"(?<![=$])\{\s*[\w.?]*entity_id\s*(?:\|\|\s*[^}]{0,24})?\}"), "",
     "mencetak `entity_id` MENTAH ke layar (pakai `entityShortFromCtx()`/`<EntityBadge>`)",
     False),
    # Bentuk TEMPLATE LITERAL untuk teks layar: `` ` • Pemilik: ${item.owner_entity_id}` ``
    # (kasus `CycleCount.jsx` — lolos pola di atas karena `${` sengaja dikecualikan di
    # sana untuk melindungi penyusunan URL). SENGAJA menuntut ada KATA lalu pemisah
    # (`Pemilik: `) tepat sebelum `${…}`: itu yang membedakan KALIMAT untuk pengguna dari
    # penyusunan kunci/testid, dua hal yang bukan teks layar dan sempat dituduh palsu:
    #   · `const key = `${r.product_id}|${r.owner_entity_id}|…`   → sebelum `${` ada `|`
    #   · `data-testid={`fulfill-candidate-${cand.entity_id}`}`   → sebelum `${` ada `-`
    (re.compile(r"[A-Za-z]{3,}[:\s]\s*\$\{\s*[\w.?]*entity_id\s*\}"), "",
     "menyisipkan `entity_id` MENTAH ke teks layar lewat template literal", False),
]

# Sumber nama manusia — bila salah satu ada di baris, cadangan ke id dianggap
# pertahanan terakhir yang wajar (bukan bug).
HUMAN_SOURCES = ("short_name", "legal_name", "_name", "doc_prefix", ".code", "entityshort",
                 "entityfull", "entitylabel")
# Konteks NON-TAMPILAN: id memang dipakai sebagai kunci React / parameter API.
# FASE P7 — ditambah penanda URL/permintaan (`${api`, `axios`, `fetch(`, `/api/`) supaya
# pola template-literal di bawah bisa menilai TEKS LAYAR tanpa menuduh penyusunan URL
# seperti `axios.post(`${API}/interco/accounts/${acc.from_entity_id}/remind`)`.
NON_DISPLAY = ("key={", "key=`", "params:", "entity_id:", "owner_entity_id:", "localstorage",
               "${api", "axios", "fetch(", "/api/")

# Berkas yang MEMANG bekerja dengan id (bukan tampilan nama) — dikecualikan eksplisit.
EXEMPT = {
    "utils/entityLabel.js",            # helper itu sendiri
    "components/EntityBadge.jsx",      # badge memakai short_name/kode, sudah aman
}


def scan(text: str, rel: str):
    out = []
    for i, line in enumerate(text.splitlines(), 1):
        s = line.strip()
        if s.startswith("//") or s.startswith("*"):
            continue
        low = line.lower()
        if any(tag in low for tag in NON_DISPLAY):
            continue
        for rx, need, msg, soft in PATTERNS:
            if need and need not in low:
                continue
            if soft and any(src in low for src in HUMAN_SOURCES):
                continue
            if rx.search(line):
                out.append((rel, i, msg, s[:120]))
    return out


def main() -> int:
    self_test = "--self-test" in sys.argv

    print(f"{C}{B}")
    print("=" * 74)
    print("  INV-UI-02 — ID TEKNIS ENTITAS TIDAK BOLEH TAMPIL KE PENGGUNA")
    print("=" * 74)
    print(f"{X}")

    if not HELPER.exists():
        print(f"  {R}[FAIL]{X} helper wajib tidak ada: {HELPER.relative_to(ROOT)}")
        return 1
    print(f"  helper bersama : {HELPER.relative_to(ROOT)} ✓")

    findings = []
    files = 0
    for path in sorted(SRC.rglob("*.js")) + sorted(SRC.rglob("*.jsx")):
        rel = str(path.relative_to(SRC))
        if rel in EXEMPT or "/ui/" in rel.replace("\\", "/"):
            continue
        files += 1
        findings += scan(path.read_text(encoding="utf-8", errors="ignore"), rel)

    if self_test:
        # BUKTI-MERAH: suntikkan pelanggaran ke berkas sementara, guard harus menangkap.
        probe = "const entityName = entities.find((e) => e.id === selectedEntity)?.name;\n"
        got = scan(probe, "__probe__.jsx")
        if not got:
            print(f"  {R}[FAIL]{X} SELF-TEST: guard TIDAK menangkap pelanggaran yang disuntik.")
            return 1
        probe2 = "const opts = entities.map((e) => ({ value: e.id, label: e.name }));\n"
        if not scan(probe2, "__probe__.jsx"):
            print(f"  {R}[FAIL]{X} SELF-TEST: pola label opsi tidak tertangkap.")
            return 1
        # FASE P7 — `entity_id` dicetak LANGSUNG (bentuk yang dulu lolos).
        probe3 = '<td className="px-3">{r.entity_id || "—"}</td>\n'
        if not scan(probe3, "__probe__.jsx"):
            print(f"  {R}[FAIL]{X} SELF-TEST: `entity_id` mentah di JSX tidak tertangkap.")
            return 1
        probe4 = '<p className="font-semibold">{transfer.source_entity_id}</p>\n'
        if not scan(probe4, "__probe__.jsx"):
            print(f"  {R}[FAIL]{X} SELF-TEST: `source_entity_id` mentah tidak tertangkap.")
            return 1
        probe5 = 'const t = ` • Pemilik: ${item.owner_entity_id}`;\n'
        if not scan(probe5, "__probe__.jsx"):
            print(f"  {R}[FAIL]{X} SELF-TEST: `entity_id` mentah di template literal "
                  f"tidak tertangkap.")
            return 1
        # ANTI TUDUH PALSU: penerusan prop & penyusunan URL bukan teks layar.
        for aman, apa in (
            ('<EntityBadge entityId={row.entity_id} />\n', "penerusan prop entityId"),
            ('<tr key={item.entity_id}>\n', "pemakaian sebagai key React"),
            ('axios.get(`${API}/interco/${acc.from_entity_id}/remind`);\n', "penyusunan URL"),
            ('const key = `${r.product_id}|${r.owner_entity_id}|${r.lot}`;\n',
             "penyusunan kunci dedup"),
            ('<label data-testid={`fulfill-candidate-${cand.entity_id}`}>\n',
             "penyusunan data-testid"),
        ):
            if scan(aman, "__probe__.jsx"):
                print(f"  {R}[FAIL]{X} SELF-TEST: menuduh palsu — {apa}.")
                return 1
        print(f"  {G}[PASS]{X} SELF-TEST: guard menangkap 5 pelanggaran yang disuntik "
              f"(termasuk `entity_id` mentah di JSX & template literal) & menolak 5 kasus "
              f"sah (bukti-merah sah).")

    print(f"  berkas diperiksa: {files}")
    if not findings:
        print(f"\n  {G}{B}✓ 0 pelanggaran — nama entitas selalu lewat helper bersama.{X}\n")
        return 0

    print(f"\n  {R}{B}✗ {len(findings)} pelanggaran:{X}")
    for rel, ln, msg, code in findings:
        print(f"    {R}✗{X} {rel}:{ln} — {msg}")
        print(f"        {Y}{code}{X}")
    print(f"\n  {Y}→ Perbaiki dengan `entityShort/entityFull/entityShortById/"
          f"entityFullById/entityOptions` dari `utils/entityLabel.js`.{X}\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
