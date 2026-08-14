#!/usr/bin/env python3
"""Build Wan-TV.m3u from public, free upstream IPTV playlists."""

from __future__ import annotations

import re
import sys
import tempfile
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

OUTPUT = Path(__file__).resolve().parents[1] / "Wan-TV.m3u"
FAVORITES_OUTPUT = Path(__file__).resolve().parents[1] / "Wan-TV-Favorites.m3u"
TIMEOUT = 45
USER_AGENT = "Wan-TV/1.0 (+https://github.com/wanshushu1217-netizen/Wan-TV)"

SOURCES = [
    ("Free-TV", "https://raw.githubusercontent.com/Free-TV/IPTV/master/playlist.m3u8"),
    ("Region", "https://iptv-org.github.io/iptv/index.country.m3u"),
    ("Language", "https://iptv-org.github.io/iptv/index.language.m3u"),
    ("Type", "https://iptv-org.github.io/iptv/index.category.m3u"),
]

ADULT_WORDS = re.compile(
    r"(?i)(^|[\s._|/\\,;:()\[\]-])(adult|xxx|porn|erotic|18\+)(?=$|[\s._|/\\,;:()\[\]-])"
)
ATTR_RE = re.compile(r'([\w-]+)="([^"]*)"')
CHINA_SATELLITE = re.compile(
    r"(?i)(卫视|衛視|satellite|hunan|zhejiang|jiangsu|dragon tv|beijing tv|anhui|guangdong|"
    r"shandong|shenzhen|liaoning|heilongjiang|henan|hubei|jiangxi|sichuan|tianjin|hebei|"
    r"guangxi|yunnan|guizhou|chongqing|shaanxi|gansu|qinghai|ningxia|xinjiang|xizang|"
    r"inner mongolia|jilin|southeast tv|travel channel)"
)
SPORTS_WORDS = re.compile(r"(?i)(sport|体育|體育|cctv\s*-?\s*5)")
NEWS_WORDS = re.compile(r"(?i)(news|新闻|新聞|財經|财经|business|finance)")


@dataclass
class Entry:
    name: str
    url: str
    attrs: dict[str, str] = field(default_factory=dict)
    groups: list[str] = field(default_factory=list)
    source_rank: int = 0


def fetch(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return response.read().decode("utf-8-sig", errors="replace")


def canonical_url(url: str) -> str:
    parts = urlsplit(url.strip())
    path = re.sub(r"/+$", "", parts.path) or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, parts.query, ""))


def parse_extinf(line: str) -> tuple[dict[str, str], str]:
    head, separator, name = line.partition(",")
    attrs = dict(ATTR_RE.findall(head))
    return attrs, name.strip() if separator else "Unnamed channel"


def clean_group(prefix: str, group: str) -> str:
    group = re.sub(r"\s+", " ", group).strip(" |/") or "Other"
    return group if prefix == "Free-TV" else f"{prefix} · {group}"


def is_allowed(entry: Entry) -> bool:
    if urlsplit(entry.url).scheme.lower() not in {"http", "https"}:
        return False
    haystack = " ".join([entry.name, *entry.groups, entry.attrs.get("tvg-id", "")])
    return not ADULT_WORDS.search(haystack)


def parse_playlist(text: str, prefix: str, source_rank: int) -> list[Entry]:
    entries: list[Entry] = []
    pending: tuple[dict[str, str], str] | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("#EXTINF:"):
            pending = parse_extinf(line)
            continue
        if pending and line and not line.startswith("#"):
            attrs, name = pending
            group = clean_group(prefix, attrs.pop("group-title", "Other"))
            entry = Entry(name, line, attrs, [group], source_rank)
            if is_allowed(entry):
                entries.append(entry)
            pending = None
    return entries


