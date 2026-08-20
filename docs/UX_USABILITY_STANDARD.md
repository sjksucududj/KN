# UX & USABILITY STANDARD — Kain Nusantara (KN3)

> **Status:** WAJIB. Di-enforce secara **executable** oleh `scripts/ux_audit.py`.
> Prosa di sini hanyalah penjelasan; yang mengikat adalah cek yang bisa GAGAL.
> **Filosofi:** ERP dipakai operator gudang & sales tiap hari — UI harus
> *cepat dipahami, tahan-salah, dan jujur soal status data*.

---

## 1. PRINSIP DASAR

1. **Selalu jujur soal status data.** Setiap area yang memuat data dari API
   WAJIB punya 3 keadaan eksplisit: **loading**, **empty**, **error**.
   Layar kosong tanpa penjelasan = bug UX.
2. **Angka harus presisi & sejajar.** Semua angka uang/kuantitas pakai
   `tabular-nums` + format `id-ID` (`formatCurrency`, `formatQty`).
3. **Tahan-salah (forgiving).** Aksi destruktif (hapus, reset, dispatch)
   butuh konfirmasi; aksi panjang butuh indikator progress.
4. **Dapat dites.** Elemen interaktif penting punya `data-testid` stabil.
5. **Konsisten.** Pakai komponen shadcn/ui (`components/ui/`), bukan elemen HTML
   mentah (mis. `<select>` native).

---

## 2. ATURAN PER-KOMPONEN (yang dicek `ux_audit.py`)

### Tabel data — `[ERROR]` bila dilanggar
- **E1** WAJIB menampilkan **loading state** (skeleton/spinner) saat fetch.
- **E2** WAJIB menampilkan **empty state** ("Belum ada data ...") saat 0 baris.
- Kolom angka uang/qty **WAJIB** `tabular-nums` (**W1** bila belum — backlog presisi).
- Baris klik-able → sediakan drill-down/detail yang jelas.

### Chart (recharts) — `[ERROR]` bila dilanggar
- **E3** WAJIB ada **empty-state guard** (jangan render chart kosong tanpa pesan).
- **W4** Sebaiknya ada `<Tooltip>` agar nilai terbaca.

### Form / Modal / Dialog
- Validasi inline + pesan error spesifik (bukan hanya "error").
- Tombol submit disable saat proses; tampilkan loading.
- Dropdown `<select>` bawaan peramban **dilarang** → pakai `components/KNSelect.jsx` (**E4**, ERROR sejak FASE P6).

### KPI / Metric card
- Angka pakai `tabular-nums`; sertakan label & satuan yang jelas.
- Bila sumber kosong → tampilkan `0` yang benar, bukan blank/NaN.

### Aksesibilitas & testability
- Elemen interaktif (tombol/aksi) punya `data-testid` (**W3** bila ≥3 tombol tanpa testid).
- Kontras warna cukup; **JANGAN** pakai background transparan dengan teks gelap
  (user bisa di tema apa pun).

---

## 3. SEVERITAS & PEMBERLAKUAN

| Kode | Severitas | Arti | Pemberlakuan |
|------|-----------|------|--------------|
| E1–E3 | **ERROR** | Loading/empty/chart hilang | File **baru/disentuh WAJIB lolos**; file lama = backlog migrasi |
| E4 | **ERROR** | `<select>` bawaan peramban | Ganti ke `KNSelect`. Naik dari WARN pada FASE P6 setelah 13 dropdown terakhir dikonversi — angkanya **0**, jadi aturannya bisa ditegakkan keras |
| W1 | WARN | Uang tanpa `tabular-nums` | Backlog presisi (target: semua lolos) |
| W3 | WARN | Interaktif tanpa `data-testid` | Tambah testid |
| W4 | WARN | Chart tanpa Tooltip | Tambah Tooltip |

```bash
python scripts/ux_audit.py            # ringkasan
python scripts/ux_audit.py --strict   # exit 1 bila ada ERROR (gate pre-finish)
python scripts/ux_audit.py --file features/orders/OrdersView.jsx
```

**Aturan emas:** kamu boleh punya backlog (file lama), tetapi **dilarang
menambah ERROR baru**. Setiap file yang kamu sentuh harus keluar dalam kondisi
≥ sama baiknya (idealnya lebih baik) dari sebelumnya.

---

## 4. BASELINE SAAT INI (per 15 Jun 2026)

`ux_audit.py` melaporkan **±15 ERROR / 20 WARN di 38 file** sebagai **migration
backlog** (utamanya tabel WMS/admin tanpa loading/empty-state eksplisit & 0
`tabular-nums`). Ini **bukan regресi** — ini utang UX eksisting yang kini
**terukur** dan bisa dicicil. Prioritas migrasi:
1. Modul transaksi tinggi (Orders, Inventory, WMS tasks) → loading/empty + `tabular-nums`.
2. Dashboard & report (chart empty-state + Tooltip).
3. Master data (admin) → empty state.

> Target jangka menengah: `ux_audit.py --strict` hijau (0 ERROR).
