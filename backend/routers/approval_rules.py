"""Approval Rules Router

Manage approval rules configuration.
"""
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from db import db
from dependencies import require_permission, current_user
from entity_scope import assert_entity_access, entity_ctx, resolve_scope_ids
from services import approval_service

router = APIRouter(prefix="/api")


# ─── Schemas ─────────────────────────────────────────────────────────────────

class ApprovalRuleCreate(BaseModel):
    """Create approval rule"""
    name: str = Field(..., min_length=1, description="Rule name")
    entity_type: str = Field(..., description="Entity type (special_order, purchase_order, transfer, etc)")
    threshold_field: str = Field(..., description="Field to check (total_amount, quantity, discount_percentage)")
    threshold_operator: str = Field(..., description="Operator: gt, gte, lt, lte, eq")
    threshold_value: float = Field(..., description="Threshold value")
    approver_role: str = Field(..., description="Approver role (manager, admin, owner)")
    description: str = Field(default="", description="Rule description")
    priority: int = Field(default=100, description="Priority (lower = higher)")
    is_active: bool = Field(default=True, description="Is active")


class ApprovalRuleUpdate(BaseModel):
    """Update approval rule"""
    name: Optional[str] = None
    threshold_field: Optional[str] = None
    threshold_operator: Optional[str] = None
    threshold_value: Optional[float] = None
    approver_role: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[int] = None
    is_active: Optional[bool] = None


# ─── Endpoints ───────────────────────────────────────────────────────────────

@router.get("/approval-rules")
async def list_approval_rules(
    request: Request,
    entity_type: Optional[str] = None,
    is_active: Optional[bool] = None
) -> List[Dict[str, Any]]:
    """List approval rules with optional filters.
    
    Query params:
    - entity_type: Filter by entity type
    - is_active: Filter by active status
    """
    await require_permission(request, "settings", "view")
    ctx = await entity_ctx(request)
    rules = await approval_service.get_approval_rules(
        entity_type=entity_type,
        is_active=is_active,
        entity_ids=resolve_scope_ids(ctx),   # FASE E-0 (L15/L17)
    )
    
    return rules


@router.post("/approval-rules")
async def create_approval_rule(
    payload: ApprovalRuleCreate,
    request: Request
) -> Dict[str, Any]:
    """Create new approval rule (admin only).
    
    Approval rules define when approval is needed based on threshold conditions.
    """
    await require_permission(request, "settings", "manage")
    user = await current_user(request)
    ctx = await entity_ctx(request)
    
    # Validate operator
    valid_operators = ["gt", "gte", "lt", "lte", "eq"]
    if payload.threshold_operator not in valid_operators:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid operator. Must be one of: {', '.join(valid_operators)}"
        )
    
    # Validate approver role
    valid_roles = ["manager", "admin", "owner"]
    if payload.approver_role not in valid_roles:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid approver role. Must be one of: {', '.join(valid_roles)}"
        )
    
    rule = await approval_service.create_approval_rule(
        name=payload.name,
        entity_type=payload.entity_type,
        threshold_field=payload.threshold_field,
        threshold_operator=payload.threshold_operator,
        threshold_value=payload.threshold_value,
        approver_role=payload.approver_role,
        description=payload.description,
        priority=payload.priority,
        is_active=payload.is_active,
        created_by=user["email"],
        entity_id=ctx.active_entity_id,   # FASE E-0 — aturan lahir milik entitas aktif
    )
    
    return rule


@router.get("/approval-rules/{rule_id}")
async def get_approval_rule(
    rule_id: str,
    request: Request
) -> Dict[str, Any]:
    """Get approval rule by ID."""
    await require_permission(request, "settings", "view")
    
    rule = await db.approval_rules.find_one({"id": rule_id}, {"_id": 0})
    if rule and rule.get("entity_id") not in (None, "", "all"):
        assert_entity_access(rule, "approval_rules", await entity_ctx(request))
    if not rule:
        raise HTTPException(status_code=404, detail="Approval rule tidak ditemukan")
    
    return rule


@router.patch("/approval-rules/{rule_id}")
async def update_approval_rule(
    rule_id: str,
    payload: ApprovalRuleUpdate,
    request: Request
) -> Dict[str, Any]:
    """Update approval rule (admin only)."""
    await require_permission(request, "settings", "manage")
    
    # Build updates dict
    updates = {}
    if payload.name is not None:
        updates["name"] = payload.name
    if payload.threshold_field is not None:
        updates["threshold_field"] = payload.threshold_field
    if payload.threshold_operator is not None:
        valid_operators = ["gt", "gte", "lt", "lte", "eq"]
        if payload.threshold_operator not in valid_operators:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid operator. Must be one of: {', '.join(valid_operators)}"
            )
        updates["threshold_operator"] = payload.threshold_operator
    if payload.threshold_value is not None:
        updates["threshold_value"] = payload.threshold_value
    if payload.approver_role is not None:
        valid_roles = ["manager", "admin", "owner"]
        if payload.approver_role not in valid_roles:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid approver role. Must be one of: {', '.join(valid_roles)}"
            )
        updates["approver_role"] = payload.approver_role
    if payload.description is not None:
        updates["description"] = payload.description
    if payload.priority is not None:
        updates["priority"] = payload.priority
    if payload.is_active is not None:
        updates["is_active"] = payload.is_active
    
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    
    try:
        rule = await approval_service.update_approval_rule(rule_id, updates)
        return rule
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/approval-rules/{rule_id}")
async def delete_approval_rule(
    rule_id: str,
    request: Request
) -> Dict[str, str]:
    """Soft delete approval rule (set is_active=False)."""
    await require_permission(request, "settings", "manage")
    
    success = await approval_service.delete_approval_rule(rule_id)
    if not success:
        raise HTTPException(status_code=404, detail="Approval rule tidak ditemukan")
    
    return {"message": "Aturan persetujuan berhasil dihapus"}
