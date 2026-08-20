"""PS-18 — Layanan **KPI DESAINER** (kinerja pelaksana R&D yang terhitung sendiri).

MASALAH NYATA
-------------
Pemilik ingin tahu *"desainer mana yang paling bisa diandalkan?"* — bukan dari kesan,
tetapi dari jejak kerja yang sudah ada di sistem. Sebelum modul ini, laporan R&D hanya
menghitung jumlah round/ACC/revisi (`rnd_sample_service.performer_report`) tanpa
menjawab pertanyaan yang paling sering ditanya pemilik: **tepat waktu atau tidak,
sering diulang atau tidak, dan siapa yang layak dinaikkan.**

DESAIN
------
* **Nol input manual.** Semua angka lahir dari `md_samples.rounds[]` yang memang sudah
  wajib ber-bukti (lampiran + catatan) saat disetor. Tidak ada tabel KPI kedua yang
  harus diisi tangan — beda dengan `hr_kpi` (KPI SDM manual) yang tetap hidup di HRD.
* **Penanggung jawab round** = `performed_by` (yang menyetor hasil). Bila round masih
  berjalan (belum disetor) dipakai `opened_by` (yang membuka round), lalu `created_by`
  permintaan sebagai jaring terakhir — supaya round TERLAMBAT tetap punya pemilik dan
  tidak hilang dari laporan.
* **Bobot & penalti dapat diubah pemilik** lewat Pusat Pengaturan (`rnd.kpi_*`), sesuai
  INV-CFG: tidak ada angka kebijakan yang dipatok di kode.
* **Grade dinormalisasi.** Bila satu komponen belum punya data (mis. belum ada round
  yang dinilai), bobotnya TIDAK dianggap nol — komponen itu dikeluarkan lalu bobot sisa
  dinormalkan ulang. Ini mencegah desainer baru langsung ter-grade "D" hanya karena
  datanya belum lengkap.
* **Periode** disaring dari tanggal nyata round (disetor → `received_at`, kalau belum
  disetor → `sent_at`).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from db import db
from config_divisions import DIVISION_BY_ID
from services import rnd_gate

COLL = "md_samples"


async def _division_map(entity_id: str) -> Dict[str, str]:
    """name -> division_id untuk PS-17 (dari `rnd_person_divisions`, fallback users)."""
    m: Dict[str, str] = {}
    async for r in db["rnd_person_divisions"].find(
            {"entity_id": entity_id}, {"_id": 0, "name": 1, "division": 1}):
        if r.get("division"):
            m[r["name"]] = r["division"]
    async for u in db.users.find({}, {"_id": 0, "name": 1, "division": 1}):
        if u.get("division") and u["name"] not in m:
            m[u["name"]] = u["division"]
    return m

# Periode laporan — sengaja pilihan pendek & mudah dipahami pemilik.
PERIODS: Tuple[str, ...] = ("month", "30d", "90d", "all")
PERIOD_LABEL: Dict[str, str] = {
    "month": "Bulan ini",
    "30d": "30 hari terakhir",
    "90d": "90 hari terakhir",
    "all": "Semua waktu",
}

# Ambang grade komposit (nilai minimum → huruf + arti untuk pemilik).
GRADE_BANDS: Tuple[Tuple[float, str, str], ...] = (
    (85.0, "A", "Sangat baik — layak jadi rujukan"),
    (70.0, "B", "Baik — sesuai harapan"),
    (55.0, "C", "Cukup — perlu perhatian"),
    (0.0, "D", "Perlu pembinaan"),
)

# Permintaan yang sudah SELESAI tidak lagi dihitung "terlambat sekarang": pemenang
# sudah dipilih / permintaan dibatalkan, jadi tak ada lagi yang menunggu.
CLOSED_SAMPLE_STATUSES = ("decided", "cancelled")
RUNNING_ROUND_STATUSES = ("open", "submitted")
RESULTS = ("acc", "revisi", "tolak")


# ─── Helper tanggal ───────────────────────────────────────────────────────────
def period_options() -> List[Dict[str, str]]:
    return [{"value": p, "label": PERIOD_LABEL[p]} for p in PERIODS]


def normalize_period(period: str = "") -> str:
    p = (period or "all").strip().lower()
    return p if p in PERIODS else "all"


def period_start(period: str = "all", today: Optional[date] = None) -> Optional[date]:
    """Tanggal awal periode (None = semua waktu)."""
    today = today or date.today()
    p = normalize_period(period)
    if p == "month":
        return today.replace(day=1)
    if p == "30d":
        return today - timedelta(days=30)
    if p == "90d":
        return today - timedelta(days=90)
    return None


def _as_date(raw: Any) -> Optional[date]:
    txt = str(raw or "")[:10]
    if not txt:
        return None
    try:
        return date.fromisoformat(txt)
    except ValueError:
        return None


def _ref_date(rd: Dict[str, Any]) -> Optional[date]:
    """Tanggal acuan round untuk penyaringan periode."""
    return (_as_date(rd.get("received_at")) or _as_date(rd.get("assessed_at"))
            or _as_date(rd.get("sent_at")) or _as_date(rd.get("due_date")))


def days_late(rd: Dict[str, Any], today: Optional[date] = None) -> int:
    """Berapa hari round yang MASIH BERJALAN sudah melewati tenggat (0 = tidak)."""
    due = _as_date(rd.get("due_date"))
    if not due:
        return 0
    today = today or date.today()
    return max((today - due).days, 0)


def designer_of(sample: Dict[str, Any], rd: Dict[str, Any]) -> str:
    """Penanggung jawab round — lihat catatan desain di docstring modul."""
    for cand in (rd.get("performed_by"), rd.get("opened_by"), sample.get("created_by")):
        name = str(cand or "").strip()
        if name:
            return name
    return "(tanpa nama)"


def grade_of(score: Optional[float]) -> Dict[str, str]:
    if score is None:
        return {"letter": "—", "meaning": "Data belum cukup untuk dinilai"}
    for minimum, letter, meaning in GRADE_BANDS:
        if score >= minimum:
            return {"letter": letter, "meaning": meaning}
    return {"letter": "D", "meaning": GRADE_BANDS[-1][2]}


def _pct(part: int, whole: int) -> Optional[float]:
    return round(part / whole * 100, 1) if whole else None


def _blank(name: str) -> Dict[str, Any]:
    return {"designer": name, "rounds": 0, "submitted": 0, "assessed": 0,
            "on_time": 0, "late_submitted": 0, "acc": 0, "revisi": 0, "tolak": 0,
            "overdue_now": 0, "overdue_critical": 0, "max_days_late": 0,
            "score_sum": 0.0, "score_n": 0, "days_sum": 0.0, "days_n": 0,
            "samples": set(), "cost": 0.0}


def _elapsed_days(rd: Dict[str, Any]) -> Optional[float]:
    try:
        t0 = datetime.fromisoformat(str(rd.get("sent_at")).replace("Z", "+00:00"))
        t1 = datetime.fromisoformat(str(rd.get("received_at")).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return max((t1 - t0).total_seconds() / 86400.0, 0.0)


# ─── Bobot kebijakan (Pusat Pengaturan) ──────────────────────────────────────
async def weights(entity_id: str = "") -> Dict[str, Any]:
    """Bobot & penalti grade yang BERLAKU + ambang eskalasi (untuk UI & perhitungan)."""
    pol = await rnd_gate.policy(entity_id or "")
    return {
        "on_time": float(pol.get("kpi_weight_on_time") or 0),
        "score": float(pol.get("kpi_weight_score") or 0),
        "acc": float(pol.get("kpi_weight_acc") or 0),
        "penalty_rework": float(pol.get("kpi_penalty_rework") or 0),
        "penalty_overdue": float(pol.get("kpi_penalty_overdue") or 0),
        "escalate_admin_days": int(pol.get("sla_escalate_admin_days") or 3),
        "round_sla_days": int(pol.get("round_sla_days") or 7),
    }


def compute_grade(row: Dict[str, Any], w: Dict[str, Any]) -> Dict[str, Any]:
    """Grade komposit 0–100 (bobot dinormalkan atas komponen yang PUNYA data)."""
    comps: List[Tuple[float, float]] = []
    if row.get("on_time_pct") is not None:
        comps.append((float(w["on_time"]), float(row["on_time_pct"])))
    if row.get("avg_score") is not None:
        comps.append((float(w["score"]), min(float(row["avg_score"]), 100.0)))
    if row.get("acc_rate") is not None:
        comps.append((float(w["acc"]), float(row["acc_rate"])))
    wsum = sum(weight for weight, _ in comps if weight > 0)
    if wsum <= 0:
        return {"grade_score": None, "grade_base": None, "grade_penalty": 0.0,
                **{f"grade_{k}": v for k, v in grade_of(None).items()}}
    base = sum(weight * val for weight, val in comps) / wsum
    late_share = _pct(int(row.get("late_total") or 0), int(row.get("rounds") or 0)) or 0.0
    penalty = (float(w["penalty_rework"]) * float(row.get("rework_pct") or 0)
               + float(w["penalty_overdue"]) * late_share)
    score = round(max(0.0, min(100.0, base - penalty)), 1)
    return {"grade_score": score, "grade_base": round(base, 1),
            "grade_penalty": round(penalty, 1),
            **{f"grade_{k}": v for k, v in grade_of(score).items()}}


# ─── Laporan utama ───────────────────────────────────────────────────────────
async def designer_kpi(query: Optional[Dict[str, Any]] = None, *, period: str = "all",
                       entity_id: str = "", division: str = "") -> Dict[str, Any]:
    """KPI per desainer/pelaksana R&D untuk satu periode.

    PS-17: tiap baris diberi `division`/`division_name`; bila `division` diisi, daftar
    disaring ke divisi itu (peringkat tetap peringkat GLOBAL agar tetap bermakna).
    """
    per = normalize_period(period)
    today = date.today()
    start = period_start(per, today)
    w = await weights(entity_id)
    admin_days = int(w["escalate_admin_days"])

    rows = await db[COLL].find(dict(query or {}), {
        "_id": 0, "id": 1, "number": 1, "status": 1, "created_by": 1, "rounds": 1,
    }).to_list(5000)

    agg: Dict[str, Dict[str, Any]] = {}
    for s in rows:
        closed = str(s.get("status") or "") in CLOSED_SAMPLE_STATUSES
        for rd in (s.get("rounds") or []):
            ref = _ref_date(rd)
            if start and (ref is None or ref < start):
                continue
            who = designer_of(s, rd)
            a = agg.setdefault(who, _blank(who))
            a["rounds"] += 1
            a["samples"].add(s.get("id") or s.get("number") or "")
            a["cost"] = round(a["cost"] + float(rd.get("cost") or 0), 2)
            if rd.get("received_at"):
                a["submitted"] += 1
                if rd.get("overdue"):
                    a["late_submitted"] += 1
                else:
                    a["on_time"] += 1
                elapsed = _elapsed_days(rd)
                if elapsed is not None:
                    a["days_sum"] += elapsed
                    a["days_n"] += 1
            res = str(rd.get("result") or "")
            if res in RESULTS:
                a["assessed"] += 1
                a[res] += 1
            if rd.get("score") is not None:
                a["score_sum"] += float(rd["score"])
                a["score_n"] += 1
            if not closed and str(rd.get("status") or "") in RUNNING_ROUND_STATUSES:
                late = days_late(rd, today)
                if late > 0:
                    a["overdue_now"] += 1
                    a["max_days_late"] = max(int(a["max_days_late"]), late)
                    if late >= admin_days:
                        a["overdue_critical"] += 1

    items: List[Dict[str, Any]] = []
    for a in agg.values():
        rework = int(a["revisi"]) + int(a["tolak"])
        late_total = int(a["late_submitted"]) + int(a["overdue_now"])
        row: Dict[str, Any] = {
            "designer": a["designer"],
            "samples": len([x for x in a["samples"] if x]),
            "rounds": a["rounds"], "submitted": a["submitted"], "assessed": a["assessed"],
            "acc": a["acc"], "revisi": a["revisi"], "tolak": a["tolak"],
            "rework": rework,
            "late_submitted": a["late_submitted"], "overdue_now": a["overdue_now"],
            "overdue_critical": a["overdue_critical"],
            "max_days_late": a["max_days_late"], "late_total": late_total,
            "on_time_pct": _pct(int(a["on_time"]), int(a["submitted"])),
            "acc_rate": _pct(int(a["acc"]), int(a["assessed"])),
            "rework_pct": _pct(rework, int(a["assessed"])),
            "avg_score": round(a["score_sum"] / a["score_n"], 1) if a["score_n"] else None,
            "avg_days": round(a["days_sum"] / a["days_n"], 1) if a["days_n"] else None,
            "cost_total": a["cost"],
        }
        row.update(compute_grade(row, w))
        items.append(row)

    items.sort(key=lambda r: (-(r["grade_score"] if r["grade_score"] is not None else -1),
                              -int(r["acc"]), str(r["designer"])))
    for i, row in enumerate(items, start=1):
        row["rank"] = i

    # PS-17 — tempel divisi tiap orang; simpan divisi yang HADIR untuk filter UI.
    dmap = await _division_map(entity_id)
    for row in items:
        div = dmap.get(row["designer"], "")
        row["division"] = div
        row["division_name"] = DIVISION_BY_ID.get(div, {}).get("name", "")
    divisions_present = sorted({r["division"] for r in items if r["division"]})
    if division:
        items = [r for r in items if r.get("division") == division]

    return {
        "period": per, "period_label": PERIOD_LABEL[per],
        "from_date": start.isoformat() if start else "",
        "to_date": today.isoformat(),
        "count": len(items), "items": items,
        "summary": _summary(items),
        "division": division,
        "divisions_present": [{"id": d, "name": DIVISION_BY_ID.get(d, {}).get("name", d)}
                              for d in divisions_present],
        "weights": w, "period_options": period_options(),
        "grade_bands": [{"min": m, "letter": ltr, "meaning": mean}
                        for m, ltr, mean in GRADE_BANDS],
    }


def _summary(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Ringkasan sekumpulan baris KPI (kartu atas layar)."""
    rounds = sum(int(r["rounds"]) for r in items)
    submitted = sum(int(r["submitted"]) for r in items)
    assessed = sum(int(r["assessed"]) for r in items)
    on_time = sum(int(r["submitted"]) - int(r["late_submitted"]) for r in items)
    acc = sum(int(r["acc"]) for r in items)
    rework = sum(int(r["rework"]) for r in items)
    graded = [r for r in items if r["grade_score"] is not None]
    scored = [r for r in items if r["avg_score"] is not None]
    return {
        "designers": len(items), "rounds": rounds, "submitted": submitted,
        "assessed": assessed, "acc": acc, "rework": rework,
        "overdue_now": sum(int(r["overdue_now"]) for r in items),
        "overdue_critical": sum(int(r["overdue_critical"]) for r in items),
        "late_submitted": sum(int(r["late_submitted"]) for r in items),
        "on_time_pct": _pct(on_time, submitted),
        "acc_rate": _pct(acc, assessed),
        "rework_pct": _pct(rework, assessed),
        "avg_score": round(sum(float(r["avg_score"]) for r in scored) / len(scored), 1)
        if scored else None,
        "avg_grade": round(sum(float(r["grade_score"]) for r in graded) / len(graded), 1)
        if graded else None,
        "best_designer": graded[0]["designer"] if graded else "",
        "best_grade": graded[0]["grade_letter"] if graded else "",
        "cost_total": round(sum(float(r["cost_total"]) for r in items), 2),
    }


