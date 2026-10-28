"""Thematic analysis of a MiningRun.

Turns raw signals into three things:

* Bleeding-neck problems - pain themes ranked by frequency, emotional
  intensity, engagement and cross-platform spread.
* Desired transformations - what people say they want, ranked the same way.
* Hook frames - unstyled hook structures filled with verbatim user language.

Everything here is rule-based and deterministic (standard library only), so a
report can always be traced back to the exact sentences that produced it.
Voice and styling are deliberately out of scope.
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from miner import MiningRun, Signal


# --------------------------------------------------------------------------- #
# Theme taxonomy
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ThemeDef:
    key: str
    label: str
    patterns: tuple[str, ...]

    def regex(self) -> re.Pattern[str]:
        return re.compile("|".join(f"(?:{p})" for p in self.patterns), re.IGNORECASE)


PAIN_THEMES = (
    ThemeDef("nothing_sticks", "Tried everything, nothing sticks", (
        r"tried (every|everything|all)", r"nothing (sticks|works|helps|changed)", r"starting over",
        r"back to (square one|scrolling|where)", r"few days", r"past week two", r"\bagain\b",
    )),
    ThemeDef("knowing_doing_gap", "Knows what to do, can't make themselves do it", (
        r"know what to do", r"can'?t (make|get) myself", r"brain (is )?fighting", r"fighting me",
    )),
    ThemeDef("lost_time", "Lost hours, lost years", (
        r"wast\w* (hours|days|time|years)", r"lost (years|months|so much time)", r"\byears\b",
        r"\b2 ?am\b", r"scrolling",
    )),
    ThemeDef("wasted_money", "Paid for solutions that didn't deliver", (
        r"\$\d+", r"waste of money", r"refund", r"overpriced", r"save your money", r"upsell", r"courses?\b",
    )),
    ThemeDef("generic_advice", "Generic, theory-heavy advice", (
        r"generic", r"same (\w+ )?(stuff|advice)", r"filler", r"fluff", r"theory", r"blog post",
        r"philosophy", r"nothing new", r"for free on",
    )),
    ThemeDef("tool_overwhelm", "Drowning in tools, tabs and apps", (
        r"drowning", r"\btabs\b", r"\bapps?\b", r"too many", r"overwhelm", r"complicated",
        r"another thing to",
    )),
    ThemeDef("real_stakes", "Real consequences: work, money, deadlines", (
        r"\bjob\b", r"falling behind", r"deadline", r"\bboss\b", r"\bgrades?\b", r"cost me", r"fired",
    )),
    ThemeDef("shame_identity", "Shame and 'am I broken?' identity doubt", (
        r"broken", r"\blazy\b", r"embarrass", r"lonely", r"ashamed", r"hate myself",
        r"what'?s wrong with me", r"guilt",
    )),
    ThemeDef("distrust", "Distrust of gurus and sellers", (
        r"never struggled", r"gurus?", r"scam", r"selling you", r"author clearly", r"influencers?",
    )),
)

DESIRE_THEMES = (
    ThemeDef("follow_through", "Finish what they start", (
        r"\bfinish\w*", r"follow through", r"\bship\b", r"get(s|ting)? (it|things) done",
    )),
    ThemeDef("control", "Feel in control of their day", (
        r"in control", r"\bcontrol", r"\bmy day\b", r"own (my|the) (day|morning|time)",
    )),
    ThemeDef("simple_system", "A simple system that survives bad days", (
        r"\bsimple\b", r"\bsystem\b", r"\bprocess\b", r"stick with", r"no fluff", r"practical",
        r"bad days", r"\bplan\b", r"real steps",
    )),
    ThemeDef("time_back", "Get their time back", (
        r"evenings? back", r"time back", r"weekends?", r"before lunch", r"free time",
    )),
    ThemeDef("relief", "Relief from guilt and stress", (
        r"guilt", r"stress", r"anxiety", r"\bpeace\b", r"\bcalm\b", r"relief", r"feel broken",
    )),
    ThemeDef("effortless_focus", "Focus that feels easy, not a fight", (
        r"\bfocus", r"deep work", r"\bflow\b", r"\beasy\b", r"not like a fight",
    )),
    ThemeDef("identity_shift", "Become someone who follows through", (
        r"(kind of )?person who", r"see myself", r"trust myself", r"not lazy", r"who i am",
    )),
    ThemeDef("measurable_results", "Concrete, measurable progress", (
        r"\b\d+ (hours?|days?|weeks?|months?|years?|pages?)\b", r"first time in", r"went from",
        r"in (about )?(a|one|two) (week|month)s?",
    )),
)

# Sentences that express a want or a result rather than a complaint.
DESIRE_INTENT = re.compile(
    r"\b(i (just |really )?want|i'?d love|would love|wish|my goal|goal is|imagine|finally|"
    r"for the first time|changed (how|my|everything)|went from|helped me|click(ed)? for me|"
    r"game[- ]?changer|i got my|i stopped|works on bad days|actually works)\b",
    re.IGNORECASE,
)

INTENSIFIERS = (
    "every single", "literally", "so tired", "sick of", "hate", "desperate", "scared", "terrified",
    "years", "can't", "cannot", "nothing", "never", "honestly", "please", "help", "worst", "useless",
    "waste", "broken", "drowning", "embarrassing", "ashamed", "again",
)
_INTENSIFIER_RE = re.compile(r"\b(" + "|".join(re.escape(w) for w in INTENSIFIERS) + r")\b", re.IGNORECASE)

STOPWORDS = frozenset(
    """a an the and or but if then so to of in on at for with from by as is are was were be been am
    i i'm i've i'd me my we our you your it it's its this that these those there here what which who
    just do does did don't not no yes up out about into over than too very can will would should
    could has have had get got all any some more most every each other one also only how why when
    where again even really still back like""".split()
)

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
_TOKEN = re.compile(r"[a-z0-9$']+")


# --------------------------------------------------------------------------- #
# Result structures
# --------------------------------------------------------------------------- #


@dataclass
class Evidence:
    """One sentence that supports a theme, with its provenance."""

    text: str
    signal: Signal
    intensity: float

    @property
    def weight(self) -> float:
        return self.intensity * (1 + math.log10(1 + self.signal.engagement))


@dataclass
class Quote:
    text: str
    repeats: int
    platforms: list[str]
    best: Evidence


@dataclass
class ThemeResult:
    key: str
    label: str
    polarity: str  # "pain" | "desire"
    evidence: list[Evidence] = field(default_factory=list)
    score: float = 0.0  # 0-100, relative to the strongest theme of the same polarity
    tier: str = ""

    @property
    def mentions(self) -> int:
        return len(self.evidence)

    @property
    def platforms(self) -> list[str]:
        return sorted({e.signal.platform.value for e in self.evidence})

    @property
    def avg_intensity(self) -> float:
        return sum(e.intensity for e in self.evidence) / len(self.evidence) if self.evidence else 0.0

    @property
    def total_engagement(self) -> int:
        return sum(e.signal.engagement for e in self.evidence)

    @property
    def keywords(self) -> Counter[str]:
        return Counter(e.signal.keyword for e in self.evidence)

    def quotes(self, n: int = 3) -> list[Quote]:
        return _dedupe_quotes(self.evidence)[:n]


@dataclass
class Phrase:
    text: str
    count: int  # number of distinct signals using it
    platforms: list[str]


@dataclass
class Hook:
    kind: str
    text: str
    source_theme: str
    evidence: Evidence


@dataclass
class KeywordSummary:
    keyword: str
    signals: int
    top_pain: ThemeResult | None
    top_desire: ThemeResult | None
    loudest_quote: Quote | None


@dataclass
class Analysis:
    pains: list[ThemeResult]
    desires: list[ThemeResult]
    vocabulary: list[Phrase]
    verbatim: list[Quote]
    emotional_words: Counter[str]
    hooks: list[Hook]
    per_keyword: list[KeywordSummary]
    sentences: int
    unclassified: int


# --------------------------------------------------------------------------- #
# Analysis
# --------------------------------------------------------------------------- #


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9$ ]+", "", text.lower()).strip()


def _sentences(signal: Signal) -> list[str]:
    parts = (s.strip() for s in _SENTENCE_SPLIT.split(signal.full_text))
    return [p for p in parts if len(p.split()) >= 3]


def _intensity(sentence: str, signal: Signal) -> float:
    score = 1.0 + 0.5 * len(_INTENSIFIER_RE.findall(sentence))
    score += 0.5 * min(sum(1 for w in sentence.split() if len(w) > 2 and w.isupper()), 2)
    score += 0.5 if "!" in sentence else 0.0
    if signal.rating is not None and signal.rating <= 2:
        score += 1.0
    return min(score, 5.0)


def _is_desire(sentence: str, signal: Signal) -> bool:
    if DESIRE_INTENT.search(sentence):
        return True
    return signal.rating is not None and signal.rating >= 4


def _dedupe_quotes(evidence: list[Evidence]) -> list[Quote]:
    groups: dict[str, list[Evidence]] = defaultdict(list)
    for e in evidence:
        groups[_norm(e.text)].append(e)
    quotes = [
        Quote(
            text=max(items, key=lambda e: e.weight).text,
            repeats=len(items),
            platforms=sorted({e.signal.platform.value for e in items}),
            best=max(items, key=lambda e: e.weight),
        )
        for items in groups.values()
    ]
    quotes.sort(key=lambda q: (q.repeats * q.best.weight, len(q.platforms)), reverse=True)
    return quotes


def _score_themes(themes: list[ThemeResult], tiers: tuple[str, str, str]) -> list[ThemeResult]:
    raw: dict[str, float] = {}
    for t in themes:
        spread = 1 + 0.25 * (len(t.platforms) - 1)
        raw[t.key] = sum(e.weight for e in t.evidence) * spread
    top = max(raw.values(), default=0.0) or 1.0
    for t in themes:
        t.score = round(100 * raw[t.key] / top, 1)
        if t.score >= 60 and len(t.platforms) >= 2:
            t.tier = tiers[0]
        elif t.score >= 30:
            t.tier = tiers[1]
        else:
            t.tier = tiers[2]
    return sorted((t for t in themes if t.evidence), key=lambda t: t.score, reverse=True)


def _vocabulary(signals: list[Signal], keywords: list[str], top_n: int = 30) -> list[Phrase]:
    keyword_tokens = {tok for k in keywords for tok in _TOKEN.findall(k.lower())}
    doc_freq: Counter[str] = Counter()
    platforms: dict[str, set[str]] = defaultdict(set)

    for signal in signals:
        seen: set[str] = set()
        for sentence in _sentences(signal):
            tokens = _TOKEN.findall(sentence.lower())
            for n in (2, 3, 4):
                for i in range(len(tokens) - n + 1):
                    gram = tokens[i : i + n]
                    if gram[0] in STOPWORDS or gram[-1] in STOPWORDS:
                        continue
                    if all(tok in keyword_tokens or tok in STOPWORDS for tok in gram):
                        continue
                    seen.add(" ".join(gram))
        for phrase in seen:
            doc_freq[phrase] += 1
            platforms[phrase].add(signal.platform.value)

    candidates = [p for p, c in doc_freq.items() if c >= 2]
    # Drop a phrase when a longer phrase containing it covers most of its uses.
    kept = [
        p for p in candidates
        if not any(p != q and f" {p} " in f" {q} " and doc_freq[q] >= 0.8 * doc_freq[p] for q in candidates)
    ]
    kept.sort(key=lambda p: (doc_freq[p] * (1 + 0.15 * p.count(" ")), len(platforms[p])), reverse=True)

    # Overlapping n-grams are usually fragments of one stock sentence; keep the strongest.
    selected: list[str] = []
    claimed: set[str] = set()
    for phrase in kept:
        bigrams = _bigrams(phrase)
        if bigrams & claimed:
            continue
        selected.append(phrase)
        claimed |= bigrams
        if len(selected) == top_n:
            break
    return [Phrase(p, doc_freq[p], sorted(platforms[p])) for p in selected]


def _bigrams(phrase: str) -> set[str]:
    words = phrase.split()
    return {f"{a} {b}" for a, b in zip(words, words[1:])}


def _clip(text: str, limit: int = 140) -> str:
    """Trim for embedding mid-sentence: no trailing full stop, capped length."""
    text = text.strip().rstrip(".")
    return text if len(text) <= limit else text[: limit - 1].rsplit(" ", 1)[0] + "…"


def _standalone(text: str) -> str:
    """Clip, but keep the line ending in terminal punctuation."""
    text = _clip(text)
    return text if text.endswith(("?", "!", "…")) else f"{text}."


def _build_hooks(pains: list[ThemeResult], desires: list[ThemeResult], vocabulary: list[Phrase]) -> list[Hook]:
    """Unstyled hook frames. Each one carries the verbatim line it was built from."""
    hooks: list[Hook] = []

    for pain in pains[:3]:
        q = pain.quotes(1)[0]
        hooks.append(Hook("Pain mirror", f'"{_standalone(q.text)}" Sound familiar?', pain.label, q.best))

    for pain, desire in zip(pains[:3], desires[:3]):
        p, d = pain.quotes(1)[0], desire.quotes(1)[0]
        hooks.append(Hook(
            "Before → after", f'From "{_clip(p.text)}" to "{_clip(d.text)}".', f"{pain.label} → {desire.label}", p.best,
        ))

    # Critiques of existing solutions, as opposed to the reviewer's own struggle.
    critique_themes = {"generic_advice", "wasted_money", "distrust"}
    complaints = [
        e for t in pains if t.key in critique_themes
        for e in t.evidence if e.signal.rating is not None and e.signal.rating <= 2
    ]
    if complaints and desires:
        c = _dedupe_quotes(complaints)[0]
        d = desires[0].quotes(1)[0]
        hooks.append(Hook(
            "Objection flip",
            f'1-star reviewers keep saying "{_clip(c.text)}". What they asked for instead: "{_clip(d.text)}".',
            "1-star reviews", c.best,
        ))

    proof = [e for t in desires for e in t.evidence if e.signal.rating is not None and e.signal.rating >= 4]
    measurable = next((t for t in desires if t.key == "measurable_results"), None)
    if measurable:
        proof.extend(measurable.evidence)
    for q in _dedupe_quotes(proof)[:2]:
        hooks.append(Hook("Proof / result", f'"{_standalone(q.text)}" Here\'s what changed.', "Transformations", q.best))

    for phrase in vocabulary[:2]:
        hooks.append(Hook(
            "Vocabulary callout", f'Why "{phrase.text}" keeps coming up, and what to do about it.', "Audience vocabulary",
            _first_evidence_with(phrase.text, pains + desires),
        ))

    unique: dict[str, Hook] = {}
    for h in hooks:
        if h.evidence is not None:
            unique.setdefault(h.text, h)
    return list(unique.values())


def _first_evidence_with(phrase: str, themes: list[ThemeResult]) -> Evidence | None:
    for theme in themes:
        for e in theme.evidence:
            if phrase in e.text.lower():
                return e
    return None


def analyze(run: MiningRun) -> Analysis:
    pain_defs = [(d, d.regex()) for d in PAIN_THEMES]
    desire_defs = [(d, d.regex()) for d in DESIRE_THEMES]
    pains = {d.key: ThemeResult(d.key, d.label, "pain") for d in PAIN_THEMES}
    desires = {d.key: ThemeResult(d.key, d.label, "desire") for d in DESIRE_THEMES}
    emotional: Counter[str] = Counter()
    all_evidence: list[Evidence] = []
    sentence_count = unclassified = 0

    for signal in run.signals:
        for sentence in _sentences(signal):
            sentence_count += 1
            emotional.update(w.lower() for w in _INTENSIFIER_RE.findall(sentence))
            evidence = Evidence(sentence, signal, _intensity(sentence, signal))
            defs, bucket = (desire_defs, desires) if _is_desire(sentence, signal) else (pain_defs, pains)
            hits = [d.key for d, rx in defs if rx.search(sentence)]
            if not hits:
                unclassified += 1
                continue
            all_evidence.append(evidence)
            for key in hits:
                bucket[key].evidence.append(evidence)

    ranked_pains = _score_themes(list(pains.values()), ("BLEEDING NECK", "CHRONIC", "BACKGROUND"))
    ranked_desires = _score_themes(list(desires.values()), ("CORE DESIRE", "SECONDARY", "NICHE"))
    vocabulary = _vocabulary(run.signals, run.keywords)

    per_keyword = []
    for keyword, signals in run.by_keyword().items():
        ids = {s.id for s in signals}

        def top_for(themes: list[ThemeResult]) -> ThemeResult | None:
            counts = {t.key: sum(1 for e in t.evidence if e.signal.id in ids) for t in themes}
            best = max(themes, key=lambda t: (counts[t.key], t.score), default=None)
            return best if best and counts[best.key] else None

        quotes = _dedupe_quotes([e for e in all_evidence if e.signal.id in ids])
        per_keyword.append(KeywordSummary(
            keyword, len(signals), top_for(ranked_pains), top_for(ranked_desires), quotes[0] if quotes else None,
        ))

    return Analysis(
        pains=ranked_pains,
        desires=ranked_desires,
        vocabulary=vocabulary,
        verbatim=sorted(_dedupe_quotes(all_evidence), key=lambda q: q.repeats, reverse=True)[:12],
        emotional_words=emotional,
        hooks=_build_hooks(ranked_pains, ranked_desires, vocabulary),
        per_keyword=per_keyword,
        sentences=sentence_count,
        unclassified=unclassified,
    )

