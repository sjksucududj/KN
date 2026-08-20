"""Kain Nusantara API — modular FastAPI application."""
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import os

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

from db import client
import bootstrap
from entity_write_guard import EntityWriteGuardMiddleware

# Import all routers
from routers import (
    auth, users, dashboard, products, customers, warehouses, uoms,
    inventory, sales_orders_extra, sales_orders, invoices, wms, documents, admin,
    reporting, audit, cycle_count, onboarding, label_printer, transfers,
    purchase_orders_extra, purchase_orders, inbound_receiving_extra, inbound_receiving, outbound_picking_extra, outbound_picking,
    entities, notifications, settings, price_approvals, pegging, tax_invoices,
    sales_returns, special_orders, approval_rules,
    suppliers, cash, purchase_returns, purchase_requisitions, vendor_bills,
    landed_cost, input_tax, rfq, qc_inspection, crm, home, categories,
    costing, ar_receipts, incentive_rates, ar_aging, bank, gl, pricelist, product_templates,
    stock_buckets, pos, so_approvals, hr, hr_attendance, hr_tracking, hr_payroll,
    hr_leave, hr_kpi, design_gallery, integrations, hr_analytics, tax_center,
    financial_statements, closing, finance_bi, crm_omnichannel, consolidation,
    rfid,
    finance_analytics, budgets, color_library,
    makloons, process_recipes, makloon_orders,
    enums, uom_conversions,
    cash_advances, vehicle_logs, pdf, esign, deliveries, product_traceability,
    return_policies, store_credit, bank_reconciliation, fixed_assets,
    production, scheduler, lots, supplier_contracts, supplier_items,
    config,          # FASE G-0 — Pusat Pengaturan (registry + resolver + simulator)
    amendments,      # FASE G-1 — Amandemen dokumen (koreksi ber-alasan & ber-persetujuan)
    payment_plans,   # FASE G-2 — Rencana pembayaran fleksibel + denda sebagai dokumen
    payment_variance,  # FASE G-3 — Selisih pembayaran (lebih/kurang bayar) ber-keputusan
    finance_cases,   # FASE G-9 — Pusat Kasus Keuangan (uang nyangkut: 11 playbook)
    contra_bons,     # FASE G-7 — Kontrabon (siklus tukar faktur supplier)
    interco,         # FASE G-6 — Transaksi antar-entitas (jual-beli antar-PT + settlement)
    interco_loans,   # FASE E-7 (E7f) — Pinjaman uang antar-PT (dokumen kembar + eliminasi)
    internal_requests,  # FASE E-7 (E7d) — Permintaan Internal: sales minta barang dari PT lain
    period_unlocks,  # FASE G-5 — Unlock periode tertutup (dual-control + jendela waktu)
    rnd,             # FASE F  — R&D & Desain (spesifikasi · labdip/proofing · lifecycle produk)
    rnd_org,         # PS-17 — Divisi sebagai aktor R&D (divisi + matriks persetujuan)
    approvals_matrix,  # PS-20 — Matriks persetujuan MENGIKAT + antrean "Persetujuan Saya"
    customer_prices,   # F1b — Daftar Harga per Pelanggan (harga langganan per pelanggan×produk)
    work_desks,        # FASE E-8 (E8.7/E8.13/E8.15/E8.20) — Meja Admin Sales & Meja Finance
    access_review,     # Utang migrasi (ii) E-8 — "Cek Kenyataan Peran" berbasis bukti
)

# ─── App factory ─────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    await bootstrap.run_bootstrap()
    # Sub-fase 1.7 — init object storage (best-effort; tak menggagalkan startup)
    try:
        from services.storage_service import init_storage
        await init_storage()
    except Exception as exc:  # noqa: BLE001
        import logging
        logging.getLogger("server").warning("[storage] init dilewati: %s", exc)
    # FASE H2 — muat cache posisi terkini (live tracking) best-effort
    try:
        from services.tracking_service import hydrate_latest
        await hydrate_latest()
    except Exception as exc:  # noqa: BLE001
        import logging
        logging.getLogger("server").warning("[tracking] hydrate dilewati: %s", exc)
    # R6.5 — Scheduler alert/notifikasi (APScheduler, zona Asia/Jakarta).
    # Guard single-instance via lock+heartbeat; nonaktifkan dgn KN_DISABLE_SCHEDULER=1.
    try:
        from services.scheduler_service import start_scheduler
        res = await start_scheduler()
        import logging
        logging.getLogger("server").info("[scheduler] %s", res)
    except Exception as exc:  # noqa: BLE001
        import logging
        logging.getLogger("server").warning("[scheduler] start dilewati: %s", exc)
    yield
    try:
        from services.scheduler_service import shutdown as sched_shutdown
        sched_shutdown()
    except Exception:  # noqa: BLE001
        pass
    client.close()


