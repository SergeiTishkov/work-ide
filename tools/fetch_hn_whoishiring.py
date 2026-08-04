"""
Фетчер источника Hacker News "Who is hiring?" — через официальный Algolia HN
Search API (http://hn.algolia.com/api/v1/), без ключа, без скрейпинга HTML.

Легаси/enterprise вакансии часто попадают именно в этот тред, а не на обычные
джоб-борды — стоит внимания, несмотря на шумный формат.

Алгоритм:
  1. search_by_date с тегами story,author_whoishiring находит самый свежий
     тред "Ask HN: Who is hiring?" (whoishiring публикует и "who wants to be
     hired" в тот же день — отфильтровываем по заголовку).
  2. Для набора ключевых слов стека ищем комментарии внутри этого треда
     (tags=comment,story_<id>) — это гораздо эффективнее, чем скачивать все
     сотни комментариев через Firebase API и грепать их по одному.
  3. Комментарии, как правило, начинают с "Company | Role | Location | ..." —
     разбираем эту конвенцию best-effort; если не парсится, используем первую
     строку как заголовок с компанией "Unknown (HN thread)".
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

SOURCE_NAME = "hn_whoishiring"
THREAD_SEARCH_URL = "http://hn.algolia.com/api/v1/search_by_date"
COMMENT_SEARCH_URL = "http://hn.algolia.com/api/v1/search"

# Сколько ключевых слов брать по умолчанию. Это БЮДЖЕТ СТОИМОСТИ, а не
# ограничение качества: каждое слово — отдельный HTTP-запрос к Algolia (см. цикл
# ниже). Пять слов = пять запросов на каждый прогон пайплайна.
DEFAULT_KEYWORD_LIMIT = 5
DEFAULT_HITS_PER_KEYWORD = 50


def _default_keywords() -> list:
    """Ключевые слова из стека активной идентичности.

    Раньше здесь был захардкоженный список стека владельца — единственный
    фетчер, куда личные данные протекли в слой сбора. Теперь слова берутся из
    profile.tech_stack.core активной идентичности, а идентичность может задать
    их явно через params в своём <префикс>_sources.yaml.
    """
    import score

    profile = score.load_profile() or {}
    core = (profile.get("tech_stack") or {}).get("core") or []
    return [str(k) for k in core[:DEFAULT_KEYWORD_LIMIT]]


def fetch(keywords: Optional[list] = None,
          hits_per_keyword: int = DEFAULT_HITS_PER_KEYWORD,
          timeout: int = common.DEFAULT_TIMEOUT,
          url: Optional[str] = None):
    import requests

    keywords = keywords or _default_keywords()
    if not keywords:
        return [], "нет ключевых слов: у идентичности пуст tech_stack.core"

    session = requests.Session()
    session.headers.update({"User-Agent": common.USER_AGENT})

    try:
        thread_resp = session.get(
            THREAD_SEARCH_URL,
            params={"tags": "story,author_whoishiring", "hitsPerPage": 10},
            timeout=timeout,
        )
        thread_resp.raise_for_status()
        thread_payload = thread_resp.json()
    except Exception as exc:  # noqa: BLE001
        return [], f"{type(exc).__name__}: {exc} (thread lookup failed)"

    story = _pick_latest_hiring_thread(thread_payload.get("hits", []))
    if story is None:
        return [], "no 'Ask HN: Who is hiring?' thread found in recent results"

    story_id = story["objectID"]
    story_title = story.get("title", "")

    seen_ids = set()
    records = []
    errors = []
    for kw in keywords:
        try:
            resp = session.get(
                COMMENT_SEARCH_URL,
                params={
                    "tags": f"comment,story_{story_id}",
                    "query": kw,
                    "hitsPerPage": hits_per_keyword,
                },
                timeout=timeout,
            )
            resp.raise_for_status()
            hits = resp.json().get("hits", [])
        except Exception as exc:  # noqa: BLE001
            errors.append(f"keyword '{kw}': {type(exc).__name__}: {exc}")
            continue

        for hit in hits:
            oid = hit.get("objectID")
            if not oid or oid in seen_ids:
                continue
            seen_ids.add(oid)
            rec = _to_common_schema(hit, story_title)
            if rec is not None:
                records.append(rec)

    error = "; ".join(errors) if errors else None
    return records, error


def _pick_latest_hiring_thread(hits: list) -> Optional[dict]:
    for hit in hits:
        title = (hit.get("title") or "").lower()
        if title.startswith("ask hn: who is hiring"):
            return hit
    return None


def _to_common_schema(hit: dict, story_title: str) -> Optional[dict]:
    object_id = hit.get("objectID")
    comment_html = hit.get("comment_text") or ""
    if not object_id or not comment_html:
        return None

    text = common.strip_html(comment_html)
    if not text:
        return None

    first_line = text.split("\n", 1)[0].strip()
    parts = [p.strip() for p in first_line.split("|") if p.strip()]

    if len(parts) >= 2:
        company, title = parts[0], parts[1]
        location_raw = parts[2] if len(parts) >= 3 else ""
    else:
        company, title, location_raw = "Unknown (HN thread)", first_line[:140], ""

    remote = "remote" in text.lower()

    return {
        "source": SOURCE_NAME,
        "external_id": str(object_id),
        "title": title or story_title,
        "company": company,
        "url": f"https://news.ycombinator.com/item?id={object_id}",
        "location_raw": location_raw,
        "remote": remote if remote else None,
        "tags": ["hn-whoishiring"],
        "description_html": comment_html,
        "posted_at_epoch": hit.get("created_at_i"),
        "salary_raw": None,
    }


if __name__ == "__main__":
    import identity as identity_mod

    identity_mod.standalone_main(fetch, SOURCE_NAME)
