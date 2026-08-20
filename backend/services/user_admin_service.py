"""FASE E-2 — AKUN PENGGUNA TERTAUT BADAN USAHA (via HR) & PENEGAKAN AKSES.

Masalah yang ditutup fase ini:
  * E2.1 **Sumber kebenaran badan usaha karyawan = HR.** Dulu `home_entity_id`
    diketik bebas di formulir akun, jadi bisa berbeda dari data HR — lalu payroll
    dan isolasi data saling bertentangan. Sekarang: bila akun tertaut karyawan,
    `home_entity_id` DIAMBIL dari `hr_employees.entity_id` dan tidak bisa dibuat
    berbeda.
  * E2.2 `allowed_entity_ids` untuk peran non-lintas (sales/gudang) hanya boleh
    berisi badan usaha yang diizinkan pemilik. **Role berubah → hitung ulang** dan
    **cabut sesi** supaya wewenang lama tidak ikut terbawa di tab yang masih terbuka.
  * E2.3 email unik (409), admin terakhir tidak boleh dinonaktifkan, sesi dibuang
    saat status→nonaktif / badan usaha dicabut / password diganti.
  * E2.4 DELETE = **nonaktifkan** (soft) + aktifkan kembali + reset password.
  * E2.5 daftar akun dengan filter + paging + pengayaan (badan usaha, karyawan,
    login terakhir).
  * E2.7 setiap perubahan penugasan/role/status tercatat di jejak audit ber-entitas.
"""
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException

from db import db
from core_utils import hash_password, new_id, now_iso, safe_doc
from services.entity_context_service import (
    CROSS_ENTITY_ROLES, PRIMARY_ENTITY_ID, all_active_entity_ids,
    resolve_allowed_entities,
)
from services import entity_lifecycle_service as lifecycle
from role_registry import assert_valid_role

EDITABLE_FIELDS = ["name", "email", "role", "phone", "home_entity_id",
                   "allowed_entity_ids", "employee_id",
                   # FASE L — pagar lini produk per akun (kosong = semua lini)
                   "allowed_line_codes"]


# ─── Pembantu ────────────────────────────────────────────────────
async def _valid_line_codes(codes: Any, entity_id: str = "") -> List[str]:
    """FASE L — normalkan `allowed_line_codes` & pastikan tiap kode ADA di master.

    Kosong = **semua lini** (bawaan). Kode asing ditolak 400 dengan menyebut
    pilihan yang sah, bukan dibuang diam-diam: akun yang lininya salah ketik akan
    melihat layar setengah kosong tanpa sebab, dan itu selalu dilaporkan sebagai
    "data saya hilang".
    """
    from services import line_scope
    if codes is None:
        return []
    if isinstance(codes, str):
        codes = [codes]
    return await line_scope.validate_codes(codes, entity_id or "",
                                           what="Lini produk untuk akun ini")


async def get_user_or_404(user_id: str) -> Dict[str, Any]:
    user = safe_doc(await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0}))
    if not user:
        raise HTTPException(status_code=404, detail="Pengguna tidak ditemukan")
    return user


async def assert_email_unique(email: str, exclude_id: str = "") -> None:
    """E2.3 — email adalah identitas login, jadi harus unik (abaikan besar-kecil)."""
    mail = (email or "").strip()
    if not mail:
        raise HTTPException(status_code=400, detail="Email wajib diisi.")
    row = await db.users.find_one(
        {"email": {"$regex": f"^{mail}$", "$options": "i"},
         "id": {"$ne": exclude_id}}, {"_id": 0, "name": 1, "status": 1})
    if row:
        state = "nonaktif" if row.get("status") != "active" else "aktif"
        raise HTTPException(
            status_code=409,
            detail=f"Email “{mail}” sudah dipakai akun {state} milik "
                   f"“{row.get('name', '?')}”. Pakai email lain atau aktifkan kembali "
                   "akun yang sudah ada.")


async def revoke_sessions(user_id: str, reason: str = "") -> int:
    """Buang semua sesi aktif user (dipakai saat wewenang berubah).

    Tanpa ini, tab yang sudah terbuka tetap memakai daftar badan usaha LAMA sampai
    sesi kedaluwarsa — artinya pencabutan akses hanya di atas kertas.
    """
    res = await db.sessions.delete_many({"user_id": user_id})
    return res.deleted_count


async def _employee(employee_id: str) -> Dict[str, Any]:
    emp = safe_doc(await db.hr_employees.find_one({"id": employee_id}, {"_id": 0}))
    if not emp:
        raise HTTPException(status_code=404,
                            detail="Karyawan (HR) tidak ditemukan. Pilih dari daftar karyawan.")
    return emp


