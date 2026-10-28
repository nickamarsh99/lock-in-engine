"""Turn a raw teleprompter take into a finished 9:16 short.

    python -m lockin.edit raw.mov --script script.txt --handle @you --theme dawn --out final.mp4

Steps: cut silences -> crop to 1080x1920 -> captions in brand style (Whisper word
timing, or the script when Whisper isn't available) -> optional hook title ->
loudness to -14 LUFS -> branded end card. Also writes an .srt for platforms that
take caption files.
"""
import argparse
import json
import re
import subprocess
import tempfile
from pathlib import Path

from . import captions
from .brand import FONTS, end_card, theme_for
from .script import parse

VIDEO = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30"


def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode:
        raise SystemExit(f"ffmpeg failed:\n{' '.join(map(str, cmd))}\n{p.stderr[-2000:]}")
    return p


def probe(path):
    out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type", "-of", "json", str(path)]).stdout
    info = json.loads(out)
    return float(info["format"]["duration"]), any(s["codec_type"] == "audio" for s in info["streams"])


def speech_segments(path, duration, noise="-34dB", min_silence=0.45, pad=0.12, min_len=0.25):
    err = run(["ffmpeg", "-hide_banner", "-i", str(path), "-af", f"silencedetect=noise={noise}:d={min_silence}", "-f", "null", "-"]).stderr
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", err)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", err)]
    silences = list(zip(starts, ends + [duration] * (len(starts) - len(ends))))
    keep, t = [], 0.0
    for s, e in silences:
        if s > t:
            keep.append((max(t - pad, 0), min(s + pad, duration)))
        t = e
    if t < duration:
        keep.append((max(t - pad, 0), duration))
    merged = []
    for s, e in keep:
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(e, merged[-1][1]))
        elif e - s >= min_len:
            merged.append((s, e))
    return merged or [(0, duration)]


def cut(src, segments, out):
    parts, labels = [], []
    for i, (s, e) in enumerate(segments):
        parts.append(f"[0:v]trim={s:.3f}:{e:.3f},setpts=PTS-STARTPTS,{VIDEO}[v{i}];[0:a]atrim={s:.3f}:{e:.3f},asetpts=PTS-STARTPTS,aresample=48000[a{i}]")
        labels.append(f"[v{i}][a{i}]")
    fc = ";".join(parts) + f";{''.join(labels)}concat=n={len(segments)}:v=1:a=1[v][a]"
    run(["ffmpeg", "-y", "-hide_banner", "-i", str(src), "-filter_complex", fc, "-map", "[v]", "-map", "[a]",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "17", "-c:a", "aac", "-b:a", "192k", str(out)])
    # Segment boundaries on the new timeline, for script-timed captions.
    t, bounds = 0.0, []
    for s, e in segments:
        bounds.append((t, t + (e - s)))
        t += e - s
    return bounds


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("raw")
    ap.add_argument("--script", help="text file with the engine's video script")
    ap.add_argument("--handle", default="@yourhandle")
    ap.add_argument("--theme", help="dawn, golden, sage, clay, dusk, linen, pine")
    ap.add_argument("--pillar", type=int, help="picks the theme when --theme is omitted")
    ap.add_argument("--title", help="hook title for the first 3 seconds (defaults to the script's first ON SCREEN cue)")
    ap.add_argument("--end-line", default="Follow for more")
    ap.add_argument("--no-cut", action="store_true", help="keep pauses")
    ap.add_argument("--whisper-model", default="base.en")
    ap.add_argument("--noise", default="-34dB", help="silence threshold; raise toward -30dB in noisy rooms")
    ap.add_argument("--max-mb", type=float, default=14, help="cap the file size so it fits the engine page (0 = no cap)")
    ap.add_argument("--out")
    a = ap.parse_args(argv)

    raw = Path(a.raw)
    out = Path(a.out or raw.with_name(raw.stem + "-final.mp4"))
    theme = theme_for(a.theme, a.pillar)
    spoken, cues = parse(Path(a.script).read_text()) if a.script else ([], [])
    title = a.title or (cues[0] if cues else None)

    duration, has_audio = probe(raw)
    if not has_audio:
        raise SystemExit("This clip has no audio track.")
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        segs = [(0, duration)] if a.no_cut else speech_segments(raw, duration, a.noise)
        kept = sum(e - s for s, e in segs)
        print(f"1/4 cutting: {duration:.1f}s -> {kept:.1f}s across {len(segs)} takes")
        bounds = cut(raw, segs, tmp / "cut.mp4")

        print("2/4 captions")
        words = captions.whisper_words(tmp / "cut.mp4", a.whisper_model)
        source = "whisper"
        if not words:
            words, source = captions.script_words(spoken, bounds), "script"
        ass = captions.build_ass(words, tmp / "cap.ass", title=title)
        if words:
            captions.build_srt(words, out.with_suffix(".srt"))
        print(f"  {len(words)} words timed from the {source}")

        print("3/4 end card")
        card = end_card(tmp / "card.png", a.handle, theme, line=a.end_line)

        print("4/4 render")
        # Cap the bitrate so the file fits the engine's 15 MB upload limit. Platforms recompress anyway.
        total = probe(tmp / "cut.mp4")[0] + 2.2
        cap = []
        if a.max_mb:
            kbps = max(900, int(a.max_mb * 8192 / total) - 200)
            cap = ["-maxrate", f"{kbps}k", "-bufsize", f"{kbps * 2}k"]
        fc = (f"[0:v]ass={ass}:fontsdir={FONTS},format=yuv420p[v0];"
              f"[0:a]loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[a0];"
              f"[1:v]scale=1080:1920,setsar=1,fps=30,format=yuv420p,fade=in:st=0:d=0.3[v1];"
              f"[v0][a0][v1][2:a]concat=n=2:v=1:a=1[v][a]")
        run(["ffmpeg", "-y", "-hide_banner", "-i", str(tmp / "cut.mp4"), "-loop", "1", "-t", "2.2", "-i", str(card),
             "-f", "lavfi", "-t", "2.2", "-i", "anullsrc=r=48000:cl=stereo", "-filter_complex", fc,
             "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "medium", "-crf", "19", *cap, "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out)])
    print(f"done: {out}  ({probe(out)[0]:.1f}s)")
    return out


if __name__ == "__main__":
    main()
