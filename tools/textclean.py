"""
Вычистка контактов из текста вакансии: почтовых адресов и ссылок.

ЗАЧЕМ ЭТО СУЩЕСТВУЕТ
--------------------
Название ".NET" невозможно искать подстрокой: ".net" есть в любом почтовом
домене. В базе лежит реальная запись с Hacker News, приехавшая заголовком
вакансии: "Please email me ... (firstname)@harnly.net".

Первая попытка обойти это была регуляркой "точка-net, перед которой не стоит
буква". Она работала, но выражала не то, что нужно: заодно она отсекала
"asp.net" и "vb.net", то есть настоящие названия технологий. Спасало лишь то,
что "ASP.NET" лежал в списке ключей отдельной строкой — стоило бы этой строке
исчезнуть, и целый пласт вакансий пропал бы молча.

Правило должно говорить ровно то, что имеется в виду: "убери контакты, а
дальше ищи технологию как обычно". Тогда ".NET", "ASP.NET" и "VB.NET"
находятся простым и понятным паттерном, а почта не находится вообще.

ПОЧЕМУ НЕ БИБЛИОТЕКА-ВАЛИДАТОР
------------------------------
Первым делом здесь стоял `email.utils.parseaddr` из стандартной библиотеки, а
следующим шагом напрашивался `email-validator` (тот, что внутри Pydantic).
Приёмка на живых данных 2026-08-05 показала, что оба решают ДРУГУЮ задачу.

`parseaddr` не распознал `(firstname)@harnly.net` — ту самую запись, из-за
которой всё и затевалось: скобки трактуются как RFC-комментарий, локальная
часть выходит пустой. `email-validator` отверг бы её тем более: он проверяет,
что адрес настоящий и доставляемый, а `(firstname)` — шаблон, куда человек
подставит имя.

И в этом суть: нам нужна не проверка адреса, а РАСПОЗНАВАНИЕ ФОРМЫ. Вопрос
не «можно ли сюда написать письмо», а «похоже ли это слово на почту
настолько, что искать в нём название технологии бессмысленно». Валидатор
отвечает на первый вопрос и потому раз за разом ошибается на втором:
всё нестандартное — шаблоны, огрызки, адреса с опечатками — он объявляет
не-почтой, и `.net` из них снова попадает в поиск.

Поэтому проверка простая и явная, а её граница описана ниже и покрыта
тестами на реальных строках из базы.

ГРАНИЦА ОСТОРОЖНОСТИ
--------------------
Убираются только однозначные случаи: слово с "@" в форме адреса и слово со
схемой (http://, https://) или с "www.". Голый домен вида "harnly.net" без
"@" и без схемы НЕ трогается — он неотличим от "asp.net", а цена ошибки
несимметрична: лишнее совпадение по стеку стоит одной строки в отчёте,
пропущенная вакансия стоит вакансии.
"""
from __future__ import annotations

import re
from typing import List, Tuple
from urllib.parse import urlparse

# Разбиение по пробельным символам: решение принимается о каждом слове
# отдельно, и границы слова достаточно, чтобы не задеть соседний текст.
_SPLIT_RE = re.compile(r"(\s+)")

# Символы, которыми слово может быть обрамлено: точка в конце предложения
# входит обязательно — "recruiting@certifyos.com." встречается в базе.
_TRIM_CHARS = "()[]{}<>\"'«»,;:!?.…"

_URL_SCHEMES = {"http", "https", "ftp", "mailto"}


def _trim(token: str) -> str:
    return token.strip(_TRIM_CHARS)


def looks_like_email(token: str) -> bool:
    """Похоже ли слово на почтовый адрес настолько, что искать в нём
    название технологии бессмысленно.

    Это НЕ валидация адреса. Распознаются в том числе шаблоны
    ("(firstname)@harnly.net"), огрызки ("@databento.com") и адреса с
    опечатками — именно они и мешают, а любой валидатор объявит их
    не-почтой и вернёт задачу в исходное состояние.
    """
    token = _trim(token)
    if token.count("@") != 1 or len(token) < 4:
        return False
    local, _, domain = token.partition("@")
    domain = domain.strip(_TRIM_CHARS)
    if "." not in domain:
        return False
    # Домен верхнего уровня — буквы, минимум две: отсекает "a@b.1" и мусор
    # вроде CSS-классов "@md:s-py-2", которых в HTML-описаниях хватает.
    tld = domain.rsplit(".", 1)[-1]
    if not tld.isalpha() or len(tld) < 2:
        return False
    # Каждая часть домена непуста: "a@.net" и "a@b..net" — не адреса.
    if any(not part for part in domain.split(".")):
        return False
    # Пустая локальная часть — это ссылка на домен или ник ("@airtable.com").
    # Технологией она тоже быть не может, поэтому убирается наравне с почтой.
    return True


def looks_like_url(token: str) -> bool:
    """Является ли слово ссылкой. Решает стандартная библиотека."""
    token = _trim(token)
    if len(token) < 5:
        return False
    parsed = urlparse(token)
    if parsed.scheme.lower() in _URL_SCHEMES and (parsed.netloc or parsed.path):
        return True
    # Схему в текстах вакансий часто опускают, но "www." пишут.
    return token.lower().startswith("www.") and "." in token[4:]


def find_contacts(text: str) -> List[Tuple[str, str]]:
    """Все слова текста, признанные контактами. Возвращает (слово, вид)."""
    found = []
    for token in _SPLIT_RE.split(text or ""):
        if not token.strip():
            continue
        if looks_like_email(token):
            found.append((token, "email"))
        elif looks_like_url(token):
            found.append((token, "url"))
    return found


def strip_contact_noise(text: str, placeholder: str = " ") -> str:
    """Текст без почтовых адресов и ссылок.

    Слово заменяется на пробел, а не удаляется: иначе соседние слова
    склеятся и породят совпадения, которых в тексте не было.
    """
    if not text:
        return text or ""
    parts = _SPLIT_RE.split(text)
    for i, token in enumerate(parts):
        if not token.strip():
            continue
        if looks_like_email(token) or looks_like_url(token):
            parts[i] = placeholder
    return "".join(parts)


def main() -> None:
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="Убрать из текста почтовые адреса и ссылки"
    )
    parser.add_argument("text", nargs="*", help="Текст; без аргументов читается stdin")
    parser.add_argument("--show", action="store_true",
                        help="Показать найденные контакты, а не очищенный текст")
    args = parser.parse_args()

    text = " ".join(args.text) if args.text else sys.stdin.read()
    if args.show:
        contacts = find_contacts(text)
        if not contacts:
            print("контактов не найдено")
            return
        for token, kind in contacts:
            print("%-8s %s" % (kind, token))
        return
    print(strip_contact_noise(text))


if __name__ == "__main__":
    main()
