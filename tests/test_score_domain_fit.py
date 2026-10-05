"""An industry bonus that reads what the vacancy requires (score._score_domain_fit),
and an exclusivity clause that is a line on the card rather than a refusal.

The owner, 2026-10-05: a crypto project that wants a .NET developer, Solidity
a plus, is the job (+20); one that wants Solidity and Rust, .NET a plus, will
not hire this CV.
"""
import copy
from pathlib import Path

import yaml

import score

CRITERIA = score.load_criteria()
PROFILE = score.load_profile()
SHARP = Path(__file__).resolve().parents[1] / "identity-templates" / \
    "sharp-senior-dotnet-remote-engineering" / "sharp_criteria.yaml"


def _criteria_with_crypto():
    criteria = copy.deepcopy(CRITERIA)
    shipped = yaml.safe_load(SHARP.read_text(encoding="utf-8"))
    criteria["domain_fit_signals"] = shipped["domain_fit_signals"]
    criteria["industry_dealbreaker_gate"] = {"threshold_hits": 2, "keywords": []}
    return criteria


def _vacancy(title, text):
    return {"id": "x", "title": title, "company": "Chain Co", "location_raw": "",
            "remote": True, "tags": [], "description_text": text, "salary_raw": None}


def _crypto(result):
    return result["score_breakdown"]["domain_fit_signals"].get("crypto") or {}


def test_a_crypto_project_hiring_dotnet_gets_the_bonus():
    v = _vacancy("Senior C# Developer", (
        "We build a blockchain settlement platform for crypto exchanges on Ethereum. "
        "Requirements: 5+ years of C# and .NET Core. "
        "Nice to have: Solidity, experience with smart contracts."))
    r = score.score_vacancy(v, _criteria_with_crypto(), PROFILE)
    assert _crypto(r)["verdict"] == "core_required"
    assert _crypto(r)["points"] == 20
    without = score.score_vacancy(v, CRITERIA, PROFILE)
    assert r["score_breakdown"]["raw_total_before_clamp"] - \
        without["score_breakdown"]["raw_total_before_clamp"] == 20


def test_a_crypto_project_wanting_solidity_and_rust_is_rejected():
    v = _vacancy("Senior Blockchain Engineer", (
        "We build DeFi protocols on Ethereum and Solana. "
        "3+ years writing smart contracts in Solidity. "
        "Excellent knowledge of Rust. "
        "5 years of experience in crypto. "
        "C# and .NET are a plus."))
    r = score.score_vacancy(v, _criteria_with_crypto(), PROFILE)
    assert _crypto(r)["verdict"] == "foreign_required"
    assert r["classification"] == "rejected"
    assert any(d.startswith("domain:") for d in r["dealbreakers"])


def test_wishes_under_a_heading_are_wishes():
    v = _vacancy("Senior .NET Developer", (
        "A crypto payments company: blockchain wallets for crypto merchants.\n"
        "Requirements:\n- 5 years of C#\n- ASP.NET Core\n"
        "Nice to have:\n- Solidity\n- Rust\n"))
    r = score.score_vacancy(v, _criteria_with_crypto(), PROFILE)
    assert _crypto(r)["verdict"] == "core_required"


def test_requiring_both_is_neither_bonus_nor_rejection():
    v = _vacancy("Senior Developer", (
        "Our blockchain exchange runs on Ethereum. "
        "You need strong C# and Solidity."))
    r = score.score_vacancy(v, _criteria_with_crypto(), PROFILE)
    assert _crypto(r)["verdict"] == "mixed"
    assert _crypto(r)["points"] == 0
    assert not any(d.startswith("domain:") for d in r["dealbreakers"])


def test_one_passing_mention_is_not_the_industry():
    v = _vacancy("Senior C# Developer", "Our clients include a blockchain startup. C# required.")
    r = score.score_vacancy(v, _criteria_with_crypto(), PROFILE)
    assert _crypto(r) == {}


def test_a_stack_spam_paragraph_is_not_the_industry():
    v = _vacancy("Senior .NET Full-stack Developer", (
        "Build an ASP.NET Core portal with C#. "
        "NOT YOUR TECH STACK? Blockchain (Ethereum/Ethers.js/Wagmi/Viem/Solana), "
        "Rust, Solidity, Web3."))
    r = score.score_vacancy(v, _criteria_with_crypto(), PROFILE)
    assert _crypto(r) == {}


def test_an_exclusivity_clause_is_noted_not_refused():
    profile = copy.deepcopy(PROFILE)
    etp = profile["employment_type_priority"]
    etp["dealbreaker_signals"] = [s for s in etp["dealbreaker_signals"]
                                  if s not in ("exclusive employment", "no other employment")]
    etp["exclusivity_signals"] = ["exclusive employment", "no other employment"]
    v = _vacancy("Senior C# Developer", (
        "Remote worldwide, contractor friendly via Deel. C# and ASP.NET Core. "
        "Employee agrees to exclusive employment and no other employment is permitted."))
    r = score.score_vacancy(v, CRITERIA, profile)
    assert not any(d.startswith("employment:") for d in r["dealbreakers"])
    assert r["score_breakdown"]["employment_exclusivity"]["hits"] == [
        "exclusive employment", "no other employment"]


def test_a_board_catalogue_of_tags_is_not_read():
    catalogue = [f"stack{i}" for i in range(30)] + ["react native", "flutter", "mobile app"]
    v = _vacancy("Senior .NET Full-stack Developer", "ASP.NET Core and C# web portal.")
    v["tags"] = catalogue
    r = score.score_vacancy(v, CRITERIA, PROFILE)
    assert not any("mobile" in d for d in r["dealbreakers"])
