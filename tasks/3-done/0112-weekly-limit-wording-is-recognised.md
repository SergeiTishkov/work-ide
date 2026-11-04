# 0112 The weekly limit's real wording stops the AI work

Source: the owner, 2026-11-04
Scope: tools

## Business
On 2026-11-03 the account met its weekly usage limit for the first time
since task 0057. Claude Code answered "You've hit your weekly limit ·
resets Nov 4, 10pm (Asia/Tbilisi)". `tools/ai_limit.py` knew "hit your
limit" and "hit your usage limit" but not this wording, so every refused
call was one ordinary error, as before task 0057:
- task 67 (the Tuesday collection): the AI check read 185 postings, then 43
  calls failed; the agent's session ended at the limit, the task failed,
  and the schedule skipped the rest of the base (69) and the CV/CL batch
  (70);
- tasks 68 (LinkedIn) and 73 (AI): 127 and 78 calls failed, sent again
  three times each, nothing read;
- task 71 (CV/CL batch): six documents failed one after another, then the
  batch crashed: `[WinError 5] Access is denied` replacing
  `data/cv_batch.json`, which the app reads every second;
- the background worker's reset check logged "claude did not answer"
  instead of the limit.

The reset time has a date in it ("Nov 4, 10pm"), which the clock reader
did not take either.

## Items
- DONE - `ai_limit`: "hit your <word> limit" is the limit; a reset time with a month and day ("resets Nov 4, 10pm (Asia/Tbilisi)") is read; tests with the real wording. The zone in brackets is read only where Python has a tz database; this machine has none (no `tzdata`), so it is read as local time, which is the same zone here
- DONE - `cv_batch`: replacing its status file is tried again for up to two seconds when Windows refuses it; a test