async def resolve_entities(*, role: str, home_entity_id: str,
                           allowed_entity_ids: Optional[List[str]],
                           employee_id: str = "") -> Tuple[str, List[str], Dict[str, Any]]:
    """E2.1/E2.2 — tentukan badan usaha utama + daftar yang boleh dioperasikan.

    Urutan kebenaran: **HR menang**. Bila `employee_id` terisi, `home_entity_id`
    diambil dari data karyawan dan nilai yang dikirim formulir diabaikan (bukan
    ditolak diam-diam — dikembalikan sebagai `info.home_from_hr` supaya UI bisa
    menjelaskan “diisi otomatis dari HR”).
    """
    all_ids = await all_active_entity_ids() or [PRIMARY_ENTITY_ID]
    info: Dict[str, Any] = {"home_from_hr": False, "employee": None}
    home = (home_entity_id or "").strip()

    if employee_id:
        emp = await _employee(employee_id)
        emp_entity = (emp.get("entity_id") or "").strip()
        if not emp_entity:
            raise HTTPException(
                status_code=400,
                detail=f"Karyawan “{emp.get('name', '')}” belum punya badan usaha di HR. "
                       "Lengkapi dulu data karyawannya, supaya akun dan payroll "
                       "tidak saling bertentangan.")
        if emp_entity not in all_ids:
            raise HTTPException(
                status_code=400,
                detail=f"Badan usaha karyawan “{emp.get('name', '')}” sudah tidak aktif. "
                       "Perbarui data HR-nya dulu.")
        home = emp_entity
        info["home_from_hr"] = True
        info["employee"] = {"id": emp["id"], "name": emp.get("name", ""),
                            "code": emp.get("code", ""), "entity_id": emp_entity}

    home = home or PRIMARY_ENTITY_ID
    if home not in all_ids:
        raise HTTPException(
            status_code=400,
            detail="Badan usaha utama tidak valid atau sudah diarsipkan. "
                   "Pilih badan usaha yang aktif.")

    if role in CROSS_ENTITY_ROLES:
        # admin/manager: lintas badan usaha (resolve dinamis di setiap request).
        allowed = resolve_allowed_entities(role, home, all_ids)
    else:
        # Peran non-lintas: HANYA home + penugasan tambahan yang disebut EKSPLISIT.
        extra = [e for e in (allowed_entity_ids or []) if e in all_ids and e != home]
        allowed = [home] + extra
    return home, allowed, info


# ─── E2.3 — admin terakhir ─────────────────────────────────────────
async def assert_not_last_admin(user_id: str, *, action: str) -> None:
    user = await get_user_or_404(user_id)
    if user.get("role") != "admin" or user.get("status") != "active":
        return
    others = await db.users.count_documents(
        {"role": "admin", "status": "active", "id": {"$ne": user_id}})
    if others == 0:
        raise HTTPException(
            status_code=409,
            detail=f"Tidak bisa {action}: ini satu-satunya admin aktif. Buat atau "
                   "naikkan satu admin lain dulu, kalau tidak sistem tidak bisa "
                   "dikelola siapa pun.")


