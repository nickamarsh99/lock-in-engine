# Daily edit run

What the scheduled Claude task does each day. Engine URL: https://claude.ai/artifact/SWZJ8k6iS6YNqGyMpxrtty

1. **Setup:** `pip install -r requirements.txt` (ffmpeg is preinstalled).
2. **What's done:** ArtifactData `list` on collection `clips`. Write every doc id (a Drive file id) to `processed.txt`.
3. **Pull new clips:** `python3 -m lockin.drive pull --skip-ids processed.txt --out inbox`. It prints JSON with `id`, `name`, `date`, `path`.
4. **Match each clip to its post:** ArtifactData `query` on `posts` where `date == clip.date`. If several, prefer the one whose title words appear in the clip name. Read `settings/main` for `handle`.
5. **Edit:** write the post's `script` to `script.txt`, then
   `python3 -m lockin.edit <path> --script script.txt --pillar <post.pillar> [--theme <post.theme>] --handle <handle> --out out/<date>.mp4`
6. **Deliver:** upload `out/<date>.mp4` with the Artifact tool (`url` = engine URL, `asset: true`). Then ArtifactData `update` on `posts/<id>` with
   `{"video": {"url": <asset url>, "id": <asset id>, "name": "<date>.mp4", "updated": <ISO time>}}`.
7. **Record:** ArtifactData `set` on `clips/<drive id>`: `{"name", "postId", "status": "done", "videoUrl", "processed": <ISO time>}`.
   A clip with no matching post: still edit it (no `--script`), upload, and record `status: "unmatched"`.
8. **Report:** one line per clip, including whether captions came from Whisper or the script.

Never post to social platforms. Never delete anything in Drive (the key is read-only anyway).
