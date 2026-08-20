# ALAT AUDIT ISOLASI ENTITAS

Dipakai pada sesi verifikasi 2026-08-10. **Jangan dibuat ulang** — perluas yang ada.
Semua skrip hanya-baca kecuali disebut sebaliknya, dan menulis laporan ke `/app/.logs/`.

| Skrip | Fungsi | Cara jalan |
|---|---|---|
| `audit_entity_isolation.py` | Sapuan SELURUH endpoint GET (±300) sebagai 4 identitas (sales PT-A, sales PT-B, admin@PT-A, admin@ALL). Menandai: kebocoran `ent_*` asing, endpoint "sama antar-PT" (kandidat shared/entity-blind), IDOR dokumen per koleksi, dan sebaran `entity_id` di seluruh koleksi DB. | `python scripts/entity_audit/audit_entity_isolation.py` → `.logs/audit_isolation_report.md` |
| `verify_leaks.py` | Bukti baris-demi-baris untuk kandidat kebocoran (menampilkan dokumen milik PT lain yang terlihat). | `python scripts/entity_audit/verify_leaks.py` |
| `verify_leaks2.py` | Endpoint AGREGAT (papan stok, neraca saldo, AR aging, ringkasan kas) + peta master data shared vs terpisah + harga per entitas. | `python scripts/entity_audit/verify_leaks2.py` |
| `probe_entity_flow.py` | Siklus hidup entitas: provisioning, duplikat short_name/doc_prefix, PATCH tanpa validasi, deaktivasi, RBAC non-admin. **MENULIS data uji** (bersihkan setelah pakai). | `python scripts/entity_audit/probe_entity_flow.py` |
| `probe_entity_flow2.py` | Cacat pengelolaan akun: `DELETE /users` 405, email duplikat lewat PATCH, turun jabatan tak mencabut akses, entitas nonaktif tetap terpilih. **MENULIS data uji.** | `python scripts/entity_audit/probe_entity_flow2.py` |

## Prasyarat
- Backend jalan (`supervisorctl status backend`) dan DB berisi data demo:
  `python /app/seed_realistic.py` (membuat `sales3@kainnusantara.id` — sales entitas `ent_kanda`,
  tanpa akun ini uji dua-entitas tidak mungkin).
- Kredensial: `memory/test_credentials.md`.

## Pembersihan setelah probe
```
mongosh --quiet --eval '
const d=db.getSiblingDB("test_database");
d.business_entities.deleteMany({short_name:{$regex:"^(PRB|PMN|NKL)"}});
d.users.deleteMany({email:{$regex:"(probe|uji\\.hapus|bekas\\.admin|sales\\.noent|sales\\.ngawur)"}});
d.customers.deleteMany({name:{$regex:"^(Probe Cust|Cust di PT mati)"}});
'
```
Catatan: probe pernah meninggalkan **12 `hr_org_units` yatim** (entitas sudah dihapus) — itu
temuan nyata (L11 di `plan.md`), bukan sekadar sampah uji.
