
import hashlib
import html
import json
import math
import re
import subprocess
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageEnhance
from moviepy import (
    ImageClip,
    VideoFileClip,
    AudioFileClip,
    CompositeAudioClip,
    CompositeVideoClip,
    concatenate_videoclips
)

ROOT = Path(__file__).resolve().parent.parent

PLAN = ROOT / "reports" / "content_plan.json"
OUTPUT = ROOT / "output"
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
SCENE_PAUSE = 0.25

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
VIDEO_EXTENSIONS = {".mp4", ".webm", ".ogv", ".mov", ".m4v"}


def load_font(size):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"
    ]

    for font_path in candidates:
        if Path(font_path).exists():
            return ImageFont.truetype(font_path, size)

    return ImageFont.load_default()


def clean_text(value):
    value = html.unescape(str(value or ""))
    return re.sub(r"\s+", " ", value).strip()


def split_sentences(text):
    text = clean_text(text)

    if not text:
        return []

    return [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+", text)
        if sentence.strip()
    ]


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


def get_licensed_assets(idea):
    """
    Accept only downloaded assets explicitly approved
    by the media discovery component.
    """
    assets = []

    for asset in idea.get("licensed_media_assets", []):
        if not isinstance(asset, dict):
            continue

        if asset.get("approved_for_reuse") is not True:
            continue

        relative_path = asset.get("local_path", "")

        if not relative_path:
            continue

        path = (ROOT / relative_path).resolve()

        try:
            path.relative_to(ROOT)
        except ValueError:
            print("Skipped media outside project directory.")
            continue

        if not path.is_file():
            continue

        kind = asset.get("kind", "")
        extension = path.suffix.lower()

        if kind == "image" and extension in IMAGE_EXTENSIONS:
            assets.append({
                "path": path,
                "kind": "image",
                "metadata": asset
            })

        elif kind == "video" and extension in VIDEO_EXTENSIONS:
            assets.append({
                "path": path,
                "kind": "video",
                "metadata": asset
            })

    # Avoid using the same local file twice.
    unique = []
    seen_paths = set()

    for asset in assets:
        key = str(asset["path"])

        if key not in seen_paths:
            seen_paths.add(key)
            unique.append(asset)

    return unique


def get_credit_line(asset):
    if not asset:
        return "CLIPFORGE ORIGINAL VISUAL"

    metadata = asset["metadata"]

    creator = clean_text(metadata.get("creator", ""))
    license_name = clean_text(metadata.get("license", ""))

    if not creator:
        creator = "Creator not identified"

    if not license_name:
        license_name = "Licence information unavailable"

    return f"MEDIA: {creator} | {license_name}"


def create_original_background(scene_number):
    """
    Create an original ClipForge background when no unused
    approved media remains. No external media is reused.
    """
    image = Image.new(
        "RGB",
        (WIDTH, HEIGHT),
        "#101522"
    )

    draw = ImageDraw.Draw(image)

    accent_positions = [
        (150, 420),
        (820, 650),
        (250, 1100),
        (850, 1350),
        (500, 850)
    ]

    x, y = accent_positions[scene_number % len(accent_positions)]

    draw.ellipse(
        (x - 260, y - 260, x + 260, y + 260),
        fill="#172b43"
    )

    draw.ellipse(
        (x - 150, y - 150, x + 150, y + 150),
        fill="#1c3854"
    )

    draw.line(
        (0, HEIGHT - 500, WIDTH, HEIGHT - 500),
        fill="#25445e",
        width=3
    )

    return image


def load_background(image_path, scene_number):
    if image_path and image_path.exists():
        try:
            image = Image.open(image_path).convert("RGB")

            image_ratio = image.width / image.height
            target_ratio = WIDTH / HEIGHT

            if image_ratio > target_ratio:
                crop_width = int(image.height * target_ratio)
                left = (image.width - crop_width) // 2

                image = image.crop((
                    left,
                    0,
                    left + crop_width,
                    image.height
                ))
            else:
                crop_height = int(image.width / target_ratio)
                top = (image.height - crop_height) // 2

                image = image.crop((
                    0,
                    top,
                    image.width,
                    top + crop_height
                ))

            image = image.resize(
                (WIDTH, HEIGHT),
                Image.Resampling.LANCZOS
            )

            return ImageEnhance.Brightness(image).enhance(0.85)

        except Exception as error:
            print(f"Image loading failed: {error}")

    return create_original_background(scene_number)


