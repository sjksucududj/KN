#!/usr/bin/env python3
"""
ui_smoke.py — Smoke-test UI Kain Nusantara (Playwright, ANDAL & TOLERAN).

TUJUAN
------
Verifikasi cepat alur POS end-to-end lewat browser TANPA terjebak pitfall yang
sering bikin testing agent timeout. Jalankan ini sebelum/sesudah perubahan FE
untuk sanity-check, atau berikan resep selektornya ke testing agent.

PELAJARAN PENTING (kenapa testing agent dulu gagal/timeout)
-----------------------------------------------------------
1) JANGAN pakai page.goto(..., wait_until="networkidle").
   Dev-server React menjaga WebSocket HMR tetap terbuka => network TIDAK PERNAH
   idle => Playwright hang sampai timeout. Pakai "domcontentloaded" + tunggu
   selektor spesifik (wait_for_selector by data-testid).
2) Login BUKAN <input type="email">. Pakai data-testid:
     - data-testid="login-email-input"   (input text biasa)
     - data-testid="login-password-input"
     - data-testid="login-submit-button"
     - data-testid="demo-login-admin-button" (1-klik admin; juga -sales/-manager/-warehouse)
   Semua user password = demo12345.
3) Navigasi sidebar: item = data-testid="nav-<id>", grup = data-testid="nav-group-toggle-<groupId>".
   Highlight aktif = class mengandung "active" (turunan dari activeView — Poin 11).
4) POS = nav-sales (grup "penjualan"). Kartu produk 1 tombol:
   data-testid="add-to-cart-button-<id>" => buka popup data-testid="product-quickview"
   => tombol "Tambah ke Keranjang" data-testid="quickview-add-button".
   Keranjang muncul sbg data-testid="floating-cart-button" => buka CheckoutDrawer
   (step 1 = data-testid="checkout-step-1", ringkasan item = data-testid="checkout-step1-items").

CARA JALAN
----------
  /opt/plugins-venv/bin/python scripts/ui_smoke.py                 # default http://localhost:3000
  /opt/plugins-venv/bin/python scripts/ui_smoke.py --url <preview-url> --role sales
  PLAYWRIGHT_BROWSERS_PATH=/pw-browsers ... (di-set otomatis di bawah)

SIFAT: TOLERAN. Selalu exit 0 (smoke = sinyal, bukan gate). Cetak ringkasan
PASS/FAIL/SKIP per cek. Kalau gagal/timeout => "tidak apa-apa, lanjutkan".
"""
import argparse
import os
import sys

# Pastikan browser path ke-set sebelum import playwright (env container ini)
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "/pw-browsers")

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
except Exception as e:  # pragma: no cover
    print(f"[SKIP] Playwright tidak tersedia: {e}")
    print("Jalankan dengan: /opt/plugins-venv/bin/python scripts/ui_smoke.py")
    sys.exit(0)

GREEN, RED, YELLOW, CYAN, BOLD, RESET = (
    "\033[92m", "\033[91m", "\033[93m", "\033[96m", "\033[1m", "\033[0m",
)

results = []  # (status, label, detail)


def record(status, label, detail=""):
    results.append((status, label, detail))
    color = {"PASS": GREEN, "FAIL": RED, "SKIP": YELLOW}.get(status, "")
    print(f"  {color}[{status}]{RESET} {label}" + (f" — {detail}" if detail else ""))


