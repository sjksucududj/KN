"""M1 — Process Recipe service: CRUD helper + forecast konversi (aman).

Forecast bisa dikonfigurasi (keputusan user #1):
- Bila `formula` (string) diisi → dievaluasi AMAN via AST terbatas.
  Variabel yang diizinkan: input_qty, gramasi, lebar, yield_factor, waste_pct,
  byproduct_pct. Fungsi: min, max, round, abs. Operator: + - * / ** % ().
- Bila kosong → fallback rumus baku:
    expected_output   = input_qty * yield_factor * (1 - waste_pct/100)
    expected_byproduct= input_qty * byproduct_pct/100
"""
import ast
from typing import Any, Dict, Optional

from db import db
from core_utils import safe_doc

_ALLOWED_BINOPS = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.Mod)
_ALLOWED_UNARY = (ast.UAdd, ast.USub)
_ALLOWED_FUNCS = {"min": min, "max": max, "round": round, "abs": abs}


def _eval_node(node: ast.AST, variables: Dict[str, float]) -> float:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return float(node.value)
        raise ValueError("Konstanta tidak valid dalam formula")
    if isinstance(node, ast.BinOp) and isinstance(node.op, _ALLOWED_BINOPS):
        left = _eval_node(node.left, variables)
        right = _eval_node(node.right, variables)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            if right == 0:
                raise ValueError("Pembagian dengan nol dalam formula")
            return left / right
        if isinstance(node.op, ast.Mod):
            if right == 0:
                raise ValueError("Modulo dengan nol dalam formula")
            return left % right
        if isinstance(node.op, ast.Pow):
            return left ** right
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, _ALLOWED_UNARY):
        val = _eval_node(node.operand, variables)
        return +val if isinstance(node.op, ast.UAdd) else -val
    if isinstance(node, ast.Name):
        if node.id in variables:
            return float(variables[node.id])
        raise ValueError(f"Variabel '{node.id}' tidak dikenal (boleh: {', '.join(variables)})")
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _ALLOWED_FUNCS:
        args = [_eval_node(a, variables) for a in node.args]
        return float(_ALLOWED_FUNCS[node.func.id](*args))
    raise ValueError("Ekspresi tidak diizinkan dalam formula")


def safe_eval_formula(expr: str, variables: Dict[str, float]) -> float:
    tree = ast.parse(expr, mode="eval")
    return _eval_node(tree.body, variables)


async def compute_forecast(params: Dict[str, Any]) -> Dict[str, Any]:
    """Hitung estimasi output + barang sisa. Bila recipe_id ada → muat default resep."""
    recipe: Optional[Dict[str, Any]] = None
    if params.get("recipe_id"):
        recipe = await db.process_recipes.find_one({"id": params["recipe_id"]}, {"_id": 0})

    def pick(key, default):
        v = params.get(key)
        if v is None and recipe is not None:
            v = recipe.get(key)
        return default if v is None else v

    input_qty = float(params.get("input_qty") or 0)
    yield_factor = float(pick("yield_factor", 1.0) or 0)
    waste_pct = float(pick("waste_pct", 0) or 0)
    byproduct_pct = float(pick("byproduct_pct", 0) or 0)
    gramasi = float(params.get("gramasi") or (recipe or {}).get("gramasi") or 0)
    lebar = float(params.get("lebar") or (recipe or {}).get("lebar") or 0)
    formula = params.get("formula")
    if formula is None and recipe is not None:
        formula = recipe.get("formula", "")
    formula = (formula or "").strip()

    variables = {
        "input_qty": input_qty, "gramasi": gramasi, "lebar": lebar,
        "yield_factor": yield_factor, "waste_pct": waste_pct, "byproduct_pct": byproduct_pct,
    }
    warnings = []
    if formula:
        try:
            expected_output = safe_eval_formula(formula, variables)
            formula_used = formula
        except ValueError as e:
            warnings.append(f"Formula gagal ({e}); pakai rumus baku.")
            expected_output = input_qty * yield_factor * (1 - waste_pct / 100)
            formula_used = ""
    else:
        expected_output = input_qty * yield_factor * (1 - waste_pct / 100)
        formula_used = ""

    expected_byproduct = input_qty * byproduct_pct / 100
    return {
        "input_qty": round(input_qty, 3),
        "yield_factor": yield_factor, "waste_pct": waste_pct, "byproduct_pct": byproduct_pct,
        "gramasi": gramasi, "lebar": lebar,
        "formula_used": formula_used,
        "expected_output": round(max(expected_output, 0), 3),
        "expected_byproduct": round(max(expected_byproduct, 0), 3),
        "recipe": safe_doc(recipe) if recipe else None,
        "warnings": warnings,
    }
