from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import logging
from selenium import webdriver
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
)
from selenium.webdriver import ChromeOptions
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _load_env(env_path: Path) -> None:
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


def _wait(driver, timeout: int = 15) -> WebDriverWait:
    return WebDriverWait(driver, timeout)


def _base_url_from_target(target_url: str) -> str:
    parsed = urlparse(target_url)
    scheme = parsed.scheme or "https"
    netloc = parsed.netloc or parsed.path
    return f"{scheme}://{netloc}"


def _load_session_cookies(session_file: Path) -> list[dict[str, str]]:
    if not session_file.exists():
        return []
    try:
        raw = json.loads(session_file.read_text(encoding="utf-8"))
    except ValueError:
        return []
    if isinstance(raw, dict):
        if "cookies" in raw and isinstance(raw["cookies"], list):
            return raw["cookies"]
        return [{"name": name, "value": value} for name, value in raw.items()]
    if isinstance(raw, list):
        return raw
    return []


def _add_cookie_safe(driver, cookie: dict[str, str], default_domain: str) -> None:
    payload = {
        "name": cookie.get("name"),
        "value": cookie.get("value"),
        "domain": cookie.get("domain") or default_domain,
        "path": cookie.get("path") or "/",
    }
    if cookie.get("secure") is not None:
        payload["secure"] = cookie["secure"]
    if cookie.get("httpOnly") is not None:
        payload["httpOnly"] = cookie["httpOnly"]
    if cookie.get("expiry") is not None:
        payload["expiry"] = cookie["expiry"]
    try:
        driver.add_cookie(payload)
    except Exception:
        pass


def _restore_session(driver, session_file: Path, base_url: str) -> bool:
    cookies = _load_session_cookies(session_file)
    if not cookies:
        logger.info("No session cookies found at %s", session_file)
        return False
    logger.info("Restoring session from %s", session_file)
    driver.get(base_url)
    parsed = urlparse(base_url)
    domain = parsed.hostname or parsed.netloc
    for cookie in cookies:
        if not cookie.get("name") or cookie.get("value") is None:
            continue
        _add_cookie_safe(driver, cookie, domain)
    driver.refresh()
    return True


def _save_session(driver, session_file: Path) -> None:
    cookies = driver.get_cookies()
    sanitized: dict[str, str] = {cookie["name"]: cookie["value"] for cookie in cookies if cookie.get("name")}
    session_file.parent.mkdir(parents=True, exist_ok=True)
    session_file.write_text(json.dumps(sanitized, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Saved session cookies to %s", session_file)


def _ensure_login(driver, email: str | None, password: str | None) -> None:
    containers = driver.find_elements(By.ID, "loginFieldsContainer")
    if not containers or not containers[0].is_displayed():
        return
    login_locator = (By.ID, "loginFieldsContainer")
    if not email or not password:
        raise RuntimeError("Login page visible but no credentials provided (set IIKO_WEB_LOGIN/IIKO_WEB_PASSWORD).")
    logger.info("Performing login")
    driver.find_element(By.ID, "login").clear()
    driver.find_element(By.ID, "login").send_keys(email)
    driver.find_element(By.ID, "password").clear()
    driver.find_element(By.ID, "password").send_keys(password)
    driver.find_element(By.CSS_SELECTOR, "button#enter").click()
    try:
        _wait(driver).until(EC.invisibility_of_element_located(login_locator))
    except TimeoutException:
        raise RuntimeError("Login failed or OTP required; still on login page.") from None


def _wait_for_guest_rows(driver, timeout: int = 15) -> list:
    return _wait(driver, timeout=timeout).until(
        EC.presence_of_all_elements_located((By.CSS_SELECTOR, ".t-grid-content table tbody tr"))
    )


def _click_show_inactive(driver) -> None:
    try:
        toggle = _wait(driver, timeout=10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, 'label[for="ShowInactive"]'))
        )
    except TimeoutException:
        logger.warning("ShowInactive toggle not found on the guests page.")
        return
    driver.execute_script("arguments[0].scrollIntoView({behavior:'auto', block:'center'});", toggle)
    driver.execute_script("arguments[0].click();", toggle)
    time.sleep(1)
    try:
        checkbox = driver.find_element(By.ID, "ShowInactive")
        if not checkbox.is_selected():
            driver.execute_script("arguments[0].click();", checkbox)
    except NoSuchElementException:
        pass
    _wait_for_guest_rows(driver)


