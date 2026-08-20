"""Router **CEK KENYATAAN PERAN** (utang migrasi (ii) FASE E-8/E-6).

Menjawab satu pertanyaan pemilik yang selama ini dijawab dengan tebakan:
*"akun mana yang berperan `manager` padahal pekerjaannya Admin Sales atau Finance?"*

Jawabannya dihitung dari jejak nyata — lihat `services/role_reality_service.py`.

Endpoint:
  GET  /api/access/role-reality                    laporan + bukti per akun
  POST /api/access/role-reality/{user_id}/apply    terapkan peran usulan (audit + cabut sesi)

KENAPA ADA ENDPOINT TERAP SENDIRI (bukan cukup `PATCH /users/{id}`)
-------------------------------------------------------------------
`PATCH /users/{id}` menerima peran APA PUN. Reklasifikasi berbasis bukti harus
**menolak** peran yang tidak muncul di usulan, supaya satu salah-klik tidak
mengubah wewenang orang ke arah yang tak pernah dihitung. Endpoint ini juga
menyimpan **potret buktinya** ke jejak audit, sehingga enam bulan kemudian masih
bisa dijawab "kenapa peran orang ini diturunkan".
"""
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Query, Request

from dependencies import require_permission, audit
from role_registry import role_label
from schemas import RoleReclassifyBody
from services import role_reality_service as svc
from services import user_admin_service as users_svc

router = APIRouter(prefix="/api")


@router.get("/access/role-reality")
async def role_reality(request: Request,
                       entity_id: str = Query("", description="filter badan usaha"),
                       role: str = Query("", description="filter peran")) -> Dict[str, Any]:
    await require_permission(request, "user", "view")
    return await svc.build_report(entity_id=entity_id, role_filter=role)


@router.post("/access/role-reality/{user_id}/apply")
async def apply_reclassification(user_id: str, body: RoleReclassifyBody,
                                 request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "user", "update")
    row = await svc.row_for(user_id)
    if not row:
        raise HTTPException(status_code=404, detail="Akun tidak ditemukan.")

    target = (body.role or "").strip()
    allowed = {row.get("suggested_role") or ""} | {
        s.get("suggested_role") or "" for s in (row.get("split") or [])}
    allowed.discard("")
    if target not in allowed:
        pilihan = " · ".join(sorted(role_label(r) for r in allowed)) or "—"
        raise HTTPException(
            status_code=400,
            detail=(
                f"Peran “{role_label(target)}” bukan usulan untuk akun ini, jadi tidak "
                f"diterapkan dari layar ini. Usulan berdasarkan jejaknya: {pilihan}. "
                f"Kalau memang mau memberi peran lain, ubah lewat formulir akun agar "
                f"keputusannya tercatat sebagai keputusan manual."))
    if target == row.get("role"):
        raise HTTPException(status_code=400,
                            detail="Peran akun sudah sama dengan usulan.")

    after = await users_svc.update_user(user_id, {"role": target})
    # Potret bukti ikut disimpan: alasan penurunan harus bisa dibaca ulang nanti.
    await audit(actor["name"], "role_reclassified", "user", user_id,
                {"from_role": row.get("role"), "to_role": target,
                 "verdict": row.get("verdict"),
                 "activity_total": row.get("activity_total"),
                 "evidence": [{"label": e["label"], "permission": e["permission"],
                               "count": e["count"]} for e in row.get("evidence", [])],
                 "note": (body.note or "").strip(),
                 "sessions_revoked": after.get("sessions_revoked", 0)},
                scope_entity_id=after.get("home_entity_id", ""))

    return {
        "user_id": user_id,
        "from_role": row.get("role"),
        "to_role": target,
        "sessions_revoked": after.get("sessions_revoked", 0),
        "message": (
            f"Peran {row.get('name')} diubah dari {role_label(row.get('role'))} menjadi "
            f"{role_label(target)}. {after.get('sessions_revoked', 0)} sesi dicabut — "
            f"ia harus masuk lagi supaya izin barunya berlaku."),
    }