def create_overlay(heading, caption, credit):
    overlay = Image.new(
        "RGBA",
        (WIDTH, HEIGHT),
        (0, 0, 0, 0)
    )

    pixels = np.zeros(
        (HEIGHT, WIDTH, 4),
        dtype=np.uint8
    )

    start_y = int(HEIGHT * 0.48)

    for y in range(start_y, HEIGHT):
        progress = (y - start_y) / (HEIGHT - start_y)
        alpha = int(205 * (progress ** 1.35))

        pixels[y, :, 3] = alpha

    overlay = Image.alpha_composite(
        overlay,
        Image.fromarray(pixels, "RGBA")
    )

    draw = ImageDraw.Draw(overlay)

    brand_font = load_font(29)
    heading_font = load_font(57)
    caption_font = load_font(43)
    credit_font = load_font(18)

    draw.text(
        (65, 75),
        "CLIPFORGE",
        font=brand_font,
        fill="white",
        stroke_width=2,
        stroke_fill=(0, 0, 0, 180)
    )

    draw.text(
        (65, 120),
        "GAMING NEWS",
        font=load_font(21),
        fill="#65d6ff"
    )

    draw.rounded_rectangle(
        (65, HEIGHT - 690, 125, HEIGHT - 680),
        radius=5,
        fill="#65d6ff"
    )

    heading_lines = wrap_text(
        draw,
        heading.upper(),
        heading_font,
        WIDTH - 130
    )

    y = HEIGHT - 640

    for line in heading_lines[:2]:
        draw.text(
            (65, y),
            line,
            font=heading_font,
            fill="white",
            stroke_width=3,
            stroke_fill=(0, 0, 0, 180)
        )
        y += 72

    y += 30

    caption_lines = wrap_text(
        draw,
        caption,
        caption_font,
        WIDTH - 140
    )

    for line in caption_lines[:5]:
        if y > HEIGHT - 180:
            break

        draw.text(
            (65, y),
            line,
            font=caption_font,
            fill="#ffffff",
            stroke_width=2,
            stroke_fill=(0, 0, 0, 190)
        )

        y += 58

    credit = clean_text(credit)

    if len(credit) > 85:
        credit = credit[:82] + "..."

    draw.text(
        (65, HEIGHT - 75),
        credit,
        font=credit_font,
        fill="#dce5ef",
        stroke_width=1,
        stroke_fill=(0, 0, 0, 180)
    )

    return np.array(overlay)


def generate_narration(text, filename):
    if not VOICE_MODEL.exists():
        raise FileNotFoundError(
            f"Piper voice model missing: {VOICE_MODEL}"
        )

    clean = clean_text(text)

    if not clean:
        raise ValueError("Cannot generate empty narration.")

    subprocess.run(
        [
            "piper",
            "--model", str(VOICE_MODEL),
            "--output_file", str(filename),
            "--length_scale", "1.05"
        ],
        input=clean,
        text=True,
        capture_output=True,
        check=True,
        timeout=90
    )

    if not Path(filename).exists():
        raise RuntimeError("Piper did not produce an audio file.")


def audio_duration(filename):
    with wave.open(str(filename), "rb") as audio:
        return audio.getnframes() / audio.getframerate()


def generate_music(filename, duration):
    """Preserve the original calming electronic soundtrack."""
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


def build_narration_units(idea):
    units = []

    segments = idea.get("script_segments", [])

    if not segments:
        segments = [{
            "label": "THE LATEST",
            "text": (
                idea.get("script")
                or idea.get("summary")
                or idea.get("title")
            )
        }]

    for segment in segments:
        heading = clean_text(
            segment.get("label", "GAMING NEWS")
        )

        text = clean_text(segment.get("text", ""))

        if not text:
            continue

        for sentence in split_sentences(text):
            units.append({
                "heading": heading,
                "text": sentence
            })

    if not units:
        raise ValueError("No narration segments available.")

    return units


