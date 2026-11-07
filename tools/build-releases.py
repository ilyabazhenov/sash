#!/usr/bin/env python3
"""Builds the release notes pages: every published release, newest first, as a blog.

Reads the GitHub releases (`gh api repos/OWNER/REPO/releases --paginate`) and writes
/releases/ (English), /ru/releases/ (Russian) and an Atom feed beside each, and adds the
two pages to sitemap.xml. Each release shows its notes up to "## Install": what's new, and
whether both apps need updating. The install steps and the hashes stay on GitHub, one link
away.

The releases on GitHub are in English. The Russian page takes each release's notes from
releases/ru/<version>.md (the same part, translated); a release without one shows the
English notes, marked as such.

The page takes its fonts and colours from site/index.html (everything in its <style>
before "* { box-sizing"), so it changes with the main page.

Usage: build-releases.py releases.json site _site [releases]   (after build-site.py, which writes _site;
releases is the folder of translated notes, releases/<lang>/<version>.md)
"""
import datetime
import html
import json
import re
import sys
from pathlib import Path

ORIGIN = "https://usesash.app"
REPO = "https://github.com/ilyabazhenov/sash"
# Obtainium's own web redirect: on a phone with Obtainium it opens the app with Sash filled in.
OBTAINIUM = "https://obtainium.imranr.dev/redirect?r=obtainium://add/" + REPO
PAGES = {"en": "/releases/", "ru": "/ru/releases/"}
HOME = {"en": "/", "ru": "/ru/"}
MONTHS_RU = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа",
             "сентября", "октября", "ноября", "декабря"]
WORDS = {
    "en": {
        "title": "What’s new in Sash",
        "lede": "Every Sash release: what changed for the Android, Mac and iPhone apps.",
        "description": "Release notes for Sash, the remote desktop for Mac on Android: every version and what it changed.",
        "apk": "Android APK", "dmg": "Mac DMG", "github": "Install steps and checksums",
        "feed": "Subscribe (Atom)", "home": "Sash home", "latest": "Latest",
        "feed-title": "What’s new in Sash", "obtainium": "Auto-updates via Obtainium",
        "foot": "Older versions, 1.9 and before, were released under GPL-3.0 and are not listed here.",
    },
    "ru": {
        "title": "Что нового в Sash",
        "lede": "Все выпуски Sash: что изменилось в приложениях для Android, Mac и iPhone.",
        "description": "Заметки к выпускам Sash, удалённого рабочего стола Mac на Android: каждая версия и что в ней изменилось.",
        "apk": "APK для Android", "dmg": "DMG для Mac", "github": "Установка и контрольные суммы",
        "feed": "Подписаться (Atom)", "home": "На главную", "latest": "Последний",
        "feed-title": "Что нового в Sash", "english": "На английском", "obtainium": "Автообновления через Obtainium",
        "foot": "Версии 1.9 и раньше выходили под GPL-3.0 и здесь не перечислены.",
    },
}


def releases_of(path):
    """The releases in `gh api --paginate` output: one array, several arrays back to back, or one object per line."""
    text, items, pos = Path(path).read_text(encoding="utf-8"), [], 0
    decoder = json.JSONDecoder()
    while pos < len(text):
        if text[pos].isspace():
            pos += 1
            continue
        value, pos = decoder.raw_decode(text, pos)
        items.extend(value if isinstance(value, list) else [value])
    out = [r for r in items if not r.get("draft") and not r.get("prerelease") and r.get("published_at")]
    return sorted(out, key=lambda r: r["published_at"], reverse=True)


def notes_of(body):
    """What's new: the body up to "## Install", without its own heading and the license line every release repeats."""
    body = (body or "").replace("\r\n", "\n")
    body = re.split(r"^## Install\b", body, flags=re.M)[0]
    body = re.sub(r"^## What[’']s new\s*\n", "", body, flags=re.M)
    body = re.sub(r"^Sash is free, under the license.*\n?", "", body, flags=re.M)
    return body.strip()


