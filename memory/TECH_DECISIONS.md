# TECH DECISIONS — Architectural Decision Records (ADR)
## Kain Nusantara WMS/ERP Platform

**Purpose:** Dokumen "mengapa" untuk setiap keputusan arsitektur & teknologi penting  
**Format:** Satu section per decision, reverse chronological  
**Status:** Living document (updated setiap kali ada keputusan arsitektur baru)

---

## ADR-008 — Session #015: Multi-Entity Inventory Ownership (Roll-as-SSOT) + Lot Integrity
**Status:** PROPOSED (keputusan inti D1–D4 ACCEPTED oleh user; sub-decision S1–S8 pending)
**Decider:** User (Vendor IT) + E2 (Emergent)
**Dokumen detail:** `docs/KN_15_INVENTORY_OWNERSHIP_LOT.md`

### Context
Grup Kain Nusantara punya >1 entitas legal (PT Kain Suka Cita, CV Kanda Suka, dst). Kebutuhan: kepemilikan
barang **dipisah per entitas** namun **boleh disimpan di gudang yang sama**. Kain disimpan per **roll** dengan
**lot** (dye-lot) yang menentukan keseragaman warna. Model Fase 0 (stok SHARED, balance unik per
product+warehouse) tidak memadai.

### Decision
1. **D1** Kepemilikan melekat pada **ROLL**; gudang = lokasi fisik **netral/shared**.
2. **D2** **Roll-as-SSOT penuh** → koleksi baru `inventory_rolls`; `inventory_balances` menjadi **proyeksi**
   dengan kunci `(product_id + warehouse_id + owner_entity_id)`; `inventory_movements` +`owner_entity_id`+`roll_id`.
3. **D3** Entitas A menjual barang milik B → **wajib inter-company transfer (B→A) dulu** (buku/akuntansi benar).
   Diimplementasi sebagai EXTEND `warehouse_transfers` (transfer_kind=inter_entity), bukan koleksi baru.
4. **D4** `unit_cost`/HPP per roll/lot **disiapkan nullable**, **diisi di Fase 4** (Finance).
5. **Integritas Lot:** 1 pengiriman diutamakan **1 lot**; **mixed-lot hanya bila qty > lot tunggal** + konfirmasi.
6. **Shortage antar-entitas:** "Fulfillment Assistant" memandu transfer antar-entitas (flow dipermudah).

### Rationale
- Roll-as-SSOT = akurat untuk tekstil (catch-weight per roll), RFID-ready (tag↔roll), dan benar untuk HPP/valuasi
  per entitas (Fase 4).
- Owner sebagai dimensi kelas-satu mencegah kebocoran kepemilikan & menjaga kebenaran buku per entitas.
- EXTEND warehouse_transfers menjaga SSOT (hindari duplikat koleksi).

### Alternatives Considered
1. **Owner = atribut gudang (warehouse.owner_entity_id):** Rejected — user butuh granularitas per-roll (1 gudang
   isi banyak owner; 1 SKU sebagian milik A/B/C).
2. **Owner-segmented balances saja (tanpa per-roll):** Rejected oleh user (pilih Opsi 2 roll penuh).
3. **Koleksi inter_entity_transfers terpisah:** Rejected — duplikasi logic stok-movement (pakai warehouse_transfers).

### Consequences
- ✅ **Positive:** kepemilikan benar per entitas, siap HPP/RFID, integritas warna (lot), flow shortage mudah.
- ⚠️ **Negative:** kompleksitas reservasi pindah ke level roll; migrasi balances→rolls; invarian gate bertambah.
- 📝 **Neutral:** phasing (Fase 0.5 enabler → Fase 1 Sales → Fase 4 Finance → Fase 5 RFID).

### Action Items
- [ ] Konfirmasi sub-decision S1–S8 (KN_15 §14).
- [ ] Setelah disepakati final: lock KN_15 → daftarkan `inventory_rolls` ke verify_contract.py + invarian baru.
- [ ] Implementasi Fase 0.5 (enabler) sebelum Fase 1 Sales. **Belum dimulai (no coding).**

---

## ADR-007 — 23 Mei 2026: Complete Documentation & Automation Strategy
**Status:** ACCEPTED  
**Decider:** User + Neo

### Context
Sistem memiliki code quality yang baik (0 debug statements, clean organization), tapi documentation gaps yang signifikan. User meminta cleanup untuk persiapan development lanjutan.