# ═════════════════════════════════════════════════════════════════════════════
#  "KPI SAYA" — kartu penilaian milik SENDIRI (Profil Saya / ESS)
#
#  PRIVASI adalah inti fitur ini: seorang desainer HANYA boleh melihat angkanya
#  sendiri. Yang dikembalikan dari tim cuma **agregat** (rata-rata & jumlah) dan
#  posisi peringkat — TIDAK PERNAH nama atau nilai rekan. Karena itu penyaringan
#  dilakukan di SERVER, bukan disembunyikan di layar.
# ═════════════════════════════════════════════════════════════════════════════
def _norm(name: str) -> str:
    return " ".join(str(name or "").strip().lower().split())


async def my_rounds(query: Optional[Dict[str, Any]] = None, *, name: str,
                    period: str = "all", limit: int = 15) -> List[Dict[str, Any]]:
    """Riwayat round MILIK SENDIRI (terbaru dulu) — umpan balik yang konkret."""
    key = _norm(name)
    if not key:
        return []
    today = date.today()
    start = period_start(normalize_period(period), today)
    rows = await db[COLL].find(dict(query or {}), {
        "_id": 0, "id": 1, "number": 1, "title": 1, "sample_type": 1, "status": 1,
        "created_by": 1, "rounds": 1,
    }).to_list(5000)
    out: List[Dict[str, Any]] = []
    for s in rows:
        closed = str(s.get("status") or "") in CLOSED_SAMPLE_STATUSES
        for rd in (s.get("rounds") or []):
            if _norm(designer_of(s, rd)) != key:
                continue
            ref = _ref_date(rd)
            if start and (ref is None or ref < start):
                continue
            running = (not closed
                       and str(rd.get("status") or "") in RUNNING_ROUND_STATUSES)
            late_now = days_late(rd, today) if running else 0
            elapsed = _elapsed_days(rd)
            out.append({
                "sample_id": s.get("id", ""), "number": s.get("number", ""),
                "title": s.get("title", ""), "sample_type": s.get("sample_type", ""),
                "round_id": rd.get("id", ""), "round_no": int(rd.get("round_no") or 0),
                "supplier_name": rd.get("supplier_name", ""),
                "status": rd.get("status", ""), "result": rd.get("result", ""),
                "score": rd.get("score"), "due_date": str(rd.get("due_date") or "")[:10],
                "submitted_at": str(rd.get("received_at") or "")[:10],
                "on_time": (not bool(rd.get("overdue"))) if rd.get("received_at") else None,
                "days": round(elapsed, 1) if elapsed is not None else None,
                "days_late": late_now,
                "ref_date": ref.isoformat() if ref else "",
            })
    out.sort(key=lambda r: str(r["ref_date"]), reverse=True)
    return out[:int(limit)]


