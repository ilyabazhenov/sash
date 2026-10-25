#!/usr/bin/env python3
"""Builds the published site: one page per language, so each has its own URL.

site/index.html holds both languages, every phrase as <span class="ru"> and
<span class="en">, and works on its own with an in-page switch. Search engines
want one language per URL, so this writes the English page to / and the Russian
one to /ru/, each with only its own text, its own head (the data-en values of
site/index.html), hreflang links between them, a link as the language switch and
the app's structured data. Then /get/, where the page's QR code points: it starts
the latest APK's download on the phone. And a 404 page, robots.txt and sitemap.xml.

Usage: build-site.py site _site   (after stamp-release.py, so the version is current)
"""
import datetime
import html
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ORIGIN = "https://usesash.app"
PAGES = {"en": "/", "ru": "/ru/"}
LANGS = {"ru": "Русский", "en": "English"}

src, out = Path(sys.argv[1]), Path(sys.argv[2])
if out.exists():
    shutil.rmtree(out)
shutil.copytree(src, out)
source = (src / "index.html").read_text(encoding="utf-8")

SPAN = re.compile(r"<span\b[^>]*>|</span>")


def strip_lang(page, lang):
    """Removes every <span class="lang">…</span>, nested spans included."""
    opener = f'<span class="{lang}">'
    parts, pos = [], 0
    while (start := page.find(opener, pos)) != -1:
        depth, end = 0, None
        for m in SPAN.finditer(page, start):
            depth += -1 if m.group().startswith("</") else 1
            if depth == 0:
                end = m.end()
                break
        if end is None:
            sys.exit(f"unclosed {opener} at {start}")
        parts.append(page[pos:start])
        pos = end
    parts.append(page[pos:])
    page = "".join(parts)
    if f'class="{lang}"' in page:
        sys.exit(f'class="{lang}" left in the page outside a plain span')
    return page


def head_for(page, lang):
    """Takes each data-en value on the English page and drops the attribute everywhere."""
    def title(m):
        return f"<title>{m.group(1) if lang == 'en' else m.group(2)}</title>"
    page = re.sub(r'<title data-en="([^"]*)">([^<]*)</title>', title, page)

    def tag(m):
        t, value = m.group(0), m.group(1)
        t = t.replace(f' data-en="{value}"', "")
        if lang == "en":
            attr = "href" if t.startswith("<link") else "content"
            t = re.sub(rf'\b{attr}="[^"]*"', lambda _: f'{attr}="{value}"', t, count=1)
        return t
    page = re.sub(r'<(?:meta|link)\b[^>]*\sdata-en="([^"]*)"[^>]*>', tag, page)

    # tags only one language needs, such as the Cyrillic font preload
    def only(m):
        return m.group(0).replace(f' data-only="{m.group(1)}"', "") if m.group(1) == lang else ""
    page = re.sub(r'<[^>]*\sdata-only="(\w+)"[^>]*>\n?', only, page)
    return re.sub(r"<!-- The English page is built[^>]*-->\n", "", page)


def switch_for(page, lang):
    """The RU / EN buttons become links to the two pages."""
    def link(m):
        l = m.group(1)
        here = ' aria-current="page"' if l == lang else ""
        return (f'<a id="lang-{l}" data-lang="{l}" href="{PAGES[l]}" hreflang="{l}" lang="{l}"'
                f' title="{LANGS[l]}"{here}>{l.upper()}</a>')
    page, n = re.subn(r'<button type="button" id="lang-(\w+)" data-lang="\1" aria-pressed="\w+">\w+</button>', link, page)
    if n != 2:
        sys.exit(f"found {n} language buttons, expected 2")
    return page


VERSION = re.search(r'data-release="version">([^<]*)<', source).group(1)
APK = re.search(r'<a\b[^>]*\bdata-release="href"[^>]*\bhref="([^"]*)"', source).group(1)


MAC = (re.search(r'<a\b[^>]*\bdata-release="mac-href"[^>]*\bhref="([^"]*)"', source) or [None, None])[1]
MAC_ABOUT = {
    "en": "The Mac side of Sash. It streams the Mac’s windows to Sash on Android.",
    "ru": "Сторона Mac для Sash. Передаёт окна Mac в Sash на Android.",
}


def text_of(fragment):
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", fragment))).strip()


def faq_of(page):
    """The questions of <div class="faq">, each <details><summary>question</summary><p>answer</p></details>."""
    block = re.search(r'<div class="faq">(.*?)\n\s*</div>\n', page, re.S)
    if not block:
        sys.exit("no FAQ block on the page")
    pairs = re.findall(r"<details\b[^>]*><summary>(.*?)</summary><p>(.*?)</p></details>", block.group(1), re.S)
    if len(pairs) < 4:
        sys.exit(f"found {len(pairs)} FAQ entries, expected at least 4")
    return [{"@type": "Question", "name": text_of(q),
             "acceptedAnswer": {"@type": "Answer", "text": text_of(a)}} for q, a in pairs]


