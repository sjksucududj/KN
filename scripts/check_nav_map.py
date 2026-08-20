#!/usr/bin/env python3
"""
Check Navigation Map Script (v2 — config-driven, truthful)
==========================================================

Memvalidasi navigasi NYATA yang berjalan, sesuai **KN_13 §528 "TARGET GROUPED
NAVIGATION IA"** (grouped, collapsible, role-filtered) — bukan konvensi flat v1.0
yang sudah usang.

SSOT yang dibaca (KODE MENANG atas DOKUMEN):
  - frontend/src/config/navigationConfig.js   → struktur grup/menu + roles
  - frontend/src/components/CoreWidgets.jsx    → konvensi testid render sidebar
  - frontend/src/features/wms/OperationsView.jsx → tab WMS (wms-tab-*)
  - frontend/src/features/orders/OrdersView.jsx  → tab Orders (tab-dashboard/list)

Konvensi testid (KN_13 §586): `nav-group-{groupId}`, `nav-{module}`, `wms-tab-{tab}`.

Gate ini BISA GAGAL (exit 1) bila ada drift nyata:
  - item tanpa id/label/roles, group kosong, id duplikat
  - admin TIDAK bisa melihat semua menu (invarian KN_13 "admin lihat semua")
      → OPT-OUT SAH (2026-07-26): item yang MEMANG dirancang khusus satu role
        boleh ditandai `adminExempt: true` di navStructure.js. Gate akan LULUS
        dan melaporkannya eksplisit. JANGAN melonggarkan `roles` hanya agar
        gate hijau — itu memalsukan RBAC dan menghilangkan niat desain.
  - item "yatim" (tak ter-reach role mana pun) / landing role tak ter-reach
  - konvensi testid render hilang
  - tab WMS wajib hilang
  - kedalaman IA > 4 (KN_13 §585)

Usage:
    python /app/scripts/check_nav_map.py [-v]
"""

import re
import sys
import argparse
from pathlib import Path

SRC = Path("/app/frontend/src")
NAV_CFG = SRC / "config/navigationConfig.js"
NAV_STRUCT = SRC / "config/navStructure.js"  # NAV_STRUCTURE + HUB_TABS (dipisah dari navigationConfig)
NAV_META = SRC / "config/navMeta.js"  # PAGE_META (judul + kicker tiap layar) — CHECK 5
ROLES_CFG = SRC / "config/roles.js"  # FASE E-8: registry peran + overlay menu peran baru
SIDEBAR = SRC / "components/CoreWidgets.jsx"
OPS_VIEW = SRC / "features/wms/OperationsView.jsx"
ORDERS_VIEW = SRC / "features/orders/OrdersView.jsx"

# FASE E-8 (E8.1) — 6 peran. `sales_admin` & `finance` TIDAK ditulis ke `roles:` di
# navStructure.js; visibilitas menunya dinyatakan sekali di `config/roles.js`
# (ROLE_NAV: inherit/add/remove) dan gate ini membaca overlay itu — supaya gate menilai
# navigasi yang BENAR-BENAR dirender, bukan separuhnya.
ROLES = ["admin", "sales", "manager", "warehouse", "sales_admin", "finance"]
REQUIRED_WMS_TABS = {"stok", "inbound", "outbound", "transfer", "cycle"}
MAX_DEPTH = 4  # KN_13 §585: Grup(L1) → Menu(L2) → Tab(L3) → Modal(L4)


class C:
    RED = "\033[91m"; GREEN = "\033[92m"; YELLOW = "\033[93m"
    BLUE = "\033[94m"; RESET = "\033[0m"; BOLD = "\033[1m"


def hdr(t): print(f"\n{C.BOLD}{C.BLUE}{'='*60}{C.RESET}\n{C.BOLD}{t}{C.RESET}\n{C.BOLD}{C.BLUE}{'='*60}{C.RESET}\n")
def ok(t): print(f"{C.GREEN}\u2713 {t}{C.RESET}")
def bad(t): print(f"{C.RED}\u2717 {t}{C.RESET}")
def warn(t): print(f"{C.YELLOW}\u26a0 {t}{C.RESET}")