def prepare_narration(units, article_id):
    total_duration = 0

    for index, unit in enumerate(units):
        voice_path = AUDIO / f"voice_{article_id}_{index}.wav"

        generate_narration(
            unit["text"],
            voice_path
        )

        duration = audio_duration(voice_path)

        unit["voice_path"] = voice_path
        unit["voice_duration"] = duration
        unit["duration"] = duration + SCENE_PAUSE
        unit["start"] = total_duration

        total_duration += unit["duration"]

        print(
            f"Caption {index + 1}: "
            f"{duration:.1f}s | {unit['text'][:65]}"
        )

    return total_duration


def prepare_video_background(path, duration):
    """
    Prepare one approved gameplay clip for one scene.
    Never loop a short clip or reuse it for another scene.
    """
    source = VideoFileClip(str(path))

    if source.duration < duration:
        source.close()
        return None

    clip = source.subclipped(0, duration).without_audio()

    scale = max(
        WIDTH / clip.w,
        HEIGHT / clip.h
    )

    clip = clip.resized(scale)

    clip = clip.cropped(
        x_center=clip.w / 2,
        y_center=clip.h / 2,
        width=WIDTH,
        height=HEIGHT
    )

    return source, clip


def make_visual_clip(unit, asset, duration, unit_index):
    credit = get_credit_line(asset)

    overlay = create_overlay(
        unit["heading"],
        unit["text"],
        credit
    )

    overlay_clip = ImageClip(
        overlay,
        transparent=True
    ).with_duration(duration)

    resources = []

    if asset and asset["kind"] == "video":
        try:
            prepared = prepare_video_background(
                asset["path"],
                duration
            )

            if prepared:
                source, background = prepared
                resources.extend([source, background])

                composite = CompositeVideoClip(
                    [background, overlay_clip],
                    size=(WIDTH, HEIGHT)
                ).with_duration(duration)

                resources.append(overlay_clip)

                return composite, resources

        except Exception as error:
            print(f"Gameplay clip failed: {error}")

    image_path = (
        asset["path"]
        if asset and asset["kind"] == "image"
        else None
    )

    image = load_background(image_path, unit_index)

    background_clip = ImageClip(
        np.array(image)
    ).with_duration(duration)

    composite = CompositeVideoClip(
        [background_clip, overlay_clip],
        size=(WIDTH, HEIGHT)
    ).with_duration(duration)

    resources.extend([
        background_clip,
        overlay_clip
    ])

    return composite, resources


def select_unique_assets(assets, unit_count):
    """
    Use each video once, then each image once.
    Do not recycle third-party media when scenes outnumber assets.
    """
    videos = [
        asset for asset in assets
        if asset["kind"] == "video"
    ]

    images = [
        asset for asset in assets
        if asset["kind"] == "image"
    ]

    queue = videos + images

    return queue[:unit_count]


def build_credits(idea, assets, article_id):
    credits_path = OUTPUT / f"credits_{article_id}.md"

    unique_assets = []
    seen = set()

    for asset in assets:
        key = str(asset["path"])

        if key not in seen:
            seen.add(key)
            unique_assets.append(asset)

    with open(credits_path, "w", encoding="utf-8") as file:
        file.write("# ClipForge Media Credits\n\n")
        file.write(f"**Story:** {idea.get('title', '')}\n\n")

        file.write(
            f"**Publisher:** {idea.get('source', 'Unknown')}\n\n"
        )

        file.write(
            f"**Original news article:** "
            f"{idea.get('source_url') or idea.get('link', '')}\n\n"
        )

        file.write("## Media actually used\n\n")

        if not unique_assets:
            file.write(
                "No third-party media was used. "
                "Original ClipForge backgrounds were used instead.\n"
            )

        for index, asset in enumerate(unique_assets, 1):
            metadata = asset["metadata"]

            file.write(f"### Asset {index}\n\n")
            file.write(f"- Type: {asset['kind']}\n")
            file.write(f"- File: {asset['path'].name}\n")
            file.write(
                f"- Title: {metadata.get('title', 'Untitled')}\n"
            )
            file.write(
                f"- Creator: {metadata.get('creator', 'Unknown')}\n"
            )
            file.write(
                f"- Licence: {metadata.get('license', 'Unknown')}\n"
            )
            file.write(
                f"- Licence URL: {metadata.get('license_url', '')}\n"
            )
            file.write(
                f"- Original source: {metadata.get('source_url', '')}\n"
            )
            file.write("\n")

    return credits_path


