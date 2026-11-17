# MIRAH + The Oracle — scope (draft for review)

Status: **draft. Architecture decided by Nigel on 20 October 2026** (see §10 "Decisions" and [ARCHITECTURE.md](ARCHITECTURE.md)); feature phasing and NYUAD approvals not yet agreed. Two layers:

- **Base: The Oracle.** From the Lab lead's *The Oracle — Living LLM Toolkit: Working Development Scope for Review* (sections 1–9 below).
- **Expansion: MIRAH.** Nigel has expanded the base scope beyond the Lab lead's document (section 10), drawing on the MIRAH architecture blueprint, the 16 October on-premises specification and the 20 October hosting proposal.

Items marked **[Proposed]** are additions for discussion. The server and hosting choice is decided: the model runs on NYUAD servers (see [ARCHITECTURE.md](ARCHITECTURE.md)).

## 1. What The Oracle is

A **post-Lab AI knowledge environment** for NYU Abu Dhabi. It brings together selected knowledge generated through Hack the Future Lab (methodology, contributor thinking, participant artefacts, reflections and emerging patterns) and makes it interactive after the three-day programme, so NYUAD can revisit, question, connect and keep developing that intelligence instead of filing a report.

**Expanded (Nigel, 20 October 2026):** used before, during and after the Lab, by NYUAD staff, to capture data. See §10.

Purpose: make the Lab's collective intelligence accessible, searchable and useful over time for strategy, research, teaching, collaboration and future Labs.

It is **not** the five-question Welcome / discovery demo. The MIRAH guided journey that runs inside it is Nigel's expansion, described in section 10.

## 2. What the LLM is supposed to do

The experience moves users from perception to agency: from encounter and inquiry toward reframing, development and action.

| Stage | Source definition | What the LLM does **[Proposed detail]** |
| --- | --- | --- |
| **INSPIRE** | Encounter provocations, alternative knowledge, methodologies and perspectives from the Lab | Surfaces relevant provocations, methods and perspectives from the library with citations; offers contrasting viewpoints rather than one answer |
| **IMAGINE** | Question assumptions, identify patterns, connect ideas, explore alternative futures | Asks reflective and critical questions; links ideas across sessions, contributors and artefacts; names recurring patterns and tensions; drafts alternative future scenarios, labelled as speculative |
| **ACTIVATE** | Develop insights into actions, prototypes, recommendations, collaborations or future lines of inquiry | Turns a chosen idea into a structured next step (action, prototype outline, recommendation, collaboration or inquiry question) grounded in cited Lab material |

Functions required by the source document:

1. Move through Lab intelligence from questioning and reflection toward ideas, decisions and action.
2. Answer questions across Lab material.
3. Retrieve ideas, themes and recommendations.
4. Identify connections between sessions, contributors and participant artefacts.
5. Surface recurring patterns, tensions and opportunities.
6. Revisit and continue developing future scenarios and ideas.
7. Use reflective or critical questioning rather than simple summaries.

Optional, to explore in the prototype: LLM **modes**: facilitation, reflective questioning, critical inquiry, pattern recognition.

### What the LLM must not do **[Proposed]**

Drawn from safeguards in earlier Lab and MIRAH documents; to be confirmed.

