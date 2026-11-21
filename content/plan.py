
import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "reports"
CONFIG = ROOT / "discovery" / "sources.json"

DEFAULT_MAX_IDEAS = 10
TARGET_MIN_SECONDS = 30
TARGET_MAX_SECONDS = 45
WORDS_PER_MINUTE = 145

# Approximate narration budget for a 30–45 second video.
MIN_TARGET_WORDS = 73
MAX_TARGET_WORDS = 108


def clean(text):
    text = html.unescape(str(text or ""))
    text = re.sub(r"<script\b[^>]*>.*?</script>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<style\b[^>]*>.*?</style>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def classify(text):
    t = text.lower()

    if any(x in t for x in [
        "gta 6", "gta vi", "grand theft auto", "vice city"
    ]):
        return "GTA"

    if "rockstar" in t:
        return "Rockstar"

    if any(x in t for x in [
        "update", "patch", "release", "launch"
    ]):
        return "Updates"

    if any(x in t for x in [
        "playstation", "ps5", "ps4"
    ]):
        return "PlayStation"

    if any(x in t for x in [
        "xbox", "game pass"
    ]):
        return "Xbox"

    if any(x in t for x in [
        "nintendo", "switch"
    ]):
        return "Nintendo"

    if any(x in t for x in [
        "pc gaming", "steam", "graphics card"
    ]):
        return "PC Gaming"

    return "Gaming"


def make_hook(category):
    hooks = {
        "GTA": "GTA fans, here's what the latest report says.",
        "Rockstar": "There's a new Rockstar development to look at.",
        "Updates": "Here's the latest update from the gaming world.",
        "PlayStation": "PlayStation players, here's the latest report.",
        "Xbox": "Xbox players, here's what has been reported.",
        "Nintendo": "Nintendo fans, here's the latest development.",
        "PC Gaming": "PC gamers, here's a story worth checking out.",
        "Gaming": "Here's the latest gaming story."
    }

    return hooks.get(category, hooks["Gaming"])


def split_sentences(text):
    text = clean(text)

    if not text:
        return []

    parts = re.split(r"(?<=[.!?])\s+", text)

    return [
        part.strip()
        for part in parts
        if len(part.strip()) > 12
    ]


def extract_article_text(article):
    """
    Prefer the fuller RSS content when it exists.
    Avoid adding the same summary twice.
    """
    parts = []

    summary = clean(article.get("summary", ""))

    if summary:
        parts.append(summary)

    content = article.get("content", [])

    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict):
                value = clean(item.get("value", ""))
            else:
                value = clean(item)

            if value:
                parts.append(value)

    elif isinstance(content, str):
        value = clean(content)

        if value:
            parts.append(value)

    description = clean(article.get("description", ""))

    if description:
        parts.append(description)

    unique_parts = []
    seen = set()

    for part in parts:
        normalized = part.lower()

        if normalized not in seen:
            seen.add(normalized)
            unique_parts.append(part)

    return " ".join(unique_parts)


def estimate_duration(text):
    words = len(clean(text).split())

    if words == 0:
        return 0

    return round((words / WORDS_PER_MINUTE) * 60)


def select_story_sentences(source_text, title, word_budget):
    """
    Select source sentences without inventing or padding facts.
    Avoid repeating the headline if it already appears in the body.
    """
    sentences = split_sentences(source_text)
    selected = []
    used_words = 0

    normalized_title = clean(title).lower().rstrip(".!?")

    for sentence in sentences:
        normalized = sentence.lower().rstrip(".!?")

        if normalized == normalized_title:
            continue

        sentence_words = len(sentence.split())

        if sentence_words < 4:
            continue

        if used_words + sentence_words > word_budget:
            remaining = word_budget - used_words

            # Do not cut a sentence in half just to hit a word target.
            if remaining < 12:
                break

            continue

        selected.append(sentence)
        used_words += sentence_words

        if used_words >= word_budget:
            break

    return selected


