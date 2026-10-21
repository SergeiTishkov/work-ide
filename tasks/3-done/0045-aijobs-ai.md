# 0045 aijobs.ai for AI engineering roles

Source: the agent, 2026-09-13; relevant again since stretch roles (2026-10-20)

## Business
A board of AI roles. In September it was set aside as mostly
machine-learning roles a .NET CV does not reach. Since the owner wants
applied AI and forward deployed roles read as a stretch, the part of it that
is engineering around models may now be in reach; research roles stay out.

## Implementation
Measured 2026-10-21 (pages 1-3 of /remote, 61 job pages read):

- /remote?page=N, 20 cards a page, 37 pages: about 728 remote postings,
  the oldest a year old. The job-type filter returns 0 for part-time,
  freelance and contract; all 61 read were full time.
- Each job page has a JobPosting (full description, date, country; a salary
  on 23 of 61), but its JSON is malformed and needs reading by pattern.
- By title: 18 engineering, 18 machine learning or research, 25 other.
  .NET or C# in one real description (Blueprint, US teams).
- Reachable from Georgia: 1 of 61 (Vertex Marketing Group, "Europe or Latin
  America"). About 40 are limited to one country, 3 to the US and Canada.
- Behind Cloudflare without a challenge; 10 requests a minute
  (x-ratelimit-limit). A full read is about 750 requests, over an hour.
- 57 of 61 apply links lead to Greenhouse boards (GitLab, xAI, Mercury,
  Monzo, Twilio and others): the site re-lists Greenhouse, which
  tools/fetch_ats.py reads directly for the boards named in the identity's
  ATS targets.

Decision: no fetcher. One reachable posting in 61 does not pay for an hour
of reading a page at a time. Employers met there are better added as ATS
targets.

## Items
- DONE - Measure how many of its remote postings are engineering rather than research, after the first stretch results; write the plan here or drop the ticket
