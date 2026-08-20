# Rencana Lanjutan Development — KN (lanjutan dari titik henti POC FASE T)

## 1) Objectives
- Menutup **FASE T (Tahapan Proses + Screen)** sampai benar-benar demonstrable end-to-end (API + UI) dan **semua gate hijau**.
- Mengubah aturan audit **“override yield wajib beralasan”** jadi **SSOT di service** (bukan hanya router) agar seed/migrasi/API konsisten.
- Memperbaiki POC agar **idempotent + nol residu** dan tidak “mengakali” gate.
- Membangun **setengah frontend FASE T yang masih kosong**: Master Tahapan Proses, pemilih tahap SPK berbasis master, *material_flow chooser*, tombol **Catat Jasa** untuk langkah `service_only`, dan surfacing `warnings[]`.

## 2) Implementation Steps

### Phase 1 — Core POC (isolasi bukti) sampai `backend/test_core_tahapan_poc.py` hijau 2×
**User stories (core proof)**
1. Sebagai manajer, saya bisa membuat SPK gaya lama (hanya `process_type`) dan hasil estimasinya sama persis dengan SPK seed lama.
2. Sebagai admin, saya tidak bisa menonaktifkan/rename tahap yang masih dipakai SPK; sistem menyebut jumlah pemakainya.
3. Sebagai staf printing, tahap `screen` sebagai jasa murni menolak Issue dan mengarahkan ke aksi yang benar.
4. Sebagai staf printing, tahap `screen` dengan kain dikirim tetap tidak mengubah kuantitas kain (metode `no_transform`).
5. Sebagai auditor, setiap override yield memiliki alasan yang tertulis dan bisa diaudit.

**Pekerjaan**
1. **Pindahkan guard “override yield wajib beralasan” ke service (SSOT)**
   - Implementasi di `backend/services/makloon_order_service.py` (dipanggil oleh semua jalur penulisan: API, seed, migrasi, internal service calls).
   - Guard tetap mengikuti setting per-entity `require_yield_reason` (default True), dan pesan error tetap sama (400) agar kontrak API tidak berubah.
2. **Perbaiki seed SPK lama (MKO-00001/2/3) agar patuh guard**
   - Di `seed_realistic.py` tambahkan `yield_override_reason` nyata (mis. rujukan kontrak `KSC/SCT-00004`).
3. **Jadikan `_fase_t_snapshot.py diff` jujur terhadap 1 perubahan input yang disengaja**
   - Tambahkan allowlist eksplisit untuk perubahan `yield_override_reason` dan suffix explain “· alasan: …” (dengan output yang keras/terlihat).
   - Tetap menuntut **SEMUA** field angka/metode/explain (selain allowlist) identik byte-per-byte.
   - DILARANG re-record `spk_before.json`.
4. **Perbaiki POC T6 cleanup order (nol residu + gate ketat)**
   - Di `backend/test_core_tahapan_poc.py`: hapus SPK T8 (yang memakai stage uji) **sebelum** menghapus stage uji, lalu re-run gate INV-DOMAIN-06.
5. Jalankan berulang:
   - `python backend/test_core_tahapan_poc.py` **2× berturut** (target 60/60, nol residu).
   - `python scripts/guardrails/verify_master_stages.py --self-test` (harus lulus).

### Phase 2 — V1 App Development (frontend end-to-end FASE T)
**User stories (UX V1)**
1. Sebagai admin, saya bisa membuka Pengaturan → Master → **Tahapan Proses**, melihat kolom yang benar, dan menambah tahap baru (“Sanforize”).
2. Sebagai staf makloon, saya memilih tahap dari master (bukan hardcode) saat membuat SPK; tahap baru muncul tanpa restart.
3. Sebagai staf printing, bila tahap `screen` bertipe `either`, saya bisa memilih **kain dikirim** atau **jasa murni** per langkah.
4. Sebagai staf printing, untuk langkah `service_only` saya melihat tombol **Catat Jasa** (bukan Issue) dan proses bisa selesai dari UI.
5. Sebagai staf, bila mitra wajib tapi belum dipilih, saya tetap bisa simpan SPK namun melihat **peringatan (`warnings[]`)** yang jelas.

**Pekerjaan**
1. **Master screen “process-stages” di FE**
   - Tambah `COLUMNS` + `CREATE_FIELDS` untuk `process-stages` di `frontend/src/features/settings/masters/masterFieldsConfig.js` agar tabel tidak kosong.
   - Pastikan field types sesuai (select/list/checkbox/number) dan semua teks Indonesia.
   - Tambah `data-testid` untuk elemen kunci (baris/kolom/aksi tambah/simpan).