### Decision
Melakukan complete cleanup (Option 3) yang mencakup:
1. **Documentation Foundation** — PRD.md, SESSION_LOG.md, TECH_DECISIONS.md, KN_13
2. **Complete Standards Suite** — KN_08-KN_12 (UI/UX, Performance, Testing, Quality, Dev Protocols)
3. **Code Cleanup** — Fix backend import error, remove console.log, verify file size
4. **Automation Tools** — validate_compliance.py, check_nav_map.py, test suite skeleton

### Rationale
- **Proactive approach:** Prevent technical debt sebelum feature expansion
- **Production readiness:** Complete docs = onboarding mudah untuk new agents/developers
- **Quality gates:** Automation tools prevent regressions
- **Time investment:** 3-4 jam sekarang saves weeks nanti

### Alternatives Considered
1. **Option 1 (Minimal):** Hanya docs critical — Rejected (incomplete baseline)
2. **Option 2 (Standard):** Docs + code cleanup — Rejected (no automation, manual gates)
3. **Option 3 (Complete):** Full compliance — **SELECTED**

### Consequences
- ✅ **Positive:** Complete KN_00 compliance, automated quality gates, production-ready docs
- ⚠️ **Negative:** 3-4 jam investment upfront
- 📝 **Neutral:** Established pattern untuk future documentation maintenance

---

## ADR-006 — Mei 2026: Inline Seed vs External Seed Script
**Status:** ACCEPTED (Inline untuk MVP, External untuk production)
**Decider:** Development Team

### Context
Seed data diperlukan untuk demo & testing. Pilihan:
1. Inline seed di `server.py` (current: 238 lines)
2. External script `seed_realistic.py`

### Decision
- **MVP Phase:** Inline seed di server.py (lines 27-238)
- **Production Phase:** External seed script (planned)

### Rationale
- **Inline Pros:** Simple, no external dependency, auto-run saat startup
- **Inline Cons:** Large file (server.py jadi 272 lines), hard to maintain
- **External Pros:** Separation of concerns, easier to update seed data, reusable
- **External Cons:** Need explicit execution, path dependency

### Implementation Status
- Current: Inline seed berjalan di `lifespan` hook
- Planned: Migrate ke `/app/seed_realistic.py` setelah MVP stable
- Issue: `demo_seed_service.py` mengharapkan external seed tapi belum ada (causing error log)

### Action Items
- [ ] Decide: Keep inline atau migrate ke external?
- [ ] If migrate: Create `/app/seed_realistic.py` dengan comprehensive data
- [ ] If keep inline: Remove `demo_seed_service.py` import atau buat dummy

---

## ADR-005 — Januari 2026: Simulated Payment (Not Production)
**Status:** ACCEPTED (Temporary)
**Decider:** Development Team

### Context
Invoicing module membutuhkan payment processing. Pilihan:
1. Integrate real payment gateway (Midtrans, Xendit, Stripe)
2. Simulate payment untuk MVP

### Decision
Simulate payment dengan endpoint `/simulate-payment` untuk MVP phase.

### Rationale
- **Time to market:** Real gateway integration butuh 1-2 minggu (PIC, testing, compliance)
- **Scope creep:** Payment bukan core WMS/ERP value prop
- **Future-proof:** Architecture ready untuk real gateway (status field, payment_method exists)

### Implementation
- Endpoint: `POST /api/sales-orders/{id}/simulate-payment`
- Logic: Update `payment_status` dari `pending` → `paid`
- No actual transaction, no webhook, no reconciliation

### Production Blocker
⚠️ System **NOT production-ready** untuk real transactions until real gateway integrated.

### Future Work
- [ ] Q3 2026: Integrate Midtrans/Xendit untuk Indonesian market
- [ ] Support partial payment (DP 30%, sisanya saat dispatch)
- [ ] Payment reconciliation dashboard

---

## ADR-004 — Januari 2026: Recharts vs Apache ECharts
**Status:** ACCEPTED (Recharts untuk MVP, ECharts untuk advanced)
**Decider:** Development Team

### Context
Dashboard & reporting membutuhkan charts library. Pilihan:
1. **Recharts** — React-native, simple, declarative
2. **Apache ECharts** — Feature-rich, interactive, complex

### Decision
- **MVP Phase:** Recharts untuk basic charts (bar, line, pie)
- **Advanced Phase:** Apache ECharts untuk drill-down, interactivity, heatmaps

### Rationale
| Criteria | Recharts | ECharts |
|---|---|---|
| Learning curve | Low | Medium-High |
| Bundle size | 350KB | 800KB (full), 200KB (minimal) |
| Interactivity | Basic | Advanced (drill-down, zoom, brush) |
| React integration | Native | Wrapper (echarts-for-react) |
| Time to implement | 1-2 hari | 3-5 hari |

