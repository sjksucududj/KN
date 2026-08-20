DEFAULT_PERMISSIONS = {
    "admin": {
        "product": ["view", "create", "update", "delete", "import", "export"],
        "color": ["view", "create", "update", "delete"],
        "makloon": ["view", "create", "update", "delete"],
        "makloon_order": ["view", "create", "issue", "receive", "cancel", "claim", "claim_approve"],
        "supplier_contract": ["view", "create", "update", "delete"],
        "supplier_item": ["view", "create", "update", "delete", "import"],
        "process_recipe": ["view", "create", "update", "delete"],
        "production": ["view", "manage_bom", "create", "release", "complete", "cancel"],
        "scheduler": ["view", "run", "configure"],
        "customer": ["view", "create", "update", "delete", "import", "export"],
        "warehouse": ["view", "create", "update", "delete", "import", "export"],
        "uom": ["view", "create", "update", "delete", "import", "export"],
        "template": ["view", "create", "update", "delete", "print", "import", "export"],
        "order": ["view", "create", "update", "delete", "approve", "confirm", "print",
                  "deliver", "verify"],
        "wms": ["view", "create", "update", "scan", "dispatch", "print", "approve"],
        "document": ["view", "create", "print"],
        "user": ["view", "create", "update", "delete"],
        "permission": ["view", "update"],
        # FASE E-0 (E0.3) — jejak audit punya resource izin SENDIRI. Sebelumnya
        # digerbang `product.view` sehingga sales & gudang membaca jejak SELURUH grup (L7).
        "audit": ["view"],
        # FASE E-0 (E0.8f) — sisi UANG antar-PT dipisah dari sisi BARANG.
        # `interco` (view/ship/receive) = aliran barang → boleh gudang.
        # `interco_finance` = saldo pasangan PT, pelunasan, laporan margin, penagihan
        #   → HANYA admin/manager (L20: gudang sebelumnya bisa membacanya).
        "interco_finance": ["view"],
        "inventory": ["view", "create", "update", "cycle_count", "approve_count", "pegging"],
        "reports": ["view", "export"],
        "label": ["view", "generate"],
        "transfer": ["view", "create", "update", "approve", "reject", "complete", "cancel"],
        "entity": ["view", "create", "update", "delete"],
        "price_approval": ["view", "create", "update", "delete", "approve", "reject"],
        "tax_invoice": ["view", "create", "update", "replace", "cancel", "print"],
        "sales_return": ["view", "create", "update", "approve", "reject"],
        # FASE F-6 — `approval.approve` DICABUT: satu-satunya endpoint yang memeriksanya
        # (`POST /approval-requests/{id}/approve|reject`) dipensiunkan karena mesin
        # persetujuan generiknya tak pernah punya produsen. Keputusan nyata dijaga izin
        # dokumennya masing-masing (`order.approve`, `transfer.approve`, dst).
        "approval": ["view"],
        "settings": ["view", "manage"],
        # FASE G-1 — amandemen dokumen finansial (koreksi ber-alasan & ber-persetujuan)
        "finance_amendment": ["propose", "approve", "admin"],
        # FASE G-2 — rencana pembayaran fleksibel + denda sebagai dokumen
        "payment_plan": ["view", "create", "update", "void"],
        "penalty": ["view", "issue", "waive", "adjust", "pay"],
        # FASE G-3 — keputusan selisih pembayaran (lebih/kurang bayar)
        "payment_variance": ["view", "decide"],
        # FASE G-9 — pusat kasus keuangan (uang nyangkut: salah transfer, dobel, giro ditolak)
        "finance_case": ["view", "create", "resolve", "admin"],
        # FASE G-7 — kontrabon: siklus tukar faktur supplier (gabung faktur, potongan, bayar)
        "contra_bon": ["view", "create", "update", "verify", "approve", "pay"],
        # FASE G-6 — transaksi antar-PT (jual-beli) + settlement/netting (admin: semua aksi)
        # FASE G-6b — `return` (retur antar-PT) & `tax` (faktur pajak internal).
        "interco": ["view", "create", "update", "approve", "ship", "receive", "invoice",
                    "cancel", "settle", "return", "tax"],
        # FASE E-7 (E7d) — Permintaan Internal: admin menindak antrean (jadikan
        # transaksi antar-PT / tolak dengan alasan).
        "internal_request": ["view", "create", "cancel", "reject", "convert"],
        # FASE F — R&D & Desain (spesifikasi · labdip/proofing · pattern · rilis produk)
        "rnd": ["view", "create", "submit", "assess", "decide", "manage"],
        "supplier": ["view", "create", "update", "delete"],
        "cash": ["view", "create", "delete"],
        "fixed_asset": ["view", "create", "update", "run", "dispose"],
        "budget": ["view", "create", "update", "delete", "configure"],
        "purchase_order": ["view", "create", "update", "approve", "reject"],
        "purchase_return": ["view", "create", "update", "approve", "reject"],
        "purchase_requisition": ["view", "create", "update", "approve", "reject"],
        "vendor_bill": ["view", "create", "update", "approve", "reject", "pay"],
        "landed_cost": ["view", "create", "update", "approve", "reject", "pay"],
        "input_tax": ["view", "create", "cancel"],
        "rfq": ["view", "create", "update", "award"],
        "ar_receipt": ["view", "create", "void"],
        "accounting": ["view", "create", "void", "manage"],
        # FASE G-5 — buka periode tertutup: usul/setujui (unlock) + posting mundur (backdate).
        "period": ["unlock", "backdate"],
        "pricelist": ["view", "manage"],
        "hr": ["view", "create", "update", "delete", "view_pii", "manage_org", "manage_settings", "manage_attendance", "manage_payroll"],
        "cash_advance": ["view", "create", "update", "submit", "approve", "reject", "disburse"],
        "cash_settlement": ["view", "create", "update", "submit", "approve", "reject", "manage"],
        "vehicle_log": ["view", "create", "update", "delete"],
        "pdf_template": ["view", "manage"],
        "esign": ["view", "sign", "manage"],
        "document_delivery": ["view", "send", "manage"],
    },
    "sales": {
        "product": ["view"],
        # FASE F — sales boleh MENGAJUKAN permintaan sample untuk pelanggan
        # (mis. minta labdip warna khusus), tetapi tidak menilai/memutus.
        "rnd": ["view", "create"],
        "color": ["view", "create"],
        # Fase D — sales HANYA view (traceability & recall output makloon).
        # Tarif/kontrak mitra (supplier_contract) TETAP tertutup: data komersial.
        "makloon": ["view"],
        "makloon_order": ["view"],
        "customer": ["view", "create", "update"],
        "warehouse": ["view"],
        "uom": ["view"],
        "template": ["view"],
        "order": ["view", "create", "update", "print"],
        # FASE G-1 — sales boleh MENGAJUKAN koreksi (bukan menyetujui).
        "finance_amendment": ["propose"],
        "payment_plan": ["view"],
        "penalty": ["view"],
        # FASE E-8 (E8.2) — keputusan SELISIH BAYAR (lebih/kurang bayar) pindah ke
        # peran `finance`. Sales yang menagih tidak boleh sekaligus memutus selisihnya.
        "payment_variance": ["view"],
        # FASE G-9 — sales boleh MELAPORKAN kasus (mis. pelanggan bilang sudah transfer) &
        # melihat perkembangannya, tetapi TIDAK boleh menutup kasus uang.
        "finance_case": ["view", "create"],
        "document": ["view", "create", "print"],
        "inventory": ["view"],
        "price_approval": ["view", "create", "update"],
        # FASE E-8 (E8.2) — PEMISAHAN TUGAS (keputusan pemilik E8.10b#2). Yang mencatat
        # UANG MASUK (kwitansi AR) dan menerbitkan FAKTUR PAJAK adalah peran `finance`,
        # bukan orang yang juga membuat pesanan & menyepakati harga. Sales tetap boleh
        # MELIHAT (dia yang ditanya pelanggan "faktur saya sudah keluar belum?"),
        # tetapi tidak lagi menerbitkan/mencatat.
        "tax_invoice": ["view"],
        "sales_return": ["view", "create", "update"],
        "ar_receipt": ["view"],
        "pricelist": ["view"],
        "cash_advance": ["view", "create", "update", "submit"],
        "cash_settlement": ["view", "create", "update", "submit"],
        "vehicle_log": ["view", "create"],
        "esign": ["view", "sign"],
        "document_delivery": ["view", "send"],
        # FASE E-7 (E7d) — jalur yang hilang untuk sales: papan stok memberi isyarat
        # "tersedia di badan usaha lain", tetapi seluruh menu Antar Entitas 403 untuk
        # sales. Sales boleh MENGAJUKAN permintaan & membatalkan miliknya; yang
        # menjadikannya transaksi antar-PT tetap admin/manajer (E-8: `sales_admin`).
        "internal_request": ["view", "create", "cancel"],
    },
    "manager": {
        "product": ["view", "export"],
        # FASE F — manager: menilai spesifikasi, memutus pemenang sample, mengubah kebijakan R&D
        "rnd": ["view", "create", "submit", "assess", "decide", "manage"],
        "color": ["view", "create", "update", "delete"],
        "makloon": ["view", "create", "update", "delete"],
        "makloon_order": ["view", "create", "issue", "receive", "cancel", "claim", "claim_approve"],
        "supplier_contract": ["view", "create", "update", "delete"],
        "supplier_item": ["view", "create", "update", "delete", "import"],
        "process_recipe": ["view", "create", "update", "delete"],
        "production": ["view", "manage_bom", "create", "release", "complete", "cancel"],
        "scheduler": ["view", "run"],
        "customer": ["view", "create", "update", "export"],
        "warehouse": ["view", "create", "update", "export"],
        "uom": ["view"],
        "template": ["view"],
        "order": ["view", "create", "update", "approve", "confirm", "print", "deliver", "verify"],
        "wms": ["view", "create", "update", "scan", "dispatch", "print", "approve"],
        "document": ["view", "create", "print"],
        "inventory": ["view", "cycle_count", "approve_count", "update", "pegging"],
        "reports": ["view", "export"],
        "label": ["view", "generate"],
        "transfer": ["view", "create", "approve", "reject", "complete"],
        "entity": ["view"],
        "price_approval": ["view", "create", "update", "approve", "reject"],
        "tax_invoice": ["view", "create", "update", "replace", "cancel", "print"],
        "sales_return": ["view", "create", "update", "approve", "reject"],
        # FASE F-6 — `approval.approve` DICABUT: satu-satunya endpoint yang memeriksanya
        # (`POST /approval-requests/{id}/approve|reject`) dipensiunkan karena mesin
        # persetujuan generiknya tak pernah punya produsen. Keputusan nyata dijaga izin
        # dokumennya masing-masing (`order.approve`, `transfer.approve`, dst).
        "approval": ["view"],
        "settings": ["view"],
        # FASE E-0 (E0.8f) — manajer ikut memegang sisi UANG antar-PT.
        "interco_finance": ["view"],
        "finance_amendment": ["propose", "approve"],
        "payment_plan": ["view", "create", "update", "void"],
        "penalty": ["view", "issue", "waive", "adjust", "pay"],
        # FASE G-3 — keputusan selisih pembayaran (lebih/kurang bayar)
        "payment_variance": ["view", "decide"],
        # FASE G-9 — manager adalah penyetuju bawaan penyelesaian kasus keuangan
        # (ambang & batas nominalnya diatur `case.require_approval_above` / `case.refund_max_amount`).
        "finance_case": ["view", "create", "resolve"],
        # FASE G-7 — manager membuat, memverifikasi & menyetujui kontrabon. Kontrabon di atas
        # `contra_bon.approval_threshold_rupiah` tetap butuh admin (dijaga service, bukan matrix).
        "contra_bon": ["view", "create", "update", "verify", "approve", "pay"],
        # FASE G-6 — manager: buat/kirim/terima/faktur transaksi antar-PT + settlement
        # (ambang bernilai besar tetap butuh admin, dijaga service).
        # FASE G-6b — manager boleh mengajukan retur & menerbitkan faktur pajak internal.
        "interco": ["view", "create", "update", "approve", "ship", "receive", "invoice",
                    "cancel", "settle", "return", "tax"],
        # FASE E-7 (E7d) — manajer menindak antrean permintaan internal.
        "internal_request": ["view", "create", "cancel", "reject", "convert"],
        "supplier": ["view", "create", "update", "delete"],
        "cash": ["view", "create", "delete"],
        "fixed_asset": ["view", "create", "update", "run", "dispose"],
        "budget": ["view", "create", "update", "delete"],
        "purchase_order": ["view", "create", "update", "approve", "reject"],
        "purchase_return": ["view", "create", "update", "approve", "reject"],
        "purchase_requisition": ["view", "create", "update", "approve", "reject"],
        "vendor_bill": ["view", "create", "update", "approve", "reject", "pay"],
        "landed_cost": ["view", "create", "update", "approve", "reject", "pay"],
        "input_tax": ["view", "create", "cancel"],
        "rfq": ["view", "create", "update", "award"],
        "ar_receipt": ["view", "create", "void"],
        "accounting": ["view", "create", "void", "manage"],
        # FASE G-5 — manager ikut boleh usul/setujui unlock & posting mundur (dual-control).
        "period": ["unlock", "backdate"],
        "pricelist": ["view", "manage"],
        "hr": ["view", "create", "update", "delete", "view_pii", "manage_org", "manage_attendance", "manage_payroll"],
        "cash_advance": ["view", "create", "update", "submit", "approve", "reject"],
        "cash_settlement": ["view", "create", "update", "submit", "approve", "reject", "manage"],
        "vehicle_log": ["view", "create", "update", "delete"],
        "pdf_template": ["view", "manage"],
        "esign": ["view", "sign", "manage"],
        "document_delivery": ["view", "send", "manage"],
        # AUDIT SALES vs ADMIN SALES / PERAN (2026-08-15) — manajer HANYA-BACA daftar akun.
        # Bukti: layar "Karyawan" (`hr-employees`, menu resmi manajer) mengambil
        # `GET /users` untuk kolom **akun tertaut** (FASE E-2: akun ditaut ke karyawan).
        # Manajer tidak punya `user.view` sehingga panggilan itu 403 lalu ditelan
        # `.catch(() => ({data: []}))` → kolomnya kosong TANPA satu pun pesan: manajer
        # menyimpulkan "karyawan ini belum punya akun" padahal punya.
        # MEMBUAT/mengubah/menghapus akun tetap milik admin (create/update/delete TIDAK diberi).
        "user": ["view"],
    },
    # ═══════════════════════════════════════════════════════════════════════════
    # FASE E-8 (E8.1b) — DUA PERAN BARU. Sampai E-7 orang yang mengurus keseluruhan
    # pesanan harus dijadikan `sales` (tak bisa Konfirmasi SO) atau `manager` (ikut
    # dapat kuasa tutup buku, payroll, bayar tagihan supplier, hapus master).
    # Registry peran: `backend/role_registry.py`.
    # ═══════════════════════════════════════════════════════════════════════════
    "sales_admin": {
        # ADMIN SALES — pemilik alur pesanan end-to-end: validasi → keputusan
        # pemenuhan (stok sendiri · ambil dari PT lain · reorder supplier) →
        # konfirmasi → dokumen → memproses retur.
        # TIDAK punya: tax_invoice · ar_receipt · payment_variance.decide · cash ·
        # accounting · vendor_bill (sisi uang & pajak tetap `finance`/manager/admin).
        "product": ["view"],
        "color": ["view"],
        "customer": ["view", "create", "update"],
        "warehouse": ["view"],
        "uom": ["view"],
        "template": ["view"],
        "pricelist": ["view"],
        "reports": ["view"],
        # `confirm` = wewenang yang dulu memaksa orang ini dijadikan manajer.
        # `deliver` = menandai pesanan terkirim (keputusan pemilik E8.10b#3:
        # boleh gudang MAUPUN Admin Sales; dicabut dari sales).
        # `verify` (E8.13) = VERIFIKASI ADMINISTRATIF — kelengkapan alamat/syarat bayar/
        # PPN/NPWP. SENGAJA dipisah dari `approve` (nilai · kredit · harga khusus) yang
        # tetap milik manajer: dulu satu-satunya gerbang adalah persetujuan nilai,
        # sehingga pemeriksaan rutin ikut menumpuk di meja manajer dan tidak ada catatan
        # siapa yang sudah memeriksa kelengkapannya.
        "order": ["view", "create", "update", "confirm", "print", "deliver", "verify"],
        "document": ["view", "create", "print"],
        # `pegging` (menahan roll untuk pelanggan/pesanan tertentu) = KEPUTUSAN
        # PEMENUHAN, dicabut dari `sales` di E8.2 dan diberikan ke peran ini.
        "inventory": ["view", "pegging"],
        "wms": ["view"],                       # memantau progres gudang, tanpa aksi
        "price_approval": ["view", "create", "update"],   # approve → manajer
        "sales_return": ["view", "create", "update"],     # approve → manajer
        "purchase_requisition": ["view", "create", "update"],  # reorder ke supplier
        # Antar-PT: boleh membuat & menagihkan; `settle`/`cancel` tetap manajer.
        "interco": ["view", "create", "update", "invoice"],
        # E8.8 — antrean Permintaan Internal (PIN) memang milik Admin Sales.
        "internal_request": ["view", "create", "cancel", "reject", "convert"],
        "transfer": ["view", "create"],        # approve → manajer/gudang
        "approval": ["view"],                  # melihat antrean, tanpa menyetujui
        "finance_amendment": ["propose"],
        "payment_plan": ["view", "create", "update"],   # void/pembebasan → manajer
        "penalty": ["view"],
        "finance_case": ["view", "create"],
        "esign": ["view", "sign"],
        "document_delivery": ["view", "send"],
        "cash_advance": ["view", "create", "update", "submit"],
        "cash_settlement": ["view", "create", "update", "submit"],
        "vehicle_log": ["view", "create"],
        "rnd": ["view"],
        "makloon_order": ["view"],
        # ─── HANYA-LIHAT, ditambah setelah AUDIT SALES vs ADMIN SALES ──────────
        # (`scripts/audit_sales_roles_ux.py`, sesi 2026-08-15). Empat izin di bawah
        # BUKAN pelebaran wewenang: semuanya `view` saja, dan semuanya menutup
        # LAYAR MATI yang terbukti — menu/tab yang memang diberikan ke peran ini
        # tetapi datanya 403 sehingga pengguna menabrak dinding tanpa penjelasan.
        #
        # `supplier`/`supplier_item` — keputusan pemilik E8.10b#4 memberi Admin Sales
        #   kuasa penuh "reorder ke supplier" (membuat PR). Tanpa membaca daftar
        #   pemasok & item pemasok, pemilih pemasok di formulir PR kosong dan
        #   `preferred_supplier_id` tak bisa diisi — kuasa yang diberikan di atas
        #   kertas tidak bisa dipakai di layar.
        # `tax_invoice` — panel detail pesanan (layar utama peran ini) membaca
        #   `GET /tax-invoices?order_id=…` untuk menunjukkan faktur pajaknya SUDAH
        #   terbit atau belum. Peran `sales` sudah punya `view`; tanpa ini Admin
        #   Sales melihat "belum ada faktur" padahal ada — kegagalan SENYAP
        #   (kesalahan gagal ditampilkan; `.catch` mengubah 403 jadi daftar kosong).
        #   MENERBITKAN faktur tetap milik `finance` (tidak ada `create` di sini).
        # `ar_receipt` — panel riwayat uang masuk di Worklist Penagihan. `sales`
        #   pun sudah boleh MELIHAT; mencatat uang masuk tetap milik `finance`.
        "supplier": ["view"],
        "supplier_item": ["view"],
        "tax_invoice": ["view"],
        "ar_receipt": ["view"],
    },
    "finance": {
        # KASIR / FINANCE — sisi UANG MASUK & PAJAK KELUARAN.
        # CATATAN: sisi HUTANG (vendor_bill.pay, contra_bon, landed_cost) TETAP
        # manajer/admin sampai pemilik memutuskan sebaliknya — jangan diperluas sendiri.
        "product": ["view"],
        "customer": ["view"],
        "template": ["view"],
        "pricelist": ["view"],
        "reports": ["view"],
        "order": ["view", "print"],            # tanpa create/update/confirm
        "document": ["view", "print"],
        "sales_return": ["view"],
        "ar_receipt": ["view", "create"],      # void → manajer
        "tax_invoice": ["view", "create", "update", "replace", "print"],   # cancel → manajer
        "payment_variance": ["view", "decide"],  # batas nominal tetap dijaga config
        "penalty": ["view", "issue"],          # waive/adjust → manajer
        "payment_plan": ["view", "update"],
        "cash": ["view", "create"],
        "accounting": ["view"],
        "finance_case": ["view", "create"],
        "finance_amendment": ["propose"],
        "approval": ["view"],
        "esign": ["view", "sign"],
        "document_delivery": ["view", "send"],
        "cash_advance": ["view", "create", "update", "submit"],
        "cash_settlement": ["view", "create", "update", "submit"],
        # AUDIT SALES vs ADMIN SALES / PERAN (2026-08-15) — Finance HANYA-BACA master supplier.
        # Bukti: "Kasus Keuangan" (`finance-cases`) adalah menu RESMI peran ini, dan
        # `FinanceCasesView.loadRefs()` mengambil `/suppliers` di dalam SATU `Promise.all`
        # bersama playbook, alasan, kebijakan, pelanggan, dan rekening. Tanpa izin ini
        # panggilan itu 403 → **seluruh** `Promise.all` gagal → playbook/pelanggan/
        # rekening kosong dan layar disambut bilah merah, padahal semua data lainnya
        # boleh dibaca. Nama lawan-transaksi memang dibutuhkan: kasus uang bisa
        # menyangkut supplier ("supplier bilang sudah kami bayar").
        # SISI HUTANG TETAP TERTUTUP: `vendor_bill`, `contra_bon`, `landed_cost` TIDAK
        # diberikan (keputusan pemilik E8.1b) — ini hanya master nama, read-only.
        "supplier": ["view"],
    },
    "warehouse": {
        "product": ["view"],
        # FASE F — warehouse: melihat permintaan sample & MENGELUARKAN bahan sample
        # dari roll (mutasi stok `sample_issue`).
        "rnd": ["view", "submit"],
        "color": ["view"],
        "makloon": ["view"],
        "makloon_order": ["view", "issue", "receive", "claim"],
        "supplier_contract": ["view"],
        "supplier_item": ["view"],
        "process_recipe": ["view"],
        "production": ["view", "create", "release", "complete"],
        "warehouse": ["view", "create", "update"],
        "uom": ["view"],
        "template": ["view"],
        "order": ["view", "deliver"],
        "wms": ["view", "create", "update", "scan", "dispatch", "print"],
        "document": ["view", "create", "print"],
        "inventory": ["view", "cycle_count", "update", "pegging"],
        "label": ["view", "generate"],
        "transfer": ["view", "create", "update"],
        "purchase_order": ["view"],
        "purchase_return": ["view", "create"],
        "purchase_requisition": ["view", "create", "update"],
        "vendor_bill": ["view"],
        # FASE G-7 — gudang IKUT MELIHAT kontrabon: dialah yang tahu barang mana sudah
        # diterima tapi fakturnya belum datang ("GR belum ditagih"). Tidak boleh mengubah uang.
        "contra_bon": ["view"],
        # FASE G-6 — gudang ikut melihat transaksi antar-PT (barang fisik lewat mereka)
        # + boleh menandai ship/receive (aliran barang), tanpa mengubah uang.
        "interco": ["view", "ship", "receive"],
        "landed_cost": ["view"],
        "input_tax": ["view"],
        "rfq": ["view", "create", "update"],
        "vehicle_log": ["view", "create", "update"],
        "esign": ["view", "sign"],
        "document_delivery": ["view", "send"],
        # AUDIT SALES vs ADMIN SALES / PERAN (2026-08-15) — gudang HANYA-BACA master supplier.
        # Bukti: peran ini SUDAH punya `rfq.create`, `purchase_requisition.create`,
        # `purchase_return.create`, `supplier_contract.view`, `supplier_item.view` —
        # tetapi TIDAK `supplier.view`. Akibatnya di 4 layar resminya (Permintaan
        # Pembelian · RFQ · Retur Beli · Kontrabon) daftar supplier 403 lalu ditelan
        # `.catch(() => ({data: []}))`: dropdown "Supplier" KOSONG tanpa pesan, jadi
        # formulir yang boleh mereka isi tak bisa diselesaikan. Membuat/mengubah master
        # supplier tetap manajer/admin.
        "supplier": ["view"],
    },
}
