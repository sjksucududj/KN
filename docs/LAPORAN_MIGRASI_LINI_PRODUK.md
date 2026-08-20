# Laporan Migrasi Lini Produk (FASE L)

> Dibuat otomatis oleh `scripts/migrate_lini_produk.py`.
> Lini adalah **pembagian kerja MD**, bukan jenis kain. Data lama tidak pernah
> menyimpannya, jadi baris di bawah adalah **tebakan mesin** yang WAJIB ditinjau
> manusia. Koreksi dilakukan **lewat layar** Master Produk (kolom *Lini*) —
> bukan dengan menjalankan skrip lagi (skrip tidak menimpa nilai yang sudah ada).

## Ringkasan

| Lini | Jumlah produk |
|---|---|
| `knit` | 1 |
| `printing` | 4 |
| `woven` | 14 |

**Perlu ditinjau: 0 produk** (motif yang biasanya DITENUN, bukan dicetak).

## Perlu ditinjau lebih dulu

| SKU | Nama | Lini usulan | Alasan |
|---|---|---|---|
| — | — | — | tidak ada |

## Seluruh produk

| SKU | Nama | Lini | Alasan | Diubah migrasi? |
|---|---|---|---|---|
| `BTK-MEGA-001` | Batik Mega Mendung Premium | printing | sudah terisi — tidak diubah | tidak |
| `TNI-GRGD-001` | Tenun Ikat Garuda Premium | woven | sudah terisi — tidak diubah | tidak |
| `LRK-CLSC-001` | Lurik Klasik Solo | woven | sudah terisi — tidak diubah | tidak |
| `SGK-PLB-001` | Songket Palembang Benang Emas | woven | sudah terisi — tidak diubah | tidak |
| `ULS-BTK-001` | Ulos Batak Ragidup | woven | sudah terisi — tidak diubah | tidak |
| `JMP-PLB-001` | Jumputan Palembang Pelangi | printing | sudah terisi — tidak diubah | tidak |
| `ENK-BALI-001` | Endek Bali Rangrang | woven | sudah terisi — tidak diubah | tidak |
| `DNM-BDG-001` | Denim Selvedge Bandung | woven | sudah terisi — tidak diubah | tidak |
| `BNG-KTN-001` | Benang Katun Cone (per Kg) | woven | sudah terisi — tidak diubah | tidak |
| `BTK-MEGA-002` | Batik Mega Mendung Premium | printing | sudah terisi — tidak diubah | tidak |
| `BTK-MEGA-003` | Batik Mega Mendung Premium | printing | sudah terisi — tidak diubah | tidak |
| `ENK-BALI-002` | Endek Bali Rangrang | woven | sudah terisi — tidak diubah | tidak |
| `ENK-BALI-003` | Endek Bali Rangrang | woven | sudah terisi — tidak diubah | tidak |
| `GREY-KTN-001` | Kain Grey Katun (per Yard) | woven | sudah terisi — tidak diubah | tidak |
| `BNG-KTN-SISA` | Benang Katun Sisa (per Kg) | woven | sudah terisi — tidak diubah | tidak |
| `GREY-KTN-SISA` | Kain Grey Katun Sisa (per Yard) | woven | sudah terisi — tidak diubah | tidak |
| `RND-KTN-150` | Katun Combed 150 gsm Warna Khusus | knit | sudah terisi — tidak diubah | tidak |
| `KMB-BTL-001` | Kain Kombinasi Batik-Lurik (per Yard) | woven | sudah terisi — tidak diubah | tidak |
| `E9-DEMO-01` | Kain Demo Rantai Retur (E-9) | woven | sudah terisi — tidak diubah | tidak |

## Dokumen yang ikut distempel

| Koleksi | Dokumen disentuh | Total dokumen |
|---|---|---|
| `sales_orders` | 0 | 11 |
| `purchase_orders` | 0 | 14 |
| `purchase_requisitions` | 0 | 5 |
| `warehouse_transfers` | 0 | 7 |
| `sales_returns` | 0 | 3 |
| `purchase_returns` | 0 | 3 |
| `interco_transactions` | 0 | 12 |
| `special_orders` | 0 | 2 |
| `internal_requests` | 0 | 2 |
| `rfqs` | 0 | 3 |
| `inventory_rolls` | 0 | 59 |
| `inventory_lots` | 0 | 32 |
| `wms_tasks` | 0 | 24 |
| `md_specs` | 0 | 2 |
| `md_samples` | 1 | 28 |
| `design_gallery` | 0 | 4 |
| `makloon_orders` | 0 | 3 |

## Cara mengoreksi (untuk pemilik)

1. Buka **Master Produk** (Admin → Produk).
2. Pakai chip **Lini** untuk melihat isi tiap lini.
3. Buka produk yang salah → ubah **Lini** → Simpan.
   Pagar `INV-LINE-02` akan menolak kombinasi yang bertentangan
   (mis. lini `knit` untuk kain `woven`) beserta alasannya.
4. Lini baru (mis. **Denim**) ditambah di **Pengaturan → Master → Lini Produk**;
   chip-nya langsung muncul di 12 layar tanpa perubahan kode.
