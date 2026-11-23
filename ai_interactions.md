# AI Interactions Log

> **Stretch features only.** Only fill in the sections that apply to stretch features you attempted. If you did not attempt a stretch feature, leave its section blank or delete it. This file is not required for the core project.

---

## Agent Workflow (SF7)

**What task did you give the agent?**

I gave Claude (as an agent) my Module 2 PawPal+ files and the final-project brief, and asked it to
extend the project into an applied AI system. I chose the feature (a RAG care advisor), the model
provider (Anthropic Claude) and the delivery (files I copy into my repo).

**What did the agent do?**

1. Ran the existing 28 tests to confirm the base project worked before changing anything.
2. Wrote 11 care guides in `knowledge/`, each with a structured `## Tasks` section.
3. Built the `pawpal_ai` package: `knowledge.py` (loader), `retriever.py` (BM25 + confidence),
   `guardrails.py` (input safety and output validation), `llm.py` (Claude client and JSON parsing),
   `advisor.py` (suggestions, answers, plan review, offline fallback) and `logging_setup.py`.
4. Ran smoke tests and fixed issues it found: stopwords checked before stemming, one task covering
   several care items, and vocabulary gaps ("bathe", "boredom").
5. Added the advisor and plan review to `app.py`, and wrote `advisor_demo.py`.
6. Wrote 60 new tests (`tests/test_advisor.py`) with a fake model, and fixed one test whose setup was wrong.
7. Wrote `evaluate.py` and `eval/cases.json`, ran them, found and fixed the "ate a bar of chocolate"
   emergency bug, and corrected a stress-test check that reported a false leak.
8. Ran `app.py` against a scripted stand-in for Streamlit to exercise the UI flow, because Streamlit
   wasn't installed in its environment.
9. Wrote `diagrams/architecture.mmd`, the README and a draft model card, and captured all outputs in `assets/`.

**What did you have to verify or fix manually?**

<!-- Fill in after you run it yourself. Things worth checking and noting here:
     - `streamlit run app.py` works in a real browser (the agent could only use a stand-in)
     - `python evaluate.py --live` with your ANTHROPIC_API_KEY, since the agent couldn't reach the API
     - the Mermaid diagram renders on GitHub / in the Mermaid Live Editor
     - the care-guide content reads as sensible to you
     - anything you changed in wording, scope or behavior -->

---
