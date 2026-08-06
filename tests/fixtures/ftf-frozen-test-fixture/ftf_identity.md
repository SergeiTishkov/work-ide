# FTF — the test fixture

> **FTF = Frozen Test Fixture.**
> This is not a live person's identity. It is a frozen snapshot of the
> configuration the project's test suite is calibrated against.

## Why it exists

The scoring tests check specific numbers and classifications: "a legacy vacancy
scores more than a startup", "a vacancy with no geography signal is rejected",
"one familiar stack match is not enough". Every one of those statements depends
on the contents of `criteria.yaml` and `profile.yaml`.

If the tests read the active identity's config, two bad things would happen:

1. The test results would depend on which identity a developer happens to keep
   active. The same commit would be green for one person and red for another.
2. Any tuning of personal criteria would break the tests — and somebody
   configuring their own search would be forced to fix somebody else's
   assertions. That quickly teaches people to "fit the test to the code" rather
   than the other way round.

A separate frozen fixture removes both problems.

## The freeze rule

**The `ftf_*` files are not synchronised with other identities and are not
updated "while we are at it".**

They may be changed only together with a deliberate change to the tests, in one
commit, with an explanation in the commit message. A divergence between `ftf`
and live identities is not a problem but a working mechanism: it turns every
change to the machinery into an explicit, reviewed update to the tests.

That is counter-intuitive, and an agent without this note will certainly try to
"tidy it up". Do not tidy it up.

## Where it came from

A byte-for-byte copy of the project's configuration at the moment it moved to a
multi-identity architecture (2026-07-31), plus an `identity: {kind: fixture}`
block.

The copy was deliberate rather than written from scratch: the test suite was 111
checks calibrated to exactly these values. A synthetic "neutral" fixture would
have meant rewriting most of the assertions inside the very refactor that was
already moving every path in the project. Too much risk at once.

## Protection against accidental use

`kind: fixture` makes `common.activate_identity()` refuse unless
`allow_fixture=True` is passed. The one place that flag is set is
`tests/conftest.py`. A real search against the fixture is impossible.

## Which tools it uses

None, really: network calls in the tests are mocked and data is written into
temporary directories (`tmp_path`) rather than into `data/ftf/`. The source and
ATS files were copied for structural completeness — so that the fixture passes
`identity.py validate` on the same terms as a real identity.
