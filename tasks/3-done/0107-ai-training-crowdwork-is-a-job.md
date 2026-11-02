# 0107 AI-training crowdwork reaches the list as a job

Source: the owner, 2026-11-02
Scope: identity:sharp, config

## Business
The AI check rejects AI-training crowdwork as "not a job posting": code
review and evaluation of AI output for model training (Alignerr, TELUS
Digital AI, the "OpenAI Codex / Claude" reviewer roles on himalayas and
remoterocketship). These postings are usually remote for anywhere. The
person applied to five of them in October; the AI check rejected all five
when it read them on 2026-10-24. In the week of 2026-10-26 it rejected five
more for this reason.

The owner, 2026-11-02: AI-training crowdwork is work, and the person can
mark it "not for me" themselves. The AI check keeps it, and the person
decides.

The rule comes from the AI check, not from the scripts: it is in
`config/ai_screen_prompt.md` (`is_job_posting` is false for "AI training
crowdwork") and in `config/ai_brief_prompt.md` (the brief lists crowdwork
for training AI models as not a posting). The scripts reject it too: the
sharp template's `ai_training_crowdwork_gate` (since 2026-08-05) adds "role:
AI-training crowdwork, not a software engineering job".

## Items
- DONE - Plan: both prompts say paid crowdwork for training AI models is a job posting, `cv_fit` counts the crowdwork that reviews or writes code as a stretch, and the sharp template turns its script gate off
- DONE - `config/ai_screen_prompt.md` (`is_job_posting`, `cv_fit`) and `config/ai_brief_prompt.md` ("Not a job posting"): crowdwork for training AI models is a job posting; a test checks the prompt
- DONE - Sharp template V35: `ai_training_crowdwork_gate: {}`, the reason in its comment and in the CHANGELOG; the local identity updated
