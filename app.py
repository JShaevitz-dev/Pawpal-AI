from datetime import date, time

import streamlit as st

from pawpal_ai import CareAdvisor, make_llm, setup_logging
from pawpal_system import FREQUENCIES, PRIORITY_RANK, Owner, Pet, Scheduler, Task, format_time

st.set_page_config(page_title="PawPal+", page_icon=":paw_prints:", layout="centered")

st.title(":paw_prints: PawPal+")
st.caption("Plan your pets' care for the day, within the time you actually have.")

setup_logging()


@st.cache_resource
def get_advisor() -> CareAdvisor:
    """One advisor per server process: loads the knowledge base and connects to Claude if a key is set."""
    return CareAdvisor(llm=make_llm())


try:
    advisor = get_advisor()
except (FileNotFoundError, ValueError) as e:  # missing or empty knowledge/ folder
    advisor = None
    st.error(f"Care advisor unavailable: {e}")

if "owner" not in st.session_state:
    st.session_state.owner = Owner("Jordan")
owner: Owner = st.session_state.owner
scheduler = Scheduler(owner)
PRIORITIES = list(PRIORITY_RANK)[::-1]  # low, medium, high


def to_time(hhmm: str) -> time:
    h, m = map(int, hhmm.split(":"))
    return time(h, m)


def task_label(task: Task) -> str:
    status = "[done] " if task.completed else ""
    return f"{status}{task.title} - {task.pet_name} (due {task.due_date.isoformat()})"


# --- Owner -------------------------------------------------------------------

st.subheader("1. Owner")
c1, c2 = st.columns(2)
with c1:
    owner.name = st.text_input("Owner name", value=owner.name).strip() or owner.name
    owner.available_minutes = int(
        st.number_input("Time available today (minutes)", min_value=0, max_value=1440,
                        value=owner.available_minutes, step=5)
    )
with c2:
    start = st.time_input("Day starts", value=to_time(owner.day_start), step=900)
    end = st.time_input("Day ends", value=to_time(owner.day_end), step=900)
if end <= start:
    st.error("Day end must be after day start.")
else:
    owner.day_start, owner.day_end = start.strftime("%H:%M"), end.strftime("%H:%M")

# --- Pets --------------------------------------------------------------------

st.subheader("2. Pets")
with st.form("add_pet", clear_on_submit=True):
    c1, c2 = st.columns([2, 1])
    pet_name = c1.text_input("Pet name", placeholder="Mochi")
    species = c2.selectbox("Species", ["dog", "cat", "other"])
    if st.form_submit_button("Add pet"):
        try:
            if not pet_name.strip():
                raise ValueError("Pet name cannot be blank")
            owner.add_pet(Pet(pet_name.strip(), species))
            st.success(f"Added {pet_name.strip()}.")
        except ValueError as e:
            st.error(str(e))

if owner.pets:
    st.write(", ".join(f"**{p.name}** ({p.species}, {len(p.tasks)} tasks)" for p in owner.pets))
else:
    st.info("Add a pet to start adding tasks.")

# --- Tasks -------------------------------------------------------------------

