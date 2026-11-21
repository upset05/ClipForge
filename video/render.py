import numpy as np
import json
from pathlib import Path
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
from moviepy import ImageClip, concatenate_videoclips

ROOT = Path(__file__).resolve().parent.parent
PLAN = ROOT / "reports" / "content_plan.json"
OUTPUT = ROOT / "output"

WIDTH = 1080
HEIGHT = 1920
DURATION = 4

def load_font(size):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"
    ]

    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)

    return ImageFont.load_default()

def wrap_text(draw, text, font, max_width):
    words = text.split()
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

def make_scene(heading, body, number):
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
        "CLIPFORGE  /  GAMING",
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

    for line in wrap_text(draw, body, body_font, WIDTH - 170):
        draw.text((80, y), line, font=body_font, fill="white")
        y += 70

        if y > HEIGHT - 300:
            break

    draw.text(
        (80, HEIGHT - 150),
        f"STORY {number}  |  CLIPFORGE",
        font=small_font,
        fill="#aab6cc"
    )

    return image

def main():
    if not PLAN.exists():
        raise FileNotFoundError("Content plan not found.")

    with open(PLAN, encoding="utf-8") as file:
        plan = json.load(file)

    ideas = plan.get("ideas", [])

    if not ideas:
        print("No content ideas available.")
        return

    OUTPUT.mkdir(exist_ok=True)

    for index, idea in enumerate(ideas[:5], 1):
        title = idea.get("title", "Gaming News")
        hook = idea.get("hook", title)
        summary = idea.get("summary", "")
        category = idea.get("category", "Gaming")

        scenes = [
            ("TODAY IN GAMING", hook),
            (category.upper(), title),
            ("THE DETAILS", summary or "More information is available from the original source."),
            ("YOUR TAKE?", "What do you think? Follow for more gaming updates.")
        ]

        clips = []

        for heading, body in scenes:
            image = make_scene(heading, body, index)
           clips.append(
    ImageClip(np.array(image)).with_duration(DURATION)
)

        video = concatenate_videoclips(clips, method="compose")

        filename = OUTPUT / f"story_{index}.mp4"

        video.write_videofile(
            str(filename),
            fps=24,
            codec="libx264",
            audio=False,
            logger=None
        )

        video.close()

        print(f"Created: {filename}")

if __name__ == "__main__":
    main()

