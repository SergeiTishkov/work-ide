"""
Live source contracts, one test per source that defines one.

Skipped unless pytest runs with --live. A failure here means the source still
answers but no longer the way its fetcher expects — the cue for
/source-doctor <source>. A source that cannot be reached today is skipped, not
failed: that is the network, not the code.
"""
import pytest

import source_contract

SOURCES = source_contract.sources_with_contracts()


@pytest.mark.live
@pytest.mark.parametrize("source", SOURCES)
def test_source_still_answers_as_its_fetcher_expects(source):
    result = source_contract.check_source(source)
    if result["status"] == source_contract.UNREACHABLE:
        pytest.skip(f"{source} is unreachable today: {result['detail']}")
    assert result["status"] == source_contract.OK, source_contract.format_result(result)
