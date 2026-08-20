# KN_29 — FASE G-2: RENCANA PEMBAYARAN FLEKSIBEL & DENDA SEBAGAI DOKUMEN

**Status:** ✅ DITUTUP · 2026-07-27
**Bukti:** POC `backend/test_g2_payment_poc.py` **53/0** · `verify_data_integrity` **201 PASS / 0 FAIL / 0 WARN**
(INV-PAY-01/02 · INV-PEN-01/02/03) · `gate.sh --full` HIJAU · `testing_agent_v3` iter_177
(backend **73/73**, UI 19/20 — sisanya masalah selector harness, bukan bug produk).

---

## 1. MASALAH PEMILIK

1. **Term pembayaran kaku.** Sistem hanya punya kode `NET30`. Kenyataannya: *"DP 15% + 6×
   cicilan bulanan"*, *"DP 30% + pelunasan 45 hari"*, milestone *30% PO / 40% kirim / 30% terima*.
   Jadwal tagih hidup di kepala orang → penagihan meleset.
2. **Denda cuma angka.** Denda hanya estimasi di laporan Umur Piutang: tidak bisa ditagih,
   tidak bisa dinegosiasikan, tidak bisa dibebaskan dengan alasan, tidak pernah masuk pembukuan.

## 2. YANG DIBANGUN

### 2.1 Rencana Pembayaran (`payment_plans`, `pyp_`, nomor `<ENT>/RPB-#####`)
* Mode sebagai **titik awal**, bukan penjara: `dp_installment` · `milestone` · `net` · `custom`.
  Setelah dibentuk, setiap baris (jenis, label, nominal, aturan & tanggal jatuh tempo) bebas diubah.
* Baris: `seq · kind (dp|installment|retention|milestone) · label · basis (percent|amount) ·
  percent · amount · due_rule (net_days|monthly|weekly|fixed_date) · due_date · status · paid_amount`.
* **Σ baris WAJIB sama dengan nilai dokumen** (toleransi `payment.plan_tolerance_rupiah`) —
  ditolak server bila tidak, divalidasi LIVE di UI sebelum simpan.
* **Tidak ada pembukuan kedua**: `paid_amount` per baris DITURUNKAN dari `sales_orders.payments[]`
  (alokasi berurutan/waterfall) setiap kwitansi masuk, sehingga jadwal tak mungkin berbeda dari kas.
* Rencana adalah **dokumen** (FASE G-4): menaut SO dua arah → muncul di Jejak Dokumen.

### 2.2 Nota Denda (`penalties`, `pnl_`, nomor `<ENT>/DN-DENDA-#####`)
```
draft (TANPA jurnal)  ──terbitkan──>  issued   Dr 1-1270 Piutang Denda / Cr 4-9300 Pendapatan Denda
   │                                    ├──bayar──>      paid      Dr Kas/Bank / Cr 1-1270
   │                                    ├──bebaskan──>   waived    JE PEMBALIK (append-only)
   │                                    └──ubah nominal─> adjusted JE SELISIH
   └── bebaskan / ubah nominal saat masih draft → cukup ubah dokumen (tak ada jurnal)
```
* **Kunci fleksibilitas:** denda lahir `draft` sehingga bisa dinegosiasikan **tanpa** mengotori GL.
* Pembebasan & perubahan nominal WAJIB **label alasan** (taksonomi `amendment_reasons` warisan
  G-1 — admin bisa menambah sendiri) + **hak putus** (`payment.penalty_waive_approver_role`).
  Sales ditolak 403.
* Perhitungan disertai `explain[]` (dasar · hari telat − tenggang · bunga · batas) supaya
  angkanya bisa dipertanggungjawabkan ke pelanggan.
* Job penjadwal **`penalty_accrual`** (harian 07:45 WIB) — idempotent: satu nota per baris per
  bulan; nota yang sudah diputus manusia tidak pernah ditimpa mesin.

