import sys
from typing import Optional

import requests


def fetch_html(url: str, timeout: int = 20) -> str:
    headers = {"User-Agent": "Mozilla/5.0 (compatible; scrape-iiko/1.0)"}
    response = requests.get(url, headers=headers, timeout=timeout)
    response.raise_for_status()
    return response.text


def main(argv: list[str]) -> int:
    url: Optional[str] = None
    if len(argv) > 1:
        url = argv[1]
    if not url:
        url = "https://m1.iiko.cards/ru-RU/CorporateNutrition/Guests"
    try:
        html = fetch_html(url)
    except Exception as exc:  # pragma: no cover - CLI convenience
        sys.stderr.write(f"Failed to fetch {url}: {exc}\n")
        return 1
    sys.stdout.write(html)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