# ─────────────────────────────────────────────────────────────────────────────
# PARSER: navigationConfig.js → list of entries
#   standalone: {"type":"standalone","id":..,"roles":[..]}
#   group:      {"type":"group","groupId":..,"roles":[..],"items":[{id,roles}..]}
# ─────────────────────────────────────────────────────────────────────────────
ROLES_RE = re.compile(r'roles:\s*\[([^\]]*)\]')
ID_RE = re.compile(r'id:\s*"([^"]+)"')
GROUPID_RE = re.compile(r'groupId:\s*"([^"]+)"')
ITEM_RE = re.compile(r'\{\s*id:\s*"([^"]+)"\s*,\s*label:\s*"([^"]*)"[^}]*?roles:\s*\[([^\]]*)\][^}]*\}')
# OPT-OUT EKSPLISIT (2026-07-26) — lihat catatan panjang di check_roles() 3a.
ADMIN_EXEMPT_RE = re.compile(r'adminExempt:\s*true')


def _roles(s):
    return [r.strip().strip('"\'') for r in s.split(",") if r.strip()]


def parse_nav_config():
    # NAV_STRUCTURE kini di navStructure.js (dipisah dari navigationConfig.js agar
    # tiap file di bawah batas guardrail); fallback ke navigationConfig.js bila perlu.
    content = NAV_STRUCT.read_text() if NAV_STRUCT.exists() else NAV_CFG.read_text()
    # isolate NAV_STRUCTURE = [ ... ]; (mendukung 'export const')
    m = re.search(r'(?:export\s+)?const NAV_STRUCTURE\s*=\s*\[(.*?)\n\];', content, re.S)
    body = m.group(1) if m else content
    entries = []
    # split per-entry by 'type:' marker (items inside groups have no 'type:')
    chunks = body.split("type:")
    for chunk in chunks[1:]:
        kind = "group" if chunk.lstrip().startswith('"group"') else (
            "standalone" if chunk.lstrip().startswith('"standalone"') else None)
        if kind is None:
            continue
        if kind == "standalone":
            idm = ID_RE.search(chunk)
            rm = ROLES_RE.search(chunk)
            entries.append({
                "type": "standalone",
                "id": idm.group(1) if idm else None,
                "roles": _roles(rm.group(1)) if rm else [],
                "adminExempt": bool(ADMIN_EXEMPT_RE.search(chunk)),
            })
        else:  # group
            gm = GROUPID_RE.search(chunk)
            # group-level roles = first roles[] that appears BEFORE 'items:'
            before_items = chunk.split("items:")[0]
            grm = ROLES_RE.search(before_items)
            items_part = chunk.split("items:", 1)[1] if "items:" in chunk else ""
            items = []
            for im in ITEM_RE.finditer(items_part):
                items.append({"id": im.group(1), "label": im.group(2),
                              "roles": _roles(im.group(3)),
                              "adminExempt": bool(ADMIN_EXEMPT_RE.search(im.group(0)))})
            entries.append({
                "type": "group",
                "groupId": gm.group(1) if gm else None,
                "roles": _roles(grm.group(1)) if grm else [],
                "items": items,
            })
    return entries


def _id_set(raw):
    """Ambil id ber-kutip dari potongan array JS.

    Sengaja TIDAK memecah dengan `split(",")`: daftar `add`/`remove` di
    `config/roles.js` diselingi komentar `// …` yang menjelaskan alasan tiap
    kelompok, dan pemecahan naif menelan id yang berada tepat sesudah komentar
    (gate lalu melaporkan "landing finance tidak ter-reach" padahal menunya ada).
    """
    cleaned = re.sub(r"//[^\n]*", "", raw or "")
    return set(re.findall(r'"([A-Za-z0-9_-]+)"', cleaned))


