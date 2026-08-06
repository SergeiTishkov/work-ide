"""
Stripping contacts — email addresses and links — out of vacancy text.

WHY THIS EXISTS
---------------
The name ".NET" cannot be searched for as a substring: ".net" is in every mail
domain. The database holds a real record from Hacker News that arrived as a
vacancy title: "Please email me ... (firstname)@harnly.net".

The first attempt to work round that was the regex "dot-net not preceded by a
letter". It worked, but it expressed the wrong thing: it also cut out
"asp.net" and "vb.net", which are real technology names. The only thing that
saved us was that "ASP.NET" sat in the keyword list as its own entry — had
that entry ever disappeared, a whole seam of vacancies would have gone
silently missing.

The rule has to say exactly what is meant: "remove contacts, then look for the
technology as usual". Then ".NET", "ASP.NET" and "VB.NET" are found by a
simple, comprehensible pattern, and an email address is not found at all.

WHY NOT A VALIDATOR LIBRARY
------------------------------
This started with `email.utils.parseaddr` from the standard library, and
`email-validator` (the one inside Pydantic) was the obvious next step.
Acceptance testing on live data, 2026-08-05, showed both solve a DIFFERENT

`parseaddr` did not recognise `(firstname)@harnly.net` — the very record this
was all started for: the parentheses are read as an RFC comment, leaving the
local part empty. `email-validator` would reject it all the more firmly: it
checks that an address is real and deliverable, and `(firstname)` is a template
for a person to substitute a name into.

And that is the crux: what is wanted is not address validation but SHAPE
RECOGNITION. The question is not "can mail be sent here" but "does this word
look enough like an address that searching it for a technology name is
pointless". A validator answers the first question and therefore keeps getting
the second one wrong: everything non-standard — templates, fragments,
addresses with typos — it declares not-email, and their `.net` goes back into

So the check is simple and explicit, its boundary is described below, and it is
covered by tests over real strings from the database.

THE BOUNDARY OF CAUTION
--------------------
Only unambiguous cases are removed: a word with "@" in the shape of an address,
and a word with a scheme (http://, https://) or with "www.". A bare domain like
"harnly.net" with no "@" and no scheme is NOT touched — it is indistinguishable
from "asp.net", and the cost of the two mistakes is not symmetric: a spurious
stack match costs one line in the report, a missed vacancy costs a vacancy.
"""
from __future__ import annotations

import re
from typing import List, Tuple
from urllib.parse import urlparse

# Splitting on whitespace: the decision is made about each word separately, and
# a word boundary is enough not to disturb neighbouring text.
_SPLIT_RE = re.compile(r"(\s+)")

# Characters a word may be wrapped in. A full stop at the end of a sentence is
# essential — "recruiting@certifyos.com." occurs in the database.
_TRIM_CHARS = "()[]{}<>\"'«»,;:!?.…"

_URL_SCHEMES = {"http", "https", "ftp", "mailto"}


def _trim(token: str) -> str:
    return token.strip(_TRIM_CHARS)


def looks_like_email(token: str) -> bool:
    """Does the word look enough like an email address that searching it for a
    technology name is pointless.

    This is NOT address validation. What is recognised includes templates
    ("(firstname)@harnly.net"), fragments ("@databento.com") and addresses with
    typos — precisely the ones that get in the way, and precisely the ones any
    validator declares not-email, returning the problem to where it started.
    """
    token = _trim(token)
    if token.count("@") != 1 or len(token) < 4:
        return False
    local, _, domain = token.partition("@")
    domain = domain.strip(_TRIM_CHARS)
    if "." not in domain:
        return False
    # The top-level domain: letters, at least two. That rejects "a@b.1" and
    # rubbish like the CSS class "@md:s-py-2", of which HTML descriptions have
    tld = domain.rsplit(".", 1)[-1]
    if not tld.isalpha() or len(tld) < 2:
        return False
    # Every domain part is non-empty: "a@.net" and "a@b..net" are not addresses.
    if any(not part for part in domain.split(".")):
        return False
    # An empty local part means a domain reference or a handle ("@airtable.com").
    # That cannot be a technology either, so it goes along with the addresses.
    return True


def looks_like_url(token: str) -> bool:
    """Is the word a link. The standard library decides."""
    token = _trim(token)
    if len(token) < 5:
        return False
    parsed = urlparse(token)
    if parsed.scheme.lower() in _URL_SCHEMES and (parsed.netloc or parsed.path):
        return True
    # Vacancy text often drops the scheme, but does write "www.".
    return token.lower().startswith("www.") and "." in token[4:]


def find_contacts(text: str) -> List[Tuple[str, str]]:
    """Every word of the text recognised as a contact. Returns (word, kind)."""
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
    """The text with email addresses and links removed.

    A word is replaced by a space rather than deleted: otherwise neighbouring
    words would join up and produce matches that were never in the text.
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
        description="Strip email addresses and links out of text"
    )
    parser.add_argument("text", nargs="*", help="Text; with no arguments, stdin is read")
    parser.add_argument("--show", action="store_true",
                        help="Show the contacts found rather than the cleaned text")
    args = parser.parse_args()

    text = " ".join(args.text) if args.text else sys.stdin.read()
    if args.show:
        contacts = find_contacts(text)
        if not contacts:
            print("no contacts found")
            return
        for token, kind in contacts:
            print("%-8s %s" % (kind, token))
        return
    print(strip_contact_noise(text))


if __name__ == "__main__":
    main()
