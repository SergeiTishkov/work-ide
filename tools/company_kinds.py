"""
Company kinds: which companies are intermediaries — a freelance marketplace,
a recruitment agency, a reposter of other companies' vacancies — and which are
employers ("other"). The catalogue and its matching rules are in
config/company_kinds.yaml.

The app's "Company" drop-down groups by kind. The app reads the database only,
so selections.write_company_kinds() stores the outcome there with every
selection: {company name as the board gave it: {"kind", "name"}}, for the
intermediaries only — a name missing from it is "other".

python tools/company_kinds.py "Proxify AB" "Hays Technology"   -> the kind of each
python tools/company_kinds.py --scan          -> every intermediary in the base, by kind
python tools/company_kinds.py --write         -> store the kinds for the app now, without a run
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from functools import lru_cache
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

KINDS = ("marketplace", "agency", "reposter")
OTHER = "other"

# Dropped from the end of a name, repeatedly: "RECRUIT EXPRESS PTE LTD" and
# "JOBSTER PRIVATE LTD." are "recruit express" and "jobster".
_LEGAL_SUFFIXES = {
    "ab", "ag", "bv", "b v", "co", "company", "corp", "corporation", "gmbh", "inc",
    "kk", "k k", "limited", "llc", "llp", "ltd", "plc", "private", "pte", "pty",
    "sa", "sarl", "srl", "oy", "as", "aps", "nv", "kg",
}


def normalise(name: str) -> str:
    """'Proxify AB' -> 'proxify'; 'Lemon.io' -> 'lemon io';
    'Fraser &amp; Co. Talent Partners Limited' -> 'fraser and co talent partners'."""
    text = (name or "").replace("&amp;", "&").replace("&", " and ").lower()
    text = re.sub(r"[^\w]+", " ", text, flags=re.UNICODE).replace("_", " ")
    words = text.split()
    changed = True
    while changed and len(words) > 1:
        changed = False
        for size in (2, 1):
            if len(words) > size and " ".join(words[-size:]) in _LEGAL_SUFFIXES:
                del words[-size:]
                changed = True
                break
    return " ".join(words)


@lru_cache(maxsize=1)
def _catalogue() -> Tuple[List[Tuple[str, str, str, bool]], List[Tuple[str, str]]]:
    """([(normalised phrase, kind, name, exact)], [(normalised keyword, kind)]),
    longest phrase first, so "haystack people" wins over "haystack"."""
    config = common.load_yaml(common.shared_config("company_kinds.yaml"))
    entries, keywords = [], []
    for kind, listed in (config.get("kinds") or {}).items():
        if kind not in KINDS:
            raise ValueError(f"config/company_kinds.yaml: unknown kind {kind!r}")
        for entry in listed or []:
            for phrase in entry.get("match") or []:
                entries.append((normalise(str(phrase)), kind, entry["name"], False))
            for phrase in entry.get("exact") or []:
                entries.append((normalise(str(phrase)), kind, entry["name"], True))
    for kind, phrases in (config.get("keywords") or {}).items():
        if kind not in KINDS:
            raise ValueError(f"config/company_kinds.yaml: unknown kind {kind!r}")
        keywords += [(normalise(str(p)), kind) for p in phrases or []]
    entries.sort(key=lambda e: -len(e[0]))
    return entries, keywords


def classify(company: Optional[str]) -> Optional[Dict[str, str]]:
    """{"kind", "name"} for an intermediary, None for any other company."""
    norm = normalise(company or "")
    if not norm:
        return None
    entries, keywords = _catalogue()
    for phrase, kind, name, exact in entries:
        if norm == phrase or (not exact and norm.startswith(phrase + " ")):
            return {"kind": kind, "name": name}
    for phrase, kind in keywords:
        # anywhere, inside a word too: "Recruitment", "Set2Recruit", "RecruitmentRevolution.com"
        if phrase in norm:
            return {"kind": kind, "name": _own_name(company)}
    return None


def _own_name(company: str) -> str:
    """A keyword match is listed under the company's own name, its legal
    suffix aside: "Deerfoot Recruitment Solutions Limited" and "... Ltd" are
    one row. The words keep the board's spelling."""
    words = re.sub(r"&amp;", "&", company).split()
    while len(words) > 1 and normalise(" ".join(words)) == normalise(" ".join(words[:-1])):
        words.pop()
    return " ".join(words).rstrip(" .,")


def mapping(companies: Iterable[str]) -> Dict[str, Dict[str, str]]:
    """{company: {"kind", "name"}} for the intermediaries among `companies`."""
    result = {}
    for company in companies:
        if company and company not in result:
            found = classify(company)
            if found:
                result[company] = found
    # a company listed under its own name, spelled two ways ("Spectrum IT
    # Recruitment", "Spectrum It Recruitment Limited"), is one row: the
    # spelling not in capitals, then the first in order
    own = {}
    for company, found in result.items():
        if found["name"] == _own_name(company):
            own.setdefault((found["kind"], normalise(company)), []).append(company)
    for companies_ in own.values():
        name = min((result[c]["name"] for c in companies_), key=lambda n: (n.isupper(), n))
        for company in companies_:
            result[company] = {**result[company], "name": name}
    return result


def _scan() -> int:
    import db

    with db.session() as conn:
        rows = conn.execute(
            "SELECT json_extract(view, '$.company') AS company, COUNT(*) FROM vacancy_identity "
            "WHERE view IS NOT NULL GROUP BY company").fetchall()
    by_name: Dict[Tuple[str, str], List] = {}
    for company, total in rows:
        found = classify(company)
        if found:
            key = (found["kind"], found["name"])
            by_name.setdefault(key, [0, []])
            by_name[key][0] += total
            by_name[key][1].append(company)
    for kind in KINDS:
        listed = sorted(((n, names) for (k, _), (n, names) in by_name.items() if k == kind),
                        key=lambda x: -x[0])
        print(f"{kind}: {len(listed)} companies, {sum(n for n, _ in listed)} vacancies")
        for (k, name), (n, names) in sorted(by_name.items(), key=lambda x: -x[1][0]):
            if k == kind:
                print(f"  {name}: {n}  <- {', '.join(sorted(names))}")
    return 0


def _write() -> int:
    """What every selection does (selections.write_company_kinds), alone:
    after an edit of config/company_kinds.yaml, the app shows it at once."""
    import db
    import selections

    with db.session() as conn:
        selections.write_company_kinds(conn)
        (value,) = conn.execute("SELECT value FROM meta WHERE key = 'company_kinds'").fetchone()
    print(f"company_kinds: {len(json.loads(value))} company names stored as intermediaries")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Which companies are freelance marketplaces, agencies or reposters "
                    "(config/company_kinds.yaml)")
    parser.add_argument("names", nargs="*", help="company names to classify")
    parser.add_argument("--scan", action="store_true",
                        help="every intermediary among the companies the app lists, by kind")
    parser.add_argument("--write", action="store_true",
                        help="store the kinds in the base for the app now, without waiting for a run")
    args = parser.parse_args(argv)
    if args.scan:
        return _scan()
    if args.write:
        return _write()
    if not args.names:
        parser.print_help()
        return 0
    for name in args.names:
        found = classify(name) or {"kind": OTHER, "name": name}
        print(json.dumps({"company": name, **found}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
