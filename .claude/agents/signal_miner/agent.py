#!/usr/bin/env python3
"""Signal Miner agent: keywords.txt -> raw signals -> thematic analysis -> report.

One command runs the whole pipeline from the project root:

    python3 .claude/agents/signal_miner/agent.py

Steps:
  1. Read keywords / competitor names from keywords.txt (one per line, # comments).
  2. Mine Reddit, X and Amazon for raw feedback via miner.py.
  3. Analyse the raw text for bleeding-neck problems, desired transformations,
     audience vocabulary and hook frames via analyzer.py.
  4. Write signals/YYYY-MM-DD.md (report) and signals/raw/YYYY-MM-DD.json (raw data).

Output is deliberately unstyled: it records what the audience said, not how a
brand would say it back.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from analyzer import Analysis, Evidence, Quote, ThemeResult, analyze  # noqa: E402
from miner import MiningRun, Platform, default_adapters, mine  # noqa: E402


def find_project_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / ".git").exists() or (candidate / "keywords.txt").exists():
            return candidate
    return start


def read_keywords(path: Path) -> list[str]:
    if not path.is_file():
        raise FileNotFoundError(f"{path} not found. Create it with one keyword or competitor name per line.")
    keywords: list[str] = []
    seen: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        keyword = line.split("#", 1)[0].strip()
        if keyword and keyword.lower() not in seen:
            seen.add(keyword.lower())
            keywords.append(keyword)
    if not keywords:
        raise ValueError(f"{path} has no keywords (blank lines and # comments are ignored).")
    return keywords


# --------------------------------------------------------------------------- #
# Report rendering
# --------------------------------------------------------------------------- #

PLATFORM_LABELS = {Platform.REDDIT.value: "Reddit", Platform.X.value: "X", Platform.AMAZON.value: "Amazon"}


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def _source(e: Evidence) -> str:
    s = e.signal
    parts = [PLATFORM_LABELS[s.platform.value]]
    if s.platform is Platform.REDDIT:
        parts.append(f"{s.context.get('subreddit', '')} ({s.context.get('listing', '')}), {s.engagement} upvotes")
    elif s.platform is Platform.X:
        parts.append(f"{s.engagement} likes+reposts")
    else:
        parts.append(f"{s.rating}★ on \"{s.context.get('product', '')}\", {s.engagement} helpful")
    parts.append(f"kw: {s.keyword}")
    return " · ".join(parts)


def _quote_line(q: Quote) -> str:
    repeat = f" **(×{q.repeats})**" if q.repeats > 1 else ""
    return f"> \"{q.text}\"{repeat}  \n> — {_source(q.best)} · [link]({q.best.signal.url})"


def _theme_table(themes: list[ThemeResult]) -> list[str]:
    lines = [
        "| # | Theme | Tier | Score | Mentions | Avg intensity | Engagement | Platforms |",
        "|---|---|---|---:|---:|---:|---:|---|",
    ]
    for i, t in enumerate(themes, 1):
        platforms = ", ".join(PLATFORM_LABELS[p] for p in t.platforms)
        lines.append(
            f"| {i} | {_cell(t.label)} | {t.tier} | {t.score:.0f} | {t.mentions} | "
            f"{t.avg_intensity:.1f} | {t.total_engagement:,} | {platforms} |"
        )
    return lines


def _theme_details(themes: list[ThemeResult], limit: int) -> list[str]:
    lines: list[str] = []
    for i, t in enumerate(themes[:limit], 1):
        top_keywords = ", ".join(f"{k} ({n})" for k, n in t.keywords.most_common(3))
        lines += [
            f"### {i}. {t.label} — {t.tier}",
            "",
            f"Score {t.score:.0f}/100 · {t.mentions} mentions · avg intensity {t.avg_intensity:.1f}/5 · "
            f"strongest for: {top_keywords}",
            "",
        ]
        for q in t.quotes(3):
            lines += [_quote_line(q), ""]
    return lines


def render_report(run: MiningRun, analysis: Analysis, report_date: date, raw_path: str) -> str:
    counts = {p.value: len(s) for p, s in run.by_platform().items()}
    mode = "MOCK" if run.is_mock else "LIVE"
    out: list[str] = [
        f"# Audience Signals — {report_date.isoformat()}",
        "",
        f"- **Run:** `{run.run_id}` · {run.started_at.strftime('%Y-%m-%d %H:%M UTC')}",
        f"- **Data mode:** {mode} ({', '.join(f'{PLATFORM_LABELS[p]}={m}' for p, m in run.sources.items())})",
        f"- **Keywords:** {', '.join(run.keywords)}",
        f"- **Signals:** {len(run.signals)} "
        f"({', '.join(f'{PLATFORM_LABELS[p]} {n}' for p, n in counts.items())}) · "
        f"{analysis.sentences} sentences, {analysis.sentences - analysis.unclassified} matched a theme",
        f"- **Raw data:** `{raw_path}`",
        "",
    ]
    if run.is_mock:
        out += [
            "> [!WARNING]",
            "> This report was generated from **simulated** data. Quotes, handles and links are mock records,",
            "> not real customer evidence. Replace the mock adapters in `miner.py` before using it for decisions.",
            "",
        ]
    if run.errors:
        out += ["> [!NOTE]", "> Some sources failed and are missing from this report:"]
        out += [f"> - {PLATFORM_LABELS[e.platform.value]} / {e.keyword}: {e.message}" for e in run.errors]
        out.append("")

    out += ["## 1. Bleeding-neck problems", "",
            "Pain themes ranked by frequency × emotional intensity × engagement × cross-platform spread. "
            "BLEEDING NECK = score ≥ 60 and seen on 2+ platforms.", ""]
    out += _theme_table(analysis.pains) + [""]
    out += _theme_details(analysis.pains, 5)

    out += ["## 2. Desired transformations", "",
            "What people say they want, or say they got from products that worked (4–5★ reviews, success posts).", ""]
    out += _theme_table(analysis.desires) + [""]
    out += _theme_details(analysis.desires, 5)

    out += ["## 3. Audience vocabulary", "",
            "Recurring phrases (2–4 words), counted once per signal. Use these exact words; don't paraphrase them.", "",
            "| Phrase | Signals | Platforms |", "|---|---:|---|"]
    out += [
        f"| {_cell(p.text)} | {p.count} | {', '.join(PLATFORM_LABELS[x] for x in p.platforms)} |"
        for p in analysis.vocabulary
    ]
    intensifiers = ", ".join(f"{w} ({n})" for w, n in analysis.emotional_words.most_common(12))
    out += ["", f"**Emotional intensifiers used:** {intensifiers or 'none'}", ""]

    out += ["### Most-repeated verbatim lines", ""]
    out += [f"{i}. \"{q.text}\" — ×{q.repeats}, {', '.join(PLATFORM_LABELS[p] for p in q.platforms)}"
            for i, q in enumerate(analysis.verbatim, 1)]
    out.append("")

    out += ["## 4. Hook frames (unstyled)", "",
            "Structural hooks built from verbatim audience language. Raw material only; "
            "voice and tone get applied later from the brand matrix.", "",
            "| # | Type | Hook frame | Built from |", "|---|---|---|---|"]
    out += [
        f"| {i} | {h.kind} | {_cell(h.text)} | {_cell(h.source_theme)} ({PLATFORM_LABELS[h.evidence.signal.platform.value]}) |"
        for i, h in enumerate(analysis.hooks, 1)
    ]
    out.append("")

    out += ["## 5. By keyword", "",
            "| Keyword | Signals | Top pain | Top desire | Loudest line |", "|---|---:|---|---|---|"]
    for k in analysis.per_keyword:
        out.append(
            f"| {_cell(k.keyword)} | {k.signals} | {_cell(k.top_pain.label) if k.top_pain else '—'} | "
            f"{_cell(k.top_desire.label) if k.top_desire else '—'} | "
            f"{_cell(k.loudest_quote.text) if k.loudest_quote else '—'} |"
        )
    out.append("")

    out += [
        "## Method", "",
        "- Every signal (title + body) is split into sentences. A sentence counts as a *desire* if it states a want "
        "or a result (\"I want…\", \"finally…\", \"went from…\") or comes from a 4–5★ review; otherwise it is "
        "checked against the pain themes. Sentences can support more than one theme.",
        "- Intensity (1–5): +0.5 per intensifier (\"literally\", \"hate\", \"years\", \"can't\"…), shouting, "
        "exclamation marks; +1 for 1–2★ reviews.",
        "- Theme score: Σ intensity × (1 + log10(1 + engagement)), × (1 + 0.25 per extra platform), "
        "normalised so the strongest theme is 100.",
        "- Theme lexicons live in `.claude/agents/signal_miner/analyzer.py` (`PAIN_THEMES`, `DESIRE_THEMES`).",
        "",
    ]
    return "\n".join(out)


# --------------------------------------------------------------------------- #
# Agent loop
# --------------------------------------------------------------------------- #


def run_pipeline(keywords_path: Path, out_dir: Path, limit: int, report_date: date,
                 seed: str | None, log=print) -> Path:
    log(f"[1/4] Reading keywords from {keywords_path}")
    keywords = read_keywords(keywords_path)
    log(f"      {len(keywords)} keywords: {', '.join(keywords)}")

    log(f"[2/4] Mining Reddit, X and Amazon ({limit} signals per keyword per platform)")
    now = datetime.now(timezone.utc)
    adapters = default_adapters(seed=seed if seed is not None else report_date.isoformat(), now=now)
    run = mine(keywords, adapters=adapters, limit=limit, log=log)
    if not run.signals:
        raise RuntimeError("No signals collected; every source failed. See errors above.")
    raw_path = run.save_json(out_dir / "raw" / f"{report_date.isoformat()}.json")
    log(f"      {len(run.signals)} signals saved to {raw_path}")

    log("[3/4] Running thematic analysis")
    analysis = analyze(run)
    log(f"      {len(analysis.pains)} pain themes, {len(analysis.desires)} desire themes, "
        f"{len(analysis.hooks)} hook frames")

    log("[4/4] Writing report")
    report_path = out_dir / f"{report_date.isoformat()}.md"
    try:
        raw_display = raw_path.relative_to(out_dir.parent).as_posix()
    except ValueError:
        raw_display = raw_path.as_posix()
    report_path.write_text(render_report(run, analysis, report_date, raw_display), encoding="utf-8")
    return report_path


def main(argv: list[str] | None = None) -> int:
    root = find_project_root(Path.cwd())
    parser = argparse.ArgumentParser(description="Run the Signal Miner pipeline end to end.")
    parser.add_argument("--keywords", type=Path, default=root / "keywords.txt",
                        help="keyword file (default: <project root>/keywords.txt)")
    parser.add_argument("--out-dir", type=Path, default=root / "signals",
                        help="report folder (default: <project root>/signals)")
    parser.add_argument("--limit", type=int, default=20,
                        help="signals per keyword per platform (default 20)")
    parser.add_argument("--date", type=date.fromisoformat, default=date.today(),
                        help="report date, YYYY-MM-DD (default today)")
    parser.add_argument("--seed", help="mock data seed (default: the report date)")
    args = parser.parse_args(argv)

    try:
        report = run_pipeline(args.keywords, args.out_dir, args.limit, args.date, args.seed)
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"\nReport ready: {report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
