# PLAN — Master Detail "360°" (Supplier · Makloon · Karyawan)

Tujuan: samakan pola detail Supplier (dulu modal) menjadi **halaman 360° penuh** seperti
Customer 360° (CRM). Berlaku juga untuk Mitra Makloon & Karyawan, dan jadi pola standar.

## Keputusan user (klarifikasi)
1. Halaman detail penuh (ganti modal), ada tombol "Kembali ke daftar".
2. Panel keuangan (pengganti "Kontrol Kredit"): Total Hutang (AP Outstanding), Jatuh Tempo/Overdue,
   Nilai PO Terbuka, Termin (TOP), Lead time + metrik bantu (Total Pembelian YTD, dsb).
3. Tab Supplier: PO · Tagihan (Vendor Bill) · Retur Beli · Daftar Harga (pricelist + **riwayat harga**) · Dokumen · Scorecard.
4. Klik tiap record → **pop-up detail** lengkap (baris item + status + aksi dokumen Pratinjau/Unduh/WA).
5. Terapkan ke Supplier + Makloon + Karyawan; jadikan pola standar ke depan.

## Aset yang sudah ada (reuse)
- `Customer360Panel.jsx` (pola referensi), `Makloon360Panel.jsx` (sudah page, perlu diperkaya).
- `DocumentActionsBar.jsx` — Pratinjau/Unduh/E-Sign/WA (reusable). doc_type: purchase_order, vendor_bill,
  purchase_return, makloon_spk, dst.
- Backend: `supplier_360()`, `makloon_360()`, `GET /hr/employees/{id}`. `bill_financials(bill)` → outstanding/pay_status.
- Detail endpoints: `/purchase-orders/{id}`, `/vendor-bills/{id}`, `/purchase-returns/{id}`, `/makloon-orders/{id}`, `/hr/payslips/{id}`.

## Phase A — Supplier 360 (utama)
- A1 Backend: perkaya `supplier_360` → `finance{ap_outstanding, overdue_amount, overdue_days, open_po_value,
  purchase_ytd, paid_total, payment_term_code, lead_time_days, avg_lead_time_days}`, `documents[]`,
  `price_list[]`, `price_history{product_id: [...]}`.
- A2 Frontend: `RecordDetailModal.jsx` (shared pop-up: meta grid + item table + DocumentActionsBar).
- A3 Frontend: `Supplier360Panel.jsx` (page) + ubah `SuppliersView` ke pola list→page.
- A4 Rebuild FE + testing_agent.

## Phase B — Makloon 360 (perkaya)
- B1 Backend: `makloon_360` + `finance{service_ap_outstanding, overdue, spk_open_value, ...}`, `documents[]`.
- B2 Frontend: `Makloon360Panel` → panel keuangan + baris klik pop-up + tab Dokumen + DocumentActionsBar (makloon_spk).
- B3 Rebuild + test.

## Phase C — Karyawan 360 (baru)
- C1 Backend: `GET /hr/employees/{id}/360` → profil + ringkasan absensi + cuti + payslip + kpi + documents.
- C2 Frontend: `Employee360Panel.jsx` + wire `EmployeesView` list→page. Payslip → PDF (doc actions).
- C3 Rebuild + test.

## Status
- [x] A · [x] B · [x] C  — SELESAI & TERUJI

## Hasil testing (testing_agent iter_140)
- Backend **100% (25/25)**; Frontend **95% (23/24)**. 0 bug.
- Supplier 360: panel penuh, KPI AP/Overdue, tab PO/Tagihan/Retur/Daftar Harga(+riwayat harga)/Dokumen/Scorecard,
  klik record → RecordDetailModal + aksi dokumen (5 tombol incl. Pratinjau) — OK.
- Makloon 360: panel + KPI Hutang Jasa, tab Order/Tagihan/Dokumen, klik → pop-up + aksi dokumen — OK.
- Karyawan 360: panel + Gaji + ringkasan absensi, tab Absensi/Cuti/Slip Gaji/KPI, slip → pop-up + Unduh PDF — OK.
- Catatan INFO (bukan bug): 2 dari 8 karyawan (Bima, Fitri) memang belum punya payslip → empty-state benar.
  6 karyawan lain punya payslip (terverifikasi DB). Payslip PDF `/api/hr/payslips/{id}/pdf` → %PDF 200.
- Navigasi list⇄halaman 360 + tombol Kembali bekerja; tidak ada layar merah.

## Pola standar (untuk pengembangan berikutnya)
`<Master>360Panel` (halaman penuh) + `RecordDetailModal` (pop-up generik: meta + item + DocumentActionsBar/customActions).
Backend: endpoint `.../{id}/360` yang mengembalikan profil + `finance` + koleksi terkait + `documents`.

