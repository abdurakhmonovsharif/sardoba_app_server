from __future__ import annotations

import argparse
import json
import os
import sys
from html.parser import HTMLParser
from pathlib import Path
from typing import Dict, Optional
from urllib.parse import urljoin, urlparse

import requests


class _LoginFormParser(HTMLParser):
    """Lightweight HTML parser to extract form action and input fields."""

    def __init__(self) -> None:
        super().__init__()
        self.form_action: Optional[str] = None
        self.inputs: Dict[str, str] = {}
        self._in_form = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_dict = {k.lower(): v for k, v in attrs}
        if tag.lower() == "form":
            if self.form_action is None:
                self.form_action = attr_dict.get("action")
                self._in_form = True
        if tag.lower() == "input" and self._in_form:
            name = attr_dict.get("name")
            if not name:
                return
            value = attr_dict.get("value") or ""
            self.inputs[name] = value

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "form":
            self._in_form = False


def _parse_login_form(html: str) -> tuple[Optional[str], Dict[str, str]]:
    parser = _LoginFormParser()
    parser.feed(html)
    return parser.form_action, parser.inputs


def perform_login(base_url: str, email: str, password: str, session: Optional[requests.Session] = None) -> dict:
    sess = session or requests.Session()
    headers = {"User-Agent": "Mozilla/5.0 (compatible; login-iiko/1.0)"}

    resp = sess.get(base_url, headers=headers, timeout=20)
    resp.raise_for_status()

    form_action, inputs = _parse_login_form(resp.text)
    inputs["Login"] = email
    inputs["Password"] = password
    # Ensure cookie consent is set; some endpoints expect this to be present.
    parsed = urlparse(resp.url)
    sess.cookies.set("CookieSet", "true", domain=parsed.hostname, path="/")

    # Try AJAX login endpoint first (as used by the page), then fall back to form action.
    ajax_url = urljoin(base_url, "/en-GB/Login/LoginAjax")
    resp2 = sess.post(ajax_url, headers=headers, data=inputs, allow_redirects=False, timeout=20)
    if resp2.status_code == 200 and resp2.text:
        # The ajax endpoint returns a redirect URL in the body; follow it.
        target = urljoin(base_url, resp2.text.strip())
        follow = sess.get(target, headers=headers, allow_redirects=True, timeout=20)
        follow.raise_for_status()
    else:
        post_url = urljoin(base_url, form_action) if form_action else base_url
        resp2 = sess.post(post_url, headers=headers, data=inputs, allow_redirects=True, timeout=20)
        resp2.raise_for_status()

    cookie_dict = requests.utils.dict_from_cookiejar(sess.cookies)
    return {
        "post_url": resp2.request.url,
        "status_code": resp2.status_code,
        "final_url": resp2.url,
        "cookies": cookie_dict,
        "text_preview": resp2.text[:5000],
    }


def _load_env_from_file(env_path: Path) -> None:
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def main(argv: list[str]) -> int:
    project_root = Path(__file__).resolve().parents[2]
    _load_env_from_file(project_root / ".env")

    env_email = (
        os.environ.get("IIKO_WEB_LOGIN")
        or os.environ.get("IIKO_LOGIN")
        or os.environ.get("IIKO_EMAIL")
    )
    env_password = (
        os.environ.get("IIKO_WEB_PASSWORD")
        or os.environ.get("IIKO_PASSWORD")
    )

    parser = argparse.ArgumentParser(description="Login to iiko and dump session cookies.")
    parser.add_argument("--email", default=env_email, help="Login email (default from .env: IIKO_WEB_LOGIN)")
    parser.add_argument(
        "--password",
        default=env_password,
        help="Login password (default from .env: IIKO_WEB_PASSWORD)",
    )
    parser.add_argument(
        "--base-url",
        default="https://m1.iiko.cards/ru-RU",
        help="Login page URL (default: %(default)s)",
    )
    parser.add_argument(
        "--save-cookies",
        default="iiko_session.json",
        help="Path to write cookies JSON (default: %(default)s)",
    )
    args = parser.parse_args(argv[1:])

    if not args.email or not args.password:
        parser.error("email and password are required (provide via args or set IIKO_WEB_LOGIN/IIKO_WEB_PASSWORD in .env)")

    try:
        result = perform_login(args.base_url, args.email, args.password)
    except Exception as exc:  # pragma: no cover - CLI convenience
        sys.stderr.write(f"Login failed: {exc}\n")
        return 1

    with open(args.save_cookies, "w", encoding="utf-8") as fp:
        json.dump(result["cookies"], fp, indent=2, ensure_ascii=False)

    sys.stdout.write(
        f"Login OK\nPOST URL: {result['post_url']}\nFinal URL: {result['final_url']}\n"
        f"Status: {result['status_code']}\nCookies saved to {args.save_cookies}\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
