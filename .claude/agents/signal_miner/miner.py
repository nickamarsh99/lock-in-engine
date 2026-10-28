#!/usr/bin/env python3
"""Signal Miner: raw audience-signal collection.

Collects raw audience feedback for a list of keywords / competitor names from
three source families:

* Reddit  - top and hot threads, plus their top comments
* X       - recent public posts
* Amazon  - 1-star and 5-star customer reviews for related books/products

The adapters in this file are mocks. They generate deterministic,
realistic-looking records so the rest of the pipeline can be built and tested
without API credentials. To go live, subclass ``SourceAdapter`` for a platform
and pass it to ``mine()``; nothing downstream needs to change.

Usage:
    python3 miner.py "deep work" "Atomic Habits" --limit 10 --out raw.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
import uuid
from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from itertools import cycle
from pathlib import Path
from typing import Any


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #


class Platform(str, Enum):
    REDDIT = "reddit"
    X = "x"
    AMAZON = "amazon"


class SignalKind(str, Enum):
    THREAD = "thread"
    COMMENT = "comment"
    POST = "post"
    REVIEW = "review"


@dataclass
class Signal:
    """One unit of raw audience feedback, normalised across platforms."""

    id: str
    platform: Platform
    kind: SignalKind
    keyword: str
    text: str
    author: str
    url: str
    created_at: datetime
    # Upvotes (Reddit), likes + reposts (X), helpful votes (Amazon).
    engagement: int
    title: str | None = None
    # Amazon star rating, 1-5. None everywhere else.
    rating: int | None = None
    # Thread id for Reddit comments.
    parent_id: str | None = None
    # Platform-specific extras: subreddit, listing, product, asin, likes, ...
    context: dict[str, str] = field(default_factory=dict)

    @property
    def full_text(self) -> str:
        return f"{self.title}\n{self.text}" if self.title else self.text

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "platform": self.platform.value,
            "kind": self.kind.value,
            "keyword": self.keyword,
            "title": self.title,
            "text": self.text,
            "author": self.author,
            "url": self.url,
            "created_at": self.created_at.isoformat(),
            "engagement": self.engagement,
            "rating": self.rating,
            "parent_id": self.parent_id,
            "context": dict(self.context),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Signal:
        return cls(
            id=data["id"],
            platform=Platform(data["platform"]),
            kind=SignalKind(data["kind"]),
            keyword=data["keyword"],
            text=data["text"],
            author=data["author"],
            url=data["url"],
            created_at=datetime.fromisoformat(data["created_at"]),
            engagement=int(data["engagement"]),
            title=data.get("title"),
            rating=data.get("rating"),
            parent_id=data.get("parent_id"),
            context=dict(data.get("context") or {}),
        )


@dataclass
class SourceError:
    """A fetch that failed. Recorded instead of aborting the whole run."""

    platform: Platform
    keyword: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"platform": self.platform.value, "keyword": self.keyword, "message": self.message}

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> SourceError:
        return cls(Platform(data["platform"]), data["keyword"], data["message"])


@dataclass
class MiningRun:
    """Everything one pipeline run collected, plus provenance."""

    keywords: list[str]
    started_at: datetime
    finished_at: datetime | None = None
    signals: list[Signal] = field(default_factory=list)
    errors: list[SourceError] = field(default_factory=list)
    # platform -> adapter mode ("mock" or "live")
    sources: dict[str, str] = field(default_factory=dict)
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    @property
    def is_mock(self) -> bool:
        return any(mode == "mock" for mode in self.sources.values())

    def by_platform(self) -> dict[Platform, list[Signal]]:
        grouped: dict[Platform, list[Signal]] = {}
        for signal in self.signals:
            grouped.setdefault(signal.platform, []).append(signal)
        return grouped

    def by_keyword(self) -> dict[str, list[Signal]]:
        grouped: dict[str, list[Signal]] = {k: [] for k in self.keywords}
        for signal in self.signals:
            grouped.setdefault(signal.keyword, []).append(signal)
        return grouped

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "keywords": list(self.keywords),
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "sources": dict(self.sources),
            "signal_count": len(self.signals),
            "errors": [e.to_dict() for e in self.errors],
            "signals": [s.to_dict() for s in self.signals],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MiningRun:
        finished = data.get("finished_at")
        return cls(
            run_id=data["run_id"],
            keywords=list(data["keywords"]),
            started_at=datetime.fromisoformat(data["started_at"]),
            finished_at=datetime.fromisoformat(finished) if finished else None,
            sources=dict(data.get("sources") or {}),
            errors=[SourceError.from_dict(e) for e in data.get("errors") or []],
            signals=[Signal.from_dict(s) for s in data.get("signals") or []],
        )

    def save_json(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return path

    @classmethod
    def load_json(cls, path: Path) -> MiningRun:
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))


# --------------------------------------------------------------------------- #
# Source adapters
# --------------------------------------------------------------------------- #


class SourceAdapter(ABC):
    """Fetches raw signals for one platform. Subclass this for a live API."""

    platform: Platform
    mode: str = "live"

    @abstractmethod
    def fetch(self, keyword: str, limit: int) -> list[Signal]:
        """Return up to ``limit`` signals for ``keyword``."""


# Mock corpus. Phrasing mirrors how people actually complain and wish online:
# first person, specific, emotional. ``{kw}`` is replaced with the keyword.

PAIN = (
    "I've tried everything for {kw} and nothing sticks past week two.",
    "Honestly I'm so tired of starting over every Monday.",
    "I waste hours every single day and I hate myself for it.",
    "Every {kw} guide says the same generic stuff. Just tell me what to actually do.",
    "I spent $200 on {kw} courses and I'm exactly where I started.",
    "It feels like my brain is fighting me the whole time.",
    "I know what to do, I just can't make myself do it.",
    "I'm falling behind at work and I'm scared it's going to cost me my job.",
    "The advice works for a few days and then I'm back to scrolling at 2am.",
    "Nobody talks about how lonely and embarrassing this is.",
    "I'm drowning in tabs, notes and apps and none of it helps.",
    "Too much theory, not enough steps. I need a plan, not a philosophy.",
    "I've lost years to this. Literally years.",
    "Is it even possible to fix this or am I just broken?",
    "Every app I try just becomes another thing to procrastinate with.",
    "My deadline is Friday and I haven't started. Again.",
)

DESIRE = (
    "I just want to sit down and actually finish what I start.",
    "I want to feel in control of my day instead of my day controlling me.",
    "Imagine getting 4 hours of real work done before lunch.",
    "I want a simple system I can stick with even on bad days.",
    "I want to stop feeling guilty every night about what I didn't do.",
    "I'd love to finally trust myself to follow through.",
    "I want my evenings back.",
    "I want to be the kind of person who just gets things done without drama.",
    "My goal is to ship the side project I've been sitting on for two years.",
    "I want focus to feel easy, not like a fight.",
)

TRANSFORMATION = (
    "This finally made {kw} click for me.",
    "For the first time in years I actually finished a project.",
    "I went from zero to 3 hours of deep focus a day in about a month.",
    "I stopped relying on motivation and started relying on a system.",
    "It changed how I see myself. I'm not lazy, I just didn't have a process.",
    "I got my evenings back and my stress dropped massively.",
    "Finally a plan that works on bad days, not just good ones.",
)

X_TAKES = (
    "Unpopular opinion: most {kw} advice is people selling you courses.",
    "Nobody needs another {kw} app. We need fewer distractions.",
    "The {kw} content online is 90% gurus who never struggled with it.",
    "Day 3 of trying {kw} again. Already back to scrolling at 2am.",
    "Why is every {kw} system so complicated? I need simple.",
)

REDDIT_TITLES = (
    "Anyone else struggle with {kw}? How did you fix it?",
    "What actually worked for you with {kw}?",
    "Is it me or is all the {kw} advice useless?",
    "Finally beat {kw} after 5 years. Here's what worked",
    "Brutally honest: what's the one thing that helped with {kw}?",
    "I'm 30 and I've lost years to this. Where do I even start?",
)

ONE_STAR = (
    "It's 90% filler and could have been a blog post.",
    "The author clearly never struggled with {kw} themselves.",
    "Same generic advice you can find for free on YouTube.",
    "Felt like a waste of money and time.",
    "All theory, zero practical steps.",
    "Started strong, then it's just an upsell for the author's course.",
)

ONE_STAR_TITLES = (
    "Save your money",
    "Nothing new here",
    "Disappointed",
    "Fluff",
    "Did not work for me",
)

FIVE_STAR = (
    "Simple, practical, no fluff. I use it every morning.",
    "Wish I'd found this 10 years ago.",
    "The first {kw} resource that didn't make me feel broken.",
    "Short chapters, real steps, and it actually works on bad days.",
    "Bought copies for my whole team.",
)

FIVE_STAR_TITLES = (
    "Life changing",
    "Finally something that works",
    "Read this first",
    "Practical and honest",
    "Worth every penny",
)

SUBREDDITS = ("productivity", "getdisciplined", "selfimprovement", "decidingtobebetter")
HANDLE_PREFIXES = ("quiet", "tired", "late", "focus", "mondays", "coffee", "night", "builder")


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower()) or "topic"


def _display_name(keyword: str) -> str:
    # Keep competitor names as typed ("Atomic Habits"); title-case plain keywords.
    return keyword.title() if keyword.islower() else keyword


class MockAdapter(SourceAdapter):
    """Deterministic mock: same keyword + seed always yields the same records."""

    mode = "mock"

    def __init__(self, seed: str = "", now: datetime | None = None) -> None:
        self.seed = seed
        self.now = now or datetime.now(timezone.utc)

    def _rng(self, keyword: str) -> random.Random:
        digest = hashlib.sha256(f"{self.platform.value}|{keyword.lower()}|{self.seed}".encode()).hexdigest()
        return random.Random(int(digest[:16], 16))

    @staticmethod
    def _id(rng: random.Random) -> str:
        return f"{rng.getrandbits(48):012x}"

    @staticmethod
    def _handle(rng: random.Random) -> str:
        return f"{rng.choice(HANDLE_PREFIXES)}_{rng.randint(10, 9999)}"

    @staticmethod
    def _engagement(rng: random.Random, scale: int) -> int:
        # Long-tailed, like real engagement: most posts small, a few large.
        return min(int(scale * (rng.paretovariate(1.3) - 1)) + rng.randint(0, 3), 50_000)

    def _ago(self, rng: random.Random, max_hours: int, after: datetime | None = None) -> datetime:
        earliest = after or self.now - timedelta(hours=max_hours)
        span = max(int((self.now - earliest).total_seconds()), 60)
        return self.now - timedelta(seconds=rng.randint(60, span))

    @staticmethod
    def _say(rng: random.Random, keyword: str, *parts: tuple[Sequence[str], int]) -> str:
        """Compose text by sampling ``count`` distinct lines from each bank."""
        lines = [line for bank, count in parts for line in rng.sample(bank, count)]
        return " ".join(line.format(kw=keyword) for line in lines)


class MockRedditAdapter(MockAdapter):
    """Top and hot threads, each followed by a handful of top comments."""

    platform = Platform.REDDIT

    def fetch(self, keyword: str, limit: int) -> list[Signal]:
        rng = self._rng(keyword)
        signals: list[Signal] = []
        listings = cycle(("hot", "top"))
        subreddits = (*SUBREDDITS, _slug(keyword))

        while len(signals) < limit:
            listing = next(listings)
            subreddit = rng.choice(subreddits)
            thread_id = self._id(rng)
            thread_url = f"https://www.reddit.com/r/{subreddit}/comments/{thread_id}/"
            created = self._ago(rng, 48 if listing == "hot" else 24 * 30)
            thread = Signal(
                id=f"rd_{thread_id}",
                platform=self.platform,
                kind=SignalKind.THREAD,
                keyword=keyword,
                title=rng.choice(REDDIT_TITLES).format(kw=keyword),
                text=self._say(rng, keyword, (PAIN, rng.randint(1, 3)), (DESIRE, 1)),
                author=self._handle(rng),
                url=thread_url,
                created_at=created,
                engagement=self._engagement(rng, 60 if listing == "top" else 20),
                context={"subreddit": f"r/{subreddit}", "listing": listing},
            )
            signals.append(thread)

            for _ in range(rng.randint(2, 4)):
                if len(signals) >= limit:
                    break
                bank = rng.choices((PAIN, DESIRE, TRANSFORMATION), weights=(5, 3, 2))[0]
                comment_id = self._id(rng)
                signals.append(
                    Signal(
                        id=f"rd_{comment_id}",
                        platform=self.platform,
                        kind=SignalKind.COMMENT,
                        keyword=keyword,
                        text=self._say(rng, keyword, (bank, rng.randint(1, 2))),
                        author=self._handle(rng),
                        url=f"{thread_url}{comment_id}/",
                        created_at=self._ago(rng, 0, after=created),
                        engagement=self._engagement(rng, 15),
                        parent_id=thread.id,
                        context={"subreddit": f"r/{subreddit}", "listing": listing},
                    )
                )
        return signals


class MockXAdapter(MockAdapter):
    """Recent public posts from the last 72 hours."""

    platform = Platform.X

    def fetch(self, keyword: str, limit: int) -> list[Signal]:
        rng = self._rng(keyword)
        hashtag = f"#{_display_name(keyword).replace(' ', '')}"
        signals: list[Signal] = []
        for _ in range(limit):
            bank = rng.choices((PAIN, DESIRE, TRANSFORMATION, X_TAKES), weights=(5, 3, 2, 3))[0]
            text = self._say(rng, keyword, (bank, 1))
            if rng.random() < 0.3:
                text = f"{text} {hashtag}"
            likes = self._engagement(rng, 25)
            reposts = likes // rng.randint(4, 12)
            post_id = str(rng.getrandbits(60))
            handle = self._handle(rng)
            signals.append(
                Signal(
                    id=f"x_{post_id}",
                    platform=self.platform,
                    kind=SignalKind.POST,
                    keyword=keyword,
                    text=text,
                    author=f"@{handle}",
                    url=f"https://x.com/{handle}/status/{post_id}",
                    created_at=self._ago(rng, 72),
                    engagement=likes + reposts,
                    context={"likes": str(likes), "reposts": str(reposts)},
                )
            )
        return signals


class MockAmazonAdapter(MockAdapter):
    """Customer reviews for books/products related to the keyword."""

    platform = Platform.AMAZON

    def __init__(self, stars: Sequence[int] = (1, 5), **kwargs: Any) -> None:
        super().__init__(**kwargs)
        if not stars or any(s not in range(1, 6) for s in stars):
            raise ValueError(f"stars must be values from 1 to 5, got {stars!r}")
        self.stars = tuple(stars)

    @staticmethod
    def _products(rng: random.Random, keyword: str) -> list[tuple[str, str]]:
        name = _display_name(keyword)
        titles = (name, f"The {name} Workbook: 30 Days to Lasting Change", f"{name} Planner & Habit Journal")
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ0123456789"
        return [("B0" + "".join(rng.choices(alphabet, k=8)), title) for title in titles]

    def fetch(self, keyword: str, limit: int) -> list[Signal]:
        rng = self._rng(keyword)
        products = self._products(rng, keyword)
        signals: list[Signal] = []
        for i in range(limit):
            asin, product = rng.choice(products)
            rating = self.stars[i % len(self.stars)]
            if rating <= 2:
                title = rng.choice(ONE_STAR_TITLES)
                text = self._say(rng, keyword, (ONE_STAR, rng.randint(1, 2)), (PAIN, 1))
            elif rating >= 4:
                title = rng.choice(FIVE_STAR_TITLES)
                text = self._say(rng, keyword, (FIVE_STAR, 1), (TRANSFORMATION, 1))
            else:
                title = "It's okay"
                text = self._say(rng, keyword, (FIVE_STAR, 1), (ONE_STAR, 1))
            review_id = "R" + "".join(rng.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", k=13))
            signals.append(
                Signal(
                    id=f"az_{review_id}",
                    platform=self.platform,
                    kind=SignalKind.REVIEW,
                    keyword=keyword,
                    title=title,
                    text=text,
                    author=self._handle(rng),
                    url=f"https://www.amazon.com/gp/customer-reviews/{review_id}?ASIN={asin}",
                    created_at=self._ago(rng, 24 * 365),
                    engagement=self._engagement(rng, 8),
                    rating=rating,
                    context={
                        "product": product,
                        "asin": asin,
                        "verified_purchase": "yes" if rng.random() < 0.85 else "no",
                    },
                )
            )
        return signals


# --------------------------------------------------------------------------- #
# Pipeline entry points
# --------------------------------------------------------------------------- #


def default_adapters(seed: str | None = None, now: datetime | None = None) -> list[SourceAdapter]:
    """Mock adapters for all three platforms. Seed defaults to today's date."""
    now = now or datetime.now(timezone.utc)
    seed = seed if seed is not None else now.date().isoformat()
    return [
        MockRedditAdapter(seed=seed, now=now),
        MockXAdapter(seed=seed, now=now),
        MockAmazonAdapter(seed=seed, now=now),
    ]