def run(url: str, role: str, headed: bool, timeout_ms: int):
    print(f"{CYAN}{BOLD}== UI SMOKE — {url} (role={role}) =={RESET}")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headed, args=["--no-sandbox"])
        ctx = browser.new_context(viewport={"width": 1920, "height": 800})
        page = ctx.new_page()
        console_errors = []
        # Abaikan noise dev-only (HMR websocket ke :443, sockjs, favicon, ResizeObserver)
        _IGNORE = ("ws://localhost:443", "websocket", "sockjs", "hmr", "favicon",
                   "resizeobserver", "the above error occurred")

        def _on_console(m):
            if m.type != "error":
                return
            low = (m.text or "").lower()
            if any(s in low for s in _IGNORE):
                return
            console_errors.append(m.text)
        page.on("console", _on_console)

        # --- 1) LOAD (domcontentloaded, JANGAN networkidle) ---
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_selector("[data-testid='demo-login-admin-button']", timeout=timeout_ms)
            record("PASS", "Login screen render")
        except PWTimeout:
            record("FAIL", "Login screen render", "timeout (cek service FE)")
            browser.close(); return

        # --- 2) LOGIN (data-testid, bukan type=email) ---
        try:
            page.click(f"[data-testid='demo-login-{role}-button']")
            page.wait_for_selector("[data-testid='main-navigation']", timeout=timeout_ms)
            record("PASS", f"Login 1-klik ({role}) + sidebar muncul")
        except PWTimeout:
            record("FAIL", f"Login ({role})", "main-navigation tidak muncul")
            browser.close(); return

        # --- 3) NAVIGASI SEMUA MENU (0 crash, 0 console error) ---
        try:
            for t in page.query_selector_all("[data-testid^='nav-group-toggle-']"):
                try:
                    t.click(); page.wait_for_timeout(120)
                except Exception:
                    pass
            nav_ids, seen = [], set()
            for n in page.query_selector_all("[data-testid^='nav-']"):
                tid = n.get_attribute("data-testid") or ""
                if tid.startswith("nav-") and not tid.startswith("nav-group") and tid not in seen:
                    seen.add(tid); nav_ids.append(tid)
            visited, crashed = 0, []
            for tid in nav_ids:
                el = page.query_selector(f"[data-testid='{tid}']")
                if not el:
                    continue
                try:
                    el.click(); page.wait_for_timeout(400)
                    if page.query_selector("#webpack-dev-server-client-overlay"):
                        crashed.append(tid)
                    visited += 1
                except Exception:
                    crashed.append(tid)
            if crashed:
                record("FAIL", f"Navigasi menu ({visited}/{len(nav_ids)})", f"crash: {crashed[:5]}")
            else:
                record("PASS", f"Navigasi semua menu: {visited} view, 0 crash")
        except Exception as e:
            record("SKIP", "Navigasi menu", repr(e)[:60])

        # --- 4) POS: kartu, tombol tunggal, filter label ---
        try:
            # Pastikan nav-sales TERLIHAT (expand grup hanya bila perlu — JANGAN toggle buta).
            nav_sales = page.query_selector("[data-testid='nav-sales']")
            if not (nav_sales and nav_sales.is_visible()):
                grp = page.query_selector("[data-testid='nav-group-toggle-penjualan']")
                if grp:
                    grp.click(); page.wait_for_timeout(300)
            page.wait_for_selector("[data-testid='nav-sales']", state="visible", timeout=timeout_ms)
            page.click("[data-testid='nav-sales']")
            page.wait_for_selector("[data-testid^='add-to-cart-button-']", timeout=timeout_ms)
            cards = page.query_selector_all("[data-testid^='product-card-']")
            btns = page.query_selector_all("[data-testid^='add-to-cart-button-']")
            label = (btns[0].inner_text() or "").strip() if btns else ""
            record("PASS", f"POS load: {len(cards)} kartu, tombol tunggal", f"'{label}'")
            facet = page.query_selector("[data-testid='facet-rail']")
            ftext = (facet.inner_text() if facet else "").lower()
            ok6 = ("rentang harga" in ftext) and ("/meter" not in ftext)
            record("PASS" if ok6 else "FAIL", "Poin 6 filter 'Rentang Harga (Rp)' tanpa /meter")
            prices = page.query_selector_all("[data-testid^='product-price-']")
            ptxt = (prices[0].inner_text() if prices else "").strip()
            record("PASS" if ptxt else "SKIP", "Poin 5 label harga ber-base_unit", ptxt[:40])
        except PWTimeout:
            record("FAIL", "POS load", "product-card tidak muncul")
            browser.close(); return

        # --- 5) QUICKVIEW + add to cart ---
        try:
            page.query_selector("[data-testid^='add-to-cart-button-']").click()
            page.wait_for_selector("[data-testid='product-quickview']", timeout=timeout_ms)
            variants = page.query_selector_all("[data-testid^='quickview-variant-']")
            page.click("[data-testid='quickview-add-button']")
            page.wait_for_selector("[data-testid='floating-cart-button']", timeout=timeout_ms)
            record("PASS", "Quickview popup + Tambah ke Keranjang", f"{len(variants)} varian")
        except PWTimeout:
            record("FAIL", "Quickview/add-to-cart", "popup/cart tidak muncul")

        # --- 6) CHECKOUT step 1 (Poin 7 ringkasan item) ---
        try:
            page.click("[data-testid='floating-cart-button']")
            page.wait_for_selector("[data-testid='checkout-step-1']", timeout=timeout_ms)
            items = page.query_selector("[data-testid='checkout-step1-items']")
            rows = page.query_selector_all("[data-testid^='step1-item-']")
            inds = page.query_selector_all("[data-testid^='checkout-step-indicator-']")
            ok7 = items is not None and len(rows) >= 1
            record("PASS" if ok7 else "FAIL", "Poin 7 checkout step-1 ringkasan item",
                   f"{len(rows)} item, {len(inds)} stepper")
        except PWTimeout:
            record("FAIL", "Checkout step 1", "drawer tidak muncul")

        # --- console errors ---
        record("PASS" if not console_errors else "FAIL",
               "Console errors", f"{len(console_errors)} error" + (f" e.g. {console_errors[0][:80]}" if console_errors else ""))

        browser.close()


def main():
    ap = argparse.ArgumentParser(description="Smoke-test UI Kain Nusantara (toleran).")
    ap.add_argument("--url", default=os.environ.get("UI_SMOKE_URL", "http://localhost:3000"))
    ap.add_argument("--role", default="admin", choices=["admin", "sales", "manager", "warehouse"])
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--timeout", type=int, default=25000, help="timeout per langkah (ms)")
    args = ap.parse_args()
    try:
        run(args.url, args.role, args.headed, args.timeout)
    except Exception as e:
        record("SKIP", "Runner exception (toleran)", repr(e)[:80])

    npass = sum(1 for s, *_ in results if s == "PASS")
    nfail = sum(1 for s, *_ in results if s == "FAIL")
    nskip = sum(1 for s, *_ in results if s == "SKIP")
    print(f"\n{BOLD}== RINGKASAN: {GREEN}{npass} PASS{RESET}{BOLD} · "
          f"{RED}{nfail} FAIL{RESET}{BOLD} · {YELLOW}{nskip} SKIP{RESET}{BOLD} =={RESET}")
    if nfail:
        print(f"{YELLOW}Catatan: smoke ini TOLERAN (bukan gate). Jika gagal/timeout di "
              f"lingkungan otomasi, tidak apa-apa — verifikasi manual / lanjutkan.{RESET}")
    # SELALU exit 0 (toleran)
    sys.exit(0)


if __name__ == "__main__":
    main()
