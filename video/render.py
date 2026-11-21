
import json
import hashlib
import subprocess
import wave
import math
from pathlib import Path
from io import BytesIO

import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFont, ImageEnhance
from moviepy import (
    ImageClip,
    AudioFileClip,
    CompositeAudioClip,
    concatenate_videoclips
)

ROOT = Path(__file__).resolve().parent.parent
PLAN = ROOT / "reports" / "content_plan.json"
OUTPUT = ROOT / "output"
ASSETS = ROOT / "assets" / "images"
AUDIO = ROOT / "assets" / "audio"

WIDTH = 1080
HEIGHT = 1920
SCENE_DURATION = 4
FPS = 24
MAX_STORIES = 5
SAMPLE_RATE = 44100

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

            return image.resize((WIDTH, HEIGHT))

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


def make_scene(heading, body, image_path=None):
    image = load_background(image_path)
    image = add_bottom_gradient(image)

    draw = ImageDraw.Draw(image)

    brand_font = load_font(29)
    title_font = load_font(67)
    body_font = load_font(39)

    draw.text(
        (65, 75),
        "CLIPFORGE",
        font=brand_font,
        fill="white",
        stroke_width=2,
        stroke_fill=(0, 0, 0, 150)
    )

    draw.text(
        (65, 120),
        "GAMING NEWS",
        font=load_font(21),
        fill="#65d6ff"
    )

    draw.rounded_rectangle(
        (65, HEIGHT - 650, 125, HEIGHT - 640),
        radius=5,
        fill="#65d6ff"
    )

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


def generate_music(filename, duration):
    """Generate an original electronic background track."""
    AUDIO.mkdir(parents=True, exist_ok=True)

    sample_count = int(SAMPLE_RATE * duration)
    audio = np.zeros(sample_count, dtype=np.float64)

    frequencies = [110, 164.81, 220, 329.63]

    for index, frequency in enumerate(frequencies):
        amplitude = 0.12 if index < 2 else 0.055
        phase = index * 0.7

        audio += amplitude * np.sin(
            2 * math.pi * frequency *
            np.arange(sample_count) / SAMPLE_RATE + phase
        )

    # Gentle pulsing electronic rhythm.
    times = np.arange(sample_count) / SAMPLE_RATE
    pulse = 0.78 + 0.22 * np.sin(2 * math.pi * 1.5 * times)
    audio *= pulse

    # Smooth fade in and fade out.
    fade_length = min(int(SAMPLE_RATE * 1.2), sample_count // 2)
    envelope = np.ones(sample_count)

    envelope[:fade_length] = np.linspace(0, 1, fade_length)
    envelope[-fade_length:] = np.linspace(1, 0, fade_length)

    audio *= envelope
    audio = np.clip(audio, -0.85, 0.85)

    stereo = np.column_stack((audio, audio))

    pcm = (stereo * 32767).astype(np.int16)

    with wave.open(str(filename), "wb") as output:
        output.setnchannels(2)
        output.setsampwidth(2)
        output.setframerate(SAMPLE_RATE)
        output.writeframes(pcm.tobytes())


def generate_narration(text, filename):
    """Generate offline speech using eSpeak NG."""
    clean_text = " ".join(str(text).split())[:260]

    if not clean_text:
        return False

    try:
        subprocess.run(
            [
                "espeak-ng",
                "-v", "en-us",
                "-s", "165",
                "-a", "170",
                "-w", str(filename),
                clean_text
            ],
            check=True,
            capture_output=True,
            timeout=30
        )

        return Path(filename).exists()

    except Exception as error:
        print(f"Narration generation failed: {error}")
        return False


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
        ("LATEST GAMING NEWS", hook, hook),
        (category.upper(), title, title),
        (
            "WHAT YOU NEED TO KNOW",
            summary or "Read the original report for more details.",
            summary or title
        ),
        (
            "WHAT DO YOU THINK?",
            "Follow ClipForge for more gaming updates.",
            "Follow ClipForge for more gaming updates."
        )
    ]

    clips = []
    audio_clips = []
    video = None
    final_audio = None

    AUDIO.mkdir(parents=True, exist_ok=True)

    try:
        music_path = AUDIO / f"music_{article_id}.wav"
        generate_music(music_path, SCENE_DURATION * len(scenes))

        music_clip = AudioFileClip(str(music_path))
        audio_clips.append(music_clip.with_volume_scaled(0.16))

        for scene_number, (heading, body, narration) in enumerate(scenes):
            frame_image = make_scene(
                heading,
                body,
                image_path
            )

            frame = np.array(frame_image)

            clip = ImageClip(frame).with_duration(SCENE_DURATION)
            clips.append(clip)

            narration_path = AUDIO / f"voice_{article_id}_{scene_number}.wav"

            if generate_narration(narration, narration_path):
                voice = AudioFileClip(str(narration_path))
                audio_clips.append(
                    voice
                    .with_start(scene_number * SCENE_DURATION)
                    .with_volume_scaled(1.0)
                )
                print(f"Voice generated for scene {scene_number + 1}")

        video = concatenate_videoclips(clips, method="compose")

        final_audio = CompositeAudioClip(audio_clips).with_duration(
            video.duration
        )

        video = video.with_audio(final_audio)

        OUTPUT.mkdir(parents=True, exist_ok=True)
        filename = OUTPUT / f"story_{index}.mp4"

        print(f"Rendering story {index}: {title}")

        video.write_videofile(
            str(filename),
            fps=FPS,
            codec="libx264",
            audio_codec="aac",
            audio_bitrate="192k",
            logger="bar"
        )

        print(f"SUCCESS: Created {filename}")

    finally:
        if video:
            video.close()

        if final_audio:
            final_audio.close()

        for clip in clips:
            clip.close()

        for clip in audio_clips:
            clip.close()


def main():
    print("ClipForge visual and audio renderer starting...")

    if not PLAN.exists():
        raise FileNotFoundError(f"Content plan not found: {PLAN}")

    with open(PLAN, "r", encoding="utf-8") as file:
        plan = json.load(file)

    ideas = plan.get("ideas", [])

    if not ideas:
        print("No content ideas available.")
        return

    OUTPUT.mkdir(parents=True, exist_ok=True)

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
    print("--------------------------------")


if __name__ == "__main__":
    main()
