
import html
import json
import re
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

ROOT = Path(__file__).resolve().parent.parent
PLAN_PATH = ROOT / "reports" / "content_plan.json"
MANIFEST_PATH = ROOT / "reports" / "media_manifest.json"
CONFIG_PATH = ROOT / "discovery" / "sources.json"
MEDIA_DIR = ROOT / "assets" / "media"

COMMONS_API = "https://commons.wikimedia.org/w/api.php"

HEADERS = {
    "User-Agent": "ClipForge/1.0 (rights-aware gaming media discovery)"
}

MAX_STORIES = 5
RESULTS_PER_SEARCH = 8
MAX_IMAGE_BYTES = 25 * 1024 * 1024
MAX_VIDEO_BYTES = 120 * 1024 * 1024
REQUEST_TIMEOUT = 30

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
VIDEO_EXTENSIONS = {".webm", ".ogv", ".mp4"}


def clean(value):
    value = html.unescape(str(value or ""))
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def safe_name(value):
    value = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(value))
    return value.strip("_")[:80] or "asset"


def get_metadata(extmetadata, key):
    value = extmetadata.get(key, {})
    return clean(value.get("value", ""))


def license_details(extmetadata):
    short_name = get_metadata(extmetadata, "LicenseShortName")
    license_url = get_metadata(extmetadata, "LicenseUrl")
    usage_terms = get_metadata(extmetadata, "UsageTerms")

    normalized = short_name.lower()
    url = license_url.lower()

    if "creativecommons.org/licenses/by-sa/" in url or "cc by-sa" in normalized:
        license_name = short_name or "CC BY-SA"
        accepted = True

    elif "creativecommons.org/licenses/by/" in url or re.search(r"\bcc by\b", normalized):
        license_name = short_name or "CC BY"
        accepted = True

    elif "creativecommons.org/publicdomain/zero/" in url or "cc0" in normalized:
        license_name = short_name or "CC0"
        accepted = True

    elif "public domain" in normalized or "public domain" in usage_terms.lower():
        license_name = short_name or "Public Domain"
        accepted = True

    else:
        license_name = short_name or "Unknown"
        accepted = False

    return {
        "license": license_name,
        "license_url": license_url,
        "usage_terms": usage_terms,
        "accepted": accepted
    }


def search_commons(query):
    params = {
        "action": "query",
        "format": "json",
        "list": "search",
        "srnamespace": 6,
        "srsearch": query,
        "srlimit": RESULTS_PER_SEARCH
    }

    response = requests.get(
        COMMONS_API,
        params=params,
        headers=HEADERS,
        timeout=REQUEST_TIMEOUT
    )
    response.raise_for_status()

    return response.json().get("query", {}).get("search", [])


def fetch_file_information(page_ids):
    if not page_ids:
        return []

    params = {
        "action": "query",
        "format": "json",
        "pageids": "|".join(str(page_id) for page_id in page_ids),
        "prop": "imageinfo",
        "iiprop": "url|mime|size|extmetadata",
        "iiurlwidth": 1600
    }

    response = requests.get(
        COMMONS_API,
        params=params,
        headers=HEADERS,
        timeout=REQUEST_TIMEOUT
    )
    response.raise_for_status()

    pages = response.json().get("query", {}).get("pages", {})

    return list(pages.values())


def determine_kind(mime, original_url):
    mime = str(mime or "").lower()
    extension = Path(urlparse(original_url).path).suffix.lower()

    if mime.startswith("image/") or extension in IMAGE_EXTENSIONS:
        return "image"

    if mime.startswith("video/") or extension in VIDEO_EXTENSIONS:
        return "video"

    return ""


def make_search_queries(idea):
    title = clean(idea.get("title", ""))
    category = clean(idea.get("category", "Gaming"))

    words = re.findall(r"[a-zA-Z0-9]+", title)

    stop_words = {
        "the", "and", "for", "with", "from", "this",
        "that", "what", "when", "will", "has", "have",
        "new", "how", "why", "about", "after", "before"
    }

    useful_words = [
        word for word in words
        if word.lower() not in stop_words
    ]

    focused_title = " ".join(useful_words[:5])

    queries = []

    if focused_title:
        queries.append(focused_title)

    if category:
        queries.append(f"{category} video game")

    # Keep searches unique and avoid overly broad empty queries.
    return list(dict.fromkeys(queries))


def inspect_result(page):
    page_id = page.get("pageid")
    title = clean(page.get("title", ""))

    if not page_id:
        return None

    information = fetch_file_information([page_id])

    if not information:
        return None

    imageinfo = information[0].get("imageinfo", [])

    if not imageinfo:
        return None

    info = imageinfo[0]
    original_url = info.get("url", "")
    mime = info.get("mime", "")

    kind = determine_kind(mime, original_url)

    if not kind:
        return None

    metadata = info.get("extmetadata", {})
    license_info = license_details(metadata)

    creator = get_metadata(metadata, "Artist")
    credit = get_metadata(metadata, "Credit")
    description = get_metadata(metadata, "ImageDescription")
    attribution_required = (
        get_metadata(metadata, "AttributionRequired").lower()
        in ("true", "yes", "1")
    )

    # CC BY and CC BY-SA require attribution. If the creator
    # cannot be identified, do not automatically approve the asset.
    attribution_missing = (
        attribution_required
        and not creator
        and not credit
    )

    approved = license_info["accepted"] and not attribution_missing

    description_url = (
        "https://commons.wikimedia.org/wiki/"
        + title.replace(" ", "_")
    )

    download_url = (
        info.get("thumburl", original_url)
        if kind == "image"
        else original_url
    )

    return {
        "commons_page_id": page_id,
        "title": title,
        "kind": kind,
        "mime": mime,
        "url": download_url,
        "original_url": original_url,
        "source_url": description_url,
        "creator": creator or credit or "Creator not identified",
        "credit": credit,
        "description": description,
        "license": license_info["license"],
        "license_url": license_info["license_url"],
        "usage_terms": license_info["usage_terms"],
        "attribution_required": attribution_required,
        "approved_for_reuse": approved,
        "rights_status": (
            "approved"
            if approved
            else "creator_attribution_missing"
            if attribution_missing
            else "license_not_accepted"
        ),
        "file_size": info.get("size", 0)
    }


