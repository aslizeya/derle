"""Assemble README GIFs from frames captured by the Playwright "capture" project.

    cd apps/web && npm run capture
    python tools/media/make_gif.py

Frames come from apps/web/test-results/frames/<name>/*.png; GIFs go to docs/screenshots/.
Requires Pillow (``pip install pillow``).
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
FRAMES = ROOT / "apps" / "web" / "test-results" / "frames"
OUT = ROOT / "docs" / "screenshots"


def make_gif(
    name: str, *, width: int, frame_ms: int, crop: tuple[int, int, int, int] | None
) -> Path:
    paths = sorted((FRAMES / name).glob("*.png"))
    if not paths:
        raise SystemExit(f"no frames in {FRAMES / name}; run `npm run capture` first")
    frames = []
    for path in paths:
        image = Image.open(path).convert("RGB")
        if crop:
            image = image.crop(crop)
        height = round(image.height * width / image.width)
        image = image.resize((width, height), Image.LANCZOS)
        frames.append(
            image.quantize(colors=128, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
        )
    # Hold the final, finished state a little longer before looping.
    durations = [frame_ms] * (len(frames) - 1) + [2500]
    target = OUT / f"{name}.gif"
    frames[0].save(
        target, save_all=True, append_images=frames[1:], duration=durations, loop=0, optimize=True
    )
    return target


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--width", type=int, default=960)
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    # Landing: the before/after card on the right half of the hero.
    landing = make_gif(
        "landing", width=args.width // 2 + 160, frame_ms=180, crop=(690, 150, 1360, 640)
    )
    upload = make_gif("upload", width=args.width, frame_ms=150, crop=(232, 0, 1360, 860))
    for target in (landing, upload):
        print(f"{target.relative_to(ROOT)}  {target.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