def _activate_row(driver, row):
    attempts = 0
    while attempts < 3:
        try:
            driver.execute_script("arguments[0].scrollIntoView({behavior: 'auto', block: 'center'});", row)
            _hover_element(driver, row)
            class_name = row.get_attribute("class") or ""
            if "t-state-hover" not in class_name:
                driver.execute_script(
                    """
                    const el = arguments[0];
                    const rect = el.getBoundingClientRect();
                    const x = rect.left + rect.width / 2;
                    const y = rect.top + rect.height / 2;
                    const opts = {bubbles: true, cancelable: true, clientX: x, clientY: y};
                    ['mousemove', 'mousedown', 'mouseup'].forEach(type => el.dispatchEvent(new MouseEvent(type, opts)));
                    """,
                    row,
                )
            try:
                _wait(driver, timeout=2).until(
                    lambda d: "t-state-hover" in (row.get_attribute("class") or "")
                    or "t-state-selected" in (row.get_attribute("class") or "")
                )
            except TimeoutException:
                pass
            return row
        except StaleElementReferenceException:
            attempts += 1
            row = _wait(driver, timeout=5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".t-grid-content table tbody tr"))
            )
    raise RuntimeError("Guest row keeps going stale while activating.")


def _hover_element(driver, element) -> None:
    try:
        ActionChains(driver).move_to_element(element).pause(0.1).perform()
        return
    except Exception:
        pass
    driver.execute_script(
        """
        const el = arguments[0];
        const rect = el.getBoundingClientRect();
        const x = rect.left + rect.width / 2;
        const y = rect.top + rect.height / 2;
        const opts = {bubbles: true, cancelable: true, clientX: x, clientY: y};
        ['mouseover', 'mouseenter', 'mousemove'].forEach(type => el.dispatchEvent(new MouseEvent(type, opts)));
        """,
        element,
    )


def _double_click_element(driver, element) -> None:
    try:
        ActionChains(driver).double_click(element).perform()
        return
    except Exception:
        pass
    driver.execute_script(
        """
        const el = arguments[0];
        const rect = el.getBoundingClientRect();
        const x = rect.left + rect.width / 2;
        const y = rect.top + rect.height / 2;
        const opts = {bubbles: true, cancelable: true, clientX: x, clientY: y};
        ['mousedown', 'mouseup', 'click', 'mousedown', 'mouseup', 'click', 'dblclick'].forEach(
            type => el.dispatchEvent(new MouseEvent(type, opts))
        );
        """,
        element,
    )


def _safe_click_element(driver, element, *, retries: int = 3) -> None:
    for attempt in range(retries):
        try:
            ActionChains(driver).move_to_element(element).pause(0.1).click().perform()
            return
        except ElementClickInterceptedException:
            driver.execute_script("arguments[0].scrollIntoView({behavior:'auto', block:'center'});", element)
            time.sleep(0.5)
    driver.execute_script("arguments[0].click();", element)


def _open_guest_details(driver, row) -> None:
    row = _activate_row(driver, row)
    try:
        row.click()
    except Exception:
        driver.execute_script("arguments[0].click();", row)
    time.sleep(0.5)
    _double_click_element(driver, row)
    _wait(driver, timeout=10).until(
        EC.visibility_of_element_located((By.CSS_SELECTOR, "#privateGuestInfo"))
    )


