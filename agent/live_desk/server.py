"""
Live send desk: Week 10 writes the email, the Week 11 evaluator judges it, and only a pass is sent.

    python -m agent.live_desk.server            # http://127.0.0.1:8100
    python -m agent.live_desk.server --port 8101

Flow per company:
  1. research   the real Week 10 enrichment pipeline on a Crunchbase company (brief built exactly as the
                benchmark export built it, so the judge sees the format it was validated on)
  2. compose    original Week 10 composer (v1) or the honest composer (v2); the draft is editable
  3. judge      Week 11 scoring_evaluator.py v0.2.1 (frozen): 5 dimensions, violations with evidence
  4. send       server re-judges (the client cannot skip it); only a full pass is delivered via Resend,
                according to OUTBOUND_MODE (off / redirect to DEMO_INBOX / live to a typed address)

Held-out benchmark companies are excluded from search so the sealed test set stays sealed.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from agent import llm_writer, outbound, send_gate  # noqa: E402
from agent.live_desk.persona import Persona, polish  # noqa: E402

HERE = Path(__file__).resolve().parent
STATE = ROOT / ".state"
SEND_LOG = STATE / "live_sends.jsonl"
_lock = threading.RLock()
_cache: dict[str, dict] = {}

app = FastAPI(title="Live send desk", description="Week 10 composes, Week 11 judges, only a pass is sent.")


# ── data: the same export code the benchmark used ───────────────────────
@contextlib.contextmanager
def _quiet():
    with contextlib.redirect_stdout(io.StringIO()):
        yield


def _export():
    """Week 11's export module: compact_brief/enrich_rows exactly as used to build the benchmark."""
    tb = str(send_gate.TB_DIR)
    if tb not in sys.path:
        sys.path.insert(0, tb)
    with _quiet():
        import generation_scripts.export_week10_briefs as ex  # noqa: WPS433
    return ex


_df = None
_held: set[str] | None = None


def _crunchbase():
    global _df
    if _df is None:
        with _quiet():
            _df = _export().load_crunchbase_data()
    return _df


def _held_out_names() -> set[str]:
    """Names in the sealed held-out (local, gitignored). Never offered in the desk."""
    global _held
    if _held is None:
        f = send_gate.TB_DIR / "generation_scripts" / "week10_export" / "week10_briefs.jsonl"
        _held = ({json.loads(l)["brief"]["prospect"].lower() for l in f.read_text(encoding="utf-8").splitlines() if l.strip()}
                 if f.exists() else set())
    return _held


def research(name: str) -> dict:
    with _lock:
        if name in _cache:
            return _cache[name]
        if name.lower() in _held_out_names():
            raise HTTPException(403, "held-out benchmark company: sealed, not available in the desk")
        ex = _export()
        t0 = time.time()
        with _quiet():
            rows = ex.enrich_rows([name], _crunchbase())
        if not rows:
            raise HTTPException(404, f"{name!r} not found in the Crunchbase sample")
        r = rows[0]
        from agent.email_agent import generate_outreach_email, generate_outreach_email_v1
        with _quiet():
            v1 = generate_outreach_email_v1({**r["raw_w10"], "prospect": r["brief"]["prospect"]})
            v2 = generate_outreach_email(r["brief"])
        out = {"name": name, "brief": r["brief"], "research_ms": round((time.time() - t0) * 1000),
               "emails": {"v1": {"subject": v1["subject"], "body": v1["body"]},
                          "v2": {"subject": v2["subject"], "body": v2["body"]}}}
        _cache[name] = out
        return out


# ── API ─────────────────────────────────────────────────────────────────
@app.get("/api/config")
def config():
    cfg = outbound.OutboundConfig.from_env()
    try:
        ev = {"ok": True, "version": send_gate.evaluator().VERSION, "path": str(send_gate.TB_DIR)}
    except send_gate.EvaluatorUnavailable as e:
        ev = {"ok": False, "error": str(e)}
    writer = {"available": llm_writer.available(), "model": __import__("os").getenv("LIVE_DESK_MODEL") or llm_writer.DEFAULT_MODEL,
              "spent_usd": llm_writer.spent_usd(), "budget_usd": llm_writer.budget_usd()}
    return {"outbound": cfg.public(), "evaluator": ev, "persona": Persona.from_env().public(), "writer": writer}


@app.get("/api/companies")
def companies(q: str = "", limit: int = 40):
    held = _held_out_names()
    names = [str(n).strip() for n in _crunchbase()["name"]]
    names = [n for n in dict.fromkeys(names) if n and n.lower() != "nan" and n.lower() not in held]
    if q:
        names = [n for n in names if q.lower() in n.lower()]
    return {"total": len(names), "names": names[:limit]}


