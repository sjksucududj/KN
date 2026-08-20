"""PAGAR TULIS MODE "SEMUA ENTITAS" (FASE E-3 / E-4 · user story 7).

MASALAH NYATA yang ditutup berkas ini (dibuktikan 2026-08-10 dengan curl):

    POST /api/customers   header  X-Entity-Id: all
    → 200 OK, dan dokumennya mendarat di  entity_id="ent_ksc"

Artinya: admin yang sedang melihat **gabungan semua badan usaha** membuat
pelanggan/pesanan/faktur, lalu dokumen itu **diam-diam** masuk ke buku badan
usaha HOME-nya. Tidak ada pesan, tidak ada pilihan. Ini persis cacat yang
dicatat di `plan.md` §1.2: *mode "Semua Entitas" menulis diam-diam ke home*.

KEPUTUSAN PEMILIK (user story 7):
    "Sebagai admin dalam mode Semua Entitas, saya bisa melihat gabungan tetapi
     TIDAK BISA membuat dokumen; sistem meminta saya memilih satu entitas dulu."

─── ATURANNYA, DALAM SATU KALIMAT ──────────────────────────────────────────────
**Membuat sesuatu yang baru butuh memilih satu badan usaha. Menindak dokumen
yang sudah ada tetap boleh, karena dokumen itu sudah punya badan usahanya.**

Turunan teknisnya (semuanya diputuskan dari TEMPLATE RUTE, bukan tebak-tebakan
string):

  1. Pagar hanya menyala bila header `X-Entity-Id` bernilai `all`
     (itulah satu-satunya cara UI masuk mode gabungan).
  2. Metode baca (GET/HEAD/OPTIONS) tidak pernah dihalangi — gabungan memang
     untuk DIBACA.
  3. Rute yang punya parameter jalur (`/api/sales-orders/{order_id}/confirm`)
     BOLEH: badan usaha diambil dari dokumennya, dan `assert_entity_access`
     sudah menjaga agar dokumen PT lain tak bisa disentuh.
  4. Rute akar koleksi (`POST /api/customers`) DITOLAK **409** dengan pesan yang
     menuntun — kecuali terdaftar sebagai TINGKAT GRUP di bawah.
  5. Deny-by-default: rute tulis baru yang lupa didaftarkan akan **menolak**
     (pengguna dapat pesan jelas) alih-alih menulis ke buku yang salah. Untuk
     urusan uang, gagal-berisik jauh lebih murah daripada sukses-salah.

Kenapa middleware dan bukan dependency per-endpoint: ada **517 rute tulis**.
Menambal satu-satu berarti pagar yang bolong di tempat yang terlupakan — dan
justru tempat terlupakan itu yang membuat cacat ini hidup selama ini.

Uji bukti-merah: `python -m entity_write_guard --self-test` dan
`backend/test_core_e3_write_guard_poc.py`.
"""
from __future__ import annotations

from collections.abc import Iterable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Match

WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

MESSAGE = (
    "Mode “Semua Entitas” hanya untuk melihat gabungan. Pilih satu badan usaha "
    "dulu di pemilih badan usaha (kanan atas) sebelum membuat atau menyimpan data — "
    "supaya dokumennya tidak masuk ke buku badan usaha yang salah."
)

