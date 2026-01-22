"""Fetch and normalise menus from Sardoba iKKO MyResto instances.

The module can be executed as a script or imported by the FastAPI backend.
It gathers menu data from configured endpoints, merges branch-specific
pricing, applies stop-lists per store, and emits a compact structure ready
for the mobile application.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from collections import OrderedDict
from copy import deepcopy
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

import httpx
from dotenv import load_dotenv

load_dotenv()

DEFAULT_MENU_URLS = [
    os.getenv("MENU_API_URL", "https://sardobarestaurant.myresto.online/api/v1/menu"),
    os.getenv("MENU_GIJDUVON_API_URL", "https://sardobagijduvon.myresto.online/api/v1/menu"),
]

STOP_LIST_API_URL = os.getenv(
    "STOP_LIST_API_URL",
    "https://sardobarestaurant.myresto.online/api/v1/menu/stop-lists",
)
STOP_LIST_GIJDUVON_API_URL = os.getenv(
    "STOP_LIST_GIJDUVON_API_URL",
    "https://sardobagijduvon.myresto.online/api/v1/menu/stop-lists",
)

STORE_IDS_ENV = os.getenv("STORE_IDS", "139350,139458,139235,157757")
STORE_IDS: List[int] = [int(s.strip()) for s in STORE_IDS_ENV.split(",") if s.strip()]

SARDOBA_GEOFIZIKA = os.getenv("SARDOBA_GEOFIZIKA")
SARDOBA_GIDIVON = os.getenv("SARDOBA_GIDIVON")
SARDOBA_SEVERNIY = os.getenv("SARDOBA_SEVERNIY")
SARDOBA_MK5 = os.getenv("SARDOBA_MK5")

STORE_NAMES: Dict[int, str] = {
    139235: "Sardoba_Geofizika",
    139350: "Sardoba_Severniy",
    139458: "Sardoba_5MK",
    157757: "Sardoba_Gijduvon",
}

if SARDOBA_GEOFIZIKA and SARDOBA_GEOFIZIKA.isdigit():
    STORE_NAMES[int(SARDOBA_GEOFIZIKA)] = STORE_NAMES.get(int(SARDOBA_GEOFIZIKA), "Geofizika")
if SARDOBA_SEVERNIY and SARDOBA_SEVERNIY.isdigit():
    STORE_NAMES[int(SARDOBA_SEVERNIY)] = STORE_NAMES.get(int(SARDOBA_SEVERNIY), "Yunusobod")
if SARDOBA_MK5 and SARDOBA_MK5.isdigit():
    STORE_NAMES[int(SARDOBA_MK5)] = STORE_NAMES.get(int(SARDOBA_MK5), "Sergeli")
if SARDOBA_GIDIVON and SARDOBA_GIDIVON.isdigit():
    STORE_NAMES[int(SARDOBA_GIDIVON)] = STORE_NAMES.get(int(SARDOBA_GIDIVON), "Gijduvon")

MENU_CACHE_TTL = int(os.getenv("MENU_CACHE_TTL", "120"))
STOPLIST_CACHE_TTL = int(os.getenv("STOPLIST_CACHE_TTL", "60"))
MENU_RESPONSE_CACHE_TTL = int(os.getenv("MENU_RESPONSE_CACHE_TTL", "30"))
HTTP_TIMEOUT = float(os.getenv("MENU_HTTP_TIMEOUT", "10"))

_menu_cache: Dict[str, tuple[float, Any]] = {}
_stoplist_cache: Dict[int, tuple[float, Set[str]]] = {}
_menu_response_cache: Optional[tuple[float, Dict[str, Any]]] = None

_http_client = httpx.Client(timeout=HTTP_TIMEOUT)
logger = logging.getLogger(__name__)


def _unique(values: Iterable[str]) -> List[str]:
    seen: Set[str] = set()
    result: List[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _get_json(url: str, ttl: int, cache: Dict[str, tuple[float, Any]]) -> Any:
    now = time.time()
    if url in cache:
        ts, data = cache[url]
        if now - ts < ttl:
            return data
    try:
        response = _http_client.get(url)
        response.raise_for_status()
        data = response.json()
        cache[url] = (now, data)
        return data
    except httpx.HTTPError as exc:
        logger.warning("Failed to fetch menu url=%s: %s", url, exc)
        raise


def fetch_menu(url: str) -> Any:
    return _get_json(url, MENU_CACHE_TTL, _menu_cache)


def _extract_images(payload: Optional[Any]) -> List[str]:
    if not payload:
        return []
    if isinstance(payload, str):
        return [payload]
    if isinstance(payload, dict):
        return _unique([value for value in payload.values() if isinstance(value, str)])
    return []


def _convert_prices(
    prices: List[Dict[str, Any]],
    stoplists: Dict[int, Set[str]],
    item_id: Optional[str],
) -> Dict[int, Dict[str, Any]]:
    result: Dict[int, Dict[str, Any]] = {}
    for price in prices:
        store_id = price.get("storeId")
        amount = price.get("price")
        if store_id is None or amount is None:
            continue
        store_name = STORE_NAMES.get(store_id, str(store_id))
        if isinstance(amount, (int, float)):
            amount = int(amount)
        disabled = bool(item_id and store_id in stoplists and item_id in stoplists[store_id])
        result[store_id] = {
            "storeId": store_id,
            "storeName": store_name,
            "price": amount,
            "disabled": disabled,
        }
    return result


def _normalise_item(
    item: Dict[str, Any],
    stoplists: Dict[int, Set[str]],
) -> Optional[Dict[str, Any]]:
    if item.get("isHidden"):
        return None

    sizes = item.get("itemSizes") or []
    size = next((s for s in sizes if s.get("isDefault")), sizes[0] if sizes else None)
    if not size:
        return None

    prices = _convert_prices(size.get("prices", []), stoplists, item.get("itemId"))
    if not prices:
        return None

    images = _extract_images(size.get("buttonImage"))
    if not images:
        images = _extract_images(item.get("buttonImage"))

    return {
        "id": item.get("itemId"),
        "name": item.get("name"),
        "slug": item.get("slug"),
        "prices": prices,
        "images": images,
    }


def _merge_category(
    aggregate: OrderedDict[str, Dict[str, Any]],
    category: Dict[str, Any],
    stoplists: Dict[int, Set[str]],
) -> None:
    key = category.get("slug") or category.get("id") or str(len(aggregate))
    target = aggregate.get(key)
    if not target:
        target = {
            "id": category.get("id"),
            "name": category.get("name"),
            "slug": category.get("slug"),
            "items": OrderedDict(),
        }
        aggregate[key] = target

    for item in category.get("items", []):
        normalised = _normalise_item(item, stoplists)
        if not normalised:
            continue

        item_key = normalised.get("id") or normalised.get("slug") or str(len(target["items"]))
        existing = target["items"].get(item_key)
        if not existing:
            existing = {
                "id": normalised.get("id"),
                "name": normalised.get("name"),
                "prices": {},
                "images": [],
            }
            target["items"][item_key] = existing

        for store_id, payload in normalised["prices"].items():
            existing["prices"][store_id] = payload

        for img in normalised["images"]:
            if img not in existing["images"]:
                existing["images"].append(img)


def _stoplist_url_for_store(store_id: int) -> str:
    base = STOP_LIST_GIJDUVON_API_URL if str(store_id) == (SARDOBA_GIDIVON or "") else STOP_LIST_API_URL
    return f"{base.rstrip('/')}/{store_id}"


def _fetch_stoplist(store_id: int) -> Set[str]:
    now = time.time()
    cache_entry = _stoplist_cache.get(store_id)
    if cache_entry and now - cache_entry[0] < STOPLIST_CACHE_TTL:
        return cache_entry[1]

    url = _stoplist_url_for_store(store_id)
    try:
        response = _http_client.get(url)
        response.raise_for_status()
        data = response.json()
    except httpx.HTTPError:
        disabled: Set[str] = set()
    else:
        result = data.get("result") if isinstance(data, dict) else None
        if isinstance(result, dict):
            disabled = {
                str(key)
                for key, value in result.items()
                if isinstance(value, (int, float)) and value <= 0
            }
        else:
            disabled = set()
    _stoplist_cache[store_id] = (now, disabled)
    return disabled


def _collect_stoplists(store_ids: Iterable[int]) -> Dict[int, Set[str]]:
    return {store_id: _fetch_stoplist(store_id) for store_id in store_ids}


def merge_menus(payloads: Sequence[Any]) -> Dict[str, Any]:
    store_ids: Set[int] = set(STORE_IDS)

    # Collect store IDs present in payloads
    for payload in payloads:
        for category in payload.get("result", {}).get("itemCategories", []):
            for item in category.get("items", []):
                for size in item.get("itemSizes", []):
                    for price in size.get("prices", []):
                        sid = price.get("storeId")
                        if isinstance(sid, int):
                            store_ids.add(sid)

    stoplists = _collect_stoplists(store_ids)
    categories_aggregate: OrderedDict[str, Dict[str, Any]] = OrderedDict()

    for payload in payloads:
        categories = payload.get("result", {}).get("itemCategories", [])
        for category in categories:
            if category.get("isHidden"):
                continue
            _merge_category(categories_aggregate, category, stoplists)

    categories_list: List[Dict[str, Any]] = []
    for category in categories_aggregate.values():
        items_output: List[Dict[str, Any]] = []
        for item in category["items"].values():
            prices_output = list(sorted(item["prices"].values(), key=lambda p: p["storeId"]))
            items_output.append(
                {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "prices": prices_output,
                    "images": item.get("images", []),
                }
            )

        categories_list.append(
            {
                "id": category.get("id"),
                "name": category.get("name"),
                "slug": category.get("slug"),
                "items": items_output,
            }
        )

    return {"success": True, "categories": categories_list}


def get_simplified_menu(urls: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    global _menu_response_cache

    target_urls = [url for url in (urls or DEFAULT_MENU_URLS) if url]
    target_urls = list(dict.fromkeys(target_urls))

    if not urls or urls == DEFAULT_MENU_URLS:
        cache_entry = _menu_response_cache
        if cache_entry:
            ts, cached_value = cache_entry
            if time.time() - ts < MENU_RESPONSE_CACHE_TTL:
                return deepcopy(cached_value)

    payloads: list[Any] = []
    for url in target_urls:
        try:
            payloads.append(fetch_menu(url))
        except httpx.HTTPError:
            continue

    if not payloads:
        if _menu_response_cache:
            _, cached_value = _menu_response_cache
            logger.warning("Returning cached menu because all sources failed")
            return deepcopy(cached_value)
        logger.error("All menu sources failed and no cache available")
        return {"success": False, "categories": []}

    merged = merge_menus(payloads)

    if not urls or urls == DEFAULT_MENU_URLS:
        _menu_response_cache = (time.time(), deepcopy(merged))

    return merged


def main() -> None:
    urls = sys.argv[1:] or DEFAULT_MENU_URLS
    try:
        simplified = get_simplified_menu(urls)
    except httpx.HTTPError as exc:  # pragma: no cover
        print(f"Failed to fetch menu: {exc}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(simplified, ensure_ascii=False, indent=2))


if __name__ == "__main__":  # pragma: no cover
    main()
