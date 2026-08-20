# AUDIT ISOLASI ENTITAS — hasil sapuan otomatis

Endpoint GET disapu: 312

## Ringkasan

- **A-isi/B-kosong**: 23
- **BOCOR-A-lihat-B**: 3
- **BOCOR-B-lihat-A**: 1
- **KOSONG**: 56
- **LINTAS-BY-DESIGN**: 14
- **SAMA-antar-PT**: 21
- **TANPA-PENANDA-ENTITAS**: 22
- **TERPISAH**: 20
- **err(A=HTTP 400|B=HTTP 400)**: 1
- **err(A=HTTP 403|B=HTTP 403)**: 144
- **err(A=HTTP 422|B=HTTP 422)**: 28

## Kebocoran

- `/api/internal-requests` — salesA=['ent_kanda', 'ent_ksc'] salesB=[]
- `/api/stock/pending-so` — salesA=['ent_kanda', 'ent_ksc'] salesB=['ent_kanda', 'ent_ksc']
- `/api/tax-invoices` — salesA=['ent_kanda', 'ent_ksc'] salesB=[]

## Identik antar-PT (SHARED / entity-blind)

- `/api/amendment-reasons` (n=33)
- `/api/color-library` (n=28)
- `/api/config/simulators` (n=0)
- `/api/document-templates` (n=2)
- `/api/expense-categories` (n=8)
- `/api/finance-cases/playbooks` (n=11)
- `/api/finance-cases/reasons` (n=12)
- `/api/gl/cash-accounts` (n=3)
- `/api/internal-requests/meta` (n=0)
- `/api/onboarding` (n=5)
- `/api/payment-plans/meta` (n=0)
- `/api/payment-terms` (n=6)
- `/api/payment-variances/meta` (n=0)
- `/api/product-categories` (n=11)
- `/api/rnd/lifecycle-board` (n=0)
- `/api/roles` (n=0)
- `/api/settings` (n=0)
- `/api/settings/effective` (n=0)
- `/api/uom-conversions/catalog` (n=0)
- `/api/uom-conversions/rules` (n=0)
- `/api/uoms` (n=6)

## Tanpa penanda entitas di respons

- `/api/amendment-reasons` (nA=33 nB=33)
- `/api/collection-reminders` (nA=1 nB=0)
- `/api/collection-worklist` (nA=3 nB=0)
- `/api/color-library` (nA=28 nB=28)
- `/api/document-templates` (nA=2 nB=2)
- `/api/expense-categories` (nA=8 nB=8)
- `/api/finance-cases/playbooks` (nA=11 nB=11)
- `/api/finance-cases/reasons` (nA=12 nB=12)
- `/api/gl/cash-accounts` (nA=3 nB=3)
- `/api/inventory/stock-analytics` (nA=15 nB=1)
- `/api/makloon-partners/scorecard` (nA=1 nB=0)
- `/api/onboarding` (nA=5 nB=5)
- `/api/payment-terms` (nA=6 nB=6)
- `/api/pos/best-sellers` (nA=7 nB=7)
- `/api/product-categories` (nA=11 nB=11)
- `/api/products` (nA=18 nB=17)
- `/api/reports/stock-aging` (nA=9 nB=0)
- `/api/reports/top-customers` (nA=4 nB=1)
- `/api/reports/warehouse-utilization` (nA=4 nB=4)
- `/api/rnd/reports/performer` (nA=4 nB=0)
- `/api/sales/commission-history` (nA=6 nB=6)
- `/api/uoms` (nA=6 nB=6)

## IDOR dokumen

| endpoint | koleksi | hasil |
|---|---|---|
| `/api/sales-orders/{id}` | sales_orders | 404 → AMAN |
| `/api/purchase-orders/{id}` | purchase_orders | 403 → AMAN |
| `/api/purchase-requisitions/{id}` | purchase_requisitions | tidak ada dokumen PT-B (tak teruji) |
| `/api/rfqs/{id}` | rfqs | tidak ada dokumen PT-B (tak teruji) |
| `/api/vendor-bills/{id}` | vendor_bills | tidak ada dokumen PT-B (tak teruji) |
| `/api/ar-receipts/{id}` | ar_receipts | 404 → AMAN |
| `/api/tax-invoices/{id}` | tax_invoices | tidak ada dokumen PT-B (tak teruji) |
| `/api/input-tax-invoices/{id}` | input_tax_invoices | tidak ada dokumen PT-B (tak teruji) |
| `/api/sales-returns/{id}` | sales_returns | 404 → AMAN |
| `/api/special-orders/{id}` | special_orders | tidak ada dokumen PT-B (tak teruji) |
| `/api/price-approvals/{id}` | price_approvals | tidak ada dokumen PT-B (tak teruji) |
| `/api/contra-bons/{id}` | contra_bons | tidak ada dokumen PT-B (tak teruji) |
| `/api/finance-cases/{id}` | finance_cases | tidak ada dokumen PT-B (tak teruji) |
| `/api/fixed-assets/{id}` | fin_fixed_assets | 403 → AMAN |
| `/api/makloons/{id}` | makloons | tidak ada dokumen PT-B (tak teruji) |
| `/api/makloon-orders/{id}` | makloon_orders | tidak ada dokumen PT-B (tak teruji) |
| `/api/suppliers/{id}` | suppliers | 403 → AMAN |
| `/api/supplier-contracts/{id}` | supplier_contracts | 403 → AMAN |
| `/api/supplier-items/{id}` | supplier_items | tidak ada dokumen PT-B (tak teruji) |
| `/api/cash-advances/{id}` | cash_advances | tidak ada dokumen PT-B (tak teruji) |
| `/api/lots/{id}` | inventory_lots | 404 → AMAN |
| `/api/landed-costs/{id}` | landed_costs | tidak ada dokumen PT-B (tak teruji) |
| `/api/transfers/{id}` | warehouse_transfers | 403 → AMAN |
| `/api/amendments/{id}` | doc_amendments | tidak ada dokumen PT-B (tak teruji) |