app = FastAPI(title="Kain Nusantara API", lifespan=lifespan)

# FASE E-3/E-4 (user story 7) — pagar tulis mode "Semua Entitas".
# Dipasang SEBELUM CORS di daftar (Starlette menjalankan middleware terakhir-
# ditambahkan paling luar), sehingga respons 409-nya tetap membawa header CORS
# dan pesannya bisa ditampilkan layar. Alasan & daftar rute tingkat grup ada di
# `entity_write_guard.py`.
app.add_middleware(EntityWriteGuardMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register all routers
for module in [
    auth, users, dashboard, products, customers, warehouses, uoms,
    inventory, sales_orders_extra, sales_orders, invoices, wms, documents, admin,
    reporting, audit, cycle_count, onboarding, label_printer, transfers,
    purchase_orders_extra, purchase_orders, inbound_receiving_extra, inbound_receiving, outbound_picking_extra, outbound_picking,
    entities, notifications, settings, price_approvals, pegging, tax_invoices,
    sales_returns, special_orders, approval_rules,
    suppliers, cash, purchase_returns, purchase_requisitions, vendor_bills,
    landed_cost, input_tax, rfq, qc_inspection, crm, home, categories,
    costing, ar_receipts, incentive_rates, ar_aging, bank, gl, pricelist, product_templates,
    stock_buckets, pos, so_approvals, hr, hr_attendance, hr_tracking, hr_payroll,
    hr_leave, hr_kpi, design_gallery, integrations, hr_analytics, tax_center,
    financial_statements, closing, finance_bi, crm_omnichannel, consolidation,
    rfid,
    finance_analytics, budgets,
    enums,          # Fase A (PS-01/02/03/09 · R7) — registry enum domain tekstil
    uom_conversions,  # Fase B (D-06/D-07) — registry konversi satuan GLOBAL + toleransi
]:
    app.include_router(module.router)

app.include_router(color_library.router)
app.include_router(makloons.router)
app.include_router(process_recipes.router)
app.include_router(makloon_orders.router)
# Digitalisasi Formulir Sukacita — Cash Advance/Settlement + Kendaraan
app.include_router(cash_advances.router)
app.include_router(vehicle_logs.router)
# Document/PDF Platform — render PDF asli, template config, branding
app.include_router(pdf.router)
# E-Sign — tanda tangan elektronik (OTP + verifikasi publik)
app.include_router(esign.router)
# Deliveries — pengiriman dokumen via WhatsApp (mode simulasi)
app.include_router(deliveries.router)
# Traceability asal barang — Kartu Asal Produk + retur presisi per roll/lot
app.include_router(product_traceability.router)
# R0 — Return Policy Engine (kebijakan retur jual: global/kategori/customer + eligibility)
app.include_router(return_policies.router)
# FASE E-4 (E4a/E4d) — MASTER BERLAPIS global → badan usaha (satu pintu untuk 6 master:
# syarat pembayaran, kategori biaya, template dokumen, kebijakan retur, tarif insentif,
# aturan persetujuan). Aturan & alasannya di services/entity_master_service.py.
from routers import entity_masters  # noqa: E402  (impor lokal: urutan router disengaja)
app.include_router(entity_masters.router)
# R5.2 — Store Credit (Saldo Kredit Pelanggan) ledger + redeem/adjust
app.include_router(store_credit.router)
# R6.1 — Bank Reconciliation otomatis (import statement + auto-match ↔ cash_transactions)
app.include_router(bank_reconciliation.router)
# FASE G-9 — Pusat Kasus Keuangan: antrean kasus uang + 11 playbook penyelesaian ber-dokumen
app.include_router(finance_cases.router)
# FASE G-7 — Kontrabon: gabung banyak faktur supplier satu siklus + potongan + bayar sekali
app.include_router(contra_bons.router)
# FASE G-6 — Transaksi antar-entitas (jual-beli antar-PT) + saldo pasangan + settlement/netting
app.include_router(interco.router)
app.include_router(interco_loans.router)       # FASE E-7 (E7f) — pinjaman antar-PT
app.include_router(internal_requests.router)  # FASE E-7 (E7d) — Permintaan Internal
app.include_router(period_unlocks.router)  # FASE G-5
# R6.2 — Fixed Assets & Depresiasi (straight-line) + disposal gain/loss (GL-safe, idempotent)
app.include_router(fixed_assets.router)
# R6.4 — Produksi In-House (BOM + Work Order): konsumsi roll bahan → produksi roll barang jadi (GL-safe)
app.include_router(production.router)
# R6.5 — Penjadwal (APScheduler) + Notifikasi/alert terjadwal + Outbox WhatsApp
app.include_router(scheduler.router)
# Fase C — Lot kelas satu (`inventory_lots`): identitas batch, silsilah, recall, label
app.include_router(lots.router)
app.include_router(supplier_contracts.router)
# Fase E — Barang Supplier (`supplier_items`): peta SKU/nama versi supplier + impor massal
app.include_router(supplier_items.router)
# FASE G-0 — Pusat Pengaturan: registry configurable + resolver berlapis + simulator +
# riwayat + berlaku-sejak + Daftar Dampak (blast-radius picker).
app.include_router(config.router)
app.include_router(amendments.router)
app.include_router(payment_plans.router)   # FASE G-2
app.include_router(payment_variance.router)  # FASE G-3
# FASE F — R&D & Desain: spesifikasi produk (md_specs) + permintaan sample labdip/proofing
# (md_samples) + rilis lifecycle produk. Hulu dari kontrak harga (Fase E) → PR → PO.
app.include_router(rnd.router)
# PS-17 — Organisasi R&D: divisi sebagai aktor + matriks persetujuan (R&D-only, additif)
app.include_router(rnd_org.router)
# PS-20 (D-14) — Matriks persetujuan MENGIKAT: antrean "Persetujuan Saya" + jejak keputusan
app.include_router(approvals_matrix.router)
# F1b — Daftar Harga per Pelanggan: harga langganan (pelanggan → PT → global) + impor/ekspor CSV
app.include_router(customer_prices.router)
# FASE E-8 (E8.7/E8.13/E8.15/E8.20) — MEJA KERJA berbasis antrean: Admin Sales & Finance.
# Tidak ada mesin baru di sini; router ini menyusun antrean dari mesin yang sudah terbukti
# (papan pending SO · backorder · retur · permintaan internal · penagihan · selisih · denda)
# lalu memberi SATU tindakan per baris. Alasan lengkap: `services/work_desk_service.py`.
app.include_router(work_desks.router)
# Utang migrasi (ii) FASE E-8 — "Cek Kenyataan Peran": daftar akun yang peran sistemnya
# lebih tinggi daripada pekerjaan nyatanya (mis. `manager` yang sebenarnya Admin Sales),
# dihitung dari jejak audit + field pembuat dokumen, bukan dari tebakan.
app.include_router(access_review.router)


@app.get("/api/")
async def root():
    return {"message": "Kain Nusantara API aktif"}


# ─── FASE H2 (HRD): Live Field Tracking via WebSocket (wss lewat ingress) ─────
# Manager/admin = subscriber (Live Map); karyawan lapangan = publisher posisi.
# Auth: ?token=<sess_token>  ·  ?mode=subscribe|publish (opsional; default by role).
import json  # noqa: E402
from fastapi import WebSocket, WebSocketDisconnect  # noqa: E402


@app.websocket("/api/ws/track")
async def ws_track(websocket: WebSocket):
    from services.tracking_service import (
        manager as track_manager, auth_ws_token, employee_for_user, store_track,
    )
    token = websocket.query_params.get("token", "")
    mode = websocket.query_params.get("mode", "")
    user = await auth_ws_token(token)
    await websocket.accept()
    if not user:
        await websocket.send_json({"type": "error", "msg": "unauthorized"})
        await websocket.close()
        return

    is_manager = user.get("role") in ("admin", "manager")
    subscribe = (mode == "subscribe") or (mode != "publish" and is_manager)

    if subscribe:
        track_manager.add_subscriber(websocket)
        await websocket.send_json({"type": "snapshot", "data": track_manager.snapshot()})
        try:
            while True:
                await websocket.receive_text()  # keepalive/ping dari klien
        except WebSocketDisconnect:
            track_manager.remove_subscriber(websocket)
        except Exception:  # noqa: BLE001
            track_manager.remove_subscriber(websocket)
        return

    # Publisher (karyawan lapangan) — kirim posisi sendiri
    emp = await employee_for_user(user["id"])
    if not emp:
        await websocket.send_json({"type": "error", "msg": "no-employee-profile"})
        await websocket.close()
        return
    await websocket.send_json({"type": "ready", "msg": "publishing", "employee_id": emp["id"]})
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                continue
            if msg.get("type") == "position" and msg.get("lat") is not None and msg.get("lon") is not None:
                pos = await store_track(emp, msg["lat"], msg["lon"],
                                        msg.get("accuracy", 0), msg.get("battery"), source="ws")
                await websocket.send_json({"type": "ack", "ts": pos["ts"]})
    except WebSocketDisconnect:
        return
    except Exception:  # noqa: BLE001
        return

    except WebSocketDisconnect:
        return
    except Exception:  # noqa: BLE001
        return