def _ensure_guest_form_visible(driver) -> None:
    try:
        toggler = _wait(driver, timeout=5).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "#privateGuestInfo .sectionTitle.toggle-block-switcher")
            )
        )
    except TimeoutException:
        return
    text = (toggler.text or "").lower()
    if "отобразить" in text:
        driver.execute_script("arguments[0].scrollIntoView({behavior:'auto', block:'center'});", toggler)
        driver.execute_script("arguments[0].click();", toggler)
        time.sleep(0.5)


def _set_text_input_value(driver, element, value: str) -> None:
    driver.execute_script(
        """
        const el = arguments[0];
        const value = arguments[1];
        el.value = value;
        const events = ['input', 'change', 'blur'];
        events.forEach(event =>
            el.dispatchEvent(new Event(event, {bubbles: true, cancelable: true}))
        );
        """,
        element,
        value,
    )


def _collect_page_phone_numbers(driver, seen: set[str]) -> None:
    rows = driver.find_elements(By.CSS_SELECTOR, ".t-grid-content table tbody tr")
    for row in rows:
        try:
            phone_cell = row.find_element(By.CSS_SELECTOR, "td.PhoneNumber")
        except NoSuchElementException:
            cells = row.find_elements(By.TAG_NAME, "td")
            phone_cell = cells[2] if len(cells) >= 3 else None
        if not phone_cell:
            continue
        phone = (phone_cell.text or "").strip()
        if phone:
            seen.add(phone)


def _next_fake_phone(phone_index: int, prefix: str, seen: set[str]) -> tuple[str, int]:
    candidate_index = phone_index
    while True:
        candidate = f"{prefix}{candidate_index:09d}"
        if candidate not in seen:
            return candidate, candidate_index + 1
        candidate_index += 1


def _max_seen_index(prefix: str, seen: set[str]) -> int:
    max_index = 0
    prefix_len = len(prefix)
    for phone in seen:
        if not phone.startswith(prefix):
            continue
        suffix = phone[prefix_len:]
        digits = "".join(ch for ch in suffix if ch.isdigit())
        if not digits:
            continue
        try:
            index = int(digits)
        except ValueError:
            continue
        if index > max_index:
            max_index = index
    return max_index


def _update_guest_info(driver, phone: str, first_name: str) -> None:
    phone_input = _wait(driver, timeout=10).until(EC.visibility_of_element_located((By.ID, "guestPhone")))
    _set_text_input_value(driver, phone_input, phone)
    first_input = driver.find_element(By.ID, "FirstName")
    _set_text_input_value(driver, first_input, first_name)
    try:
        deleted_checkbox = driver.find_element(By.ID, "IsDeleted")
        if not deleted_checkbox.is_selected():
            driver.execute_script("arguments[0].scrollIntoView({behavior:'auto', block:'center'});", deleted_checkbox)
            driver.execute_script("arguments[0].click();", deleted_checkbox)
    except NoSuchElementException:
        pass


def _is_guest_already_anonymized(driver, prefix: str) -> tuple[bool, str]:
    phone_input = driver.find_element(By.ID, "guestPhone")
    first_input = driver.find_element(By.ID, "FirstName")
    phone_value = (phone_input.get_attribute("value") or "").strip()
    first_value = (first_input.get_attribute("value") or "").strip().lower()
    deleted_checked = False
    try:
        deleted_checkbox = driver.find_element(By.ID, "IsDeleted")
        deleted_checked = deleted_checkbox.is_selected()
    except NoSuchElementException:
        pass
    has_deleted_label = first_value.startswith("deleted #") or first_value.startswith("deleted")
    return deleted_checked and phone_value.startswith(prefix) and has_deleted_label, phone_value


def _close_guest_modal(driver) -> None:
    try:
        cancel = _wait(driver, timeout=10).until(
            EC.element_to_be_clickable((By.ID, "cancelPrivateInfoButton"))
        )
    except TimeoutException:
        return
    _safe_click_element(driver, cancel)
    try:
        _wait(driver, timeout=10).until(
            EC.invisibility_of_element_located((By.CSS_SELECTOR, "#privateGuestInfo"))
        )
    except TimeoutException:
        time.sleep(0.5)