# ─── Pengayaan baris daftar (E2.5) ───────────────────────────────────
async def enrich_users(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Tambah label badan usaha, karyawan HR, dan status sesi ke setiap baris."""
    ent_rows = await db.business_entities.find(
        {}, {"_id": 0, "id": 1, "legal_name": 1, "short_name": 1, "status": 1}).to_list(500)
    ents = {e["id"]: e for e in ent_rows}

    def label(eid: str) -> Dict[str, Any]:
        e = ents.get(eid) or {}
        return {"id": eid,
                "name": e.get("legal_name") or e.get("short_name") or eid,
                "short_name": e.get("short_name", ""),
                "status": e.get("status", "unknown")}

    user_ids = [r["id"] for r in rows]
    emp_rows = await db.hr_employees.find(
        {"user_id": {"$in": user_ids}},
        {"_id": 0, "id": 1, "user_id": 1, "name": 1, "code": 1, "entity_id": 1}).to_list(500)
    emps = {e["user_id"]: e for e in emp_rows}
    sess_rows = await db.sessions.find(
        {"user_id": {"$in": user_ids}}, {"_id": 0, "user_id": 1}).to_list(1000)
    with_session = {s["user_id"] for s in sess_rows}

    out: List[Dict[str, Any]] = []
    for r in rows:
        row = dict(r)
        row.pop("password_hash", None)
        home = row.get("home_entity_id") or ""
        emp = emps.get(row["id"])
        row["home_entity"] = label(home) if home else None
        row["allowed_entities"] = [label(e) for e in (row.get("allowed_entity_ids") or [])]
        row["employee_id"] = (emp or {}).get("id", "")
        row["employee"] = ({"id": emp["id"], "name": emp.get("name", ""),
                            "code": emp.get("code", ""),
                            "entity_id": emp.get("entity_id", "")} if emp else None)
        # E2.1 — tanda peringatan untuk UI: akun belum tertaut HR, atau tertaut
        # tetapi badan usahanya beda (data lama sebelum aturan ini berlaku).
        row["hr_link_warning"] = (
            "Belum tertaut karyawan HR" if not emp else
            ("Badan usaha akun berbeda dari data HR"
             if emp.get("entity_id") and emp["entity_id"] != home else ""))
        row["has_active_session"] = row["id"] in with_session
        row["last_login_at"] = row.get("last_login_at", "")
        out.append(safe_doc(row))
    return out


# ─── Aksi ──────────────────────────────────────────────────────
async def create_user(payload: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    await assert_email_unique(payload.get("email", ""))
    role = (payload.get("role") or "").strip()
    if not role:
        raise HTTPException(status_code=400, detail="Role wajib dipilih.")
    # FASE E-8 (E8.1) — `role` dulu teks bebas: salah ketik membuat akun TANPA izin
    # apa pun dan pemiliknya bingung kenapa semua layar kosong. Sekarang divalidasi
    # terhadap registry peran, dengan pesan yang menyebut pilihan yang sah.
    role = assert_valid_role(role)
    employee_id = (payload.get("employee_id") or "").strip()
    if employee_id:
        taken = await db.users.find_one({"id": {"$ne": ""}, "employee_id": employee_id},
                                        {"_id": 0, "name": 1})
        linked = await db.hr_employees.find_one(
            {"id": employee_id, "user_id": {"$nin": ["", None]}}, {"_id": 0, "user_id": 1})
        if taken or linked:
            raise HTTPException(
                status_code=409,
                detail="Karyawan ini sudah punya akun. Satu karyawan = satu akun.")
    home, allowed, info = await resolve_entities(
        role=role, home_entity_id=payload.get("home_entity_id", ""),
        allowed_entity_ids=payload.get("allowed_entity_ids"), employee_id=employee_id)
    await lifecycle.assert_entity_writable(home, "membuat akun di badan usaha ini")

    user = {
        "id": new_id("user"),
        "name": (payload.get("name") or "").strip(),
        "email": (payload.get("email") or "").strip(),
        "role": role,
        "password_hash": hash_password(payload.get("password") or "demo12345"),
        "phone": (payload.get("phone") or "").strip(),
        "home_entity_id": home,
        "allowed_entity_ids": allowed,
        "employee_id": employee_id,
        # FASE L — pagar lini. Divalidasi terhadap master lini AKTIF supaya salah
        # ketik tidak melahirkan akun yang tak melihat apa pun (kelas bug yang sama
        # dengan `role` teks bebas pra-E8.1).
        "allowed_line_codes": await _valid_line_codes(
            payload.get("allowed_line_codes"), home),
        "status": "active",
        "created_at": now_iso(),
    }
    if not user["name"]:
        raise HTTPException(status_code=400, detail="Nama pengguna wajib diisi.")
    await db.users.insert_one(user)
    if employee_id:
        await db.hr_employees.update_one(
            {"id": employee_id},
            {"$set": {"user_id": user["id"], "updated_at": now_iso()}})
    user.pop("password_hash", None)
    return safe_doc(user), info


async def update_user(user_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """PATCH akun — dengan penegakan E2.1/E2.2/E2.3 dan pencabutan sesi bila perlu."""
    before = await get_user_or_404(user_id)
    patch = {k: v for k, v in (data or {}).items() if k in EDITABLE_FIELDS}
    revoke_reasons: List[str] = []

    if "email" in patch:
        await assert_email_unique(patch["email"], exclude_id=user_id)

    role_changed = "role" in patch and patch["role"] != before.get("role")
    if role_changed:
        # FASE E-8 (E8.1) — peran hasil ubah juga wajib dikenal registry.
        patch["role"] = assert_valid_role(patch["role"])
        await assert_not_last_admin(user_id, action="mengubah role admin terakhir")

    touches_entity = any(k in patch for k in
                         ("role", "home_entity_id", "allowed_entity_ids", "employee_id"))
    if touches_entity:
        role = patch.get("role", before.get("role", ""))
        employee_id = patch.get("employee_id", before.get("employee_id", "") or "")
        home, allowed, _info = await resolve_entities(
            role=role,
            home_entity_id=patch.get("home_entity_id", before.get("home_entity_id", "")),
            allowed_entity_ids=patch.get("allowed_entity_ids",
                                         before.get("allowed_entity_ids")),
            employee_id=employee_id)
        patch["home_entity_id"] = home
        patch["allowed_entity_ids"] = allowed
        patch["employee_id"] = employee_id
        lost = set(before.get("allowed_entity_ids") or []) - set(allowed)
        if role_changed:
            revoke_reasons.append("role berubah")
        if lost:
            revoke_reasons.append("akses badan usaha dicabut")
        if before.get("home_entity_id") != home:
            revoke_reasons.append("badan usaha utama berpindah")

    if (data or {}).get("password"):
        patch["password_hash"] = hash_password(data["password"])
        revoke_reasons.append("password diganti")

    # FASE L — pagar lini produk. Divalidasi terhadap master lini aktif; mencabut
    # lini berarti pengguna berhenti boleh melihat sebagian data, jadi sesinya WAJIB
    # dicabut (kalau tidak, dia terus bekerja dengan hak lama sampai token kedaluwarsa).
    if "allowed_line_codes" in patch:
        patch["allowed_line_codes"] = await _valid_line_codes(
            patch["allowed_line_codes"],
            patch.get("home_entity_id", before.get("home_entity_id", "")))
        if sorted(patch["allowed_line_codes"]) != sorted(before.get("allowed_line_codes") or []):
            revoke_reasons.append("akses lini produk berubah")

    if not patch:
        raise HTTPException(
            status_code=400,
            detail="Tidak ada perubahan yang bisa disimpan. Status akun diubah lewat "
                   "tombol Nonaktifkan / Aktifkan kembali.")

    patch["updated_at"] = now_iso()
    await db.users.update_one({"id": user_id}, {"$set": patch})
    if patch.get("employee_id"):
        await db.hr_employees.update_one(
            {"id": patch["employee_id"]},
            {"$set": {"user_id": user_id, "updated_at": now_iso()}})
    revoked = 0
    if revoke_reasons:
        revoked = await revoke_sessions(user_id, ", ".join(revoke_reasons))
    after = await get_user_or_404(user_id)
    after["sessions_revoked"] = revoked
    after["revoke_reasons"] = revoke_reasons
    after["changed_fields"] = [k for k in patch if k not in ("updated_at", "password_hash")]
    if "password_hash" in patch:
        after["changed_fields"].append("password")
    return after


async def set_status(user_id: str, status: str) -> Dict[str, Any]:
    """E2.4 — nonaktifkan (soft) / aktifkan kembali. TIDAK pernah menghapus baris.

    Akun dihapus keras akan memutus jejak audit & dokumen yang menyebut namanya,
    jadi “hapus” di UI selalu berarti nonaktifkan.
    """
    if status not in ("active", "inactive"):
        raise HTTPException(status_code=400, detail="Status hanya boleh active atau inactive.")
    user = await get_user_or_404(user_id)
    if status == "inactive":
        await assert_not_last_admin(user_id, action="menonaktifkan akun ini")
    else:
        home = user.get("home_entity_id") or ""
        await lifecycle.assert_entity_writable(
            home, "mengaktifkan akun di badan usaha ini")
    await db.users.update_one({"id": user_id},
                              {"$set": {"status": status, "updated_at": now_iso()}})
    revoked = await revoke_sessions(user_id, "status akun berubah") if status == "inactive" else 0
    out = await get_user_or_404(user_id)
    out["sessions_revoked"] = revoked
    return out


async def reset_password(user_id: str, new_password: str) -> Dict[str, Any]:
    """E2.4 — reset password. Password LAMA tidak pernah dibaca/dibocorkan."""
    await get_user_or_404(user_id)
    pwd = (new_password or "").strip()
    if len(pwd) < 8:
        raise HTTPException(status_code=400,
                            detail="Password baru minimal 8 karakter.")
    await db.users.update_one(
        {"id": user_id},
        {"$set": {"password_hash": hash_password(pwd), "updated_at": now_iso(),
                  "password_reset_at": now_iso()}})
    revoked = await revoke_sessions(user_id, "password direset")
    return {"user_id": user_id, "sessions_revoked": revoked,
            "message": "Password berhasil direset. Semua sesi lama sudah dicabut."}
