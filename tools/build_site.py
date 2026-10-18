"""Build the website (GitHub Pages) from site/strings.toml.

    python3 tools/build_site.py [OUT]     write OUT (default build/site): index.html in
                                          English, one folder per language, one per
                                          guide (site/guides.toml), llms.txt,
                                          robots.txt, sitemap.xml, 404.html
    python3 tools/build_site.py --readme  refresh "MultiDrop in your language" in README.md

The APT repository (dists/, pool/, keyrings) lives on the same gh-pages
branch; CI copies these files next to it without touching it.
"""

from __future__ import annotations

import html
import json
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://digitaldanis.github.io/multidrop/"
REPO = "https://github.com/digitaldanis/multidrop"
RELEASES = REPO + "/releases/latest"
BANNER = "https://raw.githubusercontent.com/digitaldanis/multidrop/main/docs/banner.png"
APT = """curl -fsSL https://digitaldanis.github.io/multidrop/multidrop-archive-keyring.gpg \\
  | sudo tee /usr/share/keyrings/multidrop-archive-keyring.gpg >/dev/null
echo "deb [signed-by=/usr/share/keyrings/multidrop-archive-keyring.gpg] https://digitaldanis.github.io/multidrop stable main" \\
  | sudo tee /etc/apt/sources.list.d/multidrop.list
sudo apt update && sudo apt install multidrop"""
KEY_FINGERPRINT = "93249FD950BF046802D087C2FE64BBDE5A1E946F"

CSS = """
:root{--bg:#fbfaf7;--fg:#1d1d1f;--muted:#5f5f66;--card:#fff;--line:#e3e0d8;--accent:#1f6feb;--accent-fg:#fff;--code:#f1f0ec}
@media (prefers-color-scheme:dark){:root{--bg:#121214;--fg:#ececee;--muted:#a0a0a8;--card:#1c1c20;--line:#2e2e34;--accent:#5a9cff;--accent-fg:#0b1220;--code:#1a1a1e}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:17px/1.6 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:52rem;margin:0 auto;padding:1.5rem 1rem 3rem}
nav.langs{display:flex;flex-wrap:wrap;gap:.35rem .8rem;font-size:.85rem;padding:.6rem 1rem;border-bottom:1px solid var(--line);justify-content:center}
nav.langs a{color:var(--muted);text-decoration:none}nav.langs a[aria-current]{color:var(--fg);font-weight:600}
img.banner{width:100%;height:auto;border-radius:14px;margin:.5rem 0 1rem}
h1{font-size:clamp(1.6rem,4.5vw,2.4rem);line-height:1.2;margin:.5rem 0}
h2{font-size:1.25rem;margin:2.2rem 0 .6rem}
.lead{font-size:1.1rem;color:var(--muted)}
.cta{display:flex;flex-wrap:wrap;gap:.6rem;margin:1.2rem 0}
.cta a{padding:.65rem 1.1rem;border-radius:10px;border:1px solid var(--line);background:var(--card);color:var(--fg);text-decoration:none;font-weight:600}
.cta a.primary{background:var(--accent);border-color:var(--accent);color:var(--accent-fg)}
ul.features{padding:0;list-style:none;display:grid;gap:.6rem}
ul.features li{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:.75rem 1rem}
pre{background:var(--code);padding:1rem;border-radius:10px;overflow-x:auto;font-size:.85rem}
details{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:.7rem 1rem;margin:.5rem 0}
summary{cursor:pointer;font-weight:600}
footer{color:var(--muted);font-size:.85rem;margin-top:3rem;border-top:1px solid var(--line);padding-top:1rem}
a{color:var(--accent)}
"""


def load() -> dict[str, dict]:
    return tomllib.loads((ROOT / "site" / "strings.toml").read_text(encoding="utf-8"))


def load_guides() -> list[dict]:
    return tomllib.loads((ROOT / "site" / "guides.toml").read_text(encoding="utf-8"))["guide"]


def url(lang: str) -> str:
    return BASE if lang == "en" else f"{BASE}{lang}/"


def inline(text: str) -> str:
    """**bold** and [links](https://…) in the strings, everything else escaped."""
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html.escape(text))
    return re.sub(r"\[(.+?)\]\((https://[^)\s]+)\)", r'<a href="\2">\1</a>', text)


