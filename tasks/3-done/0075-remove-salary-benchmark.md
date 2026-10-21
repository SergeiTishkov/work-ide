# 0075 Remove the salary yardstick no one reads

Source: the owner, 2026-10-22 (task 0053 cancelled)
Scope: tools

## Business
tools/salary_benchmark.py read IT Jobs Watch's UK pay medians for the
Markdown report. The report is gone (task 0052) and the owner cancelled
showing the yardstick in the app (task 0053), so nothing runs or reads it.

## Implementation
The tool and its tests go; the registry and docs/SOURCES.md say why. The
identities' knowledge/salary_benchmark.json files stay where they are
(data, not code); tools/merge_shared_base.py still moves one from the old
layout.

## Items
- DONE - Remove tools/salary_benchmark.py and tests/test_salary_benchmark.py; registry and docs
