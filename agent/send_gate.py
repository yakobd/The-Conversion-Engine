"""
Pre-send gate: the Week 11 Tenacious-Bench evaluator judges every email before it can be sent.

The evaluator is imported from the sibling repository (TB_DIR, default ../The_Sales_Agent_Evaluation_Bench)
unchanged: the frozen scoring_evaluator.py that produced the published results. Each email is judged
exactly the way the benchmark judged Week 10's composer (same task construction as
generation_scripts/eval_week10_composer.py), so a pass here means the same thing as a pass there.

    judge(brief, email)  -> {"all_pass", "checks", "violations", "evaluator_version"}
    allowed(judgment)    -> True only if every dimension passes

The gate is enforced server-side in the send path: a client cannot skip it.
"""
from __future__ import annotations

import importlib
import os
import sys
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TB_DIR = Path(os.getenv("TB_DIR") or (ROOT.parent / "The_Sales_Agent_Evaluation_Bench")).resolve()
# Same bench the benchmark used when it scored the Week 10 composer (eval_week10_composer.BENCH)
BENCH = {"total_engineers": 60, "available": 34, "stacks": {"python": 12, "node": 8, "ml": 6, "go": 4, "data": 4}}


class EvaluatorUnavailable(RuntimeError):
    pass


@lru_cache(maxsize=1)
def evaluator():
    if not (TB_DIR / "scoring_evaluator.py").exists():
        raise EvaluatorUnavailable(f"Week 11 evaluator not found at {TB_DIR} (set TB_DIR)")
    if str(TB_DIR) not in sys.path:
        sys.path.insert(0, str(TB_DIR))
    return importlib.import_module("scoring_evaluator")


def task_for(brief: dict, email_type: str = "cold") -> dict:
    """The Tenacious-Bench task for one outgoing email (mirrors eval_week10_composer.task_for)."""
    return {"task_id": brief.get("prospect", "live"), "input": {"hiring_signal_brief": brief, "bench_summary": BENCH,
            "email_type": email_type, "prior_thread": [], "instruction": ""},
            "ground_truth": {"required_signals": [], "forbidden_phrases": [], "max_subject_length": 60, "must_end_with_cta": True}}


def judge(brief: dict, email: dict, email_type: str = "cold") -> dict:
    E = evaluator()
    r = E.score_task(task_for(brief, email_type), {"subject": email.get("subject", ""), "body": email.get("body", "")})
    return {"all_pass": r["all_pass"], "evaluator_version": E.VERSION, "partial_score": r["partial_score"],
            "checks": {d: {"pass": r["checks"][d]["pass"], "violations": r["checks"][d]["violations"]} for d in E.DIMENSIONS},
            "violations": [{"dimension": v["dimension"], "code": v["code"], "evidence": v["evidence"]} for v in r["violations"]]}


def allowed(judgment: dict) -> bool:
    return bool(judgment.get("all_pass"))