def inline(text):
    """`code`, **bold** and [links](url) in already escaped text."""
    codes = []

    def keep(m):
        codes.append(f"<code>{m.group(1)}</code>")
        return f"\0{len(codes) - 1}\0"
    text = re.sub(r"`([^`]+)`", keep, text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2">\1</a>', text)
    return re.sub(r"\0(\d+)\0", lambda m: codes[int(m.group(1))], text)


def markdown(text):
    """The Markdown the release notes use: paragraphs, - and 1. lists, ### headings, `code`, **bold**, links."""
    out, para, items, kind = [], [], [], None

    def flush():
        nonlocal para, items, kind
        if para:
            out.append(f"<p>{inline(' '.join(para))}</p>")
        if items:
            out.append(f"<{kind}>" + "".join(f"<li>{inline(i)}</li>" for i in items) + f"</{kind}>")
        para, items, kind = [], [], None

    for line in html.escape(text, quote=False).split("\n"):
        stripped = line.strip()
        if m := re.match(r"(#{2,4})\s+(.*)", stripped):
            flush()
            out.append(f"<h3>{inline(m.group(2))}</h3>")
        elif m := re.match(r"([-*]|\d+\.)\s+(.*)", stripped):
            new = "ol" if m.group(1)[0].isdigit() else "ul"
            if para or (kind and kind != new):
                flush()
            kind = new
            items.append(m.group(2))
        elif not stripped:
            flush()
        elif items and line.startswith(("  ", "\t")):
            items[-1] += " " + stripped
        else:
            if items:
                flush()
            para.append(stripped)
    flush()
    return "\n".join(out)


def notes_in(release, lang, notes_dir):
    """The release's notes in lang, and the language they are in: a translation if there is one, else English."""
    version = release["tag_name"].lstrip("v")
    translated = notes_dir / lang / f"{version}.md" if lang != "en" else None
    if translated and translated.exists():
        return translated.read_text(encoding="utf-8").strip(), lang
    return notes_of(release.get("body")), "en"


def date_of(release, lang):
    d = datetime.date.fromisoformat(release["published_at"][:10])
    return f"{d.day} {MONTHS_RU[d.month - 1]} {d.year}" if lang == "ru" else d.strftime("%B %-d, %Y")


def asset(release, suffix):
    return next((a["browser_download_url"] for a in release.get("assets", []) if a["name"].endswith(suffix)), None)


def tokens(site):
    """The main page's fonts and colours: its <style> up to the first rule for elements."""
    source = (site / "index.html").read_text(encoding="utf-8")
    style = re.search(r"<style>\n?(.*?)\* \{ box-sizing", source, re.S)
    if not style:
        sys.exit("no tokens in site/index.html's <style>")
    return style.group(1)


STYLE = """
* { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body { margin: 0; background: var(--sky); color: var(--ink); font: 400 1rem/1.6 var(--f-body); -webkit-font-smoothing: antialiased; }
a { color: var(--signal); text-underline-offset: .2em; }
:focus-visible { outline: 2px solid var(--signal); outline-offset: 3px; border-radius: 6px; }
.wrap { width: min(100% - 32px, 720px); margin-inline: auto; }
.top { position: sticky; top: 0; z-index: 2; height: var(--hdr); background: var(--sky); border-bottom: var(--bar) solid var(--line); }
.top .wrap { height: 100%; display: flex; align-items: center; gap: 10px; }
.brand { display: flex; align-items: center; gap: 10px; min-height: 44px; color: var(--ink); text-decoration: none; margin-right: auto; font-weight: 600; }
.brand svg { width: 32px; height: 32px; border-radius: 8px; }
.lang { display: flex; padding: 2px; background: var(--paper); border-radius: 12px; }
.lang a { display: grid; place-items: center; min-height: 34px; min-width: 38px; padding: 0 10px; border-radius: 8px;
  color: var(--muted); font-size: .8125rem; font-weight: 600; text-decoration: none; }
.lang a[aria-current] { background: var(--raised); color: var(--ink); box-shadow: inset 0 calc(-1 * var(--bar)) 0 var(--signal); }
h1 { font-size: clamp(1.9rem, 5.5vw, 2.6rem); line-height: 1.1; letter-spacing: -.03em; margin: 56px 0 12px; }
.lede { color: var(--muted); margin: 0 0 8px; font-size: 1.0625rem; }
.meta { display: flex; flex-wrap: wrap; gap: 4px 18px; margin: 0 0 40px; font-size: .9375rem; }
.release { background: var(--paper); border-radius: 14px; padding: 24px clamp(18px, 4vw, 32px); margin: 0 0 20px; scroll-margin-top: calc(var(--hdr) + 16px); }
.release header { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 14px; margin: 0 0 12px; }
.release h2 { font-size: 1.375rem; line-height: 1.2; letter-spacing: -.02em; margin: 0; }
.release h2 a { color: inherit; text-decoration: none; }
.release time { color: var(--muted); font-size: .9375rem; }
.badge { font: 500 .75rem/1 var(--f-mono); color: var(--signal); background: var(--signal-soft); padding: 5px 8px; border-radius: 6px; }
.badge.quiet { color: var(--muted); background: var(--raised); }
.release h3 { font-size: 1.0625rem; margin: 20px 0 6px; }
.release ul, .release ol { padding-left: 1.25em; margin: 0 0 12px; }
.release li { margin: 0 0 10px; }
.release p { margin: 0 0 12px; }
.release code { font: 400 .875em var(--f-mono); background: var(--signal-soft); padding: .1em .35em; border-radius: 5px; overflow-wrap: anywhere; }
.links { display: flex; flex-wrap: wrap; gap: 6px 18px; margin: 16px 0 0; padding: 14px 0 0; border-top: var(--bar) solid var(--line); font-size: .9375rem; }
.foot { color: var(--muted); font-size: .875rem; margin: 40px auto 64px; }
"""

LOGO = """<svg viewBox="0 0 100 100" aria-hidden="true"><defs><linearGradient id="rel-sky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#333C7A"/><stop offset="1" stop-color="#121636"/></linearGradient></defs><rect width="100" height="100" fill="url(#rel-sky)"/><g transform="translate(50 50) scale(0.94) translate(-50 -50) translate(0 -5)"><path d="M15 47.5L45 26.5V71.5H15Z" fill="#FFBE3D"/><path d="M45 26.5L63.69 39.583A8 8 0 0 0 62 44.5V71.5H45Z" fill="#F5A30F"/><path d="M13 75.5H62V83.5H13A4 4 0 0 1 13 75.5Z" fill="#C9760A"/><path d="M13 75.5H62V79H9.031A4 4 0 0 1 13 75.5Z" fill="#F09A1C"/><path fill-rule="evenodd" d="M70 39.5H86A5 5 0 0 1 91 44.5V78.5A5 5 0 0 1 86 83.5H70A5 5 0 0 1 65 78.5V44.5A5 5 0 0 1 70 39.5ZM73 43.5H83A2 2 0 0 1 83 47.5H73A2 2 0 0 1 73 43.5Z" fill="#FFEDC2"/><path d="M70 50H86A2.5 2.5 0 0 1 88.5 52.5V78A2.5 2.5 0 0 1 86 80.5H70A2.5 2.5 0 0 1 67.5 78V52.5A2.5 2.5 0 0 1 70 50Z" fill="#F7D488"/></g></svg>"""


def page(lang, releases, css, notes_dir):
    w = WORDS[lang]
    up = "../" * PAGES[lang].strip("/").count("/") + "../"   # from /releases/ or /ru/releases/ to the site's root
    articles = []
    for i, r in enumerate(releases):
        version = r["tag_name"].lstrip("v")
        links = [f'<a href="{a}">{w[k]}</a>' for k, a in (("apk", asset(r, ".apk")), ("dmg", asset(r, ".dmg"))) if a]
        if i == 0:
            links.append(f'<a href="{OBTAINIUM}">{w["obtainium"]}</a>')
        links.append(f'<a href="{html.escape(r["html_url"])}">{w["github"]}</a>')
        latest = f' <span class="badge">{w["latest"]}</span>' if i == 0 else ""
        notes, written = notes_in(r, lang, notes_dir)
        if written != lang:
            latest += f' <span class="badge quiet">{w["english"]}</span>'

        articles.append(f"""<article class="release" id="v{version}">
  <header><h2><a href="#v{version}">Sash {version}</a></h2><time datetime="{r['published_at'][:10]}">{date_of(r, lang)}</time>{latest}</header>
  <div lang="{written}">
{markdown(notes)}
  </div>
  <p class="links">{" · ".join(links)}</p>
</article>""")
    other = "ru" if lang == "en" else "en"
    feed_url = f"{PAGES[lang]}feed.xml"
    return f"""<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{w['title']}</title>
<meta name="description" content="{w['description']}">
<link rel="canonical" href="{ORIGIN}{PAGES[lang]}">
<link rel="alternate" hreflang="{lang}" href="{ORIGIN}{PAGES[lang]}">
<link rel="alternate" hreflang="{other}" href="{ORIGIN}{PAGES[other]}">
<link rel="alternate" hreflang="x-default" href="{ORIGIN}{PAGES['en']}">
<link rel="alternate" type="application/atom+xml" title="{w['feed-title']}" href="{ORIGIN}{feed_url}">
<link rel="icon" href="{up}favicon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="{up}apple-touch-icon.png">
<meta name="theme-color" content="#15181D">
<meta name="color-scheme" content="dark">
<meta property="og:type" content="website">
<meta property="og:site_name" content="Sash">
<meta property="og:url" content="{ORIGIN}{PAGES[lang]}">
<meta property="og:title" content="{w['title']}">
<meta property="og:description" content="{w['description']}">
<meta property="og:image" content="{ORIGIN}/{'og.png' if lang == 'ru' else 'og-en.png'}">
<style>
{css.replace('url(fonts/', f'url({up}fonts/')}{STYLE}</style>
</head>
<body>
<header class="top">
  <div class="wrap">
    <a class="brand" href="{HOME[lang]}" aria-label="{w['home']}">
      {LOGO}
      Sash
    </a>
    <nav class="lang" aria-label="{'Язык' if lang == 'ru' else 'Language'}">
      <a href="{PAGES['ru']}" hreflang="ru" lang="ru" title="Русский"{' aria-current="page"' if lang == 'ru' else ''}>RU</a>
      <a href="{PAGES['en']}" hreflang="en" lang="en" title="English"{' aria-current="page"' if lang == 'en' else ''}>EN</a>
    </nav>
  </div>
</header>
<main class="wrap">
  <h1>{w['title']}</h1>
  <p class="lede">{w['lede']}</p>
  <p class="meta"><a href="{HOME[lang]}">{w['home']}</a><a href="{OBTAINIUM}">{w['obtainium']}</a><a href="{feed_url}">{w['feed']}</a></p>
{chr(10).join(articles)}
  <p class="foot">{w['foot']}</p>
</main>
<!-- Cloudflare Web Analytics --><script type='module' src='https://static.cloudflareinsights.com/beacon.min.js' data-cf-beacon='{{"token": "3d34efb0e9bb47b089dd6f0ef24abeac"}}'></script><!-- End Cloudflare Web Analytics -->
</body>
</html>
"""


def feed(lang, releases, notes_dir):
    updated = releases[0]["published_at"] if releases else datetime.datetime.now(datetime.timezone.utc).isoformat()
    url = ORIGIN + PAGES[lang]
    entries = "".join(f"""
  <entry>
    <title>Sash {r['tag_name'].lstrip('v')}</title>
    <id>{url}#v{r['tag_name'].lstrip('v')}</id>
    <link rel="alternate" type="text/html" href="{url}#v{r['tag_name'].lstrip('v')}"/>
    <published>{r['published_at']}</published>
    <updated>{r['published_at']}</updated>
    <content type="html">{html.escape(markdown(notes_in(r, lang, notes_dir)[0]))}</content>
  </entry>""" for r in releases)
    return f"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xml:lang="{lang}">
  <title>{WORDS[lang]['feed-title']}</title>
  <id>{url}</id>
  <link rel="alternate" type="text/html" href="{url}"/>
  <link rel="self" type="application/atom+xml" href="{url}feed.xml"/>
  <updated>{updated}</updated>
  <author><name>Sash</name><uri>{ORIGIN}/</uri></author>{entries}
</feed>
"""


def main():
    releases_path, site, out = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
    notes_dir = Path(sys.argv[4]) if len(sys.argv) > 4 else Path("releases")
    releases = releases_of(releases_path)
    if not releases:
        sys.exit("no published releases; no release notes pages")
    css = tokens(site)
    for lang, path in PAGES.items():
        target = out / path.strip("/") / "index.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(page(lang, releases, css, notes_dir), encoding="utf-8")
        (target.parent / "feed.xml").write_text(feed(lang, releases, notes_dir), encoding="utf-8")
        missing = [r["tag_name"] for r in releases if lang != "en" and notes_in(r, lang, notes_dir)[1] != lang]
        print(f"{lang}: {target} ({len(releases)} releases" + (f"; in English: {', '.join(missing)})" if missing else ")"))

    sitemap = out / "sitemap.xml"
    if sitemap.exists():
        lastmod = releases[0]["published_at"][:10]
        alternates = "".join(f'\n    <xhtml:link rel="alternate" hreflang="{l}" href="{ORIGIN}{p}"/>' for l, p in PAGES.items())
        urls = "".join(f"\n  <url>\n    <loc>{ORIGIN}{p}</loc>\n    <lastmod>{lastmod}</lastmod>{alternates}\n  </url>"
                       for p in PAGES.values())
        sitemap.write_text(sitemap.read_text(encoding="utf-8").replace("\n</urlset>", f"{urls}\n</urlset>"), encoding="utf-8")


if __name__ == "__main__":
    main()