@app.get("/api/featured")
def featured():
    """Companies that tell the story: the original composer fails the judge, the honest one passes."""
    f = send_gate.TB_DIR / "training_data" / "week10_train_briefs.jsonl"
    picks = []
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            j = send_gate.judge(r["brief"], r["week10_email"])
            codes = sorted({v["code"] for v in j["violations"]})
            if not j["all_pass"] and "FUNDING_NOT_RECENT" in codes and len(picks) < 4:
                picks.append({"name": r["brief"]["prospect"], "why": "original composer pitches a stale funding round"})
            elif j["all_pass"] and not any(p["why"].startswith("original composer passes") for p in picks):
                picks.append({"name": r["brief"]["prospect"], "why": "original composer passes too"})
            if len(picks) >= 5:
                break
    return {"featured": picks}


class EmailIn(BaseModel):
    subject: str = Field("", max_length=300)
    body: str = Field("", max_length=8000)


class ResearchIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    first_name: str | None = Field(None, max_length=40)


@app.post("/api/research")
def api_research(body: ResearchIn):
    """Brief + both template drafts, polished with the sender persona (what the judge and the reader see)."""
    r = research(body.name)
    p = Persona.from_env()
    return r | {"emails": {k: polish(e, p, body.first_name) for k, e in r["emails"].items()}}


class WriteIn(BaseModel):
    name: str
    first_name: str | None = Field(None, max_length=40)
    email: EmailIn | None = None   # set to ask the writer to fix this draft using the judge's findings


@app.post("/api/write")
def api_write(body: WriteIn):
    """LLM writer (v3). With `email`, it rewrites that draft once using the Week 11 violations as feedback."""
    brief = research(body.name)["brief"]
    p = Persona.from_env()
    prev, viol = None, None
    if body.email is not None:
        prev = body.email.model_dump()
        viol = send_gate.judge(brief, prev)["violations"]
        if not viol:
            return {"email": prev, "model": None, "rewrite": False, "note": "already passes: nothing to fix"}
    t0 = time.time()
    try:
        out = llm_writer.write(brief, p, body.first_name, prev, viol)
    except llm_writer.WriterError as e:
        raise HTTPException(503, str(e))
    out["email"] = polish(out["email"], p, body.first_name)
    out["write_ms"] = round((time.time() - t0) * 1000)
    out["spent_usd"] = llm_writer.spent_usd()
    return out


class JudgeIn(BaseModel):
    name: str
    email: EmailIn


@app.post("/api/judge")
def api_judge(body: JudgeIn):
    brief = research(body.name)["brief"]
    t0 = time.perf_counter()
    try:
        j = send_gate.judge(brief, body.email.model_dump())
    except send_gate.EvaluatorUnavailable as e:
        raise HTTPException(503, str(e))
    j["judge_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    return j


class SendIn(BaseModel):
    name: str
    email: EmailIn
    composer: str = "edited"
    to: str | None = Field(None, max_length=254)


@app.post("/api/send")
def api_send(body: SendIn):
    brief = research(body.name)["brief"]
    cfg = outbound.OutboundConfig.from_env()
    try:
        j = send_gate.judge(brief, body.email.model_dump())  # re-judged here: the client cannot skip the gate
    except send_gate.EvaluatorUnavailable as e:
        raise HTTPException(503, f"no judge, no send: {e}")
    rec = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "company": body.name, "composer": body.composer,
           "subject": body.email.subject, "verdict": "pass" if j["all_pass"] else "fail",
           "violations": [v["code"] for v in j["violations"]]}
    if not send_gate.allowed(j):
        rec["delivery"] = {"status": "blocked_by_evaluator"}
        _log(rec)
        raise HTTPException(409, detail={"message": "Blocked by the Week 11 evaluator", "judgment": j})
    if cfg.mode == "live" and not (body.to or "").strip():
        raise HTTPException(422, "live mode: type the recipient address (the desk never emails company data)")
    note = f"Passed the Week 11 pre-send check (Tenacious-Bench evaluator v{j['evaluator_version']})."
    d = outbound.deliver(f"a contact at {body.name}", body.email.subject, body.email.body,
                         override_to=(body.to or None), note=note, cfg=cfg)
    rec["delivery"] = {k: d[k] for k in ("mode", "status", "message_id", "error", "why")} | {"routed_to": outbound.mask(d["routed_to"])}
    _log(rec)
    return {"judgment": j, "delivery": rec["delivery"]}


@app.get("/api/sends")
def sends(limit: int = 20):
    if not SEND_LOG.exists():
        return {"sends": []}
    rows = [json.loads(l) for l in SEND_LOG.read_text(encoding="utf-8").splitlines() if l.strip()]
    return {"sends": rows[-limit:][::-1]}


def _log(rec: dict) -> None:
    with _lock:
        STATE.mkdir(exist_ok=True)
        with SEND_LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


# ── Autopilot: the judge is the gatekeeper; a human only handles what it rejected ──
from agent.live_desk.autopilot import Autopilot, Store as AutopilotStore  # noqa: E402

AUTOPILOT_DB = STATE / "autopilot.db"


def _ap_compose(name: str, brief: dict, writer: str):
    p = Persona.from_env()
    if writer == "v3":
        out = llm_writer.write(brief, p)
        return polish(out["email"], p), f"LLM writer ({out['model']})"
    raw = research(name)["emails"][writer]
    label = {"v1": "Week 10 original template (v1)", "v2": "Week 10 honest template (v2)"}[writer]
    return polish(raw, p), label


