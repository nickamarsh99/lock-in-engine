# lock-in-engine

## Always first: Brand Engine

Before any content generation, file modification, or scripting pipeline in
this repository, read `.claude/skills/brand-engine/SKILL.md` and follow it.
It sets where inputs live, how code and content are kept apart, and how
drafts reference the brand matrix.

If a message starts with `Update skill:`, follow section 4 of that file to
revise it.

## Layout

- `keywords.txt`: targets for the signal pipeline, one per line.
- `.claude/agents/signal_miner/`: audience-signal pipeline (`agent.py` runs it,
  `miner.py` collects, `analyzer.py` finds themes). Standard library only.
- `.claude/agents/signal-miner.md`: subagent that runs the pipeline and
  summarizes the report.
- `signals/`: dated reports (`YYYY-MM-DD.md`) and raw data (`raw/YYYY-MM-DD.json`).
- `brand/brand_matrix.md`: brand voice and positioning. Content drafts only.
- `drafts/`: content output.

## Commands

```bash
python3 .claude/agents/signal_miner/agent.py            # full pipeline -> signals/<today>.md
python3 .claude/agents/signal_miner/agent.py --limit 50 # more signals per keyword per platform
python3 .claude/agents/signal_miner/miner.py "deep work" --out raw.json  # collection only
```

The source adapters in `miner.py` are mocks for now. Reports say
`Data mode: MOCK` until real adapters (subclasses of `SourceAdapter`) are
passed to `mine()`.