st.subheader("3. Tasks")
if owner.pets:
    with st.form("add_task", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        pet_choice = c1.selectbox("Pet", [p.name for p in owner.pets])
        title = c2.text_input("Task title", placeholder="Morning walk")
        duration = c3.number_input("Duration (minutes)", min_value=1, max_value=240, value=20)
        c1, c2, c3 = st.columns(3)
        priority = c1.selectbox("Priority", PRIORITIES, index=2)
        frequency = c2.selectbox("Repeats", FREQUENCIES)
        due = c3.date_input("Due date", value=date.today())
        fixed = st.checkbox("Needs to happen at a specific time")
        at = st.time_input("Preferred time", value=time(8, 0), step=900)
        if st.form_submit_button("Add task"):
            try:
                pet = owner.get_pet(pet_choice)
                task = Task(title, int(duration), priority,
                            preferred_time=at.strftime("%H:%M") if fixed else None,
                            frequency=frequency, due_date=due)
                if any(t.title.lower() == task.title.lower() and t.due_date == due and not t.completed
                       for t in pet.tasks):
                    raise ValueError(f"{pet.name} already has an open '{task.title}' task due that day")
                pet.add_task(task)
                st.success(f"Added '{task.title}' for {pet.name}.")
            except ValueError as e:
                st.error(str(e))

if "flash" in st.session_state:
    st.success(st.session_state.pop("flash"))
tasks = owner.all_tasks()
if tasks:
    c1, c2 = st.columns(2)
    pet_filter = c1.selectbox("Show pet", ["All"] + [p.name for p in owner.pets])
    status_filter = c2.selectbox("Show status", ["Open", "Completed", "All"])
    shown = scheduler.filter_tasks(
        pet_name=None if pet_filter == "All" else pet_filter,
        completed={"Open": False, "Completed": True, "All": None}[status_filter],
    )
    shown = Scheduler.sort_by_priority(shown)
    if shown:
        st.table([
            {"pet": t.pet_name, "task": t.title, "minutes": t.duration_minutes, "priority": t.priority,
             "time": t.preferred_time or "flexible", "repeats": t.frequency,
             "due": t.due_date.isoformat(), "done": "yes" if t.completed else ""}
            for t in shown
        ])
    else:
        st.info("No tasks match this filter.")

    with st.expander("Edit, complete, or delete a task"):
        idx = st.selectbox("Task", range(len(tasks)), format_func=lambda i: task_label(tasks[i]))
        selected = tasks[idx]
        with st.form(f"edit_{idx}"):
            c1, c2, c3 = st.columns(3)
            new_title = c1.text_input("Title", value=selected.title)
            new_duration = c2.number_input("Duration (minutes)", min_value=1, max_value=240,
                                           value=selected.duration_minutes)
            new_priority = c3.selectbox("Priority", PRIORITIES, index=PRIORITIES.index(selected.priority))
            c1, c2 = st.columns(2)
            new_frequency = c1.selectbox("Repeats", FREQUENCIES, index=FREQUENCIES.index(selected.frequency))
            new_due = c2.date_input("Due date", value=selected.due_date)
            new_fixed = st.checkbox("Needs to happen at a specific time", value=bool(selected.preferred_time))
            new_at = st.time_input("Preferred time", step=900,
                                   value=to_time(selected.preferred_time) if selected.preferred_time else time(8, 0))
            b1, b2, b3 = st.columns(3)
            save = b1.form_submit_button("Save changes")
            complete = b2.form_submit_button("Mark complete", disabled=selected.completed)
            delete = b3.form_submit_button("Delete")
        if save:
            try:
                updated = Task(new_title, int(new_duration), new_priority,
                               preferred_time=new_at.strftime("%H:%M") if new_fixed else None,
                               frequency=new_frequency, due_date=new_due, completed=selected.completed,
                               pet_name=selected.pet_name)
                vars(selected).update(vars(updated))
                st.session_state.flash = "Task updated."
                st.rerun()
            except ValueError as e:
                st.error(str(e))
        if complete:
            nxt = scheduler.complete_task(selected)
            st.session_state.flash = (f"Marked '{selected.title}' complete."
                       + (f" Next one is due {nxt.due_date.isoformat()}." if nxt else ""))
            st.rerun()
        if delete:
            owner.get_pet(selected.pet_name).remove_task(selected)
            st.session_state.flash = f"Deleted '{selected.title}'."
            st.rerun()
elif owner.pets:
    st.info("No tasks yet. Add one above.")

# --- Care advisor (RAG) -------------------------------------------------------

st.divider()
st.subheader("4. Care advisor")
if advisor is None:
    st.info("The care advisor is turned off because the knowledge base could not be loaded.")
elif not owner.pets:
    st.info("Add a pet to get care suggestions.")
else:
    st.caption(f"Answers come only from the care guides in `knowledge/`. Mode: **{advisor.mode}**. "
               "General guidance, not veterinary advice.")
    tab_suggest, tab_ask = st.tabs(["Suggest tasks", "Ask a question"])

    with tab_suggest:
        c1, c2 = st.columns([1, 2])
        advice_pet = c1.selectbox("Pet", [p.name for p in owner.pets], key="advice_pet")
        note = c2.text_input("Anything the advisor should know? (optional)",
                             placeholder="senior dog, gets tired on long walks", key="advice_note")
        if st.button("Suggest care tasks"):
            with st.spinner("Searching the care guides..."):
                st.session_state.advice = advisor.suggest_tasks(owner.get_pet(advice_pet), note)
        advice = st.session_state.get("advice")
        if advice is not None and owner.get_pet(advice.pet_name) is not None:
            st.caption(f"For {advice.pet_name} | sources: {', '.join(advice.sources) or 'none'} | "
                       f"retrieval confidence {advice.confidence:.2f} | mode: {advice.mode}")
            if advice.notes:
                st.info(advice.notes)
            if advice.suggestions:
                with st.form("accept_suggestions"):
                    picks = []
                    for sug in advice.suggestions:
                        when = sug.preferred_time or "flexible"
                        label = (f"**{sug.title}** - {sug.duration_minutes} min, {sug.priority}, {sug.frequency}, "
                                 f"{when} `[{sug.source_id}]`")
                        if st.checkbox(label, value=sug.priority == "high", key=f"sug_{advice.pet_name}_{sug.title}"):
                            picks.append(sug)
                        if sug.rationale:
                            st.caption(sug.rationale)
                    if st.form_submit_button("Add selected tasks"):
                        pet = owner.get_pet(advice.pet_name)
                        added = []
                        for sug in picks:
                            if any(t.title.lower() == sug.title.lower() and not t.completed for t in pet.tasks):
                                continue
                            pet.add_task(CareAdvisor.to_task(sug, due=date.today()))
                            added.append(sug.title)
                        st.session_state.pop("advice")
                        st.session_state.flash = (f"Added {', '.join(added)} for {pet.name}." if added
                                                  else "Nothing new to add.")
                        st.rerun()
            else:
                st.info("No new suggestions: this pet's tasks already cover what the care guides recommend.")
            for r in advice.rejected:
                st.caption(f"Guardrail removed a suggestion: {r}")

    with tab_ask:
        c1, c2 = st.columns([1, 3])
        ask_pet = c1.selectbox("About", [p.name for p in owner.pets], key="ask_pet")
        question = c2.text_input("Question", placeholder="How often should I scoop the litter box?",
                                 key="ask_q", max_chars=500)
        if st.button("Ask"):
            st.session_state.answer = advisor.answer(question, owner.get_pet(ask_pet).species)
        ans = st.session_state.get("answer")
        if ans is not None:
            if ans.reason == "emergency":
                st.error(ans.text)
            elif ans.refused:
                st.warning(ans.text)
            else:
                st.markdown(ans.text)
            st.caption(f"Sources: {', '.join(ans.sources) or 'none'} | confidence {ans.confidence:.2f} | "
                       f"mode: {ans.mode}")

# --- Schedule ----------------------------------------------------------------

st.divider()
st.subheader("5. Build schedule")
plan_day = st.date_input("Plan for", value=date.today(), key="plan_day")

if st.button("Generate schedule", type="primary"):
    st.session_state.show_plan = True

if st.session_state.get("show_plan"):
    try:
        plan = scheduler.build_plan(plan_day)
    except ValueError as e:
        st.error(str(e))
    else:
        for w in plan.warnings:
            st.warning(f"Time conflict: {w}")
        if plan.scheduled:
            st.success(
                f"Scheduled {len(plan.scheduled)} task(s), {plan.total_minutes} of "
                f"{owner.available_minutes} available minutes."
            )
            st.table([
                {"time": f"{format_time(s.start)}-{format_time(s.end)}", "pet": s.task.pet_name,
                 "task": s.task.title, "priority": s.task.priority, "why": s.reason}
                for s in plan.scheduled
            ])
        else:
            st.info("Nothing is scheduled for this day.")
        if plan.skipped:
            st.markdown("**Left out of today's plan**")
            for task, why in plan.skipped:
                st.markdown(f"- **{task.title}** ({task.pet_name}): {why}")
        with st.expander("How this plan was built"):
            st.markdown(
                """
1. Open tasks due on this day (or overdue) are sorted by priority, high to low.
   Ties go to tasks with a set time, then to shorter tasks.
2. Tasks are added in that order while they fit in your available minutes.
   A task that doesn't fit is skipped, but shorter ones after it can still get in.
3. Tasks with a set time go at that time. If two clash, the higher-priority one keeps the slot
   and the other moves to the next free gap.
4. Flexible tasks fill the earliest free gaps, starting when your day starts.
"""
            )
            st.code(plan.to_text(), language=None)

        if advisor is not None and owner.pets:
            gaps = advisor.review_plan(plan, owner)
            st.markdown("**Care guide review**")
            if not gaps:
                st.success("This plan covers the essential daily care in the care guides.")
            for g in gaps:
                label = {"missing": "Missing", "skipped": "Left out", "priority": "Priority"}[g.kind]
                st.markdown(f"- **{label} - {g.pet_name}:** {g.message} `[{g.source_id}]`")
            if any(g.kind == "priority" for g in gaps):
                if st.button("Raise flagged tasks to high priority and rebuild"):
                    changed = CareAdvisor.apply_priority_fixes(owner, gaps)
                    st.session_state.flash = "Updated: " + "; ".join(changed)
                    st.rerun()