def build(entries: list[Entry]) -> list[Entry]:
    by_url: dict[str, Entry] = {}
    for entry in entries:
        key = canonical_url(entry.url)
        if key in by_url:
            for group in entry.groups:
                if group not in by_url[key].groups:
                    by_url[key].groups.append(group)
        else:
            by_url[key] = entry

    result: list[Entry] = []
    seen_ids: set[str] = set()
    seen_names: set[str] = set()
    for entry in sorted(by_url.values(), key=lambda item: item.source_rank):
        tvg_id = entry.attrs.get("tvg-id", "").strip().casefold()
        name_key = re.sub(r"\W+", "", entry.name, flags=re.UNICODE).casefold()
        if tvg_id and tvg_id in seen_ids:
            continue
        if not tvg_id and name_key and name_key in seen_names:
            continue
        if tvg_id:
            seen_ids.add(tvg_id)
        elif name_key:
            seen_names.add(name_key)
        result.append(entry)

    return sorted(result, key=lambda item: (item.groups[0].casefold(), item.name.casefold(), canonical_url(item.url)))


def quote(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def render(entries: list[Entry]) -> str:
    lines = ["#EXTM3U"]
    order = ["tvg-id", "tvg-name", "tvg-logo", "tvg-country", "tvg-language", "group-title"]
    for entry in entries:
        attrs = dict(entry.attrs)
        attrs["group-title"] = " / ".join(entry.groups)
        keys = [key for key in order if key in attrs]
        keys.extend(sorted(key for key in attrs if key not in keys))
        attr_text = " ".join(f'{key}="{quote(attrs[key])}"' for key in keys if attrs[key])
        suffix = f" {attr_text}" if attr_text else ""
        lines.extend([f"#EXTINF:-1{suffix},{entry.name}", entry.url])
    return "\n".join(lines) + "\n"


def country_matches(entry: Entry, codes: set[str], names: tuple[str, ...]) -> bool:
    country_codes = {
        code.strip().upper()
        for code in re.split(r"[,;/ ]+", entry.attrs.get("tvg-country", ""))
        if code.strip()
    }
    if country_codes & codes:
        return True
    groups = " ".join(entry.groups).casefold()
    return any(name.casefold() in groups for name in names)


def favorite_group(entry: Entry) -> str | None:
    groups_and_name = " ".join([entry.name, *entry.groups])
    is_china = country_matches(entry, {"CN"}, ("Region · China", "China"))
    is_taiwan = country_matches(entry, {"TW"}, ("Region · Taiwan", "Taiwan"))
    is_hong_kong = country_matches(entry, {"HK"}, ("Region · Hong Kong", "Hong Kong"))

    if is_china and (CHINA_SATELLITE.search(entry.name) or SPORTS_WORDS.search(groups_and_name)):
        return "1 · 中国卫视与体育"
    if is_taiwan and NEWS_WORDS.search(groups_and_name):
        return "2 · 台湾新闻"
    if is_hong_kong and NEWS_WORDS.search(groups_and_name):
        return "3 · 香港新闻"
    return None


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", newline="\n", dir=path.parent, delete=False
    ) as handle:
        handle.write(content)
        temporary = Path(handle.name)
    temporary.replace(path)


def main() -> int:
    all_entries: list[Entry] = []
    failures: list[str] = []
    for rank, (prefix, url) in enumerate(SOURCES):
        try:
            parsed = parse_playlist(fetch(url), prefix, rank)
            all_entries.extend(parsed)
            print(f"{prefix}: {len(parsed)} entries", file=sys.stderr)
        except Exception as exc:
            failures.append(f"{prefix}: {exc}")
            print(f"warning: {prefix} failed: {exc}", file=sys.stderr)

    if not all_entries:
        raise RuntimeError("all upstream playlists failed; existing output was left unchanged")

    result = build(all_entries)
    favorites: list[Entry] = []
    for entry in result:
        group = favorite_group(entry)
        if group:
            favorites.append(
                Entry(entry.name, entry.url, dict(entry.attrs), [group], entry.source_rank)
            )
    atomic_write(OUTPUT, render(result))
    atomic_write(FAVORITES_OUTPUT, render(favorites))
    print(f"Wrote {len(result)} unique channels to {OUTPUT}", file=sys.stderr)
    print(f"Wrote {len(favorites)} favorite channels to {FAVORITES_OUTPUT}", file=sys.stderr)
    if failures:
        print("Partial upstream failures: " + "; ".join(failures), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
