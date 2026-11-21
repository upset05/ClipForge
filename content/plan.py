
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


def clean(text):
    text = html.unescape(str(text or ""))
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


def make_hook(title, category):
    if category == "GTA":
        return "GTA fans, here's the latest development you need to know."

    if category == "Rockstar":
        return "Rockstar has a new development worth looking at."

    if category == "Updates":
        return "There's a gaming update you should know about."

    if category == "PlayStation":
        return "PlayStation players, here's what's happening."

    if category == "Xbox":
        return "Xbox players, here's the latest."

    if category == "Nintendo":
        return "Nintendo fans, here's the latest development."

    return "Here's a gaming story worth your attention."


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


def estimate_duration(text):
    words = len(clean(text).split())

    if words == 0:
        return 0

    return round((words / WORDS_PER_MINUTE) * 60)


def make_script(title, summary, category, publisher):
    hook = make_hook(title, category)
    sentences = split_sentences(summary)

    if sentences:
        report_text = " ".join(sentences[:6])
    else:
        report_text = (
            "The available report does not contain enough detail "
            "to explain the development confidently."
        )

    context = f"This story was reported by {publisher}." if publisher else (
        "This story comes from the linked gaming news report."
    )

    takeaway = (
        "We will need further confirmed details before drawing "
        "any bigger conclusions."
    )

    ending = (
        "What do you think about this development? "
        "Follow ClipForge for more gaming news."
    )

    segments = [
        {"label": "HOOK", "text": hook},
        {"label": "STORY", "text": report_text},
        {"label": "SOURCE", "text": context},
        {"label": "TAKEAWAY", "text": takeaway},
        {"label": "ENDING", "text": ending}
    ]

    narration = " ".join(
        segment["text"] for segment in segments
    )

    duration = estimate_duration(narration)

    return {
        "hook": hook,
        "segments": segments,
        "full_text": narration,
        "word_count": len(narration.split()),
        "estimated_duration_seconds": duration,
        "target_duration_seconds": [
            TARGET_MIN_SECONDS,
            TARGET_MAX_SECONDS
        ],
        "duration_status": (
            "within_target"
            if TARGET_MIN_SECONDS <= duration <= TARGET_MAX_SECONDS
            else "too_short"
            if duration < TARGET_MIN_SECONDS
            else "too_long"
        )
    }


def latest_discovery_report():
    files = sorted(
        REPORTS.glob("*.json"),
        key=lambda file: file.stat().st_mtime,
        reverse=True
    )

    for file in files:
        if file.name != "content_plan.json":
            return file

    return None


def main():
    REPORTS.mkdir(parents=True, exist_ok=True)

    if CONFIG.exists():
        with open(CONFIG, encoding="utf-8") as file:
            config = json.load(file)
    else:
        config = {}

    limits = config.get("limits", {})
    max_ideas = limits.get("max_ideas", DEFAULT_MAX_IDEAS)

    discovery_file = latest_discovery_report()

    if not discovery_file:
        print("No discovery report found.")
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
        summary = clean(article.get("summary", ""))
        category = classify(f"{title} {summary}")

        media_assets = article.get("media_assets", [])

        # Keep rights information intact. Discovery alone cannot
        # establish that an image or video is permitted for reuse.
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
            summary,
            category,
            publisher
        )

        idea = {
            "id": article.get("id", ""),
            "title": title,
            "link": link,
            "summary": summary,
            "score": article.get("score", 0),
            "category": category,
            "source": publisher,
            "source_url": link,
            "feed_url": article.get("feed_url", ""),
            "author": article.get("author", ""),
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
            "image_url": images[0] if images else "",
            "image_urls": images,
            "video_urls": videos,
            "media_assets": media_assets,
            "media_rights_review_required": bool(media_assets),
            "attribution": {
                "publisher": publisher,
                "article_title": title,
                "article_url": link,
                "author": article.get("author", "")
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
            file.write("**Script:**\n\n")

            for segment in idea["script_segments"]:
                file.write(
                    f"**{segment['label']}:** "
                    f"{segment['text']}\n\n"
                )

            file.write("**Media candidates:**\n\n")

            if idea["media_assets"]:
                for asset in idea["media_assets"]:
                    file.write(
                        f"- {asset['kind']}: {asset['url']}\n"
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

    print("--------------------------------")
    print(f"Generated ideas: {len(selected)}")
    print(f"Ideas with images: {with_images}")
    print(f"Ideas with video candidates: {with_videos}")
    print(f"Scripts within target duration: {within_target}")
    print(f"Plan: {plan_path}")
    print("Content planning complete.")
    print("--------------------------------")


if __name__ == "__main__":
    main()