def structured_data(page, lang):
    def meta(name):
        return html.unescape(re.search(rf'<meta (?:name|property)="{name}" content="([^"]*)"', page).group(1))
    url = ORIGIN + PAGES[lang]
    free = {"@type": "Offer", "price": "0", "priceCurrency": "USD"}
    data = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "WebSite",
                "@id": ORIGIN + "/#website",
                "name": "Sash",
                "url": ORIGIN + "/",
                "inLanguage": list(PAGES),
            },
            {
                "@type": "SoftwareApplication",
                "@id": ORIGIN + "/#android",
                "name": "Sash",
                "alternateName": "Sash remote desktop",
                "url": url,
                "description": meta("description"),
                "inLanguage": lang,
                "image": meta("og:image"),
                "applicationCategory": "UtilitiesApplication",
                "applicationSubCategory": "Remote desktop",
                "operatingSystem": "Android 10 or later",
                "softwareVersion": VERSION,
                "downloadUrl": APK,
                "license": "https://github.com/ilyabazhenov/sash/blob/main/LICENSE",
                "isAccessibleForFree": True,
                "offers": free,
                "sameAs": ["https://github.com/ilyabazhenov/sash"],
            },
            {
                "@type": "SoftwareApplication",
                "@id": ORIGIN + "/#mac",
                "name": "Sash for Mac",
                "url": url + "#start",
                "description": MAC_ABOUT[lang],
                "inLanguage": lang,
                "applicationCategory": "UtilitiesApplication",
                "applicationSubCategory": "Remote desktop",
                "operatingSystem": "macOS 14 or later",
                "processorRequirements": "Apple silicon",
                "softwareVersion": VERSION,
                "downloadUrl": MAC,
                "license": "https://github.com/ilyabazhenov/sash/blob/main/LICENSE",
                "isAccessibleForFree": True,
                "offers": free,
            },
            {
                "@type": "FAQPage",
                "@id": url + "#faq",
                "url": url,
                "inLanguage": lang,
                "mainEntity": faq_of(page),
            },
        ],
    }
    if not MAC:  # no Sash for Mac in the latest release
        data["@graph"] = [g for g in data["@graph"] if g.get("@id") != ORIGIN + "/#mac"]
    script = json.dumps(data, ensure_ascii=False, indent=1).replace("</", "<\\/")
    return page.replace("</head>", f'<script type="application/ld+json">\n{script}\n</script>\n</head>', 1)


def build(lang):
    other = "en" if lang == "ru" else "ru"
    page = strip_lang(source, other)
    page = head_for(page, lang)
    page = switch_for(page, lang)
    # aria-label="Theme / Тема": English first, Russian after the slash
    page = re.sub(r'aria-label="([^"/]+) / ([^"/]+)"',
                  lambda m: f'aria-label="{m.group(1) if lang == "en" else m.group(2)}"', page)
    page = page.replace('<html lang="ru">', f'<html lang="{lang}" data-lang="{lang}" data-page-lang="{lang}">', 1)
    page = structured_data(page, lang)
    depth = PAGES[lang].count("/") - 1
    if depth:
        # /ru/ sits a folder down: its relative links to fonts and icons go up one
        up = "../" * depth
        page = re.sub(r'\b(href|src)="(?!#|[a-z]+:|/)', rf'\1="{up}', page)
        page = page.replace("url(fonts/", f"url({up}fonts/")
    path = out / PAGES[lang].strip("/") / "index.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(page, encoding="utf-8")
    print(f"{lang}: {path} ({len(page) // 1024} KB)")


for lang in PAGES:
    build(lang)

