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

The owner, 2026-11-02: "Краудворк по обучению ИИ является работой, я могу
просто «не для меня» нажать если захочу" (AI-training crowdwork is work; the
person can mark it "not for me" themselves). The AI check keeps it, and the
person decides.

The rule comes from the AI check, not from the scripts: it is in
`config/ai_screen_prompt.md` (`is_job_posting` is false for "AI training
crowdwork") and in `config/ai_brief_prompt.md` (the brief lists crowdwork
for training AI models as not a posting).

## Items
- TO DO - Work out the plan and write it here as the next items
