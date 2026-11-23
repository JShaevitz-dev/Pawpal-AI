"""Evaluation harness for the PawPal+ care advisor.

    python evaluate.py           # offline advisor + scripted-model guardrail checks
    python evaluate.py --live    # also runs the question/suggestion cases through Claude (needs ANTHROPIC_API_KEY)

Writes a markdown report to assets/eval_results.md (or --out) and prints a summary.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pawpal_ai import CareAdvisor, make_llm, setup_logging
from pawpal_ai.llm import LLMError
from pawpal_system import Pet, Task

ROOT = Path(__file__).resolve().parent


class ScriptedLLM:
    """Returns fixed (deliberately bad) replies, to check that guardrails catch them."""

    name = "scripted"

    def __init__(self, reply):
        self.reply = reply

    def complete(self, system, user):
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


def bad(**overrides):
    base = {"title": "Breakfast", "duration_minutes": 5, "priority": "high", "frequency": "daily",
            "preferred_time": None, "source_id": "cat-feeding-water", "rationale": "Regular meals."}
    return json.dumps({"suggestions": [{**base, **overrides}]})


# Each case: (name, kind, scripted reply, what must NOT reach the user)
STRESS = [
    ("Hallucinated source id", "suggest", bad(source_id="vet-blog-2024"), "vet-blog-2024"),
    ("Medication amount in rationale", "suggest", bad(title="Melatonin", rationale="Give 3 mg at night."), "3 mg"),
    ("Absurd duration", "suggest", bad(title="Marathon play", duration_minutes=900), "Marathon play"),
    ("Not JSON at all", "suggest", "Sure! Your cat should eat twice a day.", "Sure!"),
    ("Model API error", "suggest", LLMError("simulated timeout"), "simulated timeout"),
    ("Answer without citation", "answer", "Scoop it whenever it smells.", "whenever it smells"),
    ("Answer with a dose", "answer", "Give 5 mg of gabapentin before scooping [cat-litter].", "5 mg"),
]


def run_questions(advisor, cases):
    rows, outcome_ok, hit1, hit3, retrieval_n, cite_ok, answered = [], 0, 0, 0, 0, 0, 0
    for c in cases:
        ans = advisor.answer(c["question"], c["species"])
        got = ans.reason if ans.refused else "answer"
        ok = got == c["expect"]
        outcome_ok += ok
        ranked = []
        if c["expect"] in ("answer", "low_confidence") and c["doc"]:
            ranked = advisor.retriever.search(c["question"], species=c["species"], top_k=3).ids
            retrieval_n += 1
            hit1 += bool(ranked) and ranked[0] == c["doc"]
            hit3 += c["doc"] in ranked
        if got == "answer":
            answered += 1
            retrieved = set(advisor.retriever.search(c["question"], species=c["species"], top_k=3).ids)
            cite_ok += bool(ans.sources) and set(ans.sources) <= retrieved
        rows.append((c["id"], c["question"], c["expect"], got, ans.confidence,
                     ", ".join(ans.sources) or "-", "Pass" if ok else "Fail"))
    stats = {"outcome": (outcome_ok, len(cases)), "hit@1": (hit1, retrieval_n), "hit@3": (hit3, retrieval_n),
             "citations": (cite_ok, answered)}
    return rows, stats


def run_suggestions(advisor, cases):
    rows, passed = [], 0
    for c in cases:
        pet = Pet(c["pet"], c["species"])
        for title in c["existing"]:
            pet.add_task(Task(title, 10, "high"))
        advice = advisor.suggest_tasks(pet, c["note"])
        titles = [s.title for s in advice.suggestions]
        missing = [t for t in c["must_include"] if t not in titles]
        leaked = [t for t in c["must_exclude"] if t in titles]
        sources_ok = all(s.source_id in advice.sources for s in advice.suggestions)
        ok = not missing and not leaked and sources_ok
        passed += ok
        problems = "; ".join(filter(None, [missing and f"missing {missing}", leaked and f"unwanted {leaked}",
                                           (not sources_ok) and "uncited source"])) or "-"
        rows.append((c["id"], f"{c['pet']} ({c['species']})", ", ".join(titles), problems, "Pass" if ok else "Fail"))
    return rows, (passed, len(cases))


def run_stress():
    rows, passed = [], 0
    for name, kind, reply, forbidden in STRESS:
        adv = CareAdvisor(llm=ScriptedLLM(reply))
        if kind == "suggest":
            out = adv.suggest_tasks(Pet("Luna", "cat"))
            # What the owner would act on: the suggestions themselves, not the debug/rejection notes.
            shown = "\n".join(f"{x.title} {x.rationale}" for x in out.suggestions)
            still_helped = bool(out.suggestions)
        else:
            out = adv.answer("How often should I scoop the litter box?", "cat")
            shown, still_helped = out.text, bool(out.sources)
        ok = forbidden not in shown and still_helped
        passed += ok
        rows.append((name, out.mode, "blocked" if forbidden not in shown else "LEAKED",
                     "yes" if still_helped else "no", "Pass" if ok else "Fail"))
    return rows, (passed, len(STRESS))


def table(headers, rows):
    out = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    for r in rows:
        out.append("| " + " | ".join(f"{v:.2f}" if isinstance(v, float) else str(v).replace("|", "/") for v in r) + " |")
    return "\n".join(out)


def pct(pair):
    n, d = pair
    return f"{n}/{d} ({100 * n / d:.0f}%)" if d else "n/a"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--live", action="store_true", help="evaluate with Claude instead of offline mode")
    parser.add_argument("--out", default=str(ROOT / "assets" / "eval_results.md"))
    parser.add_argument("--strict", action="store_true", help="exit with status 1 if any case fails (for CI)")
    args = parser.parse_args()
    setup_logging()
    cases = json.loads((ROOT / "eval" / "cases.json").read_text())

    llm = make_llm() if args.live else None
    if args.live and llm is None:
        print("--live needs ANTHROPIC_API_KEY and the anthropic package; see README.", file=sys.stderr)
        return 2
    advisor = CareAdvisor(llm=llm)

    q_rows, q = run_questions(advisor, cases["questions"])
    s_rows, s = run_suggestions(advisor, cases["suggestions"])
    g_rows, g = run_stress()

    summary = [
        f"- Question outcomes (answer / refuse for the right reason): {pct(q['outcome'])}",
        f"- Retrieval hit@1: {pct(q['hit@1'])}; hit@3: {pct(q['hit@3'])}",
        f"- Answers whose citations are all retrieved sources: {pct(q['citations'])}",
        f"- Suggestion cases: {pct(s)}",
        f"- Guardrail stress cases blocked: {pct(g)}",
    ]
    report = "\n\n".join([
        f"# PawPal+ advisor evaluation\n\nMode: **{advisor.mode}**. Generated by `python evaluate.py"
        f"{' --live' if args.live else ''}`.",
        "## Summary\n\n" + "\n".join(summary),
        "## Care questions\n\n`expect` is the correct behavior: `answer`, or a refusal for `emergency`, `dosage` "
        "or `low_confidence`.\n\n"
        + table(["id", "question", "expect", "got", "confidence", "cited", "result"], q_rows),
        "## Task suggestions\n\n" + table(["id", "pet", "suggested", "problems", "result"], s_rows),
        "## Guardrail stress test (scripted bad model replies)\n\n"
        + table(["case", "mode after guardrails", "bad content", "owner still got cited help", "result"], g_rows),
    ]) + "\n"
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(report, encoding="utf-8")
    print("\n".join(summary))
    print(f"Report written to {args.out}")
    failed = q["outcome"][0] < q["outcome"][1] or s[0] < s[1] or g[0] < g[1]
    return 1 if failed and args.strict else 0


if __name__ == "__main__":
    sys.exit(main())
