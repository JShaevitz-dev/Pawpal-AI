"""Terminal demo of the PawPal+ care advisor (RAG) working with the scheduler.

    python advisor_demo.py            # offline: retrieval + rules only, no API key needed
    python advisor_demo.py --live     # uses Claude if ANTHROPIC_API_KEY is set (falls back to offline)

Output for the offline run is saved in assets/advisor_demo_output.txt.
"""

from __future__ import annotations

import argparse
from datetime import date

from pawpal_ai import CareAdvisor, make_llm, setup_logging
from pawpal_system import Owner, Pet, Scheduler, Task

QUESTIONS = [
    ("How often should I scoop the litter box?", "cat"),
    ("Can I use human toothpaste on my dog?", "dog"),
    ("How much Benadryl can I give my dog?", "dog"),
    ("My dog just ate a bar of chocolate", "dog"),
    ("What should I feed my parrot?", "other"),
]


def build_owner(day: date) -> Owner:
    owner = Owner("Jordan", available_minutes=50, day_start="07:00", day_end="21:00")
    mochi, luna = Pet("Mochi", "dog"), Pet("Luna", "cat")
    owner.add_pet(mochi)
    owner.add_pet(luna)
    mochi.add_task(Task("Morning walk", 30, "high", preferred_time="08:00", frequency="daily", due_date=day))
    mochi.add_task(Task("Fetch in the yard", 20, "medium", frequency="daily", due_date=day))
    luna.add_task(Task("Meds", 10, "low", preferred_time="08:00", frequency="daily", due_date=day))
    luna.add_task(Task("Feed Luna", 10, "medium", frequency="daily", due_date=day))
    luna.add_task(Task("Play session", 10, "medium", due_date=day))
    return owner


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--live", action="store_true", help="use Claude if ANTHROPIC_API_KEY is set")
    parser.add_argument("--date", type=date.fromisoformat, default=date.today(), help="plan date, YYYY-MM-DD")
    args = parser.parse_args()
    setup_logging()

    advisor = CareAdvisor(llm=make_llm() if args.live else None)
    owner = build_owner(args.date)
    scheduler = Scheduler(owner)
    print(f"Advisor mode: {advisor.mode} | {len(advisor.docs)} care guides loaded\n")

    print("=== 1. Plan as the owner entered it ===")
    plan = scheduler.build_plan(args.date)
    print(plan.to_text())

    print("\n=== 2. Care guide review (retrieved rules checked against the plan) ===")
    gaps = advisor.review_plan(plan, owner)
    for g in gaps:
        print(f"  {g.to_text()}")

    print("\n=== 3. Owner accepts the priority fixes; plan is rebuilt ===")
    for change in CareAdvisor.apply_priority_fixes(owner, gaps):
        print(f"  changed {change}")
    print(scheduler.build_plan(args.date).to_text())

    print("\n=== 4. Task suggestions for Mochi (fills the 'missing' gaps) ===")
    advice = advisor.suggest_tasks(owner.get_pet("Mochi"), note="young dog with lots of energy")
    print(advice.to_text())

    print("\n=== 5. Care questions ===")
    for question, species in QUESTIONS:
        print(advisor.answer(question, species).to_text())
        print()


if __name__ == "__main__":
    main()