2. **MakloonOrderCreateModal**: ganti hardcode `PROCESS_LABELS` → master
   - Ambil opsi dari `GET /api/process-stages?spk_only=1` (dan/atau `/api/process-stages/for-line/{line}`) + fallback aman.
   - Kirim `stage_code` (dan `material_flow` bila dipilih) ke payload langkah; pertahankan `process_type` untuk kompatibilitas/regresi.
   - Tampilkan badge “tidak mengubah kain” bila `changes_stage=false`.
   - Jika `material_flow` master = `either`, tampilkan chooser dengan default `material_flow_default`.
   - Surfacing `warnings[]` setelah save (di modal, bukan toast error).
3. **MakloonOrderDetailPanel**: tombol & modal **Catat Jasa**
   - Untuk langkah `service_only`: tampilkan tombol `record-service` menggantikan `issue`.
   - Modal input minimal: mitra, dasar tarif, nominal, PPN, aux_cost; tampilkan explain ringkas.
   - Untuk langkah `moves`: tetap Issue/Receive seperti sekarang.
4. **Refactor sumber kosakata makloon**
   - `MakloonSelect.jsx`/`MakloonFormModal.jsx`: hentikan hardcode proses; gunakan `useDomainEnums()` + hasil `master_registry.process_types` via `/api/enums` (karena backend sudah meng-overlay).
   - Pastikan tidak memakai `alert/confirm/prompt` (gate INV-UI-06).
5. Rebuild FE: `bash scripts/rebuild_frontend.sh`.

### Phase 3 — Testing, gate, dan penutupan fase
**User stories (acceptance)**
1. Sebagai admin, saya bisa menambah tahap “Sanforize” dan tahap itu muncul di pemilih SPK tanpa restart.
2. Sebagai staf printing, saya menyelesaikan SPK Screen jasa murni lewat tombol Catat Jasa, tanpa roll baru.
3. Sebagai manajer, POC membuktikan angka SPK lama tidak bergeser.
4. Sebagai QA, `gate.sh --full` hijau dan tidak ada residu uji.
5. Sebagai maintainer, dokumen handoff menjelaskan titik henti baru dan jebakan fase berikutnya (FASE U).

**Checklist verifikasi**
1. Jalankan:
   - `python scripts/audit_md_erp_readiness.py --fase T`
   - `bash scripts/gate.sh --full`
   - `python scripts/guardrails/verify_master_stages.py` + `--self-test`
   - `python scripts/audit_i18n_id.py` (jika ada di gate) + `verify_api_contract` + `check_nav_map` + `ux_audit --strict` + `gate_residue.py` (sesuai gate.sh)
2. Delegasikan 1 putaran end-to-end ke `testing_agent_v3` fokus 3 user story FASE T (tambah stage, buat SPK screen service_only, lihat warnings).
3. Update dokumentasi & handoff:
   - `memory/test_credentials.md` (akun demo + password + catatan `token`)
   - `SESSION_HANDOFF.md` (FASE T ditutup + bukti)
   - `plan.md` (tandai FASE T selesai, next = FASE U)

## 3) Next Actions (langsung dieksekusi berurutan)
1. Implement SSOT guard yield-reason di `services/makloon_order_service.py` + sesuaikan router bila perlu agar pesan tetap konsisten.
2. Update `seed_realistic.py` (yield_override_reason) dan jalankan `python seed_realistic.py`.
3. Fix POC cleanup order (T6) + jalankan `python backend/test_core_tahapan_poc.py` sampai 60/60 2×.
4. Buat allowlist jujur di `_fase_t_snapshot.py diff` + jalankan `python backend/_fase_t_snapshot.py diff`.
5. Implement FE: masterFieldsConfig `process-stages`, SPK create stage picker, detail panel Catat Jasa, warnings.
6. Rebuild FE + jalankan `gate.sh --full`.

## 4) Success Criteria
- `python backend/test_core_tahapan_poc.py` **PASS semua (60/60)** dan dapat dijalankan berulang tanpa residu.
- `_fase_t_snapshot.py diff` melaporkan **identik untuk seluruh field angka & explain** kecuali **perubahan allowlist yang dicetak jelas** (yield_override_reason + suffix explain).
- UI: Master “Tahapan Proses” berkolom benar, bisa tambah “Sanforize”, muncul di form SPK.
- UI: langkah `service_only` memiliki tombol **Catat Jasa** (bukan Issue), flow selesai dari UI.
- `bash scripts/gate.sh --full` hijau; `audit_md_erp_readiness.py --fase T` SELESAI; `INV-DOMAIN-06` hijau + `--self-test` lulus.