### Implementation Status
- Current: Recharts di OrderDashboard.jsx
- Planned: Migrate ke ECharts saat implement drill-down reports (Q3 2026)

### Migration Path
```jsx
// Phase 1 (Current): Recharts
import { BarChart, Bar, XAxis, YAxis } from 'recharts';

// Phase 2 (Future): ECharts
import ReactECharts from 'echarts-for-react';
const option = { /* advanced config */ };
<ReactECharts option={option} />
```

---

## ADR-003 — Desember 2025: MongoDB (NoSQL) vs PostgreSQL (SQL)
**Status:** ACCEPTED  
**Decider:** Development Team

### Context
Primary database selection untuk WMS/ERP. Requirements:
- Multi-warehouse dengan nested structures (Zone → Rack → Bin)
- Flexible schema (textile products vary: Batik, Tenun, Songket dengan attributes berbeda)
- High write throughput (RFID events 1000+ events/second)
- Document-oriented (Order + Items + Shipments)

### Decision
**MongoDB** sebagai primary database.

### Rationale
| Criteria | MongoDB | PostgreSQL |
|---|---|---|
| **Schema flexibility** | ✅ Dynamic | ❌ Rigid (migrations) |
| **Nested structures** | ✅ Native (embedded docs) | ❌ JSON columns (not ideal) |
| **Horizontal scaling** | ✅ Sharding built-in | ⚠️ Complex (Citus ext) |
| **Write throughput** | ✅ High (async writes) | ⚠️ Moderate (ACID overhead) |
| **Transactions** | ⚠️ Limited (v4.0+) | ✅ Full ACID |
| **Query complexity** | ⚠️ Aggregation pipeline | ✅ SQL (mature) |
| **Team expertise** | ✅ Python + Motor | ⚠️ SQLAlchemy |

### Trade-offs Accepted
- **No JOIN support:** Denormalize data where needed (e.g., `warehouse_name` in order)
- **Eventual consistency:** Use `find_one_and_update` untuk atomic operations
- **No foreign keys:** Manual referential integrity checks

### Mitigations
- **SSOT principle:** One collection per entity (prevent redundancy)
- **UUID for IDs:** Avoid MongoDB ObjectId (portability)
- **Atomic operations:** Use `$inc`, `$set` dengan conditions untuk prevent race conditions

### Alternatives Considered
1. **PostgreSQL + JSONB:** Rejected (complex nested queries, rigid schema)
2. **Hybrid (Postgres + Mongo):** Rejected (operational complexity, dual writes)
3. **CockroachDB:** Rejected (overkill untuk MVP, limited Python support)

---

## ADR-002 — November 2025: FastAPI vs Django vs Flask
**Status:** ACCEPTED  
**Decider:** Development Team

### Context
Backend framework selection untuk API-first architecture. Requirements:
- RESTful API dengan high performance
- Async support untuk MongoDB (Motor) & future WebSocket
- Modern Python (3.11+)
- Auto-generated API documentation
- Type safety (Pydantic)

### Decision
**FastAPI** sebagai backend framework.

### Rationale
| Criteria | FastAPI | Django | Flask |
|---|---|---|---|
| **Performance** | ✅ High (async) | ❌ Sync (Django 4+ async limited) | ⚠️ Moderate |
| **API docs** | ✅ Auto (OpenAPI) | ❌ Manual | ❌ Manual |
| **Type safety** | ✅ Pydantic v2 | ❌ No | ❌ No |
| **Async support** | ✅ Native | ⚠️ Partial | ❌ No (needs extensions) |
| **Learning curve** | ⚠️ Medium | ❌ High (ORM, admin) | ✅ Low |
| **Boilerplate** | ✅ Low | ❌ High | ✅ Low |
| **Ecosystem** | ✅ Growing | ✅ Mature | ✅ Mature |

### Key Features Used
- **Dependency Injection:** `Depends()` untuk auth, db, permissions
- **Pydantic Models:** Request/response validation
- **APIRouter:** Modular routing per domain
- **Lifespan Events:** Seed data saat startup
- **CORS Middleware:** Frontend integration

### Alternatives Considered
1. **Django REST Framework:** Rejected (overkill, ORM lock-in, sync)
2. **Flask + extensions:** Rejected (fragmented ecosystem, no native async)
3. **Sanic:** Rejected (smaller community, less mature)

