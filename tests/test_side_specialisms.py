"""
A specialism beside the core stack is not the role.

The owner, 2026-09-14, about the part-time search refusing smart-contract work
outright: "if smart contracts are not the main thing — if the base is .NET and
the vacancy reads as .NET with smart contracts rather than smart contracts with
.NET — they must not exclude it."

A title rule cannot say that: "Senior .NET Developer (Smart Contracts)" names
the specialism as plainly as "Smart Contract Engineer" does. So the title
decides only when it names one side, and when it names both or neither the
posting decides by how much of it each side takes up — with a tie going to the
vacancy, because a missed candidate costs more than a doubtful one.
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import score  # noqa: E402

from test_score import CRITERIA, PROFILE, make_vacancy  # noqa: E402

SMART_CONTRACTS = {
    "name": "smart contracts",
    "title_patterns": [r"smart[- ]contracts?", r"\bsolidity\b", r"\bevm\b"],
    "text_patterns": [r"smart[- ]contracts?", r"\bsolidity\b", r"\bevm\b", r"\bhardhat\b"],
    "core_patterns": [r"\.net\b", r"\bdotnet\b", r"\bc#", r"\basp\.net\b"],
}


def _criteria(with_spec=True):
    criteria = copy.deepcopy(CRITERIA)
    if with_spec:
        criteria["role_complexity_signal"]["side_specialisms"] = [copy.deepcopy(SMART_CONTRACTS)]
    return criteria


def _gate(title, description, with_spec=True):
    r = score.score_vacancy(make_vacancy(title=title, description_text=description),
                            _criteria(with_spec), PROFILE)
    rc = r["score_breakdown"]["role_complexity_signal"]
    side = (rc.get("side_specialisms") or [{}])[0]
    return side.get("gated"), side.get("reason"), rc["gate_triggered"]


def test_a_smart_contract_title_is_the_role():
    gated, reason, _ = _gate("Smart Contract Engineer",
                             "Write Solidity for our DeFi protocol. TypeScript tooling, Hardhat, EVM.")
    assert gated and reason == "the title makes it the role"


def test_a_net_title_with_smart_contracts_beside_it_is_kept():
    """The owner's case exactly. The posting mentions smart-contract words more
    often than .NET — the title says which is the job."""
    gated, reason, whole_gate = _gate(
        "Senior .NET Developer (Smart Contracts)",
        "Build the C# back office that reads our smart contracts. Solidity, EVM, Hardhat a plus.")
    assert gated is False and reason == "the title puts the core stack first"
    assert whole_gate is False


def test_a_net_only_title_is_kept_however_much_the_posting_says_about_contracts():
    gated, reason, _ = _gate(
        "Senior C# Engineer",
        "Smart contracts, Solidity, EVM, Hardhat, more smart contracts.")
    assert gated is False and reason == "the title names the core stack"


def test_a_neutral_title_over_a_net_posting_is_kept():
    gated, reason, _ = _gate(
        "Backend Engineer",
        "ASP.NET Core services in C#, .NET 8, SQL Server. Some integration with smart contracts.")
    assert gated is False
    assert reason == "the core stack takes up at least as much of the posting"


def test_a_neutral_title_over_a_smart_contract_posting_is_the_role():
    gated, reason, _ = _gate(
        "Blockchain Developer",
        "Design smart contracts in Solidity, audit smart contracts, deploy to EVM chains with Hardhat. "
        "Scripts in TypeScript; one legacy C# indexer.")
    assert gated and reason == "the posting is mostly about it"


def test_both_in_the_title_the_one_named_first_is_the_role():
    """".NET with smart contracts" against "smart contracts with .NET" — the
    owner's words are about order, and so is a title's."""
    contracts_first = _gate("Solidity / C# Developer", "C# and .NET services, a little Solidity.")
    net_first = _gate("C# / Solidity Developer", "Solidity smart contracts, EVM, Hardhat; some C#.")
    assert contracts_first[:2] == (True, "the title puts it before the core stack")
    assert net_first[:2] == (False, "the title puts the core stack first")


def test_a_tie_keeps_the_vacancy():
    gated, _, _ = _gate("Developer", "C# on one side, Solidity on the other.")
    assert gated is False


def test_a_posting_that_never_mentions_it_is_untouched():
    gated, reason, whole_gate = _gate("Senior .NET Developer", "C# and SQL Server.")
    assert gated is False and reason == "not mentioned" and whole_gate is False


def test_without_the_block_nothing_changes():
    _, _, whole_gate = _gate("Smart Contract Engineer", "Solidity.", with_spec=False)
    plain = score.score_vacancy(make_vacancy(title="Smart Contract Engineer", description_text="Solidity."),
                                CRITERIA, PROFILE)
    assert "side_specialisms" not in plain["score_breakdown"]["role_complexity_signal"]
    assert whole_gate == plain["score_breakdown"]["role_complexity_signal"]["gate_triggered"]


def test_the_hard_title_list_still_rules_out_on_its_own():
    """A specialism kept beside .NET does not cancel a different refusal."""
    criteria = _criteria()
    criteria["role_complexity_signal"]["title_red_flag_patterns"] = ["protocol engineer"]
    r = score.score_vacancy(make_vacancy(title="Protocol Engineer (.NET, Smart Contracts)",
                                         description_text="C# and Solidity."), criteria, PROFILE)
    assert r["score_breakdown"]["role_complexity_signal"]["gate_triggered"]
