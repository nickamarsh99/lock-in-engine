# Lock-In Engine

The production side of a faith and holistic-health content brand. The **engine page** (a private claude.ai artifact) is where posts are planned, written, and designed. This repo holds what runs outside the page: the video auto-editor, the post-kit renderer, and the brand assets they share.

- Engine page: https://claude.ai/artifact/SWZJ8k6iS6YNqGyMpxrtty (source: `engine/lock-in-engine.html`)
- Posts, settings, and the voice guide live in the page's database: `posts/*`, `settings/main`, `voice/profile`

## The engine page

| Tab | What it's for |
| --- | --- |
| Sprint | 30-day calendar, pillar mix, what's landing |
| Content → Board | Ideas → Drafts → Ready → Posted. Runway meter, Plan 10 ideas, batch drafting |
| Content → Library | Every post, searchable and filterable, with bulk actions |
| Content → Feed grid | Preview the profile grid; "Balance the looks" alternates light and dark |
| Content → Studio | Edit a post: slides, photos, look, type, caption, script, X post, finished video, results |
| Ideas → Generate | Claude writes a post in any format, look, and type |
| Ideas → Journal | Private prayer journal that surfaces post ideas |
| Ideas → Swipe file | Screenshots of posts you admire, broken down by Claude |
| Tree | Mind map of pillars, niches, series, ideas, inspiration, brands, values |
| Playbook | Voice guide, settings, Bloom lessons, Sunday review |

Slide looks: Dawn, Golden Hour, Sage Morning, Clay, Dusk, Linen Sun, Ember, Journal, Olive Grove, Morning Mist, Harvest, Desert Rose, Evening Pine.
Fonts: Bold (Barlow Condensed), Serif (Newsreader), Garamond (Cormorant Garamond), Fraunces, Editorial (DM Serif Display), Slab (Zilla Slab), Typewriter (Courier Prime), Handwritten (Caveat).
Scenes (drawn in each look's colors): Mountains, Hills, Pine ridge, Ocean, Dunes, Wheat field, Night sky, Sun rays, Paper. Uploaded photos are reusable from Studio's photo library.

**Ask Claude** (header bar, the floating Ask button, or press `/`): a chat on every tab for hooks, ideas, captions, and rewrites. It knows the brand brief and voice, can search the library and tree through page tools, and every result can be saved as an idea, sent to Generate, added to the tree, or copied. "Continue in Claude" opens a full claude.ai chat for web research.

## Daily flow (semi-automatic)

1. **Write.** Studio in the engine page. Claude drafts from your pillars, voice guide, and best posts.
2. **Film.** Press *Film it* on a post to open the teleprompter. One take, pauses are fine.
3. **Edit.** The raw clip goes through `lockin.edit`: silences cut, 9:16 crop, brand captions, hook title, loudness, end card.
4. **Post.** Save the slides and finished video to your phone, paste the caption, and post to IG, TikTok, YouTube Shorts, and X.
5. **Log.** Tick placements and enter saves, shares, and follows in Studio. The voice guide learns from your edits.

## Video auto-edit

```bash
python3 -m lockin.edit raw.mov --script script.txt --pillar 2 --handle @you --out final.mp4
```

| Flag | What it does |
| --- | --- |
| `--script` | The post's video script. Its first `[ON SCREEN: ...]` cue becomes the hook title, and its words time the captions when Whisper isn't available. |
| `--theme` / `--pillar` | End-card look. Same themes as the carousel slides. |
| `--noise -30dB` | Raise the silence threshold in a noisy room. |
| `--no-cut` | Keep the pauses. |

Outputs `final.mp4` (1080×1920, H.264, -14 LUFS) and `final.srt`.

**Captions** use [faster-whisper](https://pypi.org/project/faster-whisper/) word timestamps when it's installed and its model can download (needs `huggingface.co` and `*.hf.co` allowed in the environment's network settings). Without it, captions are timed from the script, which tracks a straight teleprompter read but drifts on ad-libs.

## Post kit

```bash
node kit/render.js post.json out/ --handle @you
```

Renders the carousel PNGs with the engine's own slide code (`render/slides.generated.js`), plus `caption.txt`, `video-script.txt`, and `x-post.txt`. After changing the engine page, run `python3 tools/extract_renderer.py`.

## Setup

```bash
pip install -r requirements.txt   # add faster-whisper for accurate captions
npm install
```

Needs `ffmpeg`. Fonts are in `brand/fonts` (SIL Open Font License).

## Raw clips from Google Drive

Drop clips into the **Lock-In Raw** Drive folder, named with the post date first (`2026-10-29.mov`). A read-only service account pulls them:

```bash
python3 -m lockin.drive list
python3 -m lockin.drive pull --skip-ids processed.txt --out inbox
```

Needs `GDRIVE_SA_JSON` and `GDRIVE_RAW_FOLDER_ID` in the environment. Finished videos go back through the engine page (its asset store), not Drive, because service accounts can't own files in a personal Drive. The daily run is in `docs/daily-run.md`.

## Not automated

- **Posting:** manual by choice. Upgrade path: a unified posting API (one key for IG, TikTok drafts, YT, X) or the official APIs.