---

## ADR-001 — November 2025: React 19 vs Next.js vs Vue 3
**Status:** ACCEPTED  
**Decider:** Development Team

### Context
Frontend framework selection untuk enterprise WMS/ERP. Requirements:
- Component-based architecture
- Real-time updates (future WebSocket)
- Rich UI components (Shadcn/UI)
- State management (client + server)
- Large dataset handling (virtual scroll)

### Decision
**React 19** sebagai frontend framework.

### Rationale
| Criteria | React 19 | Next.js | Vue 3 |
|---|---|---|---|
| **Ecosystem** | ✅ Largest | ✅ Large (React-based) | ⚠️ Smaller |
| **Shadcn/UI support** | ✅ Native | ✅ Compatible | ❌ No (PrimeVue, Vuetify) |
| **Learning curve** | ⚠️ Medium | ⚠️ Medium-High | ✅ Low |
| **SSR needed?** | ❌ No (internal app) | ✅ Yes (but overkill) | ❌ No |
| **Build complexity** | ✅ CRA (simple) | ⚠️ Next.js config | ✅ Vite |
| **Team expertise** | ✅ High | ⚠️ Medium | ❌ Low |

### Key Libraries Integrated
- **Shadcn/UI:** 45+ pre-built components (TailwindCSS + Radix UI)
- **TanStack Query:** Server state management (planned)
- **Zustand:** Client state management (planned)
- **React Hook Form + Zod:** Form validation
- **Recharts:** Data visualization

### Why Not Next.js?
- **No SSR needed:** Internal app, tidak perlu SEO
- **Complexity overhead:** File-based routing, server components not needed
- **Deployment simplicity:** Static build easier untuk Kubernetes

### Why Not Vue 3?
- **Component library:** Shadcn/UI not available (PrimeVue kurang modern)
- **Team familiarity:** React ecosystem lebih familiar
- **Hiring:** React developers lebih banyak di Indonesia

### Future Considerations
- **React 19 features planned:** Suspense, Transitions, Server Components (if needed)
- **Migration path:** If SSR needed later → Next.js (minimal refactor)

---

## ADR-000 — November 2025: Monorepo vs Separate Repos
**Status:** ACCEPTED  
**Decider:** Development Team

### Context
Code organization strategy untuk backend + frontend + docs. Pilihan:
1. **Monorepo:** Satu repo dengan `/backend`, `/frontend`, `/docs` folders
2. **Separate Repos:** `kn-backend`, `kn-frontend`, `kn-docs`

### Decision
**Monorepo** dengan struktur:
```
/app/
  /backend/       # FastAPI
  /frontend/      # React 19
  /docs/          # Standards & documentation
  /memory/        # PRD, SESSION_LOG, TECH_DECISIONS
  /scripts/       # Automation tools
  /tests/         # Shared tests
```

### Rationale
- ✅ **Atomic commits:** Frontend + backend changes dalam satu PR
- ✅ **Shared tooling:** Lint, test, deploy dari root
- ✅ **Version sync:** Tidak ada version mismatch antara FE/BE
- ✅ **Simpler CI/CD:** One pipeline untuk full-stack
- ⚠️ **Repo size:** Larger, tapi manageable untuk MVP

### Alternatives Considered
1. **Separate Repos:** Rejected (coordination overhead, versioning complexity)
2. **Turborepo/Nx:** Rejected (overkill untuk small team, added complexity)

### Trade-offs
- **Build time:** Monorepo bisa lebih lama (mitigasi: cache, incremental builds)
- **Access control:** Tidak bisa granular per-repo (mitigasi: branch protection)

---

## TEMPLATE — ADR-XXX: [Decision Title]
**Status:** [PROPOSED / ACCEPTED / REJECTED / DEPRECATED]  
**Date:** [YYYY-MM-DD]  
**Decider:** [Who decided]

### Context
[Describe the problem/situation that requires a decision]

### Decision
[What was decided]

### Rationale
[Why this decision was made, comparison table if applicable]

### Alternatives Considered
1. **Alternative 1:** [Why rejected]
2. **Alternative 2:** [Why rejected]

### Consequences
- ✅ **Positive:** [Benefits]
- ⚠️ **Negative:** [Costs/Trade-offs]
- 📝 **Neutral:** [Side effects]

### Action Items (if applicable)
- [ ] Action 1
- [ ] Action 2

---

**Last Updated:** 23 Mei 2026  
**Maintained by:** Development Team  
**Review Cycle:** Per major architectural decision
