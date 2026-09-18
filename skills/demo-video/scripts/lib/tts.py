"""TTS providers behind one contract: synthesize(text, out_path) -> duration ms.

    say       macOS built-in. Korean voice Yuna by default. Accepts Apple prosody markup [[slnc N]] [[rate N]] [[emph +]].
    edge-tts  Microsoft neural voices via the edge-tts CLI (pip install edge-tts). ko-KR-SunHiNeural by default.
              Sends the text to a Microsoft service - not for confidential subtitles (DESIGN A5). Markup is
              stripped; a [[slnc N]] becomes a comma pause, rate maps to a percent offset.
    none      no narration; narrate refuses to run.

Rate is words per minute as macOS `say` counts it; edge-tts gets the same intent as a relative percent
around its default (150 wpm ~ -10%, 180 ~ +5%). Durations are always measured on the rendered file.
"""
import re
import shutil
import subprocess
from pathlib import Path

from . import common

DEFAULT_VOICE = {"say": "Yuna", "edge-tts": "ko-KR-SunHiNeural", "none": None}
MARKUP = re.compile(r"\[\[.*?\]\]")


def spoken_text(text):
    return MARKUP.sub("", text or "").strip()


def available():
    out = []
    if shutil.which("say"):
        out.append("say")
    if shutil.which("edge-tts"):
        out.append("edge-tts")
    return out


def ext(provider):
    return "aiff" if provider == "say" else "mp3"


def check_voice(provider, voice, probe_dir: Path):
    """Synthesize a short probe. Returns None when fine, else the reason."""
    if provider == "none":
        return "narration provider is none"
    if provider not in available():
        return f"{provider} is not installed" + (" (pip install edge-tts)" if provider == "edge-tts" else "")
    probe = probe_dir / f".voice-check.{ext(provider)}"
    try:
        ms = synthesize(provider, voice, 170, "테스트 문장입니다", probe)
    except RuntimeError as e:
        return str(e)
    if ms < 200:
        return f"voice '{voice}' produced no audio - it is listed but not installed"
    return None


def synthesize(provider, voice, rate_wpm, text, out: Path) -> int:
    out.parent.mkdir(parents=True, exist_ok=True)
    if provider == "say":
        r = subprocess.run(["say", "-v", voice, "-r", str(int(rate_wpm)), "-o", str(out), text], capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"say failed: {r.stderr.strip()[-200:]}")
    elif provider == "edge-tts":
        plain = edge_text(text)
        pct = int(round((rate_wpm - 165) / 165 * 100))          # 165 wpm ~ the service default pace
        r = subprocess.run(["edge-tts", "--voice", voice, f"--rate={pct:+d}%", "--text", plain, "--write-media", str(out)],
                           capture_output=True, text=True)
        if r.returncode != 0 or not out.exists():
            raise RuntimeError(f"edge-tts failed: {r.stderr.strip()[-200:]}")
    else:
        raise RuntimeError(f"unknown provider {provider}")
    return common.duration_ms(out)


def edge_text(text):
    """Apple markup -> plain text edge-tts can read: pauses become commas, the rest is dropped."""
    t = re.sub(r"\[\[slnc\s+\d+\]\]", ", ", text)
    t = MARKUP.sub("", t)
    return re.sub(r"\s+", " ", t).strip()
