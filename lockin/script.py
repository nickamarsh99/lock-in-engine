"""Read engine video scripts: spoken lines vs. on-screen cues."""
import re

CUE = re.compile(r"^\[\s*on screen:?\s*(.*?)\]$", re.I)
LABEL = re.compile(r"^(HOOK|CTA)\s*(\([^)]*\))?\s*:\s*", re.I)


def parse(text):
    spoken, cues = [], []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        m = CUE.match(line)
        if m:
            cues.append(m.group(1).strip())
        else:
            spoken.append(LABEL.sub("", line))
    return spoken, cues