- Answer from outside the approved library without saying so. Every factual claim cites its source; speculation is labelled.
- Profile, diagnose or rank people, or infer sensitive traits.
- Reveal material a user's access level does not permit, including private reflections.
- Take autonomous external actions (publishing, sending, committing on NYUAD's behalf).
- Add its own outputs to the trusted library without human approval.
- Replace facilitators or the Lab lead's interpretation.

## 3. Content

| Content (source list) | Sensitivity **[Proposed]** | Prototype default **[Proposed]** |
| --- | --- | --- |
| Lab methodology and process | Low | Include |
| Contributor provocations and session summaries | Low–medium (contributor consent to reuse) | Include once contributors agree |
| Key themes, tensions and recurring patterns | Low (derived) | Include |
| Agreed actions and recommendations | Medium (institutional) | Include if NYUAD agrees |
| Miro and workshop outputs | Medium | Include curated, de-identified selection |
| Participant artefacts and future concepts | Medium–high | Only with participant consent |
| Reflections and evaluation insights | High | Exclude until consent and access rules are agreed |
| Selected transcripts or recordings | High | Exclude from prototype; source says only "where appropriate and consented" |

## 4. Users

NYUAD leadership; Arts & Humanities faculty and staff; Lab participants; facilitators and contributors; future Lab or research teams. Access levels to be agreed with NYUAD.

**Decided (Nigel, 20 October 2026):** users are NYUAD staff. See §10 for the open point on non-staff Lab participants whose input is captured.

## 5. Prototype — in and out **[Proposed]**

**In:** sign-in with role-based access; curated library of agreed material; question answering with citations; Inspire–Imagine–Activate journey; at least two modes (reflective questioning, pattern recognition); save and export a user's own work; delete own work; admin upload and approval of library material; short user guide (purpose, access, limitations, future development), as the source requires.

**Out of the base prototype:** transcripts and recordings until consented. Items listed in section 10 (MIRAH journey, learning, external services, facilitator tools, voice, Arabic) are part of Nigel's expansion and are phased there.

## 6. Development approach (source)

1. Agree priority users and use cases.
2. Agree what material can be included.
3. Structure the knowledge base.
4. Build the LLM interface and retrieval system.
5. Test interaction modes and the Inspire–Imagine–Activate journey.
6. Review with NYUAD.
7. Refine and hand over the prototype.

Indicative timing in the source: about **one week to build and one week to test, once scope and data parameters are agreed.** Agreement of steps 1–2 is therefore the critical path.

## 7. Acceptance checks **[Proposed]**

- Answers cite library sources; unsupported claims are refused or labelled.
- A user cannot retrieve material above their access level (tested per role).
- Each journey stage produces its intended output on a set of synthetic test questions agreed with the Lab lead.
- Prompt-injection and restricted-content tests pass.
- Export and deletion of a user's own work work end to end.
- Works in current Chrome, Safari, Edge and Firefox; keyboard and screen-reader basics.
- User guide delivered.

## 8. Decisions NYUAD must make, and how each affects the server

The source lists these as areas requiring NYUAD review. The server decision follows from the answers.

| NYUAD decision (source) | Why it matters for the server |
| --- | --- |
| Primary use case | Sets expected users and load |
| Users and access levels | Sets identity and role design (SSO) |
| Data inclusion | High-sensitivity material raises the hosting bar |
| Participant consent | Decides whether artefacts and reflections can be used at all |
| **Privacy and external LLM use** | **Decided:** the model runs locally on NYUAD GPU servers. Claude, OpenAI and Perplexity are a switchable feature; NYUAD decides whether and when each may be switched on in production. |
| **Data hosting** | Where the library and saved work live; university-hosted in all current proposals |
| Ownership and retention | Sets backup, deletion and retention design |
| Future updating and maintenance | Decides who curates and operates it after handover |
| Export and reuse of material | Sets export features and licence terms |

**[Proposed] Load note:** because the system is used during the Lab as well as before and after it, peak load is the live workshop: the 16 October spec sizes for 20 concurrent users plus 50% headroom (a burst of about 90 model requests). Confirm the expected numbers with NYUAD, because they set the GPU hardware.

## 9. Open questions for Nigel and the Lab lead

1. When does the Lab run? Capture before, during and after depends on the dates. Until Lab material exists, the library starts with methodology, provocations and synthetic examples.
2. How does MIRAH relate to The Oracle for this prototype: a later layer, or out of scope?
3. Final arc wording: Inspire–Imagine–**Activate** (this document) or Inspire–Imagine–**Return** (programme and decks)?
4. Is 20 November a fixed date, given the source's build clock starts only after scope and data are agreed?
5. Who are the named product owner, curator and NYUAD service owner?

The scope should remain flexible until NYUAD has agreed the key privacy, ownership and institutional-use questions (source).

## 10. Nigel's expansion — MIRAH

Beyond the Lab lead's base scope, the system includes **MIRAH** (Arabic for "mirror"): the perception-to-agency guide. **The Oracle is the brain that powers MIRAH**: the knowledge library, retrieval and model layer. MIRAH is the guided experience users interact with. HTFL is the experience; MIRAH is the mechanism; The Oracle is the brain. The expansion changes the base scope's timing and users: it is used **before, during and after the Lab, by NYUAD staff**, to capture data. Phasing below is **[Proposed]**; Nigel to confirm each line.

| Expansion | Source | Proposed phase |
| --- | --- | --- |
| Nine-stage guided journey with an artefact per stage: Mirror → Current Lens; Disrupt → Assumption Break; Connect → Pattern Map; Reframe → Reframed Opportunities; Imagine → Future Branches; Become → Agency Statement (opt-in, private by default); Build → Opportunity Canvas; Experiment → Seven-Day Experiment; Reflect → Learning Record. Socratic, one question at a time; participant can edit, reject, revisit or skip | Blueprint | Go-live (core stages), rest after |
| Modes: Guided Journey (25–45 min), Fast Pass (10 min), Workshop Room (facilitator-led), Return and Reflect, Curator Preview | Blueprint | Guided Journey at go-live; others after |
| Truth labels on every claim: Evidence, Inference, Hypothesis, Creative provocation | Blueprint, decks | Go-live |
| Orchestrator over specialist agents (Lens Reader, Frame Breaker, Pattern Weaver, Future Worldbuilder, Power & Bias Guardian, Research-to-Value Translator, Experiment Architect, Evidence Verifier) with schema and evidence checks before any reply | Blueprint | Go-live in simplified form |
| Library learning: curator-approved contributions become searchable immediately | 16 Oct spec | Go-live |
| Adapter training on consented, de-identified, reviewed examples every 4 weeks, with release tests and rollback | 16 Oct spec | After go-live (needs ≥ 500 approved examples, Legal/privacy/IRB approval) |
| External services (Perplexity research, Claude, OpenAI) through one university gateway with user approval of outbound text and a kill switch | 16 Oct spec, 20 Oct proposal | When contracts and Legal approval are in place |
| Facilitator console (progress and shared artefacts only, never private reflections), team and room sharing | Blueprint | After go-live |
| MIR'AH Index: six dimensions scored 0–4 on the proposal, never the person | Blueprint | After go-live |
| Voice | Spec, proposal | Separate approved workstream |
| Arabic RTL interface | Blueprint, spec | English first, RTL-ready layout; Arabic later |

### Decisions — Nigel, 20 October 2026

1. **Where the model runs:** on NYUAD servers. The 20 October API-first hosting proposal is superseded.
2. **Development:** on a separate developer server with dummy data only.
3. **External services:** Claude, OpenAI and Perplexity are a controlled feature that can be switched on or off; production use needs contracts and Legal approval first.
4. **Training:** The Oracle trains on local input with guardrails. Legal, privacy and (for research use) IRB approval are still required before any training run.
5. **Users and timing:** NYUAD staff; before, during and after the Lab.
6. **Go-live:** 20 November 2026.

### Still open

1. **Lab participants who are not staff.** If their input is captured during the Lab and used for training, they need consent and opt-out, even if they never sign in. Otherwise, training input is limited to staff.
2. **Training at go-live.** Adapter training needs approved local input first (the 16 October spec sets at least 500 examples). At go-live, learning is through the library; the first adapter release follows.
3. **Lab dates.** "Before the Lab" capture requires knowing when the Lab runs.
4. **NYUAD hardware.** Go-live depends on GPU servers being delivered and installed by about 7 November. Fallback to agree: a borrowed NYUAD GPU server.
5. **Timeline.** The full expansion does not fit by 20 November; the go-live column above is the most that fits and needs Nigel's confirmation.
6. **Superseded proposal.** If the 20 October API-first proposal was shared with NYUAD IT, they need to be told it is replaced.