def plain(text: str) -> str:
    """The strings without **bold** and link markup, for meta data."""
    return re.sub(r"\[(.+?)\]\(https://[^)\s]+\)", r"\1", text.replace("**", ""))


def meta(lang: str, title: str, description: str, canonical: str) -> str:
    e = html.escape
    return f"""<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)}</title>
<meta name="description" content="{e(description)}">
<link rel="canonical" href="{canonical}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="MultiDrop">
<meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(description)}">
<meta property="og:url" content="{canonical}">
<meta property="og:image" content="{BANNER}">
<meta property="og:locale" content="{lang}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{e(title)}">
<meta name="twitter:description" content="{e(description)}">
<meta name="twitter:image" content="{BANNER}">
<meta name="theme-color" content="#1f6feb">
<link rel="icon" href="https://raw.githubusercontent.com/digitaldanis/multidrop/main/data/icons/multidrop.svg" type="image/svg+xml">"""


def guide_links(guides: list[dict]) -> str:
    return " · ".join(f'<a href="{BASE}{g["slug"]}/">{html.escape(g["h1"])}</a>' for g in guides)


def ld(*items: dict) -> str:
    return "\n".join('<script type="application/ld+json">'
                     + json.dumps(d, ensure_ascii=False).replace("</", "<\\/") + "</script>"
                     for d in items)