def parse_role_nav():
    """Baca `ROLE_NAV` dari `config/roles.js` → {role: {inherit, add, remove}}.

    FASE E-8: peran baru menyatakan menunya di satu tempat (inherit + add/remove)
    daripada menyebar dua nama ke ~40 baris `navStructure.js`.
    """
    if not ROLES_CFG.exists():
        return {}
    src = ROLES_CFG.read_text()
    m = re.search(r"export const ROLE_NAV\s*=\s*\{(.*?)\n\};", src, re.S)
    if not m:
        return {}
    out = {}
    for rm in re.finditer(r"(\w+):\s*\{(.*?)\n  \},", m.group(1), re.S):
        role, blk = rm.group(1), rm.group(2)
        inh = re.search(r'inherit:\s*"([^"]+)"', blk)
        add = re.search(r"add:\s*\[(.*?)\]", blk, re.S)
        rem = re.search(r"remove:\s*\[(.*?)\]", blk, re.S)
        out[role] = {
            "inherit": inh.group(1) if inh else None,
            "add": _id_set(add.group(1) if add else ""),
            "remove": _id_set(rem.group(1) if rem else ""),
        }
    return out


def parse_role_home():
    """Baca `ROLE_HOME_REGISTRY` dari `config/navMeta.js` → {role: navId}.

    KENAPA DIBACA, BUKAN DITULIS ULANG DI SINI: peta beranda peran sebelumnya
    di-hard-code di gate ini (`landing = {...}`). Akibatnya ia menjadi SUMBER KEDUA:
    saat GELOMBANG 2 memindahkan beranda `sales_admin`/`finance` ke meja kerjanya,
    kode aplikasi benar tetapi gate memerah — dan tekanan berikutnya adalah
    "kembalikan saja berandanya supaya hijau", yaitu gate yang menyetir desain.
    Sekarang gate memeriksa KETERJANGKAUAN beranda yang benar-benar dipakai aplikasi.
    """
    if not NAV_META.exists():
        return {}
    src = NAV_META.read_text()
    m = re.search(r"export const ROLE_HOME_REGISTRY\s*=\s*\{(.*?)\n\};", src, re.S)
    if not m:
        return {}
    out = {}
    for rm in re.finditer(r'"?(\w+)"?:\s*\{[^}]*?navId:\s*"([^"]+)"', m.group(1), re.S):
        out[rm.group(1)] = rm.group(2)
    return out


def reachable_ids(entries, role, role_nav=None):
    """Replicate buildNavGroups(): group visible if role in group.roles; items filtered by role.

    Ikut menghormati overlay `ROLE_NAV` (FASE E-8) supaya perhitungan gate identik
    dengan `roleCanSee()` yang dipakai sidebar, tab hub, command palette & deep-link.
    """
    rule = (role_nav or {}).get(role) or {}

    def visible(roles, ident):
        if ident and ident in rule.get("remove", ()):
            return False
        if role in roles:
            return True
        if ident and ident in rule.get("add", ()):
            return True
        inh = rule.get("inherit")
        return bool(inh and inh in roles)

    out = set()
    for e in entries:
        if not visible(e["roles"], e.get("groupId") or e.get("id")):
            continue
        if e["type"] == "standalone":
            if e["id"]:
                out.add(e["id"])
        else:
            for it in e["items"]:
                if visible(it["roles"], it["id"]):
                    out.add(it["id"])
    return out


