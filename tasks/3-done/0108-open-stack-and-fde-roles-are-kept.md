# 0108 Roles open to several languages and forward deployed roles are not cut for the stack

Source: the owner, 2026-11-02
Scope: identity:sharp, config

## Business
The owner, 2026-11-02: good postings appear often for forward deployed
engineers and for engineers without a hard stack requirement ("experience
with Go/Java/Rust or something similar"), and there were many of them. Such a
role is a fit: the language is one of several the employer accepts, not the
expertise the role needs.

In the week of 2026-10-26 the AI check kept 14 of the 445 new postings the
scripts passed to it. Whether these roles are among the rejected ones has
not been measured yet. The rule in force since 2026-10-28 (the local
identity): another main language is a stretch unless expertise in it is
stressed.

## Items
- DONE - Measure: rejected forward deployed roles and roles that list a language as one of several, by the reason the AI check gave. Forward deployed titles: 46 read, 43 rejected; 34 of them on location ("no") with `cv_fit` "stretch", 9 on both. Texts that list a language among others ("or similar", "any modern language"): 222 read; 178 rejected on location, 18 for fit with location "yes", several of these crowdwork (task 0107) or specialist roles. Location is the main cause, and task 0109 changes it
- DONE - Plan: the stack rule made explicit in both prompts (a language named as one of several the posting accepts is not a requirement of it; judge on the work and the level); forward deployed and solutions engineers who write code stay at least a stretch; the location side is task 0109
- DONE - `config/ai_screen_prompt.md` (`cv_fit`) and `config/ai_brief_prompt.md` ("Roles that fit"): the rule above; the sharp template's description says it too (V35)