def mine(
    keywords: Sequence[str],
    adapters: Sequence[SourceAdapter] | None = None,
    limit: int = 20,
    log: Callable[[str], None] | None = None,
) -> MiningRun:
    """Fetch ``limit`` signals per keyword from every adapter."""
    if limit < 1:
        raise ValueError("limit must be at least 1")
    adapters = list(adapters) if adapters is not None else default_adapters()
    run = MiningRun(
        keywords=list(keywords),
        started_at=datetime.now(timezone.utc),
        sources={a.platform.value: a.mode for a in adapters},
    )
    for keyword in keywords:
        for adapter in adapters:
            try:
                batch = adapter.fetch(keyword, limit)
            except Exception as exc:  # one failing source must not sink the run
                run.errors.append(SourceError(adapter.platform, keyword, f"{type(exc).__name__}: {exc}"))
                if log:
                    log(f"  {adapter.platform.value:<7} {keyword!r}: FAILED ({exc})")
                continue
            run.signals.extend(batch)
            if log:
                log(f"  {adapter.platform.value:<7} {keyword!r}: {len(batch)} signals ({adapter.mode})")
    run.finished_at = datetime.now(timezone.utc)
    return run


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Collect raw audience signals for keywords.")
    parser.add_argument("keywords", nargs="+", help="keywords or competitor names")
    parser.add_argument("--limit", type=int, default=20, help="signals per keyword per platform (default 20)")
    parser.add_argument("--seed", help="mock seed (default: today's date)")
    parser.add_argument("--out", type=Path, help="write the run as JSON to this path")
    args = parser.parse_args(argv)

    run = mine(args.keywords, adapters=default_adapters(seed=args.seed), limit=args.limit, log=print)
    print(f"{len(run.signals)} signals, {len(run.errors)} errors")
    if args.out:
        print(f"saved {run.save_json(args.out)}")
    return 1 if run.errors and not run.signals else 0


if __name__ == "__main__":
    sys.exit(main())
