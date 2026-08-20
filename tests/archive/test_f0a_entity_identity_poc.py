"""POC F0-A — Entity Identity & Context (Multi-Entity foundation).

User stories diuji:
- Login mengembalikan entity_context (home, allowed, active, entities, can_switch).
- Setiap user punya home_entity_id + allowed_entity_ids sesuai role (Model 1).
- Admin/manager lintas-entitas (allowed=semua, can_switch=True); sales/warehouse terkunci 1.
- /auth/me menghormati header X-Entity-Id: admin bisa switch ke ent_kanda; sales TIDAK bisa.
- /auth/context mengembalikan konteks; entitas punya field enrich (currency/coa_template/incentive_payer/is_pkp).
- Entitas Kanda = non-PKP (default_tax_mode non_ppn) → is_pkp False; KSC PKP True.
"""
import requests

BASE = "http://localhost:8001/api"
P = F = 0


def ok(c, m):
    global P, F
    P += 1 if c else 0
    F += 0 if c else 1
    print(f"  [{'PASS' if c else 'FAIL'}] {m}")


def login_full(email):
    return requests.post(f"{BASE}/auth/login", json={"email": email, "password": "demo12345"}).json()


def H(tok, entity=None):
    h = {"Authorization": f"Bearer {tok}"}
    if entity:
        h["X-Entity-Id"] = entity
    return h


def main():
    # ─── Login + entity_context ──────────────────────────────────────────────
    print("=== Login membawa entity_context ===")
    adm = login_full("admin@kainnusantara.id")
    ok("entity_context" in adm, "login admin punya entity_context")
    ec = adm["entity_context"]
    for k in ["home_entity_id", "allowed_entity_ids", "active_entity_id", "can_switch_entity", "entities"]:
        ok(k in ec, f"entity_context punya '{k}'")
    ok(adm["user"].get("home_entity_id") == "ent_ksc", "admin home = ent_ksc")
    ok(set(ec["allowed_entity_ids"]) == {"ent_ksc", "ent_kanda"}, "admin allowed = kedua entitas")
    ok(ec["can_switch_entity"] is True, "admin can_switch True")
    ok("password_hash" not in adm["user"], "user tidak membocorkan password_hash")

    # ─── Distribusi per-role (Model 1) ───────────────────────────────────────
    print("\n=== Distribusi entitas per role (Model 1) ===")
    sales = login_full("sales@kainnusantara.id")
    sales3 = login_full("sales3@kainnusantara.id")
    mgr = login_full("manager@kainnusantara.id")
    wh = login_full("warehouse@kainnusantara.id")
    ok(sales["user"]["home_entity_id"] == "ent_ksc" and sales["entity_context"]["allowed_entity_ids"] == ["ent_ksc"], "sales Ayu terkunci ent_ksc")
    ok(sales["entity_context"]["can_switch_entity"] is False, "sales can_switch False")
    ok(sales3["user"]["home_entity_id"] == "ent_kanda" and sales3["entity_context"]["allowed_entity_ids"] == ["ent_kanda"], "sales Citra terkunci ent_kanda (demo multi-entitas)")
    ok(mgr["entity_context"]["can_switch_entity"] is True, "manager can_switch True")
    ok(wh["entity_context"]["allowed_entity_ids"] == ["ent_ksc"], "warehouse terkunci ent_ksc")

    # ─── Switch via header X-Entity-Id ───────────────────────────────────────
    print("\n=== /auth/me menghormati X-Entity-Id ===")
    adm_tok = adm["token"]
    me_default = requests.get(f"{BASE}/auth/me", headers=H(adm_tok)).json()
    ok(me_default["entity_context"]["active_entity_id"] == "ent_ksc", "admin tanpa header → active home (ent_ksc)")
    me_kanda = requests.get(f"{BASE}/auth/me", headers=H(adm_tok, "ent_kanda")).json()
    ok(me_kanda["entity_context"]["active_entity_id"] == "ent_kanda", "admin X-Entity-Id=ent_kanda → active ent_kanda")
    # sales coba paksa entitas lain → harus diabaikan (tetap home)
    sales_tok = sales["token"]
    me_sales_force = requests.get(f"{BASE}/auth/me", headers=H(sales_tok, "ent_kanda")).json()
    ok(me_sales_force["entity_context"]["active_entity_id"] == "ent_ksc", "sales paksa ent_kanda → DITOLAK, tetap ent_ksc (isolasi)")

    # ─── /auth/context ───────────────────────────────────────────────────────
    print("\n=== /auth/context ===")
    ctx = requests.get(f"{BASE}/auth/context", headers=H(adm_tok, "ent_kanda"))
    ok(ctx.status_code == 200 and ctx.json()["active_entity_id"] == "ent_kanda", "/auth/context honor header")

    # ─── Field enrich entitas + PKP ──────────────────────────────────────────
    print("\n=== Entitas enrich + PKP ===")
    ents = {e["id"]: e for e in requests.get(f"{BASE}/entities", headers=H(adm_tok)).json()}
    ok(set(ents) >= {"ent_ksc", "ent_kanda"}, "2 entitas ada di master")
    for k in ["currency", "coa_template", "incentive_payer", "numbering_scheme"]:
        ok(k in ents["ent_ksc"], f"entitas punya field enrich '{k}'")
    ok(ents["ent_ksc"]["incentive_payer"] == "sales_entity", "incentive_payer = sales_entity (Model 1)")
    ec_ent = {e["id"]: e for e in adm["entity_context"]["entities"]}
    ok(ec_ent["ent_ksc"]["is_pkp"] is True, "KSC is_pkp True (default_tax_mode=ppn)")
    ok(ec_ent["ent_kanda"]["is_pkp"] is False, "Kanda is_pkp False (non_ppn)")

    print(f"\n{'='*54}\n  PASS {P}  |  FAIL {F}\n{'='*54}")
    return F == 0


if __name__ == "__main__":
    import sys
    sys.exit(0 if main() else 1)