def _click_save_private_info(driver) -> None:
    save_button = _wait(driver, timeout=10).until(
        EC.element_to_be_clickable((By.ID, "savePrivateInfoButton"))
    )
    driver.execute_script("arguments[0].scrollIntoView({behavior:'auto', block:'center'});", save_button)
    _safe_click_element(driver, save_button)
    try:
        _wait(driver, timeout=10).until(EC.staleness_of(save_button))
    except TimeoutException:
        time.sleep(1)
    try:
        _wait(driver, timeout=15).until(
            EC.invisibility_of_element_located((By.CSS_SELECTOR, "#privateGuestInfo"))
        )
    except TimeoutException:
        time.sleep(1)


def _process_guest_by_index(
    driver,
    index: int,
    counter: int,
    phone_index: int,
    prefix: str,
    seen: set[str],
) -> tuple[int, int]:
    rows = _wait_for_guest_rows(driver)
    if index >= len(rows):
        raise IndexError("Guest row index out of range")
    row = rows[index]
    _open_guest_details(driver, row)
    _ensure_guest_form_visible(driver)
    already_anonymized, current_phone = _is_guest_already_anonymized(driver, prefix)
    if already_anonymized:
        if current_phone:
            seen.add(current_phone)
        logger.info("Skipping guest #%s because it was already anonymized (%s)", counter, current_phone)
        _close_guest_modal(driver)
        return counter + 1, phone_index
    fake_phone, phone_index = _next_fake_phone(phone_index, prefix, seen)
    first_name = f"deleted #{counter}"
    _update_guest_info(driver, fake_phone, first_name)
    seen.add(fake_phone)
    _click_save_private_info(driver)
    logger.info("Marked guest #%s as deleted with phone %s", counter, fake_phone)
    return counter + 1, phone_index


def _process_current_page(
    driver,
    counter: int,
    phone_index: int,
    prefix: str,
    seen: set[str],
    start_index: int = 0,
) -> tuple[int, int]:
    rows = _wait_for_guest_rows(driver)
    total = len(rows)
    logger.info("Processing %s guests on current page", total)
    for index in range(start_index, total):
        rows = _wait_for_guest_rows(driver)
        if index >= len(rows):
            break
        try:
            counter, phone_index = _process_guest_by_index(
                driver, index, counter, phone_index, prefix, seen
            )
        except Exception as exc:
            logger.exception("Failed to process guest #%s on this page: %s", counter, exc)
            counter += 1
    return counter, phone_index


def _click_next_page(driver) -> bool:
    try:
        pager = _wait(driver, timeout=10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".t-pager"))
        )
    except TimeoutException:
        return False
    next_link = None
    for candidate in pager.find_elements(By.CSS_SELECTOR, "a.t-link"):
        try:
            candidate.find_element(By.CSS_SELECTOR, "span.t-icon.t-arrow-next")
        except NoSuchElementException:
            continue
        next_link = candidate
        break
    if not next_link:
        return False
    classes = (next_link.get_attribute("class") or "").split()
    if "t-state-disabled" in classes:
        return False
    driver.execute_script("arguments[0].scrollIntoView({behavior:'auto', block:'center'});", next_link)
    try:
        next_link.click()
    except (ElementClickInterceptedException, StaleElementReferenceException):
        _safe_click_element(driver, next_link)
    try:
        _wait(driver, timeout=15).until(EC.staleness_of(next_link))
    except TimeoutException:
        time.sleep(1)
    _wait_for_guest_rows(driver)
    return True


