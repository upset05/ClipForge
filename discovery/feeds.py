
import json
import re
import hashlib
import html
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import feedparser

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "discovery" / "sources.json"
OUTPUT = ROOT / "reports"


def clean(text):
    text = html.unescape(str(text or ""))
    return re.sub(r"\s+", " ", text).strip()


def extract_image(entry):
    """
    Extract the best available image URL from an RSS entry.
    """

    # 1. Media RSS images
    media_content = entry.get("media_content", [])

    for media in media_content:
        image_url = media.get("url", "")
        media_type = media.get("type", "")

        if image_url and (
            media_type.startswith("image/")
            or re.search(r"\.(jpg|jpeg|png|webp)(\?|$)", image_url, re.I)
        ):
            return {
                "url": image_url,
                "caption": clean(media.get("title", "")),
                "source": "media_content"
            }

    # 2. Media thumbnails
    thumbnails = entry.get("media_thumbnail", [])

    if thumbnails:
        image_url = thumbnails[0].get("url", "")

        if image_url:
            return {
                "url": image_url,
                "caption": "",
                "source": "media_thumbnail"
            }

    # 3. Enclosures
    for enclosure in entry.get("enclosures", []):
        image_url = enclosure.get("href") or enclosure.get("url", "")
        media_type = enclosure.get("type", "")

        if image_url and media_type.startswith("image/"):
            return {
                "url": image_url,
                "caption": "",
                "source": "enclosure"
            }

    # 4. Images embedded in the article summary
    summary = entry.get("summary", "")

    image_matches = re.findall(
        r'<img[^>]+src=["\']([^"\']+)["\']',
        summary,
        re.IGNORECASE
    )

    if image_matches:
        return {
            "url": html.unescape(image_matches[0]),
            "caption": "",
            "source": "summary"
        }

    # 5. Images embedded in content blocks
    for content in entry.get("content", []):
        value = content.get("value", "")

        image_matches = re.findall(
            r'<img[^>]+src=["\']([^"\']+)["\']',
            value,
            re.IGNORECASE
        )

        if image_matches:
            return {
                "url": html.unescape(image_matches[0]),
                "caption": "",
                "source": "content"
            }

    return {
        "url": "",
        "caption": "",
        "source": "unavailable"
    }


def score_article(article, keywords, priority):
    text = clean(
        f"{article.get('title', '')} "
        f"{article.get('summary', '')}"
    ).lower()

    score = 0

    for word in keywords:
        if word.lower() in text:
            score += 1

    for word in priority:
        if word.lower() in text:
            score += 5

    return score


def main():
    with open(CONFIG, encoding="utf-8") as file:
        config = json.load(file)

    OUTPUT.mkdir(parents=True, exist_ok=True)

    articles = []
    seen = set()

    print("ClipForge discovery starting...")

    for url in config["feeds"]:
        try:
            print(f"Checking feed: {url}")

            feed = feedparser.parse(url)

            if getattr(feed, "bozo", False):
                print(f"Feed warning: {url}")

            for entry in feed.entries:
                title = clean(entry.get("title"))
                link = entry.get("link", "")

                if not title or not link:
                    continue

                key = hashlib.sha256(
                    link.encode("utf-8")
                ).hexdigest()

                if key in seen:
                    continue

                seen.add(key)

                score = score_article(
                    entry,
                    config["keywords"],
                    config["priority_keywords"]
                )

                if score <= 0:
                    continue

                image = extract_image(entry)

                published = (
                    entry.get("published")
                    or entry.get("updated")
                    or ""
                )

                article = {
                    "id": key[:16],
                    "title": title,
                    "link": link,
                    "summary": clean(entry.get("summary")),
                    "image_url": image["url"],
                    "image_caption": image["caption"],
                    "image_source": image["source"],
                    "score": score,
                    "source": url,
                    "published": published
                }

                articles.append(article)

        except Exception as error:
            print(f"Feed failed: {url} | {error}")

    articles.sort(
        key=lambda item: item["score"],
        reverse=True
    )

    now = datetime.now(timezone.utc)
    date = now.strftime("%Y-%m-%d")

    report = {
        "generated_at": now.isoformat(),
        "total_candidates": len(articles),
        "articles_with_images": sum(
            1 for article in articles
            if article["image_url"]
        ),
        "articles": articles[:50]
    }

    json_path = OUTPUT / f"{date}.json"
    md_path = OUTPUT / f"{date}.md"

    with open(json_path, "w", encoding="utf-8") as file:
        json.dump(
            report,
            file,
            indent=2,
            ensure_ascii=False
        )

    with open(md_path, "w", encoding="utf-8") as file:
        file.write(f"# ClipForge Discovery — {date}\n\n")
        file.write(f"Found {len(articles)} relevant articles.\n\n")
        file.write(
            f"Articles with images: "
            f"{report['articles_with_images']}\n\n"
        )

        for article in articles[:30]:
            file.write(f"## {article['title']}\n\n")
            file.write(f"Score: {article['score']}\n\n")
            file.write(f"{article['summary'][:600]}\n\n")

            if article["image_url"]:
                file.write(
                    f"Image: {article['image_url']}\n\n"
                )
            else:
                file.write("Image: Not available in feed\n\n")

            file.write(f"Source: {article['link']}\n\n")
            file.write("---\n\n")

    print("--------------------------------")
    print(f"Candidates: {len(articles)}")
    print(f"Articles with images: {report['articles_with_images']}")
    print(f"Report: {md_path}")
    print("Discovery complete.")
    print("--------------------------------")


if __name__ == "__main__":
    main()
