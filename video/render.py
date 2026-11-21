
import json
import hashlib
import subprocess
import wave
import math
import random
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
VOICE_DIR = ROOT / "assets" / "voices"

VOICE_MODEL = VOICE_DIR / "en_US-lessac-medium.onnx"

WIDTH = 1080
HEIGHT = 1920
FPS = 24
MAX_STORIES = 5
SAMPLE_RATE = 44100

MUSIC_VOLUME = 0.12
VOICE_VOLUME = 1.0
SCENE_PAUSE = 0.35

HEADERS = {
    "User-Agent": "ClipForge/2.0 (gaming news renderer)"
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


def get_image_urls(idea):
    """Read multiple image URLs when the content planner provides them."""
    urls = []

    supplied = idea.get("image_urls", [])

    if isinstance(supplied, list):
        urls.extend(supplied)

    primary = idea.get("image_url")

    if primary:
        urls.append(primary)

    unique = []

    for url in urls:
        if isinstance(url, str) and url.startswith(("http://", "https://")):
            if url not in unique:
                unique.append(url)

    return unique


def download_images(urls, article_id):
    ASSETS.mkdir(parents=True, exist_ok=True)

    downloaded = []

    for index, url in enumerate(urls[:8]):
        filename = ASSETS / f"{article_id}_{index}.jpg"

        if filename.exists():
            downloaded.append(filename)
            continue

        try:
            response = requests.get(
                url,
                headers=HEADERS,
                timeout=20
            )
            response.raise_for_status()

            if len(response.content) > 15 * 1024 * 1024:
                continue

            image = Image.open(
                BytesIO(response.content)
            ).convert("RGB")

            if image.width < 300 or image.height < 200:
                continue

            image.thumbnail((1800, 1800))
            image.save(filename, "JPEG", quality=90)

            downloaded.append(filename)

            print(f"Image downloaded: {filename.name}")

        except Exception as error:
            print(f"Image download failed: {error}")

    return downloaded


def load_background(image_path, scene_number):
    if image_path and Path(image_path).exists():
        image = Image.open(image_path).convert("RGB")

        # Use different framing when the article only has one image.
        image_ratio = image.width / image.height
        target_ratio = WIDTH / HEIGHT

        if image_ratio > target_ratio:
            crop_width = int(image.height * target_ratio)
            available = image.width - crop_width

            offset = int(
                available * ((scene_number * 0.23) % 1)
            )

            image = image.crop(
                (offset, 0, offset + crop_width, image.height)
            )
        else:
            crop_height = int(image.width / target_ratio)
            available = image.height - crop_height

            offset = int(
                available * ((scene_number * 0.23) % 1)
            )

            image = image.crop(
                (0, offset, image.width, offset + crop_height)
            )

        image = image.resize((WIDTH, HEIGHT))
        image = ImageEnhance.Brightness(image).enhance(0.82)

        return image

    return Image.new("RGB", (WIDTH, HEIGHT), "#101522")


def add_bottom_gradient(image):
    image = image.convert("RGBA")

    gradient = Image.new(
        "RGBA",
        (WIDTH, HEIGHT),
        (0, 0, 0, 0)
    )

    pixels = gradient.load()
    start_y = int(HEIGHT * 0.57)

    for y in range(start_y, HEIGHT):
        progress = (y - start_y) / (HEIGHT - start_y)
        alpha = int(205 * (progress ** 1.4))

        for x in range(WIDTH):
            pixels[x, y] = (0, 0, 0, alpha)

    return Image.alpha_composite(image, gradient)


def make_scene(heading, caption, image_path, scene_number):
    image = load_background(image_path, scene_number)
    image = add_bottom_gradient(image)

    draw = ImageDraw.Draw(image)

    brand_font = load_font(29)
    title_font = load_font(65)
    caption_font = load_font(39)

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
        y += 82

    # Captions are placed below the heading.
    y += 25

    caption_lines = wrap_text(
        draw,
        caption,
        caption_font,
        WIDTH - 140
    )

    for line in caption_lines[:5]:
        if y > HEIGHT - 130:
            break

        draw.text(
            (65, y),
            line,
            font=caption_font,
            fill="#e8edf5",
            stroke_width=2,
            stroke_fill=(0, 0, 0, 190)
        )

        y += 55

    return image.convert("RGB")


def generate_narration(text, filename):
    """Generate neural narration using Piper."""
    clean_text = " ".join(str(text).split())

    if not clean_text:
        return False

    if not VOICE_MODEL.exists():
        raise FileNotFoundError(
            f"Piper voice model missing: {VOICE_MODEL}"
        )

    try:
        subprocess.run(
            [
                "piper",
                "--model", str(VOICE_MODEL),
                "--output_file", str(filename),
                "--length_scale", "1.05"
            ],
            input=clean_text,
            text=True,
            capture_output=True,
            check=True,
            timeout=90
        )

        return Path(filename).exists()

    except Exception as error:
        print(f"Piper narration failed: {error}")
        raise


def audio_duration(filename):
    with wave.open(str(filename), "rb") as audio:
        return audio.getnframes() / audio.getframerate()


def generate_music(filename, duration):
    """Generate the original calming electronic background track."""
    AUDIO.mkdir(parents=True, exist_ok=True)

    sample_count = max(1, int(SAMPLE_RATE * duration))
    times = np.arange(sample_count) / SAMPLE_RATE

    audio = np.zeros(sample_count, dtype=np.float64)

    frequencies = [110, 164.81, 220, 329.63]

    for index, frequency in enumerate(frequencies):
        amplitude = 0.12 if index < 2 else 0.055

        audio += amplitude * np.sin(
            2 * math.pi * frequency * times + index * 0.7
        )

    pulse = 0.78 + 0.22 * np.sin(
        2 * math.pi * 1.5 * times
    )

    audio *= pulse

    fade_length = min(
        int(SAMPLE_RATE * 1.5),
        sample_count // 2
    )

    envelope = np.ones(sample_count)

    if fade_length > 0:
        envelope[:fade_length] = np.linspace(
            0, 1, fade_length
        )

        envelope[-fade_length:] = np.linspace(
            1, 0, fade_length
        )

    audio *= envelope
    audio = np.clip(audio, -0.85, 0.85)

    stereo = np.column_stack((audio, audio))
    pcm = (stereo * 32767).astype(np.int16)

    with wave.open(str(filename), "wb") as output:
        output.setnchannels(2)
        output.setsampwidth(2)
        output.setframerate(SAMPLE_RATE)
        output.writeframes(pcm.tobytes())


def build_scenes(idea):
    title = str(idea.get("title", "Gaming News"))
    hook = str(idea.get("hook", title))
    summary = str(idea.get("summary", "")).strip()
    category = str(idea.get("category", "Gaming"))

    if not summary:
        summary = title

    # Keep the narration meaningful rather than repeating the same
    # sentence in several scenes.
    return [
        {
            "heading": "THE LATEST",
            "narration": hook
        },
        {
            "heading": category.upper(),
            "narration": title
        },
        {
            "heading": "HERE'S WHAT HAPPENED",
            "narration": summary
        },
        {
            "heading": "THE BIG QUESTION",
            "narration": (
                "What do you think about this development? "
                "Follow ClipForge for more gaming news."
            )
        }
    ]


def create_video(idea, index):
    title = str(idea.get("title", "Gaming News"))

    article_id = idea.get("id") or hashlib.sha256(
        idea.get("link", title).encode("utf-8")
    ).hexdigest()[:16]

    print(f"\nPreparing story {index}: {title}")

    image_urls = get_image_urls(idea)
    images = download_images(image_urls, article_id)

    print(f"Usable images: {len(images)}")

    scenes = build_scenes(idea)

    AUDIO.mkdir(parents=True, exist_ok=True)
    OUTPUT.mkdir(parents=True, exist_ok=True)

    voice_files = []
    voice_clips = []
    video_clips = []

    music_clip = None
    final_audio = None
    video = None

    try:
        # Generate all narration before deciding scene durations.
        for scene_number, scene in enumerate(scenes):
            voice_path = AUDIO / (
                f"voice_{article_id}_{scene_number}.wav"
            )

            generate_narration(
                scene["narration"],
                voice_path
            )

            duration = audio_duration(voice_path)

            scene["voice_path"] = voice_path
            scene["duration"] = duration + SCENE_PAUSE

            voice_files.append(voice_path)

            print(
                f"Scene {scene_number + 1}: "
                f"{duration:.1f}s narration"
            )

        total_duration = sum(
            scene["duration"] for scene in scenes
        )

        print(f"Video duration: {total_duration:.1f} seconds")

        # Create music to match the complete video.
        music_path = AUDIO / f"music_{article_id}.wav"
        generate_music(music_path, total_duration)

        music_clip = AudioFileClip(str(music_path))

        music_clip = music_clip.with_volume_scaled(
            MUSIC_VOLUME
        )

        voice_timeline = []
        current_time = 0

        for scene_number, scene in enumerate(scenes):
            # Rotate through available images. If only one exists,
            # use different crops for each scene.
            image_path = (
                images[scene_number % len(images)]
                if images else None
            )

            frame_image = make_scene(
                scene["heading"],
                scene["narration"],
                image_path,
                scene_number
            )

            frame = np.array(frame_image)

            clip = ImageClip(frame).with_duration(
                scene["duration"]
            )

            video_clips.append(clip)

            voice = AudioFileClip(
                str(scene["voice_path"])
            )

            voice = voice.with_start(current_time)
            voice = voice.with_volume_scaled(VOICE_VOLUME)

            voice_clips.append(voice)
            voice_timeline.append(voice)

            current_time += scene["duration"]

        video = concatenate_videoclips(
            video_clips,
            method="compose"
        )

        final_audio = CompositeAudioClip(
            [music_clip] + voice_timeline
        ).with_duration(video.duration)

        video = video.with_audio(final_audio)

        filename = OUTPUT / f"story_{index}.mp4"

        print(f"Rendering: {filename.name}")

        video.write_videofile(
            str(filename),
            fps=FPS,
            codec="libx264",
            audio_codec="aac",
            audio_bitrate="192k",
            preset="medium",
            logger="bar"
        )

        print(
            f"SUCCESS: {filename.name} "
            f"({video.duration:.1f} seconds)"
        )

    finally:
        if video:
            video.close()

        if final_audio:
            final_audio.close()

        for clip in video_clips:
            clip.close()

        for clip in voice_clips:
            clip.close()

        if music_clip:
            music_clip.close()


def main():
    print("ClipForge 2.0 renderer starting...")

    if not PLAN.exists():
        raise FileNotFoundError(
            f"Content plan not found: {PLAN}"
        )

    with open(PLAN, "r", encoding="utf-8") as file:
        plan = json.load(file)

    ideas = plan.get("ideas", [])

    if not ideas:
        print("No content ideas available.")
        return

    rendered = 0

    for index, idea in enumerate(
        ideas[:MAX_STORIES], 1
    ):
        create_video(idea, index)
        rendered += 1

    print("--------------------------------")
    print("ClipForge rendering complete.")
    print(f"Videos successfully created: {rendered}")
    print("--------------------------------")


if __name__ == "__main__":
    main()