def _process_all_pages(
    driver, prefix: str, start_page: int, start_index: int, min_phone_index: int
) -> int:
    counter = 1
    phone_index = 1
    seen: set[str] = set()
    page_index = 1
    phone_index_initialized = False
    while True:
        logger.info("Starting page %s", page_index)
        _collect_page_phone_numbers(driver, seen)
        if page_index < start_page:
            if not _click_next_page(driver):
                break
            page_index += 1
            continue
        current_start_index = start_index if page_index == start_page else 0
        if not phone_index_initialized:
            phone_index = max(
                phone_index,
                min_phone_index,
                _max_seen_index(prefix, seen) + 1,
            )
            phone_index_initialized = True
        counter, phone_index = _process_current_page(
            driver, counter, phone_index, prefix, seen, current_start_index
        )
        if not _click_next_page(driver):
            break
        page_index += 1
    return max(0, counter - 1)


def _goto_guests_page(driver, target_url: str, attempts: int = 3) -> None:
    for i in range(attempts):
        driver.get(target_url)
        try:
            _wait(driver, timeout=15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".t-grid-content table tbody tr"))
            )
            return
        except TimeoutException:
            if i == attempts - 1:
                raise
            time.sleep(2)


def main(argv: list[str]) -> int:
    project_root = Path(__file__).resolve().parents[2]
    _load_env(project_root / ".env")

    default_email = os.environ.get("IIKO_WEB_LOGIN") or os.environ.get("IIKO_LOGIN") or os.environ.get("IIKO_EMAIL")
    default_password = os.environ.get("IIKO_WEB_PASSWORD") or os.environ.get("IIKO_PASSWORD")

    parser = argparse.ArgumentParser(description="Anonymize guest phones and names via the iiko web interface.")
    parser.add_argument("--email", default=default_email, help="Login email (default from env)")
    parser.add_argument("--password", default=default_password, help="Login password (default from env)")
    parser.add_argument("--headless", action="store_true", help="Run Chrome headless")
    parser.add_argument(
        "--session-file",
        default=os.environ.get("IIKO_SESSION_FILE") or "iiko_session.json",
        help="Path to load/save session cookies (default: %(default)s)",
    )
    parser.add_argument(
        "--fake-phone-prefix",
        default=os.environ.get("IIKO_FAKE_PHONE_PREFIX") or "+891",
        help="Prefix for generated fake phone numbers (default: %(default)s)",
    )
    parser.add_argument(
        "--start-page",
        type=int,
        default=1,
        help="Page number to start processing (1-indexed, default: %(default)s)",
    )
    parser.add_argument(
        "--start-index",
        type=int,
        default=0,
        help="Row index on the start page to resume from (0-indexed, default: %(default)s)",
    )
    parser.add_argument(
        "--min-phone-index",
        type=int,
        default=int(os.environ.get("IIKO_MIN_PHONE_INDEX", "101")),
        help="Minimum phone sequence number to start from (default: %(default)s)",
    )
    args = parser.parse_args(argv[1:])

    options = ChromeOptions()
    if args.headless:
        options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    driver.set_window_size(1400, 900)

    target_url = "https://m1.iiko.cards/ru-RU/CorporateNutrition/Guests"
    session_file = Path(args.session_file).expanduser()
    base_url = _base_url_from_target(target_url)

    try:
        logger.info("Starting anonymization run with session file %s", session_file)
        _restore_session(driver, session_file, base_url)
        driver.get(target_url)
        _ensure_login(driver, args.email, args.password)
        _save_session(driver, session_file)
        _goto_guests_page(driver, target_url)
        _click_show_inactive(driver)
        total = _process_all_pages(
            driver,
            args.fake_phone_prefix,
            max(1, args.start_page),
            max(0, args.start_index),
            max(1, args.min_phone_index),
        )
        logger.info("Completed anonymization of %s guests", total)

        if not args.headless:
            print("Automation done. Browser open for inspection; close the window to exit.")
            _wait(driver, timeout=86400).until(lambda d: False)  # block until browser is manually closed.
    finally:
        try:
            driver.quit()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