# ─── TINGKAT GRUP: rute tulis yang SAH tanpa memilih satu badan usaha ─────────
# Alasan tiap baris ditulis eksplisit. Tiga golongan saja yang boleh masuk sini:
#   (S) targetnya koleksi SHARED di `entity_scope.SCOPE_FIELD` (tidak punya
#       kolom badan usaha, jadi tidak ada risiko salah buku);
#   (G) memang urusan TINGKAT GRUP / lintas badan usaha by design;
#   (P) hanya PRATINJAU / hitungan / pekerjaan pemeliharaan — tidak melahirkan
#       dokumen baru milik satu badan usaha.
GROUP_LEVEL_EXACT: frozenset = frozenset({
    # (S) identitas & sesi
    "/api/auth/login", "/api/auth/logout",
    # (S) master badan usaha & akun itu sendiri (business_entities, users = SHARED)
    "/api/entities", "/api/users", "/api/permissions",
    # (S) konfigurasi sistem (system_settings = SHARED); nilai per-entitas dipilih
    #     lewat payload `entity_id`, bukan lewat konteks aktif.
    "/api/settings",
    "/api/config/values", "/api/config/values/reset", "/api/config/values/clear",
    "/api/config/simulate", "/api/config/impact-preview", "/api/config/impact-apply",
    # (S) master katalog bersama
    "/api/products", "/api/product-categories", "/api/product-templates",
    "/api/product-templates/detach", "/api/color-library",
    "/api/uoms", "/api/uom-conversions/rules", "/api/uom-conversions/settings",
    "/api/document-templates", "/api/payment-terms", "/api/sales-return-policies",
    "/api/gl/accounts", "/api/amendment-reasons",
    # (S) gudang: belum punya kolom badan usaha (FASE E-4 menambah sharing_mode);
    #     tetap master tingkat grup supaya admin bisa mendaftarkannya lebih dulu.
    "/api/warehouses",
    # (G) tarif insentif: badan usahanya dari payload (`entity_id`, bawaan "all")
    "/api/incentive-rates",
    # (G) FASE E-4 (E4.7) — harga per badan usaha: layar Pricelist SELALU mengirim
    #     `entity_id` di payload/kuerinya (ada pemilih badan usaha sendiri di layar),
    #     jadi tidak ada risiko "salah buku" walau konteksnya gabungan. Server tetap
    #     memeriksa badan usaha itu termasuk yang boleh diakses pengguna.
    "/api/pricelist", "/api/pricelist/import",
    # (S) infrastruktur penjadwal & WhatsApp (sys_* = SHARED)
    "/api/scheduler/settings", "/api/scheduler/wa-test",
    "/api/deliveries/whatsapp/settings", "/api/deliveries/whatsapp/rules",
    "/api/deliveries/whatsapp/send",
    "/api/notifications/generate", "/api/notifications/read-all",
    "/api/onboarding/reset", "/api/admin/integrations", "/api/admin/seed-demo",
    # (S) setelan modul (semuanya system_settings)
    "/api/lots/settings", "/api/receiving/uom-settings",
    "/api/hr/settings", "/api/hr/payroll/settings",
    # (G) ANTAR-BADAN-USAHA by design: dokumen kembar hidup di DUA badan usaha,
    #     jadi layar & POC-nya memang bekerja dalam konteks gabungan.
    "/api/interco/transactions", "/api/interco/settlements", "/api/interco/returns",
    "/api/transfers/inter-company",
    # (G) konsolidasi grup
    "/api/finance/consolidation/eliminations",
    "/api/finance/consolidation/eliminations/sync-from-pairs",
    "/api/consolidation/sync-g6",
    # (P) pratinjau / hitungan — tidak menyimpan dokumen
    "/api/amendments/preview", "/api/bank-reconciliation/preview",
    "/api/labels/preview", "/api/pdf/preview", "/api/documents/barcode",
    "/api/documents/generate",
    "/api/enums/products/validate", "/api/enums/stage-transitions/validate",
    "/api/finance/budget-check", "/api/hr/payroll/runs/preview",
    "/api/payment-plans/preview", "/api/payment-variances/assess",
    "/api/process-recipes/forecast", "/api/makloon-orders/estimate",
    "/api/supplier-contracts/resolve", "/api/supplier-contracts/tariff-preview",
    "/api/supplier-contracts/policy",
    "/api/uom-conversions/convert", "/api/uom-conversions/check-variance",
    "/api/sales-orders/preview-allocation", "/api/sales-orders/preview-lots",
    "/api/sales-orders/preview-roll-reconcile",
    "/api/esign/verify",
    # (P) pekerjaan pemeliharaan tingkat grup (dijalankan penjadwal/admin)
    "/api/finance-cases/scan", "/api/contra-bons/run-reminder",
    "/api/fixed-assets/run-depreciation", "/api/rnd/sla/escalate",
    "/api/finance/period-unlocks/reclose-expired", "/api/gl/sync",
    "/api/documents/refs/backfill", "/api/collection-reminders/mark",
    "/api/rfid/devices/seed-defaults",
})

# Awalan tingkat grup — dipakai untuk keluarga rute yang seluruhnya grup.
# (`/api/interco/...` sudah tercakup lewat aturan "punya parameter jalur", tetapi
#  ditulis eksplisit supaya niatnya terbaca dan tidak bergantung pada bentuk URL.)
GROUP_LEVEL_PREFIXES: tuple = (
    "/api/auth/",
    "/api/interco/",
    "/api/config/",
)


def is_group_level(template: str) -> bool:
    """Apakah rute ini sah ditulis tanpa memilih satu badan usaha?"""
    if not template:
        return False
    if template in GROUP_LEVEL_EXACT:
        return True
    return any(template.startswith(p) for p in GROUP_LEVEL_PREFIXES)


