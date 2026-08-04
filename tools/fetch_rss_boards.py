"""
Фетчер job-бордов, отдающих стандартный RSS.

Один модуль на несколько площадок вместо файла на каждую: Jobspresso и Berlin
Startup Jobs отличаются ровно одним — адресом фида. Формат job-RSS
стандартизован (WordPress WP Job Manager и его клоны), и заводить под каждый
почти одинаковый файл значит гарантированно получить расхождение при первой же
правке.

Добавить площадку = добавить строку в BOARDS. Если её фид окажется устроен
иначе — вот тогда и появится отдельный модуль, а не заранее.
"""
from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

SOURCE_NAME = "rss_boards"

BOARDS = {
    # name: (url, remote_only, локация по умолчанию)
    "jobspresso": ("https://jobspresso.co/?feed=job_feed", True, "Worldwide"),
    "berlinstartupjobs": ("https://berlinstartupjobs.com/feed/", False, "Berlin, Germany"),
}

# В job-RSS компания и локация лежат в отдельных namespace-полях, но далеко не
# всегда: у части площадок они внутри заголовка через дефис или в описании.
_NS = {"job": "http://www.w3.org/2005/Atom"}
_COMPANY_IN_TITLE = re.compile(r"^(?P<title>.+?)\s+(?:at|@|-)\s+(?P<company>[^-]+)$")


def _text(node, tag: str) -> str:
    found = node.find(tag)
    return (found.text or "").strip() if found is not None and found.text else ""


def _split_title_and_company(raw_title: str, explicit_company: str):
    """Компанию берём из отдельного поля, если оно есть; иначе разбираем
    заголовок вида «Senior Developer at Acme»."""
    if explicit_company:
        return raw_title.strip(), explicit_company.strip()
    m = _COMPANY_IN_TITLE.match(raw_title.strip())
    if m:
        return m.group("title").strip(), m.group("company").strip()
    return raw_title.strip(), ""


def _item_to_common_schema(item, board: str, remote_only: bool, default_location: str):
    raw_title = _text(item, "title")
    url = _text(item, "link")
    if not raw_title or not url:
        return None

    # Разные площадки кладут компанию в разные теги; проверяем известные.
    explicit_company = ""
    for tag in ("{http://www.w3.org/2005/Atom}company", "company", "dc:creator",
                "{http://purl.org/dc/elements/1.1/}creator"):
        explicit_company = _text(item, tag)
        if explicit_company:
            break

    title, company = _split_title_and_company(raw_title, explicit_company)
    if not company:
        return None  # без компании запись бесполезна для дедупликации и отчёта

    categories = [c.text.strip() for c in item.findall("category") if c is not None and c.text]

    return {
        "source": SOURCE_NAME,
        "external_id": url,
        "title": title,
        "company": company,
        "url": url,
        "location_raw": _text(item, "location") or default_location,
        "remote": True if remote_only else None,
        "tags": [f"board:{board}"] + categories[:5],
        "description_text": common.strip_html(_text(item, "description")),
        "posted_at": _text(item, "pubDate") or None,
        "salary_raw": None,
    }


def fetch(boards: Optional[List[str]] = None, timeout: int = common.DEFAULT_TIMEOUT):
    import requests

    boards = boards or list(BOARDS)
    records: List[dict] = []
    skipped = 0
    errors: List[str] = []

    for board in boards:
        cfg = BOARDS.get(board)
        if not cfg:
            errors.append(f"неизвестная площадка '{board}'")
            continue
        url, remote_only, default_location = cfg

        try:
            resp = requests.get(url, headers={"User-Agent": common.USER_AGENT}, timeout=timeout)
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{board}: {type(exc).__name__}")
            continue

        items = root.findall(".//item")
        if not items:
            errors.append(f"{board}: в фиде нет элементов item")
            continue

        for item in items:
            rec = _item_to_common_schema(item, board, remote_only, default_location)
            if rec is None:
                skipped += 1
                continue
            records.append(rec)

    note = []
    if skipped:
        note.append(f"пропущено {skipped} записей без компании")
    if errors:
        note.append("; ".join(errors[:3]))
    return records, ("; ".join(note) or None)


def main() -> None:
    import argparse
    import identity as identity_mod

    parser = argparse.ArgumentParser(description="Сбор вакансий с RSS-бордов")
    identity_mod.add_identity_arg(parser)
    parser.add_argument("--board", action="append", choices=sorted(BOARDS))
    args = parser.parse_args()
    identity_mod.activate_or_exit(args.identity)
    records, note = fetch(args.board)
    print(f"{SOURCE_NAME}: {len(records)} записей ({note or 'без замечаний'})")


if __name__ == "__main__":
    main()