# ─────────────────────────────────────────────────────────────────────────────
# CHECK 1 — Config integrity + testid convention
# ─────────────────────────────────────────────────────────────────────────────
def check_config(entries, verbose=False):
    hdr("CHECK 1: Nav config integrity + testid convention")
    issues = 0
    all_ids = []

    for e in entries:
        if e["type"] == "standalone":
            if not e["id"]:
                bad("standalone entry tanpa id"); issues += 1
            if not e["roles"]:
                bad(f"standalone '{e.get('id')}' tanpa roles"); issues += 1
            if e["id"]:
                all_ids.append(e["id"])
        else:
            gid = e.get("groupId")
            if not gid:
                bad("group entry tanpa groupId"); issues += 1
            if not e["roles"]:
                bad(f"group '{gid}' tanpa roles"); issues += 1
            if not e["items"]:
                bad(f"group '{gid}' KOSONG (0 item)"); issues += 1
            for it in e["items"]:
                if not it["id"] or not it["label"]:
                    bad(f"group '{gid}': item tanpa id/label"); issues += 1
                if not it["roles"]:
                    bad(f"group '{gid}': item '{it['id']}' tanpa roles"); issues += 1
                all_ids.append(it["id"])

    # duplicate ids
    dups = sorted({x for x in all_ids if all_ids.count(x) > 1})
    if dups:
        bad(f"id navigasi duplikat: {dups}"); issues += len(dups)

    # testid convention in CoreWidgets.jsx (render layer)
    side = SIDEBAR.read_text()
    conv = {
        "nav-${...id}": re.search(r'data-testid=\{`nav-\$\{[^}]+\}`\}', side),
        "nav-group-${groupId}": re.search(r'data-testid=\{`nav-group-\$\{[^}]+\}`\}', side),
        "nav-group-toggle-${groupId}": re.search(r'data-testid=\{`nav-group-toggle-\$\{[^}]+\}`\}', side),
    }
    for name, found in conv.items():
        if not found:
            bad(f"CoreWidgets.jsx: konvensi testid '{name}' tidak ditemukan"); issues += 1
        elif verbose:
            ok(f"testid convention: {name}")

    if issues == 0:
        n_groups = sum(1 for e in entries if e["type"] == "group")
        n_items = len(all_ids)
        ok(f"Config valid: {len(entries)} entri ({n_groups} grup), {n_items} id unik, konvensi testid render OK")
    return issues


# ─────────────────────────────────────────────────────────────────────────────
# CHECK 2 — WMS tabs + Orders tabs (dari source nyata)
# ─────────────────────────────────────────────────────────────────────────────
def check_tabs(verbose=False):
    hdr("CHECK 2: WMS tabs (wms-tab-*) + Orders tabs")
    issues = 0
    ops = OPS_VIEW.read_text()
    if not re.search(r'data-testid=\{`wms-tab-\$\{[^}]+\}`\}', ops):
        bad("OperationsView.jsx: render testid `wms-tab-${tab.id}` tidak ditemukan"); issues += 1
    # parse WMS_TABS array ids
    m = re.search(r'WMS_TABS\s*=\s*\[(.*?)\];', ops, re.S)
    tab_ids = set(re.findall(r'id:\s*"([^"]+)"', m.group(1))) if m else set()
    missing = REQUIRED_WMS_TABS - tab_ids
    if missing:
        bad(f"WMS tab wajib hilang: {sorted(missing)}"); issues += len(missing)
    elif verbose:
        ok(f"WMS tabs: {sorted(tab_ids)}")

    # Orders tabs
    if ORDERS_VIEW.exists():
        ordv = ORDERS_VIEW.read_text()
        for t in ["tab-dashboard", "tab-list"]:
            if f'data-testid="{t}"' not in ordv:
                warn(f"Orders tab '{t}' tidak ditemukan (opsional)")

    if issues == 0:
        ok(f"Semua {len(REQUIRED_WMS_TABS)} tab WMS hadir + konvensi testid OK")
    return issues


