
import json
import re
import hashlib
from pathlib import Path
from io import BytesIO

import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFont, ImageEnhance
from moviepy import ImageClip, concatenate_videoclips

ROOT = Path(__file__).resolve().parent.parent
PLAN = ROOT / "reports" / "content_plan.json"
OUTPUT = ROOT / "output"
ASSETS = ROOT / "assets" / "images"

WIDTH = 1080
HEIGHT = 1920
SCENE_DURATION = 4
FPS = 24
MAX_STORIES = 5

HEADERS = {
    "User-Agent": "ClipForge/1.0 (gaming news video renderer)"
}


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


def download_image(url, article_id):
    if not url:
        return None

    ASSETS.mkdir(parents=True, exist_ok=True)

    filename = ASSETS / f"{article_id}.jpg"

    if filename.exists():
        return filename

    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=20
        )
        response.raise_for_status()

        if len(response.content) > 15 * 1024 * 1024:
            print("Image skipped: file too large.")
            return None

        image = Image.open(BytesIO(response.content)).convert("RGB")
        image.thumbnail((1600, 1600))

        image.save(filename, "JPEG", quality=88)

        print(f"Downloaded image: {filename}")

        return filename

    except Exception as error:
        print(f"Image download failed: {error}")
        return None


def load_background(image_path):
    if image_path and Path(image_path).exists():
        try:
            image = Image.open(image_path).convert("RGB")

            image_ratio = image.width / image.height
            target_ratio = WIDTH / HEIGHT

            if image_ratio > target_ratio:
                new_width = int(image.height * target_ratio)
                left = (image.width - new_width) // 2
                image = image.crop(
                    (left, 0, left + new_width, image.height)
                )
            else:
                new_height = int(image.width / target_ratio)
                top = (image.height - new_height) // 2
                image = image.crop(
                    (0, top, image.width, top + new_height)
                )

            image = image.resize((WIDTH, HEIGHT))
            image = ImageEnhance.Brightness(image).enhance(0.48)

            return image

        except Exception as error:
            print(f"Background image error: {error}")

    return Image.new("RGB", (WIDTH, HEIGHT), "#101522")


def make_scene(heading, body, story_number, scene_number, image_path=None):
    image = load_background(image_path)

    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (8, 13, 25, 105))
    image = Image.alpha_composite(image.convert("RGBA"), overlay)

    draw = ImageDraw.Draw(image)

    title_font = load_font(66)
    body_font = load_font(43)
    small_font = load_font(28)

    draw.rounded_rectangle(
        (65, 75, WIDTH - 65, 180),
        radius=28,
        fill=(36, 52, 79, 235)
    )

    draw.text(
        (95, 105),
        "CLIPFORGE / GAMING",
        font=small_font,
        fill="white"
    )

    draw.rounded_rectangle(
        (55, 250, WIDTH - 55, HEIGHT - 260),
        radius=35,
        fill=(10, 16, 29, 175)
    )

    heading_lines = wrap_text(
        draw,
        heading,
        title_font,
        WIDTH - 170
    )

    y = 330

    for line in heading_lines[:3]:
        draw.text(
            (80, y),
            line,
            font=title_font,
            fill="#65d6ff"
        )
        y += 85

    y += 55

    body_lines = wrap_text(
        draw,
        body,
        body_font,
        WIDTH - 170
    )

    for line in body_lines[:12]:
        if y > HEIGHT - 390:
            break

        draw.text(
            (80, y),
            line,
            font=body_font,
            fill="white"
        )
        y += 70

    draw.text(
        (80, HEIGHT - 180),
        f"STORY {story_number}  |  SCENE {scene_number}",
        font=small_font,
        fill="#d4deef"
    )

    return image.convert("RGB")


def create_video(idea, index):
    title = str(idea.get("title", "Gaming News"))
    hook = str(idea.get("hook", title))
    summary = str(idea.get("summary", ""))
    category = str(idea.get("category", "Gaming"))

    article_id = idea.get("id") or hashlib.sha256(
        idea.get("link", title).encode("utf-8")
    ).hexdigest()[:16]

    image_path = download_image(
        idea.get("image_url", ""),
        article_id
    )

    scenes = [
        ("TODAY IN GAMING", hook),
        (category.upper(), title),
        ("THE DETAILS", summary or "More information is available from the original source."),
        ("YOUR TAKE?", "What do you think about this? Follow for more gaming updates.")
    ]

    clips = []
    video = None

    try:
        for scene_number, (heading, body) in enumerate(scenes, 1):
            frame_image = make_scene(
                heading,
                body,
                index,
                scene_number,
                image_path
            )

            frame = np.array(frame_image)

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

        print(f"SUCCESS: Created {filename}")

    finally:
        if video:
            video.close()

        for clip in clips:
            clip.close()


def main():
    print("ClipForge visual renderer starting...")

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
    print("ClipForge rendering complete.")
    print(f"Videos successfully created: {rendered}")
    print(f"Output directory: {OUTPUT}")
    print("--------------------------------")


if __name__ == "__main__":
    main()
