# 🐛 BUG BACKLOG - Frontend Issues

**Date Created:** 2026-06-18  
**Audit Conducted By:** Neo (Agent)  
**Audit Method:** Manual screenshot testing + code inspection

---

## ✅ STATUS UPDATE — #080 (2026-07-05): Verified during FIXING PHASE

All P0/P1 frontend bugs below were **already resolved** by a prior session and are now **re-verified working** (live UI screenshots + code review):

| Bug | Severity | Status |
|-----|----------|--------|
| #1 Dashboard cards leak to all pages | P0 | ✅ FIXED — `App.js` renders MetricCards only when `isHomeView` (HOME_VIEWS). Verified: no card leak on Orders/Special-Order/Returns pages. |
| #2 Onboarding on all pages | P0 | ✅ FIXED — `App.js` gates OnboardingPanel with `showOnboarding && isHomeView`. Verified: no onboarding leak. |
| #3 Redundant navigation tabs | P1 | ✅ RESOLVED — IA restructured to **Hub-Tabs** model (one sidebar menu = one process; variations = tabs). No duplicate nav. |
| #4 Special Order (OD) menu not accessible | P1 | ✅ FIXED — now a tab under the `sales-orders` hub; clicking renders full Special Order page (stats + table + "Buat Special Order"). |
| #5 Returns status tab text formatting | P2 | ✅ FIXED — `.tab-pills`(flex+gap) renders spaced pills "Semua \| Draft \| Menunggu \| Approved \| Ditolak". |
| #6 Inconsistent page titles | P2 | ✅ Addressed — consistent `PAGE_META` kicker/title (e.g. "BERANDA › PENJUALAN"). |
| #7 Tab badge position | P3 | (cosmetic — not in P0/P1 scope) |

> The original report below is retained for history (it reflected the state BEFORE the fixes were applied).

---


## 🔴 CRITICAL BUGS (P0 - Must Fix ASAP)

### BUG #1: Dashboard Cards Leaking to All Pages
**Severity:** CRITICAL  
**Pages Affected:** ALL pages except Beranda  
**Description:**  
Dashboard summary cards (Produk Aktif, Available QTY, Reserved QTY, Active Orders, Gudang) are rendering on EVERY page, including:
- Master Data & Audit
- Approval Inbox  
- Approval Harga Khusus
- Returns & Barang Sisa
- Special Order (OD)
- All other pages

**Root Cause:**  
Likely in `App.js` - dashboard cards are rendered OUTSIDE the conditional view logic, causing them to appear globally instead of only on dashboard/home view.

**Expected Behavior:**  
Dashboard cards should ONLY appear on "Beranda" (home/dashboard) view.

**Steps to Reproduce:**
1. Login as any user
2. Navigate to any page except Beranda
3. Observe dashboard cards at top of page

**Fix Priority:** P0 (CRITICAL)  
**Estimated Fix Time:** 15-30 minutes

**Fix Approach:**
```javascript
// In App.js, wrap dashboard cards with conditional:
{activeView === "home" && (
  <DashboardCards {...} />
)}
```

---

### BUG #2: "Onboarding — admin" Section on All Pages
**Severity:** HIGH  
**Pages Affected:** ALL pages  
**Description:**  
An "Onboarding — admin" section with checklist items appears below dashboard cards on all pages. This is admin onboarding UI that should only appear once or on a specific onboarding page.

**Items Shown:**
- Buat gudang pertama
- Buat UOM pertama  
- Buat produk pertama
- Konfigurasi document template
- Buat user baru
- Review permission matrix

**Expected Behavior:**  
Onboarding checklist should:
- Only appear on first login, OR
- Only appear on dedicated onboarding page, OR
- Be dismissible and not reappear

**Fix Priority:** P0 (HIGH)  
**Estimated Fix Time:** 30 minutes

---

### BUG #3: Redundant Navigation Tabs
**Severity:** MEDIUM  
**Pages Affected:** Approval Harga Khusus, possibly others  
**Description:**  
Pages have redundant navigation:
- Sidebar menu item: "Approval Harga"  
- Page content has tabs: "Semua, Menunggu (1), Disetujui, Ditolak, Draft"

This creates confusion - users don't know if they should use sidebar or page tabs.

**Expected Behavior:**  
**Option A:** Remove page tabs, use sidebar for navigation  
**Option B:** Keep page tabs for filtering, ensure they're clearly labeled as "Status Filters" not navigation

**Fix Priority:** P1 (MEDIUM)  
**Estimated Fix Time:** 1 hour (if redesigning navigation pattern)

---

## 🟡 HIGH PRIORITY BUGS (P1 - Fix Soon)

### BUG #4: Special Order (OD) Menu Not Accessible
**Severity:** HIGH  
**Pages Affected:** Navigation  
**Description:**  
"Special Order (OD)" menu item exists in sidebar but clicking doesn't navigate to the page. Link appears but is not functional.

**Steps to Reproduce:**
1. Login as Admin/Sales
2. Expand PENJUALAN group
3. Look for "Special Order" menu item - NOT FOUND

**Expected Behavior:**  
Menu item should be visible and clickable, navigating to Special Orders page.

**Root Cause:**  
Likely mismatch between:
- navigationConfig.js ID: "special-orders"
- Sidebar rendering logic not finding this ID
- Or missing from role-based filtering