def decide(method: str, template: str, entity_header: str) -> bool:
    """`True` = boleh lanjut, `False` = tolak 409.

    Dipisah dari middleware supaya bisa diuji tanpa server (self-test di bawah).
    """
    if (entity_header or "").strip().lower() != "all":
        return True                      # bukan mode gabungan → bukan urusan pagar ini
    if method.upper() not in WRITE_METHODS:
        return True                      # membaca gabungan justru tujuan mode ini
    if is_group_level(template):
        return True                      # tingkat grup / SHARED / pratinjau
    # `{` = rute punya parameter jalur → menindak dokumen yang SUDAH punya badan
    # usaha. Tanpa parameter = akar koleksi = MEMBUAT data baru → wajib pilih satu.
    return "{" in template


def _route_template(app, scope) -> str:
    """Template rute (mis. `/api/sales-orders/{order_id}`) untuk request ini.

    Middleware berjalan SEBELUM routing, jadi templatenya dicocokkan manual
    dengan mesin routing Starlette yang sama — bukan regex karangan sendiri,
    supaya keputusan pagar tidak pernah berbeda dari rute yang benar-benar
    dijalankan. Hanya dijalankan untuk request tulis bermode gabungan (jarang).
    """
    for route in getattr(app, "routes", []):
        try:
            match, _child = route.matches(scope)
        except Exception:  # noqa: BLE001,S112 — rute non-HTTP (WebSocket/Mount): lewati
            continue
        if match == Match.FULL:
            return getattr(route, "path", "") or ""
    return ""


class EntityWriteGuardMiddleware(BaseHTTPMiddleware):
    """Menolak pembuatan data baru selagi pengguna berada di mode gabungan."""

    async def dispatch(self, request: Request, call_next):
        header = request.headers.get("X-Entity-Id", "")
        if (header or "").strip().lower() == "all" \
                and request.method.upper() in WRITE_METHODS:
            template = _route_template(request.app, request.scope)
            if not decide(request.method, template, header):
                return JSONResponse(status_code=409, content={"detail": MESSAGE})
        return await call_next(request)


# ─── SELF-TEST (bukti-merah: pagar harus bisa MEMERAH) ───────────────────────
def _self_test() -> int:
    cases: Iterable[tuple] = (
        # (metode, template, header, boleh_lanjut, keterangan)
        ("POST", "/api/customers", "all", False, "buat pelanggan di mode gabungan DITOLAK"),
        ("POST", "/api/sales-orders", "all", False, "buat pesanan di mode gabungan DITOLAK"),
        ("POST", "/api/ar-receipts", "all", False, "catat uang masuk DITOLAK"),
        ("POST", "/api/approval-rules", "all", False, "aturan persetujuan DITOLAK"),
        ("POST", "/api/hr/employees", "all", False, "karyawan DITOLAK"),
        ("POST", "/api/customers", "ent_ksc", True, "setelah memilih badan usaha: BOLEH"),
        ("POST", "/api/customers", "", True, "tanpa header (bawaan home): BOLEH"),
        ("GET", "/api/customers", "all", True, "membaca gabungan: BOLEH"),
        ("POST", "/api/products", "all", True, "master katalog bersama: BOLEH"),
        ("POST", "/api/uoms", "all", True, "master satuan bersama: BOLEH"),
        ("POST", "/api/entities", "all", True, "membuat badan usaha itu sendiri: BOLEH"),
        ("PATCH", "/api/users/{user_id}", "all", True, "ubah akun: BOLEH"),
        ("POST", "/api/interco/returns", "all", True, "retur antar-badan-usaha: BOLEH"),
        ("POST", "/api/tax-invoices/{fkt_id}/replace", "all", True,
         "aksi atas dokumen yang sudah ada: BOLEH"),
        ("POST", "/api/sales-orders/preview-lots", "all", True, "pratinjau: BOLEH"),
        ("DELETE", "/api/customers/{customer_id}", "all", True, "hapus dokumen ada: BOLEH"),
        ("POST", "/api/rute-baru-yang-lupa-didaftarkan", "all", False,
         "deny-by-default untuk rute tulis baru"),
    )
    fails = 0
    print("== SELF-TEST entity_write_guard (pagar mode “Semua Entitas”) ==")
    for method, template, header, expect, why in cases:
        got = decide(method, template, header)
        ok = got == expect
        fails += 0 if ok else 1
        print(f"  [{'PASS' if ok else 'FAIL'}] {method:6} {template:48} "
              f"X-Entity-Id={header or '(kosong)':8} → {'lanjut' if got else '409'}  · {why}")
    print(f"\n  {'HIJAU — pagar terbukti bisa memerah.' if not fails else f'MERAH — {fails} kasus gagal.'}")
    return 1 if fails else 0


if __name__ == "__main__":
    import sys
    sys.exit(_self_test())
