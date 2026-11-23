# Model Card: PawPal+ Care Advisor

<!-- Draft written with AI help from the project's real history. Before submitting, read every section,
     check it against your own experience, and rewrite the "AI collaboration" part in your own voice. -->

## Model details

| | |
|---|---|
| System | PawPal+ Care Advisor, a retrieval-augmented advisor attached to the PawPal+ daily care scheduler |
| Base project | PawPal+ (Module 2): a priority- and time-budget-based pet care scheduler with a Streamlit UI |
| Language model | Anthropic Claude through the `anthropic` SDK (default `claude-haiku-5-5`, set with `PAWPAL_MODEL`), temperature 0. Optional. |
| Offline mode | No model. Suggestions come from the care guides' task lists and answers are extracted from guide sentences. Used when there is no API key or the model's output fails validation. |
| Retrieval | BM25 keyword search over 11 markdown care guides in `knowledge/`, filtered by species |
| No training | No model was trained or fine-tuned. Behavior comes from the retrieved guides, prompts and rule-based guardrails. |

## Intended use

- **For:** pet owners planning routine daily care for dogs, cats and small pets, including finding care
  they've forgotten, setting sensible priorities, and answering general care questions with a source.
- **Not for:** diagnosing illness, emergencies, medication doses, breed- or condition-specific medical
  advice, or any animal not covered by the guides. The app says so and points the user to a vet.

## Data

The knowledge base is 11 short guides written for this project from widely published general pet-care
guidance: feeding, water, exercise, litter, grooming, enrichment, medication safety, emergencies and
routine planning. **No veterinarian reviewed them.** They hold general rules of thumb such as "most
adult dogs do well on two meals a day", not individual advice. No user data leaves the app except the
question, the pet's species, its task titles and the owner's note, which are sent to the Claude API
when a key is configured.

## How it makes decisions

1. Sanitize the input (control characters, length cap).
2. Safety check. Emergency wording such as poisoning, seizures or "ate chocolate", and dose requests
   ("how much" plus a medicine word), get a fixed response telling the user to contact their vet. These
   never reach retrieval or the model.
3. Retrieve the top guides for the pet's species. Confidence is the IDF-weighted share of the question's
   words found in the top guide. Below 0.5 the advisor declines.
4. Generate with Claude, which is given only the retrieved guides and must cite them, or with the
   offline generator.
5. Validate every output. A suggestion needs valid fields, must cite a source it was actually given,
   must not mention a medication amount, and must not duplicate an existing task. An answer must cite a
   retrieved source and must not mention a dose. If validation fails, the advisor falls back to offline mode.
6. The owner decides which suggestions to add and whether to apply the plan review's priority fixes.

## Evaluation results

From `python evaluate.py` in offline mode (full report: `assets/eval_results.md`) and `python -m pytest`:

| Check | Result |
|---|---|
| Automated tests (scheduler + advisor) | 88/88 pass |
| Care questions answered or refused correctly | 20/21 (95%) |
| Retrieval hit@1 on questions with a known source | 14/14 (100%) |
| Answers citing only retrieved sources | 13/13 (100%) |
| Task suggestion cases | 4/4 |
| Scripted bad model replies blocked (hallucinated source, dose, absurd duration, non-JSON, API error, uncited answer, dose in answer) | 7/7 |

Live Claude output has **not** been evaluated yet; the development environment had no API access.
Claude mode is covered by fake-model tests and by the guardrails, which treat its output as untrusted.
`python evaluate.py --live` produces that report.

## Limitations and biases

- **Coverage bias.** Dogs and cats have three or four guides each; every other species shares one
  "small pets" guide. A rabbit owner gets thinner advice, and a bird or reptile owner gets refusals. The
  guides also assume indoor cats and typical adult animals; puppies, seniors, working dogs and pets with
  medical conditions get the same generic advice.
- **One author's choices.** What counts as "essential", "high priority" or a 30-minute walk reflects the
  guides as written, not a veterinary standard. The plan review enforces those choices, so it can nag
  about a reasonable routine that differs from them.
- **Keyword retrieval misses synonyms.** "Prioritize" doesn't match "priority", so a fair question was
  refused (eval Q11). The confidence score measures word overlap, not whether the answer is true.
- **Rule-based safety checks can miss or over-trigger.** The emergency check missed "ate a bar of
  chocolate" until it was fixed, and it could miss other phrasings. The dose rule refuses "I missed a dose,
  what now?" even though the safe answer ("call your vet; don't double the dose") is in the guides.
- **Offline answers are extractive.** A sentence pulled out of a paragraph can lose its context; for
  example, "...sit at the top of that range" without the sentence that defines the range.
- **English only**, and the guides have not been reviewed for accuracy by a professional.

## Misuse and how it is limited

- **Seeking dangerous medical advice** (doses, human medicines): blocked before the model, with a vet
  referral, and dose amounts are filtered out of any model output.
- **Prompt injection through the owner's note or question:** owner text is wrapped in tags the system
  prompt marks as data. The model can only cite sources it was given, and every suggestion is validated
  as structured data, so injected text can't add tasks from outside the guides. Off-topic instructions
  ("ignore previous instructions...") score 0 retrieval confidence and are refused.
- **Over-reliance:** every answer shows its source and confidence, the UI states that the guidance is
  general and not veterinary advice, and nothing changes the schedule without the owner's click.

## Testing surprises

- The demo looked correct before the evaluation set exposed the chocolate-phrasing bug in the
  emergency check. That kind of bug only shows up with varied, realistic test inputs.
- Retrieval was more accurate than the confidence score suggested. On Q11 the right guide ranked first,
  but the answer was refused because of the vocabulary mismatch. Ranking and "should we answer" are
  separate problems.
- The first version of the stress test reported a leak that wasn't one: the error message appeared in
  the debug "mode" line, not in the advice. Defining exactly what counts as reaching the user mattered
  as much as the guardrail itself.

## AI collaboration

**How AI was used.** I used Claude as a coding agent to extend the project: to propose the RAG design,
write the knowledge base, the `pawpal_ai` package, the tests and the evaluation harness, and to run the
demo and tests after each change. I chose the feature (RAG care advisor rather than an agentic planner or
both), the model provider (Claude) and the scope, and I reviewed the outputs.

**A helpful suggestion I accepted.** Making offline mode a complete mode, rather than an error message,
and testing Claude mode with a scripted fake model. That made the system reproducible without an API
key, and it gave the guardrails a concrete job: any model output that fails validation is replaced by
cited, offline advice. The guardrail stress test grew out of this.

**A flawed suggestion I revised.** The AI's first version of the emergency check only matched patterns
like "ate chocolate" or "ate a chocolate". Running the demo with "My dog just ate a bar of chocolate"
returned a normal answer about toxins instead of the emergency response. The pattern was widened to
allow words between the verb and the substance, and an evaluation case was added so it stays fixed.
Similarly, the first suggestion logic let one existing "Feeding" task hide both the Breakfast and Dinner
suggestions. It looked plausible in the output and was only caught by checking the result against what
a dog actually needs.

<!-- Add your own example here if you rejected or changed something yourself, e.g. a design choice,
     wording in the UI, or something you decided was out of scope. -->