## Sebaran entity_id di DB

| koleksi | field | total | KSC | KANDA | all | KOSONG | lain |
|---|---|---|---|---|---|---|---|
| approval_rules | entity_id | 9 | 0 | 0 | 9 | 0 | 0 |
| ar_receipts | entity_id | 9 | 8 | 1 | 0 | 0 | 0 |
| audit_logs | entity_id | 79 | 0 | 0 | 0 | 7 | 66 |
| bank_accounts | entity_id | 5 | 3 | 2 | 0 | 0 | 0 |
| bank_statement_formats | entity_id | 7 | 0 | 0 | 7 | 0 | 0 |
| bank_statement_lines | entity_id | 6 | 6 | 0 | 0 | 0 | 0 |
| budgets | entity_id | 18 | 9 | 9 | 0 | 0 | 0 |
| cash_transactions | entity_id | 27 | 20 | 7 | 0 | 0 | 0 |
| cash_transactions | owner_entity_id | 27 | 3 | 0 | 0 | 24 | -24 |
| contra_bons | entity_id | 3 | 3 | 0 | 0 | 0 | 0 |
| credit_notes | entity_id | 1 | 1 | 0 | 0 | 0 | 0 |
| customer_prices | entity_id | 3 | 3 | 0 | 0 | 0 | 0 |
| customers | entity_id | 5 | 4 | 1 | 0 | 0 | 0 |
| cycle_count_sessions | entity_id | 2 | 2 | 0 | 0 | 0 | 0 |
| design_gallery | entity_id | 3 | 3 | 0 | 0 | 0 | 0 |
| doc_amendments | entity_id | 4 | 4 | 0 | 0 | 0 | 0 |
| document_templates | entity_id | 2 | 0 | 0 | 2 | 0 | 0 |
| entity_prices | entity_id | 6 | 1 | 5 | 0 | 0 | 0 |
| expense_categories | entity_id | 8 | 0 | 0 | 8 | 0 | 0 |
| fin_budget_rules | entity_id | 2 | 1 | 1 | 0 | 0 | 0 |
| fin_depreciation_entries | entity_id | 25 | 18 | 7 | 0 | 0 | 0 |
| fin_fixed_assets | entity_id | 4 | 2 | 2 | 0 | 0 | 0 |
| finance_cases | entity_id | 3 | 3 | 0 | 0 | 0 | 0 |
| gl_accounts | entity_id | 74 | 0 | 0 | 0 | 74 | 0 |
| hr_attendance | entity_id | 22 | 22 | 0 | 0 | 0 | 0 |
| hr_devices | entity_id | 1 | 1 | 0 | 0 | 0 | 0 |
| hr_employees | entity_id | 11 | 10 | 1 | 0 | 0 | 0 |
| hr_field_tracks | entity_id | 6 | 6 | 0 | 0 | 0 | 0 |
| hr_geofences | entity_id | 2 | 1 | 1 | 0 | 0 | 0 |
| hr_kpi | entity_id | 6 | 6 | 0 | 0 | 0 | 0 |
| hr_leave_balances | entity_id | 11 | 10 | 1 | 0 | 0 | 0 |
| hr_leave_requests | entity_id | 2 | 2 | 0 | 0 | 0 | 0 |
| hr_org_units | entity_id | 24 | 12 | 12 | 0 | 0 | 0 |
| hr_overtime | entity_id | 1 | 1 | 0 | 0 | 0 | 0 |
| hr_payroll_runs | entity_id | 1 | 1 | 0 | 0 | 0 | 0 |
| hr_payslips | entity_id | 6 | 6 | 0 | 0 | 0 | 0 |
| hr_shifts | entity_id | 2 | 1 | 1 | 0 | 0 | 0 |
| hr_visits | entity_id | 2 | 2 | 0 | 0 | 0 | 0 |
| incentive_rates | entity_id | 11 | 0 | 0 | 11 | 0 | 0 |
| interco_accounts | entity_id | 4 | 2 | 2 | 0 | 0 | 0 |
| interco_loans | entity_id | 2 | 1 | 1 | 0 | 0 | 0 |
| interco_returns | entity_id | 2 | 1 | 1 | 0 | 0 | 0 |
| interco_settlements | entity_id | 1 | 0 | 1 | 0 | 0 | 0 |
| interco_transactions | entity_id | 10 | 5 | 5 | 0 | 0 | 0 |
| internal_requests | entity_id | 3 | 3 | 0 | 0 | 0 | 0 |
| inventory_balances | owner_entity_id | 22 | 21 | 1 | 0 | 0 | 0 |
| inventory_lots | entity_id | 28 | 27 | 1 | 0 | 0 | 0 |
| inventory_lots | owner_entity_id | 28 | 27 | 1 | 0 | 0 | 0 |
| inventory_movements | owner_entity_id | 43 | 41 | 2 | 0 | 0 | 0 |
| inventory_rolls | owner_entity_id | 55 | 54 | 1 | 0 | 0 | 0 |
| journal_entries | entity_id | 113 | 83 | 30 | 0 | 0 | 0 |
| makloon_orders | entity_id | 3 | 3 | 0 | 0 | 0 | 0 |
| makloons | entity_id | 3 | 3 | 0 | 0 | 0 | 0 |
| md_samples | entity_id | 28 | 28 | 0 | 0 | 0 | 0 |
| md_specs | entity_id | 2 | 2 | 0 | 0 | 0 | 0 |
| mfg_boms | entity_id | 2 | 2 | 0 | 0 | 0 | 0 |
| mfg_work_orders | entity_id | 3 | 3 | 0 | 0 | 0 | 0 |
| notifications | entity_id | 27 | 24 | 3 | 0 | 0 | 0 |
| number_sequences | entity_id | 34 | 22 | 12 | 0 | 0 | 0 |
| payment_plans | entity_id | 3 | 2 | 1 | 0 | 0 | 0 |
| payment_terms | entity_id | 6 | 0 | 0 | 6 | 0 | 0 |
| payment_variance_decisions | entity_id | 4 | 4 | 0 | 0 | 0 | 0 |
| penalties | entity_id | 3 | 1 | 2 | 0 | 0 | 0 |
| price_approvals | entity_id | 5 | 5 | 0 | 0 | 0 | 0 |
| process_recipes | entity_id | 2 | 2 | 0 | 0 | 0 | 0 |
| purchase_orders | entity_id | 13 | 9 | 4 | 0 | 0 | 0 |
| purchase_requisitions | entity_id | 7 | 7 | 0 | 0 | 0 | 0 |
| purchase_returns | entity_id | 2 | 2 | 0 | 0 | 0 | 0 |
| rfid_reads | owner_entity_id | 45 | 45 | 0 | 0 | 0 | 0 |
| rfid_tags | owner_entity_id | 43 | 43 | 0 | 0 | 0 | 0 |
| rnd_person_divisions | entity_id | 5 | 5 | 0 | 0 | 0 | 0 |
| sales_incentives | entity_id | 3 | 2 | 1 | 0 | 0 | 0 |
| sales_orders | entity_id | 10 | 8 | 2 | 0 | 0 | 0 |
| sales_returns | entity_id | 2 | 1 | 1 | 0 | 0 | 0 |
| sales_targets | entity_id | 3 | 2 | 1 | 0 | 0 | 0 |
| shipments | entity_id | 4 | 2 | 2 | 0 | 0 | 0 |
| special_orders | entity_id | 3 | 3 | 0 | 0 | 0 | 0 |
| supplier_contracts | entity_id | 11 | 10 | 1 | 0 | 0 | 0 |
| supplier_items | entity_id | 8 | 8 | 0 | 0 | 0 | 0 |
| supplier_price_lists | entity_id | 22 | 14 | 8 | 0 | 0 | 0 |
| suppliers | entity_id | 8 | 5 | 3 | 0 | 0 | 0 |
| tax_invoices | entity_id | 3 | 3 | 0 | 0 | 0 | 0 |
| tax_invoices_in | entity_id | 1 | 0 | 1 | 0 | 0 | 0 |
| vendor_bills | entity_id | 8 | 8 | 0 | 0 | 0 | 0 |
| warehouse_transfers | entity_id | 5 | 4 | 1 | 0 | 0 | 0 |
| wms_tasks | entity_id | 22 | 18 | 4 | 0 | 0 | 0 |