def make_script(title, source_text, category, publisher):
    hook = make_hook(category)

    # Reserve space for the hook, source line and short closing.
    hook_words = len(hook.split())
    ending = "Follow ClipForge for more gaming news."
    ending_words = len(ending.split())

    source_line = (
        f"This report comes from {publisher}."
        if publisher
        else "This is based on the linked news report."
    )

    source_words = len(source_line.split())

    story_budget = (
        MAX_TARGET_WORDS
        - hook_words
        - ending_words
        - source_words
    )

    story_sentences = select_story_sentences(
        source_text,
        title,
        story_budget
    )

    segments = [
        {"label": "HOOK", "text": hook}
    ]

    if story_sentences:
        segments.append({
            "label": "THE STORY",
            "text": " ".join(story_sentences)
        })

    if publisher:
        segments.append({
            "label": "SOURCE",
            "text": source_line
        })

    segments.append({
        "label": "ENDING",
        "text": ending
    })

    narration = " ".join(
        segment["text"] for segment in segments
    )

    word_count = len(narration.split())
    duration = estimate_duration(narration)

    if duration < TARGET_MIN_SECONDS:
        duration_status = "too_short"
    elif duration > TARGET_MAX_SECONDS:
        duration_status = "too_long"
    else:
        duration_status = "within_target"

    return {
        "hook": hook,
        "segments": segments,
        "full_text": narration,
        "word_count": word_count,
        "estimated_duration_seconds": duration,
        "target_duration_seconds": [
            TARGET_MIN_SECONDS,
            TARGET_MAX_SECONDS
        ],
        "duration_status": duration_status,
        "source_sentence_count": len(story_sentences)
    }


def latest_discovery_report():
    files = sorted(
        REPORTS.glob("*.json"),
        key=lambda file: file.stat().st_mtime,
        reverse=True
    )

    for file in files:
        if file.name == "content_plan.json":
            continue

        try:
            with open(file, encoding="utf-8") as source:
                data = json.load(source)

            if isinstance(data.get("articles"), list):
                return file

        except (OSError, json.JSONDecodeError):
            continue

    return None