async def my_kpi(query: Optional[Dict[str, Any]] = None, *, name: str,
                 period: str = "30d", entity_id: str = "") -> Dict[str, Any]:
    """Kartu penilaian diri sendiri + pembanding tim yang AGREGAT (tanpa nama rekan)."""
    rep = await designer_kpi(query, period=period, entity_id=entity_id)
    key = _norm(name)
    me = next((r for r in rep["items"] if _norm(r["designer"]) == key), None)
    team = rep["summary"]
    rounds = await my_rounds(query, name=name, period=period)
    return {
        "designer": name,
        "period": rep["period"], "period_label": rep["period_label"],
        "from_date": rep["from_date"], "to_date": rep["to_date"],
        "period_options": rep["period_options"],
        "weights": rep["weights"], "grade_bands": rep["grade_bands"],
        "me": me,                                   # None = belum punya round R&D
        "rank": me["rank"] if me else None,
        "total_designers": rep["count"],
        # HANYA angka gabungan tim — sengaja TANPA daftar/nama rekan.
        "team": {
            "designers": team["designers"], "avg_grade": team["avg_grade"],
            "on_time_pct": team["on_time_pct"], "rework_pct": team["rework_pct"],
            "avg_score": team["avg_score"],
        },
        "rounds": rounds,
        "overdue": [r for r in rounds if int(r["days_late"]) > 0],
    }