def create_video(idea, index):
    title = clean_text(idea.get("title", "Gaming News"))

    article_id = idea.get("id") or hashlib.sha256(
        idea.get("link", title).encode("utf-8")
    ).hexdigest()[:16]

    print(f"\nPreparing story {index}: {title}")

    OUTPUT.mkdir(parents=True, exist_ok=True)
    AUDIO.mkdir(parents=True, exist_ok=True)

    assets = get_licensed_assets(idea)

    print(
        f"Approved media available: {len(assets)} "
        f"({sum(a['kind'] == 'video' for a in assets)} videos, "
        f"{sum(a['kind'] == 'image' for a in assets)} images)"
    )

    units = build_narration_units(idea)

    total_duration = prepare_narration(
        units,
        article_id
    )

    print(f"Total video duration: {total_duration:.1f} seconds")

    music_path = AUDIO / f"music_{article_id}.wav"

    generate_music(
        music_path,
        total_duration
    )

    music_clip = None
    final_audio = None
    final_video = None

    visual_clips = []
    audio_clips = []
    resources = []
    used_assets = []

    try:
        music_clip = AudioFileClip(str(music_path))
        music_clip = music_clip.with_volume_scaled(MUSIC_VOLUME)

        selected_assets = select_unique_assets(
            assets,
            len(units)
        )

        visual_sequence = []

        for unit_index, unit in enumerate(units):
            asset = (
                selected_assets[unit_index]
                if unit_index < len(selected_assets)
                else None
            )

            if asset:
                used_assets.append(asset)
                print(
                    f"Scene {unit_index + 1}: "
                    f"{asset['kind']} - {asset['path'].name}"
                )
            else:
                print(
                    f"Scene {unit_index + 1}: "
                    "Original ClipForge background"
                )

            visual, visual_resources = make_visual_clip(
                unit,
                asset,
                unit["duration"],
                unit_index
            )

            visual_sequence.append(visual)
            visual_clips.append(visual)
            resources.extend(visual_resources)

            voice = AudioFileClip(
                str(unit["voice_path"])
            )

            voice = voice.with_start(unit["start"])
            voice = voice.with_volume_scaled(VOICE_VOLUME)

            audio_clips.append(voice)

        final_video = concatenate_videoclips(
            visual_sequence,
            method="compose"
        )

        final_audio = CompositeAudioClip(
            [music_clip] + audio_clips
        ).with_duration(final_video.duration)

        final_video = final_video.with_audio(final_audio)

        filename = OUTPUT / f"story_{index}.mp4"

        print(f"Rendering {filename.name}...")

        final_video.write_videofile(
            str(filename),
            fps=FPS,
            codec="libx264",
            audio_codec="aac",
            audio_bitrate="192k",
            preset="medium",
            logger="bar"
        )

        credits_path = build_credits(
            idea,
            used_assets,
            article_id
        )

        print("--------------------------------")
        print(f"SUCCESS: {filename.name}")
        print(f"Duration: {final_video.duration:.1f} seconds")
        print(f"Unique third-party assets used: {len(used_assets)}")
        print(f"Credits: {credits_path.name}")
        print("--------------------------------")

    finally:
        if final_video:
            final_video.close()

        if final_audio:
            final_audio.close()

        for clip in visual_clips:
            try:
                clip.close()
            except Exception:
                pass

        for resource in resources:
            try:
                resource.close()
            except Exception:
                pass

        for clip in audio_clips:
            try:
                clip.close()
            except Exception:
                pass

        if music_clip:
            music_clip.close()


def main():
    print("ClipForge 3.1 renderer starting...")

    if not PLAN.exists():
        raise FileNotFoundError(
            f"Content plan not found: {PLAN}"
        )

    with open(PLAN, encoding="utf-8") as file:
        plan = json.load(file)

    ideas = plan.get("ideas", [])

    if not ideas:
        print("No content ideas available.")
        return

    rendered = 0

    for index, idea in enumerate(ideas[:MAX_STORIES], 1):
        create_video(idea, index)
        rendered += 1

    print("--------------------------------")
    print("ClipForge rendering complete.")
    print(f"Videos successfully created: {rendered}")
    print("--------------------------------")


if __name__ == "__main__":
    main()