# ─────────────────────────────────────────────────────────────────────────────
# CHECK 3 — Role matrix (KN_13: admin lihat semua; tak ada item yatim; landing reachable)
# ─────────────────────────────────────────────────────────────────────────────
def check_roles(entries, verbose=False):
    hdr("CHECK 3: Role-based access (KN_13 role matrix)")
    issues = 0

    # semua item id (union) + himpunan yang SENGAJA dikecualikan dari 3a
    all_items = set()
    admin_exempt = {}
    for e in entries:
        if e["type"] == "standalone" and e["id"]:
            all_items.add(e["id"])
            if e.get("adminExempt"):
                admin_exempt[e["id"]] = e["roles"]
        elif e["type"] == "group":
            for it in e["items"]:
                all_items.add(it["id"])
                if it.get("adminExempt"):
                    admin_exempt[it["id"]] = it["roles"]

    role_nav = parse_role_nav()
    reach = {r: reachable_ids(entries, r, role_nav) for r in ROLES}
    if role_nav:
        ok(f"overlay ROLE_NAV terbaca untuk {len(role_nav)} peran baru: "
           + " · ".join(f"{r}(+{len(v['add'])}/-{len(v['remove'])}"
                        + (f", warisi {v['inherit']}" if v["inherit"] else "") + ")"
                        for r, v in sorted(role_nav.items())))

    # 3a. admin lihat semua — DENGAN OPT-OUT EKSPLISIT (kebijakan 2026-07-26)
    #
    # MASALAH LAMA: invarian ini mutlak, sehingga menambah layar KHUSUS satu role
    # (mis. panel scanner gudang) selalu memerahkan gate. Repo ini bahkan sudah
    # menuliskan solusi-tambalnya di SESSION_HANDOFF §5:
    #   "longgarkan `roles` item yang sudah ada bila perlu"
    # — artinya gate MENYURUH agen MEMALSUKAN RBAC (memberi admin akses yang
    # sebenarnya tak dirancang untuknya) hanya supaya hijau. Gate yang memaksa
    # kompromi desain adalah gate yang merugikan.
    #
    # SEKARANG: invarian tetap default (admin memang harus melihat semua menu),
    # tetapi pengecualian boleh dinyatakan EKSPLISIT & terdokumentasi di
    # navStructure.js dengan `adminExempt: true`. Bedanya krusial:
    #   - dulu: RBAC dipalsukan diam-diam agar gate hijau  (niat hilang)
    #   - kini: pengecualian tertulis, terbaca gate, dan dilaporkan  (niat terjaga)
    admin_missing = (all_items - reach["admin"]) - set(admin_exempt)
    if admin_missing:
        bad(f"admin TIDAK bisa melihat: {sorted(admin_missing)} (invarian 'admin lihat semua'). "
            f"Bila ini DISENGAJA, tandai item itu `adminExempt: true` di navStructure.js "
            f"— jangan melonggarkan `roles` (itu memalsukan RBAC).")
        issues += len(admin_missing)
    elif verbose:
        ok(f"admin reach semua {len(all_items) - len(admin_exempt)} item wajib")
    if admin_exempt:
        warn(f"{len(admin_exempt)} item sengaja dikecualikan dari 'admin lihat semua' "
             f"(adminExempt): " + ", ".join(f"{k}→{v}" for k, v in sorted(admin_exempt.items())))

    # 3b. tidak ada item yatim (ter-reach minimal 1 role)
    union = set().union(*reach.values())
    orphan = all_items - union
    if orphan:
        bad(f"item yatim (tak ter-reach role mana pun): {sorted(orphan)}"); issues += len(orphan)

    # 3c. landing view per role reachable (IA v2 — hub-and-tab, selaras ROLE_HOME_REGISTRY)
    # FASE E-8: dua peran baru ikut diperiksa — peran yang mendarat di layar yang tidak
    # ada di menunya akan melihat halaman kosong tanpa jalan keluar. Petanya DIBACA dari
    # `navMeta.js` (SSOT), bukan disalin ke sini; lihat `parse_role_home()`.
    landing = parse_role_home()
    if not landing:
        bad("ROLE_HOME_REGISTRY tidak bisa dibaca dari navMeta.js"); issues += 1
    # `navId: "home"` bukan menu sesungguhnya — App.js menerjemahkannya ke beranda peran.
    for role, nid in sorted(landing.items()):
        if nid not in reach[role]:
            bad(f"landing role '{role}' → '{nid}' tidak ter-reach"); issues += 1
        elif verbose:
            ok(f"landing {role} → {nid} OK")

    if issues == 0:
        counts = ", ".join(f"{r}:{len(reach[r])}" for r in ROLES)
        ok(f"Role matrix konsisten (item ter-reach → {counts})")
    return issues