### 2.3 Frontend
| Layar | Isi |
|---|---|
| **Keuangan → Rencana Bayar & Denda** (`payment-plans`) | 5 KPI · tab **Antrean Denda** & **Jadwal Pembayaran** · filter status · aksi denda · deep-link ke Jejak Dokumen & pesanan |
| Panel **Jadwal Pembayaran & Denda** di detail SO | ringkasan terbayar · tabel baris + status · tombol *Susun/Ubah Jadwal* · *Hitung Denda* · panel denda |
| **PaymentPlanBuilder** | template DP%/jumlah cicilan/jarak · edit bebas per baris · **validasi Σ live** (badge “Sudah pas” / “Selisih …”) · tombol “sisa” membebankan selisih ke satu baris · Simpan disabled bila belum pas |
| **PenaltyPanel** | Terbitkan · Ubah Nominal · Bebaskan · Catat Bayar — dialog mewajibkan label alasan |

## 3. KONFIGURASI (Pusat Pengaturan → **Uang Masuk & Piutang**)
`payment.plan_required_above_amount` · `payment.plan_tolerance_rupiah` ·
`payment.default_dp_percent` · `payment.default_installments` ·
`payment.default_installment_interval` · `payment.penalty_mode` (off|draft|auto) ·
`payment.penalty_base` (installment|outstanding) · `payment.penalty_cap_pct` ·
`payment.penalty_min_amount` · `payment.penalty_waive_requires_approval` ·
`payment.penalty_waive_approver_role`.

Bunga & tenggang **sengaja memakai kunci lama** `ar.denda_rate_pct_per_month` & `ar.grace_days`
supaya laporan Umur Piutang dan nota denda tidak pernah bercerita beda.

POC membuktikan sakelar ini **nyata**: `off` → tidak ada denda; tenggang 180 hari → telat 62 hari
belum kena denda; `auto` → denda langsung terbit + berjurnal; bunga 2%→4% menggandakan nominal;
batas 0,5% benar-benar memotong.

## 4. INVARIAN (bukti-merah semua diuji di POC)
| Kode | Isi |
|---|---|
| INV-PAY-01 | Σ baris rencana == nilai dokumen (toleransi configurable) |
| INV-PAY-02 | alokasi terbayar ≤ nominal baris & ≤ kas nyata dokumen |
| INV-PEN-01 | denda `draft` tidak boleh punya jurnal |
| INV-PEN-02 | `waived`/`adjusted` wajib label alasan + pemutus |
| INV-PEN-03 | Σ denda terbit belum dibayar == saldo GL 1-1270 |

Gate: `verify_data_integrity` (201) + `POC FASE G-2` pada `gate.sh --full`.

## 5. AKUN GL BARU
`1-1270` Piutang Denda Pelanggan · `4-9300` Pendapatan Denda Keterlambatan.

## 6. CARA UJI CEPAT
```bash
cd /app
python backend/test_g2_payment_poc.py       # harus 53 / 0
python scripts/verify_data_integrity.py     # harus 201 PASS / 0 FAIL
bash scripts/gate.sh --full                 # semua gate HIJAU
```
UI: Keuangan → **Rencana Bayar & Denda**; atau buka satu pesanan → panel
**Jadwal Pembayaran & Denda** → *Susun Jadwal*.

## 7. BATAS CAKUPAN (jujur)
* Rencana pembayaran baru berlaku untuk **sales_order** (PO/vendor bill menyusul di G-7).
* Pembebasan/perubahan denda memakai **hak putus berbasis peran**, belum antrean approval
  bertingkat seperti amandemen G-1 (kebijakan `payment.penalty_waive_requires_approval` sudah
  disiapkan sebagai sakelarnya).
* Kolom denda pada laporan Umur Piutang masih estimasi lama; menautkannya ke nota denda nyata
  adalah pekerjaan lanjutan kecil (endpoint & data sudah tersedia).
* Nota denda belum punya template PDF khusus (bisa dicetak setelah didaftarkan di Print Center).
