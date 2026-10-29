# Lock-In Engine: notes for Claude

Read `README.md` first. The creator posts faith + holistic health content (8 pillars, weights in the engine page's `PILLARS`).

- The engine page is the source of truth for slide design. Edit `engine/lock-in-engine.html`, republish it to the artifact URL in the README, then run `python3 tools/extract_renderer.py`.
- Read and write posts with the ArtifactData tool on the engine URL. Collections: `posts` (status idea/drafted/ready/posted; format carousel/quote/reel/text), `settings` (doc `main`), `voice` (doc `profile`), `tree` (content tree nodes), `swipe` (inspiration posts with Claude's analysis). The prayer journal lives under `data/users/<id>`: private to the creator; only read it when asked to.
- Keep the bank stocked: the goal is always `settings.runwayTarget` (default 10) posts in `ready`.
- Voice: follow `voice/profile.notes` and the creator's approved posts (status `ready`/`posted`). Integrity rules: no disease or cure claims, Scripture quoted briefly with its reference, products disclosed, no cursing or insults.
- Brand colors and themes live in `brand/brand.json` (video) and `THEMES` in the engine page (slides). Keep them in sync.
