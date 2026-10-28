---
name: brand-engine
description: Permanent operating constraints for the lock-in-engine repository. Load BEFORE any content generation (copy, hooks, posts, scripts, emails, outlines), any file modification, or any scripting/data pipeline work in this repo, and whenever the user types "Update skill:". Defines where content inputs live (signals/), the code-to-content isolation rule, the brand matrix reference, and the self-update protocol.
---

# Brand Engine: Portable Capability Pack

**Version:** 1.0.0 · **Last updated:** 2026-10-28

This pack is the long-term frame for every task in this repository. It decides
*where inputs come from*, *which rules apply to which kind of output*, and *how
the pack itself improves over time*. It holds no brand voice; voice lives in
the brand matrix (section 3).

Precedence: the user's explicit instruction in the current turn > this pack >
default behavior. If a turn's instruction conflicts with this pack, follow the
instruction and mention the conflict in one line.

---

## 1. System behaviors

1. **Read first.** Before starting any content generation, file modification,
   or scripting pipeline, read this file in full. Don't work from memory of an
   earlier version; it may have been updated.
2. **Classify the task** before acting, and state the class in one short line
   (e.g. `Mode: CODE`):
   - **CODE**: scripts, agents, analyzers, configs, tests, tooling.
   - **DATA**: running pipelines, producing or transforming raw data and reports.
   - **CONTENT**: anything an audience will read: drafts, hooks, posts,
     scripts, emails, landing copy, outlines.
   - **MIXED**: contains more than one of the above. Split it and apply each
     zone's rules to its own part (section 3).
3. **Check inputs** using the lookup order in section 2 before generating
   anything that relies on audience knowledge.
4. **Never fabricate audience evidence.** Quotes, statistics, pain points and
   phrasing presented as coming from the audience must trace back to a file in
   `signals/`. If no signal supports a claim, say so instead of inventing one.

---

## 2. Memory architecture

Fixed locations. Look here first, write here only.

| Purpose | Path | Rules |
|---|---|---|
| Seed keywords / competitors | `keywords.txt` | One per line, `#` comments. Edit only when asked. |
| Signal reports | `signals/YYYY-MM-DD.md` | Primary content input. Newest first. Never edit by hand. |
| Raw signal data | `signals/raw/YYYY-MM-DD.json` | Source of truth for verbatim quotes. Read-only. |
| Signal pipeline | `.claude/agents/signal_miner/` | `agent.py` (run), `miner.py` (collect), `analyzer.py` (themes). |
| Signal subagent | `.claude/agents/signal-miner.md` | Delegate signal refreshes to it. |
| Brand matrix | `brand/brand_matrix.md` | The only source of voice, tone, vocabulary rules and offers. |
| Content drafts | `drafts/YYYY-MM-DD_<slug>.md` | All CONTENT output goes here unless the user names a path. |
| This pack | `.claude/skills/brand-engine/SKILL.md` | Changed only through section 4. |

**Lookup order for content inputs:**

1. Material the user supplies in the current turn.
2. The newest report in `signals/` (by filename date).
3. The matching `signals/raw/*.json` to verify or extend a verbatim quote.
4. Older reports in `signals/`, to spot trends (a theme rising or fading).

**Freshness:** If the newest report is more than 14 days old, or the task's
topic isn't among its keywords, say so and offer to refresh with
`python3 .claude/agents/signal_miner/agent.py` (after updating `keywords.txt`
if needed). Don't block on it unless the user wants fresh data.

**Mock data:** A report whose header says `Data mode: MOCK` is simulated. It can
be used to test formats and flows, but its quotes must never be presented as
real customer evidence. Label any draft built on it `[MOCK SIGNALS]`.

**Empty signals/:** Don't invent audience data. Offer to run the pipeline, or
ask the user for source material.

---

## 3. Code-to-content isolation

Two zones with opposite rules. Every file belongs to exactly one.

### Objective zone: CODE and DATA

Covers `.claude/agents/**`, all scripts and analyzers, `signals/**`, raw data
formats and schemas, configs, tests, code comments, commit messages.

- Neutral, descriptive, factual. No brand voice, no persuasion, no slogans.
- No brand names, taglines, offers or tone rules hardcoded into code, prompts
  embedded in code, or data schemas.
- Code **never reads** `brand/brand_matrix.md`. Pipelines output raw audience
  signals only, so the same engine works under any brand.
- Reports record what the audience said, in their words. Don't rewrite
  signals to sound on-brand, and never edit a generated report to fit a draft.

### Styled zone: CONTENT

Covers `drafts/**` and any output an audience will read.

- **Read `brand/brand_matrix.md` before writing.** Voice, tone, vocabulary,
  banned words, positioning and offers come only from that file, never from
  this pack and never from your own defaults.
- If the matrix is missing or still says `status: TEMPLATE`, stop and ask the
  user to fill it in. Only produce copy without it if the user explicitly
  asks, and then label the draft `[UNSTYLED: brand matrix not applied]`.
- Every draft starts with a provenance header:
  ```
  ---
  brand_matrix: brand/brand_matrix.md (as of <date or commit>)
  signals: signals/<file>.md [+ others]
  themes_used: <pain/desire themes from the report>
  ---
  ```
- Verbatim audience quotes keep their exact wording when shown as quotes. You
  may choose which quotes to use; you may not edit them.
- Hook frames in signal reports are raw material. Style them with the matrix;
  don't publish them as-is.

### Mixed tasks

Do the objective part first and keep it objective (e.g. add a new keyword and
re-run the pipeline), then do the content part as a separate step under the
styled-zone rules. Don't let one zone's rules leak into the other's files.

---

## 4. Continuous improvement loop

**Trigger:** a user message starting with `Update skill:` (any capitalization),
followed by feedback.

**Protocol:**

1. **Map** the feedback to the section(s) it affects. If it's about voice,
   tone, wording or offers, it belongs in `brand/brand_matrix.md`, not here:
   say so and offer to edit the matrix instead.
2. **Edit this file in place.** Merge the feedback into the existing rule it
   refines rather than appending a contradicting rule. Remove anything the new
   rule makes obsolete. Keep the section numbering and the frontmatter intact.
   Update the frontmatter `description` if the trigger conditions changed.
3. **Ambiguity:** if the feedback could reasonably mean two different rules,
   ask one clarifying question before editing.
4. **Core rules:** removing or weakening the read-first rule (1.1), the
   no-fabrication rule (1.4), or the isolation boundary (section 3) requires
   the feedback to say so explicitly. If it only implies it, confirm first.
5. **Version bump:** patch (`1.0.x`) for wording or clarification, minor
   (`1.x.0`) for a new or changed rule, major (`x.0.0`) for removing or
   reversing a core rule. Update **Last updated**.
6. **Log** the change in section 5: version, date, one-line summary, and the
   user's feedback quoted.
7. **Report back** in a few lines: what changed, which sections, new version.
   Then follow the updated pack from the next action on.

---

## 5. Changelog

| Version | Date | Change | Feedback |
|---|---|---|---|
| 1.0.0 | 2026-10-28 | Initial pack: system behaviors, memory architecture, code-to-content isolation, improvement loop. | n/a |
