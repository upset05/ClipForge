
import json
import re
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from moviepy import ImageClip, concatenate_videoclips

ROOT = Path(__file__).resolve().parent.parent
PLAN = ROOT / "reports" / "content_plan.json"
OUTPUT = ROOT / "output"

WIDTH = 1080
HEIGHT = 1920
SCENE_DURATION = 4
FPS = 24
MAX_STORIES = 5


def load_font(size):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"
    ]

    for font_path in candidates:
        if Path(font_path).exists():
            return ImageFont.truetype(font_path, size)

    return ImageFont.load_default()


def wrap_text(draw, text, font, max_width):
    words = str(text).split()
    lines = []
    current = ""

    for word in words:
        test = f"{current} {word}".strip()

        if draw.textbbox((0, 0), test, font=font)[2] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word

    if current:
        lines.append(current)

    return lines


def make_scene(heading, body, story_number, scene_number):
    image = Image.new("RGB", (WIDTH, HEIGHT), "#101522")
    draw = ImageDraw.Draw(image)

    title_font = load_font(66)
    body_font = load_font(43)
    small_font = load_font(28)

    draw.rounded_rectangle(
        (65, 75, WIDTH - 65, 180),
        radius=28,
        fill="#24344f"
    )

    draw.text(
        (95, 105),
        "CLIPFORGE / GAMING",
        font=small_font,
        fill="white"
    )

    draw.text(
        (75, 300),
        heading,
        font=title_font,
        fill="#65d6ff"
    )

    y = 470
    max_width = WIDTH - 170

    for line in wrap_text(draw, body, body_font, max_width):
        if y > HEIGHT - 300:
            break

        draw.text(
            (80, y),
            line,
            font=body_font,
            fill="white"
        )
        y += 70

    draw.text(
        (80, HEIGHT - 150),
        f"STORY {story_number}  |  SCENE {scene_number}",
        font=small_font,
        fill="#aab6cc"
    )

    return image


def create_video(idea, index):
    title = str(idea.get("title", "Gaming News"))
    hook = str(idea.get("hook", title))
    summary = str(idea.get("summary", ""))
    category = str(idea.get("category", "Gaming"))

    scenes = [
        ("TODAY IN GAMING", hook),
        (category.upper(), title),
        ("THE DETAILS", summary or "More information is available from the original source."),
        ("YOUR TAKE?", "What do you think? Follow for more gaming updates.")
    ]

    clips = []

    try:
        for scene_number, (heading, body) in enumerate(scenes, 1):
            image = make_scene(
                heading,
                body,
                index,
                scene_number
            )

            # Convert the Pillow image into a NumPy array.
            frame = np.array(image)

            clip = ImageClip(frame).with_duration(SCENE_DURATION)
            clips.append(clip)

        video = concatenate_videoclips(clips, method="compose")

        OUTPUT.mkdir(parents=True, exist_ok=True)

        filename = OUTPUT / f"story_{index}.mp4"

        print(f"Rendering story {index}: {title}")

        video.write_videofile(
            str(filename),
            fps=FPS,
            codec="libx264",
            audio=False,
            logger="bar"
        )

        video.close()

        print(f"SUCCESS: Created {filename}")

    finally:
        for clip in clips:
            clip.close()


def main():
    print("ClipForge video renderer starting...")

    if not PLAN.exists():
        raise FileNotFoundError(
            f"Content plan not found: {PLAN}"
        )

    with open(PLAN, "r", encoding="utf-8") as file:
        plan = json.load(file)

    ideas = plan.get("ideas", [])

    if not ideas:
        print("No content ideas available. Nothing to render.")
        return

    OUTPUT.mkdir(parents=True, exist_ok=True)

    print(f"Content ideas available: {len(ideas)}")

    rendered = 0

    for index, idea in enumerate(ideas[:MAX_STORIES], 1):
        try:
            create_video(idea, index)
            rendered += 1

        except Exception as error:
            print(f"FAILED to render story {index}: {error}")
            raise

    print("--------------------------------")
    print(f"ClipForge rendering complete.")
    print(f"Videos successfully created: {rendered}")
    print(f"Output directory: {OUTPUT}")
    print("--------------------------------")


if __name__ == "__main__":
    main()