**Fix Priority:** P1 (HIGH)  
**Estimated Fix Time:** 30 minutes

---

### BUG #5: Returns Page - Status Tab Text Formatting Issue
**Severity:** LOW (Visual)  
**Pages Affected:** Returns & Barang Sisa  
**Description:**  
Status filter tabs show text without spaces: "SemuaDraftMenungguApprovedDitolak"

**Expected Behavior:**  
Should show: "Semua | Draft | Menunggu | Approved | Ditolak" with proper spacing/separators

**Fix Priority:** P2 (LOW - Visual only)  
**Estimated Fix Time:** 15 minutes

**Fix Approach:**
Check CSS for tab-bar styling, ensure proper margins/paddings between tabs.

---

## 🔵 MEDIUM PRIORITY (P2 - Nice to Fix)

### BUG #6: Inconsistent Page Titles
**Severity:** LOW  
**Description:**  
Some pages have "PENJUALAN" kicker, some don't. Some have icons, some don't.

**Examples:**
- Approval Harga Khusus: Has "PENJUALAN" kicker  
- Returns & Barang Sisa: Has "PENJUALAN" kicker  
- Approval Inbox: Has "APPROVALS" kicker

**Expected Behavior:**  
Consistent heading structure across all pages from PAGE_META in navigationConfig.js

**Fix Priority:** P2 (MEDIUM)  
**Estimated Fix Time:** 30 minutes

---

## 🟢 LOW PRIORITY (P3 - Can Wait)

### BUG #7: Tab Badge Count Position
**Severity:** LOW (Visual)  
**Description:**  
On Approval Harga page, "Menunggu" tab shows badge "1" but positioning might be off.

**Fix Priority:** P3 (LOW)  
**Estimated Fix Time:** 10 minutes

---

## 📋 AUDIT SUMMARY

**Total Bugs Found:** 7  
**Critical (P0):** 2  
**High (P1):** 2  
**Medium (P2):** 1  
**Low (P3):** 2  

**Estimated Total Fix Time:** 3-4 hours

---

## 🔍 ROOT CAUSE ANALYSIS

### Why Guardrails Failed:

1. **`validate_compliance.py`**
   - ✅ Checks: File size (<500 lines), testid presence
   - ❌ Doesn't Check: UI element isolation, cross-page side effects

2. **`verify_contract.py`**
   - ✅ Checks: API endpoint availability
   - ❌ Doesn't Check: Frontend UI issues

3. **Testing Agent**
   - ✅ Checks: Feature functionality, API integration
   - ❌ Doesn't Check: Visual regressions, layout issues, UX consistency

### What Was Missing:

1. **Visual Regression Testing**
   - No automated screenshot comparison
   - No baseline screenshots for each page

2. **Cross-Page Testing**
   - Each feature tested in isolation
   - No verification that new features don't pollute other pages

3. **UX Review Checklist**
   - No checklist for:
     - Irrelevant content on pages
     - Redundant navigation
     - Consistent heading structure
     - Onboarding flow dismissal

---

## 🎯 RECOMMENDED FIXES (In Priority Order)

### Immediate Fixes (Next Session):
1. ✅ Fix BUG #1: Remove dashboard cards from non-dashboard pages (15 min)
2. ✅ Fix BUG #2: Make onboarding dismissible or conditional (30 min)
3. ✅ Fix BUG #4: Make Special Order menu accessible (30 min)
4. ✅ Fix BUG #5: Fix Returns tab text formatting (15 min)

**Total Time:** ~1.5 hours

### Follow-up Fixes:
5. Review and fix BUG #3: Navigation pattern consistency (1 hour)
6. Polish: BUG #6 & #7 (40 minutes)

---

## 🛠️ PROPOSED NEW GUARDRAILS

To prevent these issues in future:

### 1. Visual Regression Check Script
```bash
# scripts/visual_regression_check.sh
# Take screenshots of all pages
# Compare with baseline
# Flag differences
```

### 2. Cross-Page Audit Script
```bash
# scripts/cross_page_audit.py
# Check for:
# - Dashboard cards only on dashboard
# - Onboarding only on onboarding page
# - No redundant navigation
```

### 3. UX Checklist (Manual)
```markdown
Before declaring feature complete:
- [ ] Take screenshots of ALL pages
- [ ] Verify no side effects on other pages
- [ ] Check navigation consistency
- [ ] Verify role-based access
- [ ] Test with different users
```

---

## 📝 HONEST ASSESSMENT

**What Went Wrong:**
1. **Over-focus on feature completion** without sufficient integration testing
2. **Assumed "compile success = working correctly"** - wrong assumption
3. **No visual verification** before declaring complete
4. **Guardrails too narrow** - only checked code quality, not UX quality

**Lessons Learned:**
1. **Always take screenshots** before finishing any feature
2. **Test cross-page effects** - new features can pollute existing pages
3. **UX review is non-negotiable** - working code ≠ good UX
4. **Guardrails need expansion** to cover visual/UX aspects

**Commitment Going Forward:**
- Every feature completion will include full page audit
- Screenshot evidence for all affected pages
- Cross-page side effect verification
- UX checklist sign-off

---

END OF REPORT