# The QR code's target: the download starts by itself, the page says what comes next.
(out / "get").mkdir(exist_ok=True)
(out / "get" / "index.html").write_text(f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<meta http-equiv="refresh" content="1; url={APK}">
<title>Download Sash {VERSION}</title>
<link rel="icon" href="../favicon.svg" type="image/svg+xml">
<style>
:root {{ color-scheme: light dark; --bg: #E3E9F2; --ink: #111620; --muted: #4A5468; --signal: #2B62EE; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg: #0D1017; --ink: #E6EAF2; --muted: #A3ACBD; --signal: #3A7BFF; }} }}
body {{ margin: 0; min-height: 100vh; display: grid; place-items: center; background: var(--bg); color: var(--ink);
  font: 400 1.0625rem/1.55 system-ui, -apple-system, Roboto, sans-serif; }}
main {{ max-width: 26rem; padding: 32px 20px; }}
h1 {{ font-size: 1.5rem; line-height: 1.25; margin: 0 0 12px; }}
p {{ margin: 0 0 14px; color: var(--muted); }}
a.btn {{ display: inline-block; margin: 6px 0 18px; padding: 14px 20px; border-radius: 14px; background: var(--signal);
  color: #fff; font-weight: 600; text-decoration: none; }}
a {{ color: inherit; }}
html:not([lang="ru"]) .ru, html[lang="ru"] .en {{ display: none; }}
</style>
<script>if (/^ru/i.test(navigator.language || '')) {{ document.documentElement.lang = 'ru'; document.title = 'Скачать Sash {VERSION}'; }}</script>
</head>
<body>
<main>
  <div class="en">
    <h1>Downloading Sash {VERSION}</h1>
    <p>When it’s done, open the APK. Android asks to allow installs from your browser: turn on “Allow from this source”.</p>
    <a class="btn" href="{APK}">Download APK</a>
    <p>Then install <a href="/#start">Sash for Mac</a> on the Mac and pair them on the same Wi‑Fi. <a href="/#start">Step by step</a></p>
  </div>
  <div class="ru">
    <h1>Скачивается Sash {VERSION}</h1>
    <p>Когда загрузится, откройте APK. Android попросит разрешить установку для браузера: включите «Разрешить из этого источника».</p>
    <a class="btn" href="{APK}">Скачать APK</a>
    <p>Затем поставьте <a href="/ru/#start">Sash для Mac</a> на Mac и сопрягите их в одной Wi‑Fi сети. <a href="/ru/#start">По шагам</a></p>
  </div>
</main>
<!-- Cloudflare Web Analytics --><script type='module' src='https://static.cloudflareinsights.com/beacon.min.js' data-cf-beacon='{{"token": "3d34efb0e9bb47b089dd6f0ef24abeac"}}'></script><!-- End Cloudflare Web Analytics -->
</body>
</html>
""", encoding="utf-8")

# GitHub Pages serves /404.html for any address it doesn't have.
(out / "404.html").write_text(f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>Page not found · Sash</title>
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<style>
:root {{ color-scheme: light dark; --bg: #E3E9F2; --ink: #111620; --muted: #4A5468; --signal: #2B62EE; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg: #0D1017; --ink: #E6EAF2; --muted: #A3ACBD; --signal: #3A7BFF; }} }}
body {{ margin: 0; min-height: 100vh; display: grid; place-items: center; background: var(--bg); color: var(--ink);
  font: 400 1.0625rem/1.55 system-ui, -apple-system, Roboto, sans-serif; }}
main {{ max-width: 26rem; padding: 32px 20px; }}
h1 {{ font-size: 1.5rem; line-height: 1.25; margin: 0 0 12px; }}
p {{ margin: 0 0 14px; color: var(--muted); }}
a.btn {{ display: inline-block; margin: 6px 0 18px; padding: 14px 20px; border-radius: 14px; background: var(--signal);
  color: #fff; font-weight: 600; text-decoration: none; }}
a {{ color: inherit; }}
html:not([lang="ru"]) .ru, html[lang="ru"] .en {{ display: none; }}
</style>
<script>if (/^ru/i.test(navigator.language || '')) {{ document.documentElement.lang = 'ru'; document.title = 'Страница не найдена · Sash'; }}</script>
</head>
<body>
<main>
  <div class="en">
    <h1>There’s no such page</h1>
    <p>Sash is a remote desktop for Mac on Android: your Mac’s windows on your phone, foldable or tablet.</p>
    <a class="btn" href="/">Go to usesash.app</a>
  </div>
  <div class="ru">
    <h1>Такой страницы нет</h1>
    <p>Sash — удалённый рабочий стол Mac на Android: окна вашего Mac на телефоне, складном или планшете.</p>
    <a class="btn" href="/ru/">На главную</a>
  </div>
</main>
</body>
</html>
""", encoding="utf-8")

# When the page last changed, for the sitemap: the newest commit touching the site (CI's shallow clone gives HEAD's date)
try:
    LASTMOD = subprocess.run(["git", "log", "-1", "--format=%cs", "--", str(src), __file__],
                             capture_output=True, text=True, check=True).stdout.strip()
except (OSError, subprocess.CalledProcessError):
    LASTMOD = ""
LASTMOD = LASTMOD or datetime.date.today().isoformat()

alternates = "".join(
    f'\n    <xhtml:link rel="alternate" hreflang="{l}" href="{ORIGIN}{p}"/>' for l, p in PAGES.items()
) + f'\n    <xhtml:link rel="alternate" hreflang="x-default" href="{ORIGIN}{PAGES["en"]}"/>'
urls = "".join(f"\n  <url>\n    <loc>{ORIGIN}{p}</loc>\n    <lastmod>{LASTMOD}</lastmod>{alternates}\n  </url>" for p in PAGES.values())
(out / "sitemap.xml").write_text(
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">'
    f"{urls}\n</urlset>\n", encoding="utf-8")
(out / "robots.txt").write_text(f"User-agent: *\nAllow: /\n\nSitemap: {ORIGIN}/sitemap.xml\n", encoding="utf-8")