def json_ld(lang: str, t: dict) -> str:
    app = {
        "@context": "https://schema.org", "@type": "SoftwareApplication", "name": "MultiDrop",
        "alternateName": ["MultiDrop for Windows", "MultiDrop for Linux"],
        "applicationCategory": "UtilitiesApplication",
        "applicationSubCategory": "File transfer",
        "operatingSystem": "Windows 10, Windows 11, Linux",
        "description": t["description"], "inLanguage": lang, "url": url(lang),
        "downloadUrl": RELEASES, "codeRepository": REPO, "image": BANNER,
        "license": "https://www.gnu.org/licenses/gpl-3.0.html", "isAccessibleForFree": True,
        "featureList": [plain(f) for f in t["features"]],
        "offers": {"@type": "Offer", "price": "0", "priceCurrency": "USD"},
    }
    faq = {
        "@context": "https://schema.org", "@type": "FAQPage", "inLanguage": lang,
        "mainEntity": [{"@type": "Question", "name": q,
                        "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in t["faq"]],
    }
    return ld(app, faq)


def page(lang: str, t: dict, all_langs: dict[str, dict], guides: list[dict]) -> str:
    e = html.escape
    alternates = "\n".join(f'<link rel="alternate" hreflang="{code}" href="{url(code)}">'
                           for code in all_langs) + f'\n<link rel="alternate" hreflang="x-default" href="{BASE}">'
    langs = " ".join(
        f'<a href="{url(code)}" hreflang="{code}" lang="{code}"'
        + (' aria-current="page"' if code == lang else "") + f'>{e(s["name"])}</a>'
        for code, s in all_langs.items())
    features = "\n".join(f"<li>{inline(f)}</li>" for f in t["features"])
    faq = "\n".join(f"<details><summary>{e(q)}</summary><p>{e(a)}</p></details>" for q, a in t["faq"])
    direction = t.get("dir", "ltr")
    return f"""<!doctype html>
<html lang="{lang}" dir="{direction}">
<head>
{meta(lang, t["title"], t["description"], url(lang))}
{alternates}
{json_ld(lang, t)}
<style>{CSS}</style>
</head>
<body>
<nav class="langs" aria-label="{e(t["languages"])}">{langs}</nav>
<main>
<img class="banner" src="{BANNER}" alt="{e(t["title"])}" width="1280" height="640">
<h1>{e(t["h1"])}</h1>
<p class="lead">{e(t["lead"])}</p>
<div class="cta">
<a class="primary" href="{RELEASES}">{e(t["download"])}</a>
<a href="#linux">{e(t["linux"])}</a>
<a href="{REPO}">★ {e(t["source"])}</a>
</div>
<h2>{e(t["features_title"])}</h2>
<ul class="features">
{features}
</ul>
<h2 id="linux">{e(t["apt_title"])}</h2>
<pre><code>{e(APT)}</code></pre>
<p><small>GPG: <code>{KEY_FINGERPRINT}</code> · Fedora, Arch, openSUSE: <a href="{REPO}#fedora-arch-opensuse-and-other-distributions">GitHub</a></small></p>
<h2>{e(t["faq_title"])}</h2>
{faq}
<footer>
<p lang="en">Guides: {guide_links(guides)}</p>
<p>{e(t["footer"])}</p>
<p><a href="{REPO}">GitHub</a> · <a href="{REPO}/releases">Releases</a> · <a href="{BASE}llms.txt">llms.txt</a> · GPL-3.0</p>
</footer>
</main>
</body>
</html>
"""


def guide_page(g: dict, en: dict, guides: list[dict]) -> str:
    e = html.escape
    canonical = f"{BASE}{g['slug']}/"
    sections = "\n".join(f"<h2>{e(h)}</h2>\n<p>{inline(text)}</p>" for h, text in g["sections"])
    steps = ""
    if g.get("steps"):
        items = "\n".join(f"<li>{inline(s)}</li>" for s in g["steps"])
        steps = f"<h2>How to set it up</h2>\n<ol>\n{items}\n</ol>"
    faq = "\n".join(f"<details><summary>{e(q)}</summary><p>{inline(a)}</p></details>"
                    for q, a in g["faq"])
    if faq:
        faq = f"<h2>{e(en['faq_title'])}</h2>\n{faq}"
    data = [{
        "@context": "https://schema.org", "@type": "TechArticle", "headline": g["h1"],
        "description": g["description"], "inLanguage": "en", "url": canonical, "image": BANNER,
        "author": {"@type": "Organization", "name": "MultiDrop", "url": REPO},
        "about": {"@type": "SoftwareApplication", "name": "MultiDrop", "url": BASE,
                  "applicationCategory": "UtilitiesApplication",
                  "operatingSystem": "Windows 10, Windows 11, Linux",
                  "offers": {"@type": "Offer", "price": "0", "priceCurrency": "USD"}},
    }, {
        "@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "MultiDrop", "item": BASE},
            {"@type": "ListItem", "position": 2, "name": g["h1"], "item": canonical}],
    }]
    if g.get("steps"):
        data.append({"@context": "https://schema.org", "@type": "HowTo", "name": g["h1"],
                     "step": [{"@type": "HowToStep", "position": i, "text": plain(s)}
                              for i, s in enumerate(g["steps"], 1)]})
    if g["faq"]:
        data.append({"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
            {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": plain(a)}}
            for q, a in g["faq"]]})
    return f"""<!doctype html>
<html lang="en">
<head>
{meta("en", g["title"], g["description"], canonical)}
{ld(*data)}
<style>{CSS}</style>
</head>
<body>
<nav class="langs"><a href="{BASE}">MultiDrop</a> <a href="{RELEASES}">{e(en["download"])}</a> <a href="{BASE}#linux">{e(en["linux"])}</a> <a href="{REPO}">GitHub</a></nav>
<main>
<h1>{e(g["h1"])}</h1>
<p class="lead">{inline(g["lead"])}</p>
<div class="cta">
<a class="primary" href="{RELEASES}">{e(en["download"])}</a>
<a href="{BASE}#linux">{e(en["linux"])}</a>
<a href="{REPO}">★ {e(en["source"])}</a>
</div>
{sections}
{steps}
{faq}
<footer>
<p>More guides: {guide_links([o for o in guides if o is not g])}</p>
<p>{e(en["footer"])}</p>
<p><a href="{REPO}">GitHub</a> · <a href="{REPO}/releases">Releases</a> · <a href="{BASE}llms.txt">llms.txt</a> · GPL-3.0</p>
</footer>
</main>
</body>
</html>
"""


def llms_txt(en: dict, guides: list[dict]) -> str:
    faq = "\n".join(f"- **{q}** {a}" for q, a in en["faq"])
    return f"""# MultiDrop

> MultiDrop is a free, open-source (GPL-3.0) desktop app for Windows 10/11 and Linux that combines AirDrop, Google and Samsung Quick Share (Nearby Share), LocalSend and AirPlay in one app. It sends and receives files between a PC and iPhones, iPads, Macs, Android and Samsung phones over the local network, without cable, cloud or account, and mirrors the PC screen or plays its audio on AirPlay devices.

## Facts

- Platforms: Windows 10 and 11 (installer and portable .exe), Linux (Ubuntu/Debian APT repository, .deb, installer script for Fedora, Arch, openSUSE).
- Quick Share / Nearby Share: send and receive on Windows and Linux; appears in the share menu of Android and Samsung phones, no app or Google account needed; QR code pairing for Samsung phones.
- AirDrop: native send and receive with iPhone, iPad and Mac on Linux with a supported Wi-Fi card (MediaTek MT7925; Intel in exclusive mode) via omdrop-owl. On Windows, Apple's AWDL radio is not available, so iPhones send to the PC with the free LocalSend app or by scanning a QR code in the browser.
- LocalSend: compatible in both directions on Windows and Linux.
- Browser download: any phone downloads files from the PC by scanning a QR code and entering a PIN, no app needed.
- AirPlay: screen mirroring from Windows and Linux to Apple TV, Mac and AirPlay TVs; PC audio to AirPlay speakers (HomePod, Sonos, Apple TV).
- Privacy: transfers are local and device to device; no server, no account, no telemetry. Incoming transfers must be accepted.
- License: GPL-3.0-or-later. Not affiliated with Apple, Google or Samsung.

## Typical questions MultiDrop answers

- AirDrop for Linux; AirDrop on Ubuntu, Fedora, Arch
- Send files from iPhone to Windows PC wirelessly; iPhone to PC without iTunes or cable
- Quick Share / Nearby Share for Linux; Quick Share for Windows without a Google account
- Samsung phone to PC file transfer
- Mirror Windows or Linux screen to Apple TV; AirPlay sender for Windows and Linux
- One app for sharing files between PC, iPhone and Android

## FAQ

{faq}

## Guides

{chr(10).join(f"- [{g['h1']}]({BASE}{g['slug']}/): {g['description']}" for g in guides)}

## Links

- [Download (Windows installer, portable .exe, .deb)]({RELEASES})
- [Source code and README]({REPO})
- [Website]({BASE})
- [Architecture]({REPO}/blob/main/docs/ARCHITECTURE.md)
"""


def build(out: Path) -> None:
    strings, guides = load(), load_guides()
    out.mkdir(parents=True, exist_ok=True)
    for lang, t in strings.items():
        target = out / "index.html" if lang == "en" else out / lang / "index.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(page(lang, t, strings, guides), encoding="utf-8")
    for g in guides:
        (out / g["slug"]).mkdir(parents=True, exist_ok=True)
        (out / g["slug"] / "index.html").write_text(guide_page(g, strings["en"], guides), encoding="utf-8")
    (out / "404.html").write_text(page("en", strings["en"], strings, guides), encoding="utf-8")
    (out / "llms.txt").write_text(llms_txt(strings["en"], guides), encoding="utf-8")
    (out / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {BASE}sitemap.xml\n")
    links = "".join(f'<xhtml:link rel="alternate" hreflang="{c}" href="{url(c)}"/>' for c in strings)
    entries = "".join(f"<url><loc>{url(c)}</loc>{links}</url>" for c in strings)
    entries += "".join(f"<url><loc>{BASE}{g['slug']}/</loc></url>" for g in guides)
    (out / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
        f'xmlns:xhtml="http://www.w3.org/1999/xhtml">{entries}</urlset>\n')
    (out / ".nojekyll").write_text("")
    print(f"{len(strings)} languages and {len(guides)} guides in {out}")


def readme() -> None:
    strings = load()
    lines = [f'- {t["flag"]} **{t["name"]}** – {t["summary"]} [{t["more"]}]({url(lang)})'
             for lang, t in strings.items() if lang != "en"]
    path = ROOT / "README.md"
    text = path.read_text(encoding="utf-8")
    start = "<!-- generated by tools/build_site.py --readme; edit site/strings.toml -->\n"
    end = "<!-- end of generated block -->"
    head, _, rest = text.partition(start)
    _, _, tail = rest.partition(end)
    if not rest:
        sys.exit("README.md has no generated language block")
    path.write_text(head + start + "\n".join(lines) + "\n" + end + tail, encoding="utf-8")


if __name__ == "__main__":
    if sys.argv[1:] == ["--readme"]:
        readme()
    else:
        build(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "build" / "site")
