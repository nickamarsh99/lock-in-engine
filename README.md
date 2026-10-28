# Lock-In Engine

The production side of a faith and holistic-health content brand. The **engine page** (a private claude.ai artifact) is where posts are planned, written, and designed. This repo holds what runs outside the page: the video auto-editor, the post-kit renderer, and the brand assets they share.

- Engine page: https://claude.ai/artifact/SWZJ8k6iS6YNqGyMpxrtty (source: `engine/lock-in-engine.html`)
- Posts, settings, and the voice guide live in the page's database: `posts/*`, `settings/main`, `voice/profile`

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
