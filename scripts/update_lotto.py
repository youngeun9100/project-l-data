#!/usr/bin/env python3
"""Fetch and validate Lotto 6/45 draw history for Project.L."""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SOURCE_PAGE = "https://www.dhlottery.co.kr/lt645/winNumber"
DATA_ENDPOINT = "https://www.dhlottery.co.kr/lt645/selectPstLt645Info.do"
DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "data" / "winning_numbers.json"
BATCH_SIZE = 200


class LottoDataError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate the existing file without contacting the network.",
    )
    return parser.parse_args()


def load_existing(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "schemaVersion": 1,
            "latestDraw": 0,
            "latestDrawDate": None,
            "source": SOURCE_PAGE,
            "draws": [],
        }

    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise LottoDataError(f"Cannot read {path}: {exc}") from exc


def request_draws(start: int, end: int) -> list[dict[str, Any]]:
    query = urllib.parse.urlencode(
        {"srchStrLtEpsd": str(start), "srchEndLtEpsd": str(end)}
    )
    request = urllib.request.Request(
        f"{DATA_ENDPOINT}?{query}",
        headers={
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Referer": SOURCE_PAGE,
            "User-Agent": "Project-L-Data-Updater/1.0",
            "X-Requested-With": "XMLHttpRequest",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            content_type = response.headers.get_content_type()
            body = response.read().decode("utf-8")
    except (urllib.error.URLError, TimeoutError, UnicodeDecodeError) as exc:
        raise LottoDataError(f"Request failed for draws {start}-{end}: {exc}") from exc

    if content_type != "application/json":
        raise LottoDataError(
            f"Expected JSON for draws {start}-{end}, received {content_type}"
        )

    try:
        payload = json.loads(body)
        rows = payload["data"]["list"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise LottoDataError(f"Unexpected response for draws {start}-{end}") from exc

    if not isinstance(rows, list):
        raise LottoDataError(f"Draw list is not an array for draws {start}-{end}")
    return rows


def normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    try:
        draw = int(row["ltEpsd"])
        numbers = sorted(int(row[f"tm{index}WnNo"]) for index in range(1, 7))
        bonus = int(row["bnsWnNo"])
        date = datetime.strptime(str(row["ltRflYmd"]), "%Y%m%d").date().isoformat()
    except (KeyError, TypeError, ValueError) as exc:
        raise LottoDataError(f"Invalid draw row: {row!r}") from exc

    if draw < 1:
        raise LottoDataError(f"Invalid draw number: {draw}")
    if len(set(numbers)) != 6 or any(number < 1 or number > 45 for number in numbers):
        raise LottoDataError(f"Invalid winning numbers in draw {draw}: {numbers}")
    if bonus < 1 or bonus > 45 or bonus in numbers:
        raise LottoDataError(f"Invalid bonus number in draw {draw}: {bonus}")

    return {"draw": draw, "date": date, "numbers": numbers, "bonus": bonus}


def validate_document(document: dict[str, Any]) -> None:
    if document.get("schemaVersion") != 1:
        raise LottoDataError("Unsupported schemaVersion")
    if document.get("source") != SOURCE_PAGE:
        raise LottoDataError("Unexpected source URL")

    draws = document.get("draws")
    if not isinstance(draws, list):
        raise LottoDataError("draws must be an array")

    normalized = [normalize_public_draw(item) for item in draws]
    expected = list(range(1, len(normalized) + 1))
    actual = [item["draw"] for item in normalized]
    if actual != expected:
        raise LottoDataError("Draw history must be continuous and ordered from draw 1")

    latest = len(normalized)
    if document.get("latestDraw") != latest:
        raise LottoDataError("latestDraw does not match the draw list")

    expected_date = normalized[-1]["date"] if normalized else None
    if document.get("latestDrawDate") != expected_date:
        raise LottoDataError("latestDrawDate does not match the latest draw")


def normalize_public_draw(item: dict[str, Any]) -> dict[str, Any]:
    try:
        draw = int(item["draw"])
        date = datetime.strptime(str(item["date"]), "%Y-%m-%d").date().isoformat()
        numbers = [int(number) for number in item["numbers"]]
        bonus = int(item["bonus"])
    except (KeyError, TypeError, ValueError) as exc:
        raise LottoDataError(f"Invalid public draw: {item!r}") from exc

    if numbers != sorted(numbers):
        raise LottoDataError(f"Numbers are not sorted in draw {draw}")
    if len(numbers) != 6 or len(set(numbers)) != 6:
        raise LottoDataError(f"Draw {draw} must contain six unique numbers")
    if any(number < 1 or number > 45 for number in numbers):
        raise LottoDataError(f"Number outside 1-45 in draw {draw}")
    if bonus < 1 or bonus > 45 or bonus in numbers:
        raise LottoDataError(f"Invalid bonus number in draw {draw}")

    return {"draw": draw, "date": date, "numbers": numbers, "bonus": bonus}


def fetch_missing(existing: dict[str, Any]) -> dict[str, Any]:
    validate_document(existing)
    by_draw = {item["draw"]: item for item in existing["draws"]}
    next_draw = existing["latestDraw"] + 1

    while True:
        end = next_draw + BATCH_SIZE - 1
        rows = request_draws(next_draw, end)
        if not rows:
            break

        received = [normalize_row(row) for row in rows]
        for item in received:
            if item["draw"] < next_draw or item["draw"] > end:
                raise LottoDataError(f"Server returned draw outside requested range: {item['draw']}")
            by_draw[item["draw"]] = item

        highest = max(item["draw"] for item in received)
        next_draw = highest + 1
        if len(received) < BATCH_SIZE:
            break
        time.sleep(0.2)

    draws = [by_draw[number] for number in sorted(by_draw)]
    result = {
        "schemaVersion": 1,
        "latestDraw": len(draws),
        "latestDrawDate": draws[-1]["date"] if draws else None,
        "source": SOURCE_PAGE,
        "draws": draws,
    }
    validate_document(result)
    return result


def write_if_changed(path: Path, before: dict[str, Any], after: dict[str, Any]) -> bool:
    if before == after:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(after, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    temporary.replace(path)
    return True


def main() -> int:
    args = parse_args()
    try:
        existing = load_existing(args.output)
        validate_document(existing)
        if args.check:
            print(f"Valid: {existing['latestDraw']} draws")
            return 0

        updated = fetch_missing(existing)
        changed = write_if_changed(args.output, existing, updated)
        status = "Updated" if changed else "Already current"
        print(f"{status}: {updated['latestDraw']} draws")
        return 0
    except LottoDataError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

