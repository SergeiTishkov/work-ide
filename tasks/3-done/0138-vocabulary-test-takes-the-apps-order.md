# 0138 The vocabulary test takes the app's own order of the classes

Source: the agent, 2026-11-21
Scope: tools

## Business
Task 0136 put "Never say never" right after "Long shots" in the app's
`CLASS_KEYS`. `tests/test_vocabulary_sync.py` required the app's sections in
the scripts' `report.LISTED_CLASSES` order (never_say_never last), so it
failed on main from that merge on. The test now checks that the app lists
the same classes, its own picks first, in an order of its own.

## Items
- DONE - `test_the_classes_agree_between_the_scripts_the_clean_up_and_the_app` compares the classes, not their order
