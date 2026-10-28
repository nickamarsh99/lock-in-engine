"""Word timings (Whisper when available, the teleprompter script otherwise) and brand-styled ASS captions."""
import re

from .brand import BRAND


def whisper_words(audio_path, model="base.en"):
    """Word timestamps from faster-whisper. Returns None if it isn't installed or the model can't load."""
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return None
    try:
        m = WhisperModel(model, device="cpu", compute_type="int8")
    except Exception as e:  # model download blocked, missing files, etc.
        print(f"  whisper unavailable ({e.__class__.__name__}); using script timing")
        return None
    segments, _ = m.transcribe(str(audio_path), word_timestamps=True, vad_filter=True)
    return [(w.word.strip(), w.start, w.end) for s in segments for w in (s.words or []) if w.word.strip()]


def script_words(spoken_lines, segments):
    """Spread the script's words across speech segments in proportion to their length.

    Segments are (start, end) on the edited timeline. Each pause resets drift, so a
    teleprompter read lands close; ad-libs won't match. Whisper is the accurate path.
    """
    words = " ".join(spoken_lines).split()
    if not words or not segments:
        return []
    total = sum(e - s for s, e in segments)
    out, i = [], 0
    for n, (s, e) in enumerate(segments):
        share = len(words) - i if n == len(segments) - 1 else round(len(words) * (e - s) / total)
        chunk = words[i:i + share]
        i += len(chunk)
        weights = [len(w) + 2 for w in chunk]
        t = s
        for w, wt in zip(chunk, weights):
            d = (e - s) * wt / sum(weights)
            out.append((w, t, t + d))
            t += d
    return out


def chunk(words, max_words=3, max_chars=18):
    groups, cur = [], []
    for w in words:
        cur.append(w)
        text = " ".join(x[0] for x in cur)
        if len(cur) >= max_words or len(text) >= max_chars or re.search(r"[.!?,;:]$", w[0]):
            groups.append(cur)
            cur = []
    if cur:
        groups.append(cur)
    return groups


def _ts(t):
    t = max(t, 0)
    return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"


def _ass_color(hex_color, alpha=0):
    n = hex_color.lstrip("#")
    return f"&H{alpha:02X}{n[4:6]}{n[2:4]}{n[0:2]}"


def _clean(text):
    return text.replace("{", "(").replace("}", ")").upper()


def build_ass(words, path, title=None, title_until=3.0, accent="#F2A35E"):
    c = BRAND["captions"]
    fill, outline, hi = _ass_color(c["fill"]), _ass_color(c["outline"]), _ass_color(accent or c["highlight"])
    lines = [
        "[Script Info]", "ScriptType: v4.00+", "PlayResX: 1080", "PlayResY: 1920", "WrapStyle: 0", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        # Captions sit above the bottom UI band that TikTok, Reels, and Shorts cover.
        f"Style: Cap,Barlow Condensed ExtraBold,104,{fill},{fill},{outline},&H64000000,0,0,0,0,100,100,1,0,1,6,3,2,80,80,560,1",
        f"Style: Title,Barlow Condensed ExtraBold,92,{_ass_color(c['outline'])},{fill},{hi},{hi},0,0,0,0,100,100,1,0,3,18,0,8,90,90,250,1",
        "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    if title:
        lines.append(f"Dialogue: 1,{_ts(0)},{_ts(title_until)},Title,,0,0,0,,{{\\fad(150,250)}}{_clean(title)}")
    groups = chunk(words)
    for gi, g in enumerate(groups):
        # Hold the last word a beat, but never into the next chunk, or two lines stack.
        end = g[-1][2] + 0.08
        if gi + 1 < len(groups):
            end = min(end, groups[gi + 1][0][1])
        for k, (_, s, e) in enumerate(g):
            nxt = g[k + 1][1] if k + 1 < len(g) else end
            text = " ".join(
                (f"{{\\c{hi}}}{_clean(w)}{{\\c{fill}}}" if j == k else _clean(w)) for j, (w, _, _) in enumerate(g)
            )
            lines.append(f"Dialogue: 0,{_ts(s)},{_ts(nxt)},Cap,,0,0,0,,{text}")
    open(path, "w").write("\n".join(lines) + "\n")
    return path


def build_srt(words, path):
    out = []
    for i, g in enumerate(chunk(words, 6, 36), 1):
        f = lambda t: f"{int(t // 3600):02d}:{int(t % 3600 // 60):02d}:{int(t % 60):02d},{int(t * 1000 % 1000):03d}"
        out.append(f"{i}\n{f(g[0][1])} --> {f(g[-1][2])}\n{' '.join(w for w, _, _ in g)}\n")
    open(path, "w").write("\n".join(out))
    return path