# ─────────────────────────────────────────────────────────────────────────────
# CHECK 4 — Kedalaman IA ≤ 4 (KN_13 §585)
# ─────────────────────────────────────────────────────────────────────────────
def check_depth(entries, verbose=False):
    hdr("CHECK 4: Kedalaman IA (maks 4 — KN_13 §585)")
    # standalone item = L1 (menu langsung)
    # group = L1, item = L2, item-with-WMS-tab → tab = L3 (+ modal L4 = batas)
    max_depth = 1
    has_group = any(e["type"] == "group" for e in entries)
    if has_group:
        max_depth = 2
    # WMS items punya tab (deep-link tab) → +1
    ops = OPS_VIEW.read_text()
    if "wms-tab-" in ops:
        max_depth = 3
    if max_depth > MAX_DEPTH:
        bad(f"Kedalaman IA {max_depth} > {MAX_DEPTH}"); return 1
    ok(f"Kedalaman IA = {max_depth} (Grup→Menu→Tab) ≤ {MAX_DEPTH} \u2014 sesuai KN_13")
    return 0


# ─────────────────────────────────────────────────────────────────────────────
# CHECK 5 — PAGE_META coverage (FASE E-7): setiap layar punya judul & kicker
#
# KENAPA GATE INI ADA: layar baru `internal-requests` (E7d) lolos semua gate lain
# tetapi merender kepala halaman "BERANDA · WORKSPACE" + judul cadangan
# "Kain Nusantara" — pengguna kehilangan konteks di layar yang justru mengurus
# uang antar badan usaha. Kelas bug ini tak terlihat oleh gate struktur menu
# karena menunya BENAR; yang hilang cuma metadata judulnya.
# ─────────────────────────────────────────────────────────────────────────────
def check_page_meta(verbose=False):
    hdr("CHECK 5: PAGE_META coverage (judul + kicker tiap layar)")
    if not NAV_META.exists():
        bad("navMeta.js tidak ditemukan"); return 1
    meta_src = NAV_META.read_text()
    try:
        start = meta_src.index("export const PAGE_META")
        block = meta_src[start:meta_src.index("\n};", start)]
    except ValueError:
        bad("blok PAGE_META tidak bisa dibaca di navMeta.js"); return 1
    meta_keys = set(re.findall(r'^\s*"?([A-Za-z0-9_-]+)"?\s*:\s*\{', block, re.M))

    views = set()
    for f in (NAV_STRUCT, SRC / "config/hubTabs.js"):
        if f.exists():
            views |= set(re.findall(r'view:\s*"([A-Za-z0-9_-]+)"', f.read_text()))

    missing = sorted(v for v in views if v not in meta_keys)
    if missing:
        for v in missing:
            bad(f"layar '{v}' TIDAK punya PAGE_META → judul jatuh ke cadangan generik")
        return len(missing)
    ok(f"{len(views)} layar semuanya punya judul & kicker (PAGE_META: {len(meta_keys)} entri)")
    return 0


def main():
    ap = argparse.ArgumentParser(description="Check Navigation Map compliance (config-driven)")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    print(f"\n{C.BOLD}Navigation Map Validator v2 (config-driven){C.RESET}")
    print("Reference: KN_13 §528 TARGET GROUPED NAVIGATION IA\n")

    if not NAV_CFG.exists():
        bad("navigationConfig.js tidak ditemukan"); sys.exit(1)

    entries = parse_nav_config()
    total = 0
    total += check_config(entries, args.verbose)
    total += check_tabs(args.verbose)
    total += check_roles(entries, args.verbose)
    total += check_depth(entries, args.verbose)
    total += check_page_meta(args.verbose)

    hdr("SUMMARY")
    if total == 0:
        ok("Navigation map COMPLIANT dengan KN_13 (grouped IA)")
        print(f"\n{C.GREEN}{C.BOLD}\u2713 NAV MAP: PASS{C.RESET}\n")
        sys.exit(0)
    else:
        warn(f"{total} issue ditemukan")
        print(f"\n{C.YELLOW}{C.BOLD}\u26a0 NAV MAP: NEEDS ATTENTION{C.RESET}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