def _ap_rewrite(name: str, brief: dict, current: dict, violations: list):
    p = Persona.from_env()
    out = llm_writer.write(brief, p, None, current, violations)
    return polish(out["email"], p), out["model"]


def _ap_deliver(name: str, email: dict, judgment: dict, to: str | None):
    cfg = outbound.OutboundConfig.from_env()
    note = f"Passed the Week 11 pre-send check (Tenacious-Bench evaluator v{judgment['evaluator_version']})."
    d = outbound.deliver(f"a contact at {name}", email["subject"], email["body"], override_to=to, note=note, cfg=cfg)
    _log({"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "company": name, "composer": "autopilot",
          "subject": email["subject"], "verdict": "pass", "violations": [],
          "delivery": {k: d[k] for k in ("mode", "status", "message_id", "error", "why")} | {"routed_to": outbound.mask(d["routed_to"])}})
    return {k: d[k] for k in ("mode", "status", "message_id", "error", "why")} | {"routed_to": outbound.mask(d["routed_to"])}


def _ap_instructions(violations: list) -> str:
    return llm_writer._prompting().revision_message(violations)


_autopilot: Autopilot | None = None


def autopilot() -> Autopilot:
    global _autopilot
    if _autopilot is None:
        _autopilot = Autopilot(
            AutopilotStore(AUTOPILOT_DB),
            research=lambda name: research(name)["brief"], compose=_ap_compose, judge=send_gate.judge,
            rewrite=(_ap_rewrite if llm_writer.available() else None), instructions=_ap_instructions,
            deliver=_ap_deliver, outbound_mode=lambda: outbound.OutboundConfig.from_env().mode)
    return _autopilot


def _candidate_companies() -> list[str]:
    """Companies with real signals first (the benchmark's train briefs), then the rest of the sample."""
    held, done = _held_out_names(), autopilot().store.done_companies()
    names = []
    f = send_gate.TB_DIR / "training_data" / "week10_train_briefs.jsonl"
    if f.exists():
        names = [json.loads(l)["brief"]["prospect"] for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
    names += [str(n).strip() for n in _crunchbase()["name"]]
    return [n for n in dict.fromkeys(names) if n and n.lower() != "nan" and n.lower() not in held and n.lower() not in done]


class StartIn(BaseModel):
    writer: str = Field("v3", pattern="^v[123]$")
    count: int = Field(5, ge=1, le=50)
    companies: list[str] | None = None


@app.post("/api/autopilot/start")
def autopilot_start(body: StartIn):
    ap = autopilot()
    if body.writer == "v3" and not llm_writer.available():
        raise HTTPException(503, "LLM writer needs OPENROUTER_API_KEY")
    names = body.companies or _candidate_companies()[: body.count]
    try:
        run_id = ap.start(names[: body.count], body.writer)
    except (RuntimeError, ValueError) as e:
        raise HTTPException(409, str(e))
    return {"run_id": run_id, "companies": names[: body.count]}


@app.post("/api/autopilot/stop")
def autopilot_stop():
    autopilot().stop()
    return {"ok": True}


@app.get("/api/autopilot")
def autopilot_state():
    ap = autopilot()
    items = ap.store.items()
    counts: dict = {}
    for it in items:
        counts[it["status"]] = counts.get(it["status"], 0) + 1
    return {"running": ap.running(), "run_id": ap.run_id, "counts": counts, "items": items,
            "max_per_run": int(os.getenv("AUTOPILOT_MAX_PER_RUN", "10")), "mode": outbound.OutboundConfig.from_env().mode,
            "fixer": "LLM writer" if llm_writer.available() else None}


class ApproveIn(BaseModel):
    by: str = Field("admin", max_length=60)
    email: EmailIn | None = None      # optional admin edit; re-judged before sending
    to: str | None = Field(None, max_length=254)


@app.post("/api/autopilot/{item_id}/approve")
def autopilot_approve(item_id: str, body: ApproveIn):
    r = autopilot().approve(item_id, body.by, body.email.model_dump() if body.email else None, body.to)
    if not r["ok"]:
        raise HTTPException(409, detail=r)
    return r


class RejectIn(BaseModel):
    by: str = Field("admin", max_length=60)
    reason: str = Field("", max_length=300)


@app.post("/api/autopilot/{item_id}/reject")
def autopilot_reject(item_id: str, body: RejectIn):
    r = autopilot().reject(item_id, body.by, body.reason)
    if not r["ok"]:
        raise HTTPException(409, detail=r)
    return r


@app.get("/autopilot", include_in_schema=False)
def autopilot_page():
    return FileResponse(HERE / "static" / "autopilot.html")


app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(HERE / "static" / "index.html")


def main():
    import uvicorn
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8100)
    ap.add_argument("--host", default="127.0.0.1")
    a = ap.parse_args()
    uvicorn.run(app, host=a.host, port=a.port)


if __name__ == "__main__":
    main()
