"""The website (tools/build_site.py, site/strings.toml)."""

import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_every_language_has_every_text():
    strings = tomllib.loads((ROOT / "site" / "strings.toml").read_text(encoding="utf-8"))
    en = strings["en"]
    for lang, t in strings.items():
        assert set(en) - {"dir"} <= set(t), lang
        assert len(t["features"]) == len(en["features"]), lang
        assert len(t["faq"]) == len(en["faq"]) and all(len(qa) == 2 for qa in t["faq"]), lang


def test_build_writes_pages_with_valid_structured_data(tmp_path):
    subprocess.run([sys.executable, str(ROOT / "tools" / "build_site.py"), str(tmp_path)],
                   check=True, capture_output=True)
    pages = sorted(tmp_path.rglob("index.html"))
    assert len(pages) >= 18
    for page in pages:
        text = page.read_text(encoding="utf-8")
        blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', text, re.S)
        assert {json.loads(b)["@type"] for b in blocks} == {"SoftwareApplication", "FAQPage"}
        assert 'hreflang="x-default"' in text
    assert 'dir="rtl"' in (tmp_path / "ar" / "index.html").read_text(encoding="utf-8")
    sitemap = (tmp_path / "sitemap.xml").read_text()
    assert sitemap.count("<loc>") == len(pages)
    assert "AirDrop" in (tmp_path / "llms.txt").read_text()


def test_readme_language_block_is_current():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    strings = tomllib.loads((ROOT / "site" / "strings.toml").read_text(encoding="utf-8"))
    for lang, t in strings.items():
        if lang != "en":
            assert t["summary"] in readme, f"README.md is stale for {lang}: tools/build_site.py --readme"
