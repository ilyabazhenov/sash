#!/usr/bin/env python3
"""Writes the latest release into the marketing page before it is published.

Elements marked data-release="version|name|size-ru|size-en" get their text
replaced, data-release="href" gets the APK's download URL, and data-release="mac-href" the
Mac disk image's (Sash-<version>.dmg) when the release has one. The page keeps
working without this step: the values in the markup are the fallback.

Usage: stamp-release.py site/index.html release.json
where release.json is `gh release view --json tagName,assets`.
"""
import json
import re
import sys

page_path, release_path = sys.argv[1], sys.argv[2]
release = json.load(open(release_path))
apks = [a for a in release.get("assets", []) if a["name"].endswith(".apk")]
if not apks:
    sys.exit("no .apk asset in the release; page left as is")
apk = apks[0]

mb = apk["size"] / 1_000_000
values = {
    "version": release["tagName"].lstrip("v"),
    "name": apk["name"],
    "size-ru": f"{mb:.1f}".replace(".", ",") + "&nbsp;МБ",
    "size-en": f"{mb:.1f}&nbsp;MB",
}

page = open(page_path, encoding="utf-8").read()


def text(m):
    return m.group(1) + values[m.group(3)] + m.group(4)


page, n = re.subn(r'(<(\w+)\b[^>]*\bdata-release="(version|name|size-ru|size-en)"[^>]*>)[^<]*(</\2>)', text, page)
page, h = re.subn(r'(<a\b[^>]*\bdata-release="href"[^>]*\bhref=")[^"]*(")',
                  lambda m: m.group(1) + apk["url"] + m.group(2), page)
dmgs = [a for a in release.get("assets", []) if a["name"].endswith(".dmg")]
m = 0
if dmgs:
    page, m = re.subn(r'(<a\b[^>]*\bdata-release="mac-href"[^>]*\bhref=")[^"]*(")',
                      lambda x: x.group(1) + dmgs[0]["url"] + x.group(2), page)
else:
    # No disk image in this release: the Mac buttons go rather than link to a missing file.
    page, gone = re.subn(r'\s*<a\b[^>]*\bdata-release="mac-href"[^>]*>.*?</a>', "", page, flags=re.S)
    print(f"no .dmg asset in the release; {gone} Mac buttons removed")
open(page_path, "w", encoding="utf-8").write(page)
print(f"stamped {values['version']}, {apk['name']}: {n} texts, {h} links, {m} Mac links")