# ═════════════════════════════════════════════════════════════════════════════
#  TREN NILAI DESAINER PER BULAN (grafik) — PS-18 lanjutan
#
#  Owner ingin melihat ARAH kinerja tiap desainer, bukan sekadar angka bulan ini.
#  Untuk setiap bulan pada jendela terakhir, kami menghitung ULANG grade komposit
#  memakai `compute_grade` yang SAMA dengan tabel KPI — hanya saja round disaring
#  per-bulan (berdasarkan `_ref_date`). Dengan begitu titik grafik = "nilai desainer
#  bila dinilai dari pekerjaan bulan itu", konsisten dengan kolom "Nilai" di tabel.
# ═════════════════════════════════════════════════════════════════════════════
_MONTH_ABBR_ID = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun",
                  "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]


def _month_key(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def _month_label(key: str) -> str:
    try:
        y, m = key.split("-")
        return f"{_MONTH_ABBR_ID[int(m) - 1]} {y}"
    except (ValueError, IndexError):
        return key


def _last_months(n: int, today: Optional[date] = None) -> List[str]:
    """Daftar kunci bulan (YYYY-MM) dari n bulan lalu s.d. bulan berjalan (urut naik)."""
    today = today or date.today()
    y, m, keys = today.year, today.month, []
    for _ in range(max(1, n)):
        keys.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            m, y = 12, y - 1
    return list(reversed(keys))


async def designer_kpi_trend(query: Optional[Dict[str, Any]] = None, *, months: int = 6,
                             entity_id: str = "", metric: str = "grade") -> Dict[str, Any]:
    """Tren nilai desainer per bulan (grade komposit / rata-rata skor) untuk grafik."""
    months = max(3, min(int(months or 6), 12))
    metric = "avg_score" if str(metric or "").lower() in ("avg_score", "score") else "grade"
    today = date.today()
    keys = _last_months(months, today)
    keyset = set(keys)
    w = await weights(entity_id)

    rows = await db[COLL].find(dict(query or {}), {
        "_id": 0, "id": 1, "status": 1, "created_by": 1, "rounds": 1,
    }).to_list(5000)

    # buckets[month_key][designer] = agregat ringkas
    buckets: Dict[str, Dict[str, Dict[str, Any]]] = {k: {} for k in keys}
    designers: set = set()
    for s in rows:
        for rd in (s.get("rounds") or []):
            ref = _ref_date(rd)
            if not ref:
                continue
            mk = _month_key(ref)
            if mk not in keyset:
                continue
            who = designer_of(s, rd)
            designers.add(who)
            a = buckets[mk].setdefault(who, _blank(who))
            a["rounds"] += 1
            if rd.get("received_at"):
                a["submitted"] += 1
                if rd.get("overdue"):
                    a["late_submitted"] += 1
                else:
                    a["on_time"] += 1
            res = str(rd.get("result") or "")
            if res in RESULTS:
                a["assessed"] += 1
                a[res] += 1
            if rd.get("score") is not None:
                a["score_sum"] += float(rd["score"])
                a["score_n"] += 1

    series: List[Dict[str, Any]] = []
    for who in designers:
        points: List[Dict[str, Any]] = []
        vals: List[float] = []
        total_rounds = 0
        for k in keys:
            a = buckets[k].get(who)
            if not a:
                points.append({"month": k, "score": None, "avg_score": None,
                               "grade_score": None, "rounds": 0})
                continue
            rework = int(a["revisi"]) + int(a["tolak"])
            row = {
                "rounds": a["rounds"], "assessed": a["assessed"],
                "on_time_pct": _pct(int(a["on_time"]), int(a["submitted"])),
                "acc_rate": _pct(int(a["acc"]), int(a["assessed"])),
                "rework_pct": _pct(rework, int(a["assessed"])),
                "avg_score": round(a["score_sum"] / a["score_n"], 1) if a["score_n"] else None,
                "rework": rework, "late_total": int(a["late_submitted"]),
            }
            g = compute_grade(row, w)
            score = g["grade_score"] if metric == "grade" else row["avg_score"]
            total_rounds += int(a["rounds"])
            points.append({"month": k, "score": score, "avg_score": row["avg_score"],
                           "grade_score": g["grade_score"], "rounds": int(a["rounds"])})
            if score is not None:
                vals.append(float(score))
        series.append({"designer": who, "points": points,
                       "rounds": total_rounds,
                       "avg": round(sum(vals) / len(vals), 1) if vals else None})

    series.sort(key=lambda r: (r["avg"] is None, -(r["avg"] or 0), str(r["designer"])))
    return {
        "months": keys,
        "month_labels": [_month_label(k) for k in keys],
        "metric": metric,
        "metric_label": "Grade komposit (0–100)" if metric == "grade" else "Rata-rata skor",
        "count": len(series),
        "designers": [s["designer"] for s in series],
        "series": series,
        "weights": w,
    }