def main():
    REPORTS.mkdir(parents=True, exist_ok=True)

    if CONFIG.exists():
        with open(CONFIG, encoding="utf-8") as file:
            config = json.load(file)
    else:
        config = {}

    limits = config.get("limits", {})
    max_ideas = int(
        limits.get("max_ideas", DEFAULT_MAX_IDEAS)
    )

    discovery_file = latest_discovery_report()

    if not discovery_file:
        print("No valid discovery report found.")
        return

    with open(discovery_file, encoding="utf-8") as file:
        report = json.load(file)

    candidates = report.get("articles", [])

    selected = []
    seen_links = set()

    for article in candidates:
        title = clean(article.get("title"))
        link = clean(article.get("link"))

        if not title or not link or link in seen_links:
            continue

        seen_links.add(link)

        publisher = clean(article.get("source", ""))
        source_text = extract_article_text(article)

        category = classify(
            f"{title} {source_text}"
        )

        media_assets = article.get("media_assets", [])

        if not isinstance(media_assets, list):
            media_assets = []

        # RSS media remains unapproved until separately checked.
        for asset in media_assets:
            asset["approved_for_reuse"] = False

            if not asset.get("rights_status"):
                asset["rights_status"] = "unverified"

        images = [
            asset["url"]
            for asset in media_assets
            if asset.get("kind") == "image" and asset.get("url")
        ]

        videos = [
            asset["url"]
            for asset in media_assets
            if asset.get("kind") == "video" and asset.get("url")
        ]

        script = make_script(
            title,
            source_text,
            category,
            publisher
        )

        idea = {
            "id": article.get("id", ""),
            "title": title,
            "link": link,
            "summary": clean(article.get("summary", "")),
            "source_text": source_text,
            "score": article.get("score", 0),
            "category": category,
            "source": publisher,
            "source_url": link,
            "feed_url": article.get("feed_url", ""),
            "author": clean(article.get("author", "")),
            "published": article.get("published", ""),
            "hook": script["hook"],
            "script": script["full_text"],
            "script_segments": script["segments"],
            "word_count": script["word_count"],
            "estimated_duration_seconds": (
                script["estimated_duration_seconds"]
            ),
            "target_duration_seconds": (
                script["target_duration_seconds"]
            ),
            "duration_status": script["duration_status"],
            "source_sentence_count": script["source_sentence_count"],
            "image_url": images[0] if images else "",
            "image_urls": images,
            "video_urls": videos,
            "media_assets": media_assets,
            "media_rights_review_required": bool(media_assets),
            "attribution": {
                "publisher": publisher,
                "article_title": title,
                "article_url": link,
                "author": clean(article.get("author", ""))
            }
        }

        selected.append(idea)

        if len(selected) >= max_ideas:
            break

    now = datetime.now(timezone.utc)
    date = now.strftime("%Y-%m-%d")

    plan = {
        "generated_at": now.isoformat(),
        "source_report": discovery_file.name,
        "total_ideas": len(selected),
        "ideas": selected
    }

    plan_path = REPORTS / "content_plan.json"

    with open(plan_path, "w", encoding="utf-8") as file:
        json.dump(
            plan,
            file,
            indent=2,
            ensure_ascii=False
        )

    markdown_path = REPORTS / f"ideas-{date}.md"

    with open(markdown_path, "w", encoding="utf-8") as file:
        file.write(f"# ClipForge Content Plan — {date}\n\n")
        file.write(f"Generated ideas: {len(selected)}\n\n")

        for index, idea in enumerate(selected, 1):
            file.write(
                f"## Story {index}: {idea['category']}\n\n"
            )
            file.write(f"**Title:** {idea['title']}\n\n")
            file.write(f"**Publisher:** {idea['source']}\n\n")
            file.write(f"**Hook:** {idea['hook']}\n\n")
            file.write(
                f"**Estimated duration:** "
                f"{idea['estimated_duration_seconds']} seconds\n\n"
            )
            file.write(
                f"**Duration status:** {idea['duration_status']}\n\n"
            )
            file.write(
                f"**Word count:** {idea['word_count']}\n\n"
            )
            file.write("**Narration:**\n\n")

            for segment in idea["script_segments"]:
                file.write(
                    f"**{segment['label']}:** "
                    f"{segment['text']}\n\n"
                )

            file.write("**Media candidates:**\n\n")

            if idea["media_assets"]:
                for asset in idea["media_assets"]:
                    file.write(
                        f"- {asset.get('kind', 'unknown')}: "
                        f"{asset.get('url', '')}\n"
                    )
                    file.write(
                        f"  - Creator: "
                        f"{asset.get('creator') or 'Unknown'}\n"
                    )
                    file.write(
                        f"  - Rights: "
                        f"{asset.get('rights_status', 'unverified')}\n"
                    )
                    file.write("  - Approved: No\n")
            else:
                file.write("No media candidates found.\n")

            file.write(
                f"\n**Original article:** {idea['link']}\n\n"
            )
            file.write("---\n\n")

    with_images = sum(
        bool(idea["image_urls"]) for idea in selected
    )

    with_videos = sum(
        bool(idea["video_urls"]) for idea in selected
    )

    within_target = sum(
        idea["duration_status"] == "within_target"
        for idea in selected
    )

    too_short = sum(
        idea["duration_status"] == "too_short"
        for idea in selected
    )

    print("--------------------------------")
    print(f"Generated ideas: {len(selected)}")
    print(f"Ideas with images: {with_images}")
    print(f"Ideas with video candidates: {with_videos}")
    print(f"Scripts within target: {within_target}")
    print(f"Scripts too short: {too_short}")
    print(f"Plan: {plan_path}")
    print("Content planning complete.")
    print("--------------------------------")


if __name__ == "__main__":
    main()
