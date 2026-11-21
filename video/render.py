
import json
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
        image.save(filename, "JPEG", quality=90)

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
            return image

        except Exception as error:
            print(f"Background image error: {error}")

    return Image.new("RGB", (WIDTH, HEIGHT), "#101522")


def add_bottom_gradient(image):
    image = image.convert("RGBA")

    gradient = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    pixels = gradient.load()

    start_y = int(HEIGHT * 0.55)

    for y in range(start_y, HEIGHT):
        progress = (y - start_y) / (HEIGHT - start_y)
        alpha = int(175 * (progress ** 1.5))

        for x in range(WIDTH):
            pixels[x, y] = (0, 0, 0, alpha)

    return Image.alpha_composite(image, gradient)


def make_scene(heading, body, scene_number, image_path=None):
    image = load_background(image_path)
    image = add_bottom_gradient(image)

    draw = ImageDraw.Draw(image)

    brand_font = load_font(29)
    title_font = load_font(67)
    body_font = load_font(39)

    # Small branding, without a solid background panel.
    draw.text(
        (65, 75),
        "CLIPFORGE",
        font=brand_font,
        fill=(255, 255, 255, 235),
        stroke_width=2,
        stroke_fill=(0, 0, 0, 150)
    )

    draw.text(
        (65, 120),
        "GAMING NEWS",
        font=load_font(21),
        fill="#65d6ff",
        stroke_width=1,
        stroke_fill=(0, 0, 0, 130)
    )

    # Small cyan accent line.
    draw.rounded_rectangle(
        (65, HEIGHT - 650, 125, HEIGHT - 640),
        radius=5,
        fill="#65d6ff"
    )

    # Headline.
    heading_lines = wrap_text(
        draw,
        heading,
        title_font,
        WIDTH - 130
    )

    y = HEIGHT - 600

    for line in heading_lines[:3]:
        draw.text(
            (65, y),
            line,
            font=title_font,
            fill="white",
            stroke_width=3,
            stroke_fill=(0, 0, 0, 180)
        )
        y += 85

    y += 20

    # Supporting text.
    body_lines = wrap_text(
        draw,
        body,
        body_font,
        WIDTH - 140
    )

    for line in body_lines[:4]:
        if y > HEIGHT - 160:
            break

        draw.text(
            (65, y),
            line,
            font=body_font,
            fill="#e8edf5",
            stroke_width=2,
            stroke_fill=(0, 0, 0, 180)
        )
        y += 54

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
        ("LATEST GAMING NEWS", hook),
        (category.upper(), title),
        ("WHAT YOU NEED TO KNOW", summary or "Read the original report for more details."),
        ("WHAT DO YOU THINK?", "Follow ClipForge for more gaming updates.")
    ]

    clips = []
    video = None

    try:
        for scene_number, (heading, body) in enumerate(scenes, 1):
            frame_image = make_scene(
                heading,
                body,
                scene_number,
                image_path
            )

            frame = np.array(frame_image)

            # Gentle zoom across each scene.
            clip = (
                ImageClip(frame)
                .with_duration(SCENE_DURATION)
                .resized(lambda t: 1.0 + 0.025 * (t / SCENE_DURATION))
                .with_position("center")
            )

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
