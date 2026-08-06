"""
Репутация работодателя: связь между выдачей и её проверкой.

ЧТО БЫЛО СЛОМАНО
----------------
Замер 2026-08-06: в hot_lead и worth_a_look было 55 компаний, и НИ У ОДНОЙ
не было репутации. У двух из 55 хотя бы проверялся возраст.

Причина не в том, что кто-то забыл. Причина структурная: обогащение вызывалось
только из `pipeline.py`, то есть привязывалось к СБОРУ вакансий. А выдача
меняется не только при сборе — она меняется при каждой правке фильтров и весов,
после которой всё пересчитывается. За эту сессию выдача пересобиралась
десяток раз, и каждый раз в неё приходили компании, которых обогащение никогда
не видело.

То есть связь была не «выдача → проверка», а «сбор → проверка». Между ними
разница, и она молчаливая: отчёт писал «репутация не проверялась», человек
читал это как «данных нет», а на самом деле это значило «мы даже не пытались».

ТРИ СОСТОЯНИЯ ВМЕСТО ДВУХ
-------------------------
Именно эта неразличимость и была главной бедой, поэтому теперь состояний три:

  found                 данные есть: рейтинг, work-life balance, отзывы;
  insufficient_sources  ПРОВЕРЯЛИ, но ничего достоверного не нашли — компания
                        маленькая и малоизвестная, отзывов о ней нет;
  (записи нет)          не проверяли. Для hot_lead и worth_a_look это дефект
                        процесса, и отчёт обязан кричать о нём, а не молчать.

Второе состояние добавлено по прямой просьбе владельца 2026-08-06: «если
автоматика сработала, а компания маленькая и неизвестная, то так и пиши —
репутация проверялась, но не определена из-за отсутствия достаточного
количества источников».

ПОЧЕМУ СБОР НЕ ПОЛНОСТЬЮ АВТОМАТИЧЕН
------------------------------------
Площадки с отзывами закрыты для скриптов: Glassdoor, Indeed, Trustpilot и
levels.fyi отвечают 403 за Cloudflare, официальный Glassdoor API — 410 Gone
(замер 2026-07-31). Пройти туда можно только маскировкой под браузер, а это
запрещено Большой Конституцией (§5, граница дозволенного).

Поэтому автоматически собирается то, что отдаётся честно (возраст и размер
компании из Wikidata), а рейтинги ищет агент обычным веб-поиском — так же,
как их искал бы человек. Автоматика здесь в другом: система САМА составляет
список того, что надо проверить, сама фиксирует результат каждой попытки и
сама жалуется, если список не обработан. Ничего из этого не держится на
памяти агента — в этом проекте такие правила уже ломались.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

# Классы выдачи, для которых репутация ОБЯЗАТЕЛЬНА. long_shot сюда не входит
# намеренно: это хвост, человек до него обычно не доходит, а проверка каждой
# компании хвоста стоила бы сотен запросов ради вакансий, которые он не
# откроет.
REQUIRED_CLASSES = ("hot_lead", "worth_a_look")

VERDICT_FOUND = "found"
VERDICT_INSUFFICIENT = "insufficient_sources"

# Сколько дней результат считается свежим. Репутация компании меняется
# медленно, но не бесконечно медленно.
FRESH_DAYS = 90


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_fresh(record: dict, days: int = FRESH_DAYS) -> bool:
    stamp = (record or {}).get("checked_at")
    if not stamp:
        return False
    try:
        checked = datetime.fromisoformat(stamp)
    except ValueError:
        return False
    if checked.tzinfo is None:
        checked = checked.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - checked).days < days


def shortlist_companies(vacancies: dict, classes=REQUIRED_CLASSES) -> dict:
    """{название компании: лучший класс её вакансий} по текущей выдаче."""
    order = {"hot_lead": 3, "worth_a_look": 2, "long_shot": 1}
    found = {}
    for rec in vacancies.values():
        if rec.get("duplicate_of"):
            continue
        name = rec.get("company")
        cls = (rec.get("computed") or {}).get("classification")
        if not name or cls not in classes:
            continue
        if order.get(cls, 0) > order.get(found.get(name, ""), 0):
            found[name] = cls
    return found


def worklist(vacancies: dict, companies: dict, classes=REQUIRED_CLASSES,
             limit: Optional[int] = None) -> List[dict]:
    """Компании выдачи, у которых нет свежей ПОПЫТКИ проверить репутацию.

    Именно попытки, а не данных: компания, о которой ничего не нашлось, из
    списка уходит — иначе каждый прогон заново искал бы отзывы о конторе из
    пяти человек, которых не существует.
    """
    by_name = {entry.get("name"): entry for entry in companies.values()}
    todo = []
    for name, cls in sorted(shortlist_companies(vacancies, classes).items(),
                            key=lambda kv: (kv[1] != "hot_lead", kv[0])):
        entry = by_name.get(name) or {}
        if _is_fresh(entry.get("reputation")):
            continue
        todo.append({
            "company": name,
            "classification": cls,
            "url": _sample_url(vacancies, name),
        })
        if limit and len(todo) >= limit:
            break
    return todo


def _sample_url(vacancies: dict, name: str) -> Optional[str]:
    for rec in vacancies.values():
        if rec.get("company") == name and rec.get("url"):
            return rec["url"]
    return None


def coverage(vacancies: dict, companies: dict, classes=REQUIRED_CLASSES) -> dict:
    """Сколько компаний выдачи проверено и с каким исходом."""
    by_name = {entry.get("name"): entry for entry in companies.values()}
    stats = {"companies": 0, "found": 0, "insufficient": 0, "unchecked": 0}
    for name in shortlist_companies(vacancies, classes):
        stats["companies"] += 1
        rep = (by_name.get(name) or {}).get("reputation")
        if not _is_fresh(rep):
            stats["unchecked"] += 1
        elif rep.get("verdict") == VERDICT_INSUFFICIENT:
            stats["insufficient"] += 1
        else:
            stats["found"] += 1
    return stats


def mark_insufficient(companies: dict, name: str, searched: str = "") -> bool:
    """Фиксирует «искали — не нашли». Возвращает False, если компании нет.

    Это ПОЛНОЦЕННЫЙ результат проверки, а не её отсутствие. Без него отчёт не
    может отличить «маленькая незаметная компания» от «до неё не дошли руки»,
    а для человека это очень разные вещи: первое — свойство компании, второе
    — дефект процесса.
    """
    slug = common.normalize_company_name(name)
    entry = companies.get(slug)
    if entry is None:
        return False
    entry["reputation"] = {
        "verdict": VERDICT_INSUFFICIENT,
        "checked_at": _now(),
        "searched": searched or "Glassdoor, Indeed, Trustpilot, общий веб-поиск",
        "overall_rating": None,
        "work_life_balance": None,
        "red_flags": [],
    }
    return True


def main() -> None:
    import argparse
    import identity as identity_mod
    import kb

    parser = argparse.ArgumentParser(
        description="Репутация компаний выдачи: что проверено, что осталось")
    identity_mod.add_identity_arg(parser)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("worklist", help="Кого осталось проверить")
    p_list.add_argument("--limit", type=int, default=None)
    p_list.add_argument("--include-long-shot", action="store_true",
                        help="Добавить хвост выдачи (обычно не нужно)")

    sub.add_parser("coverage", help="Покрытие выдачи проверками")

    p_none = sub.add_parser(
        "mark-insufficient",
        help="Записать: искали, достоверных отзывов не нашли")
    p_none.add_argument("--company", required=True)
    p_none.add_argument("--searched", default="",
                        help="Где искали — попадёт в отчёт")

    args = parser.parse_args()
    identity_mod.activate_or_exit(args.identity)

    vacancies = kb.load_vacancies()
    companies = kb.load_companies()
    classes = REQUIRED_CLASSES + (("long_shot",) if getattr(args, "include_long_shot", False) else ())

    if args.cmd == "worklist":
        todo = worklist(vacancies, companies, classes, args.limit)
        if not todo:
            print("Все компании выдачи проверены — работы нет.")
            return
        print("Компаний без свежей проверки: %d\n" % len(todo))
        for item in todo:
            print("  %-11s %s" % (item["classification"], item["company"]))
        print("\n  Нашли данные:   python tools/kb.py set-company-reputation "
              "--company \"<имя>\" --rating N --wlb N --source Glassdoor")
        print("  Ничего нет:     python tools/reputation.py mark-insufficient "
              "--company \"<имя>\"")
        return

    if args.cmd == "coverage":
        stats = coverage(vacancies, companies, classes)
        print("Компаний в выдаче (%s): %d" % ("+".join(classes), stats["companies"]))
        print("  репутация найдена:            %d" % stats["found"])
        print("  проверено, источников мало:   %d" % stats["insufficient"])
        print("  НЕ ПРОВЕРЕНО:                 %d" % stats["unchecked"])
        return

    if args.cmd == "mark-insufficient":
        if not mark_insufficient(companies, args.company, args.searched):
            print("Компания '%s' не найдена в базе." % args.company)
            sys.exit(1)
        kb.save_companies(companies)

        # Пересчёт обязателен, а не желателен. Отчёт читает СОХРАНЁННЫЙ
        # computed, а не пересчитывает на лету: без этого шага запись
        # сохранится, но в отчёте у вакансии так и останется «ещё не
        # проверялась» — то есть работа сделана, а человек видит обратное.
        # Ровно так и вышло при первом прогоне 2026-08-06.
        import score

        vacancies = kb.load_vacancies()
        kb.attach_company_reputation(vacancies, companies)
        criteria, profile = score.load_criteria(), score.load_profile()
        touched = 0
        for rec in vacancies.values():
            if rec.get("company") != args.company:
                continue
            view = {k: v for k, v in rec.items() if k not in ("computed", "manual")}
            rec["computed"] = score.score_vacancy(view, criteria, profile)
            touched += 1
        kb.save_vacancies(vacancies)
        print("Записано: '%s' — проверяли, достоверных отзывов не нашли. "
              "Пересчитано вакансий: %d" % (args.company, touched))


if __name__ == "__main__":
    main()