def download_approved_asset(asset, story_id):
    if not asset.get("approved_for_reuse"):
        return ""

    url = asset.get("url", "")
    kind = asset.get("kind", "")

    extension = Path(urlparse(url).path).suffix.lower()

    allowed = (
        IMAGE_EXTENSIONS
        if kind == "image"
        else VIDEO_EXTENSIONS
    )

    if extension not in allowed:
        return ""

    maximum = (
        MAX_IMAGE_BYTES
        if kind == "image"
        else MAX_VIDEO_BYTES
    )

    MEDIA_DIR.mkdir(parents=True, exist_ok=True)

    filename = (
        f"{safe_name(story_id)}_"
        f"{safe_name(asset['commons_page_id'])}{extension}"
    )

    destination = MEDIA_DIR / filename

    if destination.exists():
        return str(destination.relative_to(ROOT))

    try:
        with requests.get(
            url,
            headers=HEADERS,
            stream=True,
            timeout=REQUEST_TIMEOUT
        ) as response:
            response.raise_for_status()

            content_length = int(
                response.headers.get("Content-Length", "0") or 0
            )

            if content_length > maximum:
                print(f"Skipped oversized asset: {asset['title']}")
                return ""

            downloaded = 0

            with open(destination, "wb") as file:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if not chunk:
                        continue

                    downloaded += len(chunk)

                    if downloaded > maximum:
                        file.close()
                        destination.unlink(missing_ok=True)
                        print(f"Download exceeded size limit: {asset['title']}")
                        return ""

                    file.write(chunk)

        return str(destination.relative_to(ROOT))

    except Exception as error:
        destination.unlink(missing_ok=True)
        print(f"Media download failed: {asset['title']} | {error}")
        return ""


def discover_for_story(idea):
    story_id = idea.get("id") or safe_name(idea.get("title", "story"))

    found = []
    seen = set()

    for query in make_search_queries(idea):
        print(f"Searching Commons: {query}")

        try:
            results = search_commons(query)
        except Exception as error:
            print(f"Commons search failed: {error}")
            continue

        for result in results:
            page_id = result.get("pageid")

            if not page_id or page_id in seen:
                continue

            seen.add(page_id)

            try:
                asset = inspect_result(result)

                if not asset:
                    continue

                asset["story_id"] = story_id
                asset["story_title"] = idea.get("title", "")
                asset["discovery_source"] = "Wikimedia Commons"

                if asset["approved_for_reuse"]:
                    asset["local_path"] = download_approved_asset(
                        asset,
                        story_id
                    )

                    if not asset["local_path"]:
                        asset["download_status"] = "failed"
                    else:
                        asset["download_status"] = "downloaded"
                else:
                    asset["local_path"] = ""
                    asset["download_status"] = "not_downloaded"

                found.append(asset)

                time.sleep(0.15)

            except Exception as error:
                print(f"Could not inspect Commons result: {error}")

    return found


def main():
    if not PLAN_PATH.exists():
        raise FileNotFoundError(
            f"Content plan not found: {PLAN_PATH}"
        )

    with open(PLAN_PATH, encoding="utf-8") as file:
        plan = json.load(file)

    with open(CONFIG_PATH, encoding="utf-8") as file:
        config = json.load(file)

    limits = config.get("limits", {})
    max_stories = min(
        MAX_STORIES,
        limits.get("max_videos_per_run", MAX_STORIES)
    )

    ideas = plan.get("ideas", [])[:max_stories]

    all_assets = []
    approved_downloads = 0

    print("ClipForge media discovery starting...")

    for index, idea in enumerate(ideas, 1):
        print(f"\nStory {index}: {idea.get('title', 'Untitled')}")

        assets = discover_for_story(idea)

        # Only downloaded, approved files are sent to the renderer.
        usable = [
            asset for asset in assets
            if asset.get("approved_for_reuse")
            and asset.get("local_path")
        ]

        idea["licensed_media_assets"] = usable

        approved_downloads += len(usable)
        all_assets.extend(assets)

        print(
            f"Media candidates: {len(assets)} | "
            f"Approved and downloaded: {len(usable)}"
        )

    plan["media_discovery"] = {
        "provider": "Wikimedia Commons",
        "completed_at": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ).isoformat(),
        "total_candidates": len(all_assets),
        "approved_downloads": approved_downloads
    }

    with open(PLAN_PATH, "w", encoding="utf-8") as file:
        json.dump(plan, file, indent=2, ensure_ascii=False)

    manifest = {
        "generated_at": plan["media_discovery"]["completed_at"],
        "provider": "Wikimedia Commons",
        "total_candidates": len(all_assets),
        "approved_downloads": approved_downloads,
        "assets": all_assets
    }

    with open(MANIFEST_PATH, "w", encoding="utf-8") as file:
        json.dump(manifest, file, indent=2, ensure_ascii=False)

    print("\n--------------------------------")
    print(f"Stories checked: {len(ideas)}")
    print(f"Media candidates: {len(all_assets)}")
    print(f"Approved downloads: {approved_downloads}")
    print(f"Updated plan: {PLAN_PATH}")
    print(f"Media manifest: {MANIFEST_PATH}")
    print("Media discovery complete.")
    print("--------------------------------")


if __name__ == "__main__":
    main()
