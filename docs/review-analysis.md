# Review Analysis: 314 Issues by @AndresBPinto

**Period:** April 15–17, 2026
**Entities reviewed:** 309 unique (276 events + 33 authoritative events)
**Data:** [`review-data.json`](review-data.json) (314 parsed issue records)

---

## Overview

| Action | Count | % | Validated |
|--------|-------|---|-----------|
| mark_valid | 146 | 46% | 82 |
| mark_blocked | 96 | 31% | 73 |
| report (needs fix) | 64 | 20% | 61 |
| mark_unusable | 7 | 2% | 4 |

**Approval rate: 46%** — fewer than half the extracted events passed review.

Notes:
- 4 duplicate reviews: event/777, event/470, event/387, authoritativeevent/1898
- 1 issue (#118) had malformed JSON (unescaped quotes)
- 221 of 314 issues already processed into `edits.jsonl`

### By table

| | event (279) | authoritativeevent (34) |
|---|---|---|
| Valid | 129 (46%) | 17 (50%) |
| Blocked | 96 (34%) | 0 (0%) |
| Report | 50 (18%) | 14 (41%) |
| Unusable | 4 (1%) | 3 (9%) |

Authoritative events have a higher valid rate but also a much higher report rate — they tend to be partially correct rather than completely wrong.

---

## Error Patterns

### Pattern 1: Not a PE (96 blocked)

The largest error category. The model extracts events that don't meet the definition of a public event (PE).

| Sub-category | Count | Key issues |
|---|---|---|
| Generic "inte en PE" | 52 | Various non-public events |
| Internal meetings (internt möte) | 29 | Board, party, union internals |
| Too vague | 4 | No specific time/place |
| Strikes | 3 | Excluded per reviewer |
| Election meetings (valmöte) | 2 | |
| Lectures (föredrag) | 1 | |
| Other | 5 | Funerals, exhibitions, festivals |

#### Blacklist gap analysis

Many terms the reviewer flagged are **already blacklisted** in `pilot_2024/src/lists/meetingtype_blacklist.txt` but events still slip through:

| Term | Blacklisted? | Notes |
|------|:---:|---|
| `fest` | Yes | Still producing events — variant names? |
| `sammanträde` | Yes | Still producing events |
| `styrelsemöte` | Yes | Still producing events |
| `kommunalstämma` | Yes | Still producing events |
| `begravning` | Yes | Still producing events |
| `föredrag` | Yes | Still producing events |
| `konferens` | Yes | Still producing events |
| `kongress` | **No** | Add |
| `årssammankomst` | **No** | Add |
| `järnvägsmöte` | **No** | Add |
| `utställning` | **No** | Add |
| `valmöte` | **No** | Add |

**Hypothesis:** The model extracts meeting types with names that don't exactly match blacklist entries (e.g., "styrelsens sammanträde" vs. "sammanträde"). This is likely a substring matching gap or model naming variance.

#### Strejk/strike conflict

`strejk` is on the **whitelist** (`meetingtype_whitelist.txt`) but the reviewer blocks strikes. This is a codebook definition question to resolve.

---

### Pattern 2: Wrong/missing location (24 reports)

| Sub-pattern | Count | Examples |
|---|---|---|
| Too vague ("Sverige", "överallt") | 8 | #115, #135, #272 |
| Missing location entirely | 6 | #99, #124, #259 |
| Wrong location | 5 | #131 (Ralmö→Malmö, OCR), #317 (merged cities) |
| Multiple locations need splitting | 3 | #231, #250 |
| Wrong granularity (street vs. city) | 2 | #316 |

---

### Pattern 3: Wrong timestamp (21 reports)

| Sub-pattern | Count | Examples |
|---|---|---|
| Should be May 1st ("1 maj") | 8 | #139, #170, #200, #249, #266, #334 |
| Other wrong date | 6 | #62 (6→4 aug), #107, #284 |
| Forward-looking article | 4 | #138, #209 |
| Uncertain time | 3 | #60, #228, #335 |

May Day is a systematic normalization failure: "majdemonstration" articles consistently get wrong dates.

---

### Pattern 4: Merge/split needed (8 reports)

- **Merge:** #41/#42 (Ramlösa duplicates), #47, #63, #125 (same as #221), #279/#280 (same as #654)
- **Split:** #140 (two meetings), #207 (two demonstrations), #231 (per location), #250 (three locations), #278 (multiple agitation meetings)
- **Composite:** #64 (three events combined)

---

### Pattern 5: Non-events extracted (6 reports)

Events extracted from texts describing events that were prevented, planned but not held, or hypothetical:

| Issue | Description |
|---|---|
| #119 | Demonstration blocked by authorities |
| #209 | "Thinking about" holding a meeting |
| #349 | PE prevented by police chief |
| #348 | Gathering forbidden |
| #193 | Chairperson role taken as evidence of meeting |
| #344 | Agitating text, no PE mentioned |

---

### Pattern 6: Hallucinations / no textual support (4 cases)

| Issue | Description |
|---|---|
| #98 | "Meeting seems to be a hallucination" |
| #51 | Correctly logged meeting, but article text doesn't support it |
| #52 | Same as above |
| #243 | "No actual meeting mentioned in text" |

---

### Pattern 7: Missing actors (3 reports)

| Issue | Description |
|---|---|
| #39 | Wrong actors (nations instead of individuals) |
| #71 | Speakers not extracted as actors |
| #107 | Actors in text but not picked up |

---

## Actionable Items

### P0 — Investigate blacklist bypass

Many blacklisted terms still produce events. Root-cause investigation needed:
- Are variant names bypassing exact-match?
- Is the blacklist check running at the right pipeline stage?
- Files: `pilot_2024/src/lists/meetingtype_blacklist.txt`, `pilot_2024/src/meetingtypes/resolution_rules.py`

### P0 — Resolve strejk/strike policy

`strejk` is whitelisted but reviewer blocks strikes. Decision needed from project team.

### P1 — Add missing blacklist terms

Add: `kongress`, `årssammankomst`, `järnvägsmöte`, `utställning`, `valmöte`

### P1 — Prompt: internal vs. public meetings

Add explicit instruction to extraction prompt to exclude internal/closed/members-only meetings.
File: `pilot_2024/src/event_extracter.py`

### P2 — May Day timestamp normalization

Add post-processing rule: articles about "majdemonstration" → timestamp May 1st.

### P2 — Location vagueness filter

Add "Sverige", "överallt" to location blacklist. Consider city-level requirement in prompt.

### P3 — Non-event detection

Add prompt guidance: don't extract events described as prevented, forbidden, or hypothetical.

### P3 — Actor extraction

Low volume but systematic: improve prompt to extract named speakers/participants.

---

## Discussion Points

1. **Strike policy:** Should strikes be included or excluded? Whitelist says yes, reviewer says no.
2. **Blacklist effectiveness:** Why do blacklisted terms still produce events?
3. **Location granularity:** City-level + sub-location, or just city?
4. **Forward-looking articles:** Should these produce events at all?

---

## All Block Reasons

<details>
<summary>96 blocked issues with reasons</summary>

| # | Entity | Reason |
|---|---|---|
| 72 | event/20 | inte en PE |
| 79 | event/41 | inte en PE |
| 86 | event/76 | inte en PE |
| 90 | event/90 | Internt partimöte, inte PE |
| 93 | event/97 | för vagt, kopplar inte till faktiska möten |
| 96 | event/105 | konferenser ska väl vara på vår blacklist? |
| 104 | event/141 | Inte ett offentligt tillgängligt möte |
| 105 | event/136 | Revisionsberättelse, inte en PE |
| 108 | event/127 | stängt möte mellan kommitte och statsrådsberedningen |
| 115 | event/165 | Sverige är en för vag plats |
| 116 | event/164 | beskriver slutet möte; 1 maj datum fel |
| 118 | event/209 | för vagt ("funderar på att") |
| 119 | event/208 | demonstrationen ägde inte rum, blev hindrad |
| 121 | event/210 | Föredrag ska inte inkluderas |
| 123 | event/222 | strejkmöte, inte en öppen PE |
| 128 | event/254 | inte en PE |
| 129 | event/253 | utställning inte en PE |
| 134 | event/267 | Domstolsförhandling inte en PE |
| 136 | event/261 | för brett och vagt |
| 138 | event/278 | för vagt, framåtsyftande |
| 142 | event/271 | Strejkmöte, inte PE |
| 143 | event/290 | valmöte inte PE |
| 145 | event/287 | internt möte mellan fackföreningar |
| 146 | event/280 | internt möte |
| 147 | event/279 | inte PE |
| 148 | event/315 | inte PE |
| 149 | event/314 | föredrag inte PE |
| 150 | event/312 | inte en PE |
| 152 | event/297 | medlemsmöte, inte PE |
| 154 | event/323 | inte en PE |
| 159 | event/371 | inte en PE |
| 161 | event/329 | inte en PE |
| 162 | event/328 | inte en PE |
| 164 | event/386 | internt möte |
| 165 | event/385 | internt möte |
| 168 | event/374 | internt möte med majdemonstrationer på dagordningen |
| 177 | event/409 | strejk |
| 178 | event/407 | inte en PE |
| 180 | event/403 | högtidsdag, inte en PE |
| 184 | event/415 | internt möte; styrelsemöten till blacklist |
| 185 | event/414 | internt möte |
| 186 | event/413 | internt möte; sammanträde till blacklist |
| 190 | event/423 | järnvägsmöte, inte PE |
| 194 | event/428 | möte för bara rösträttsinnehavare |
| 201 | event/450 | inte PE; *fest till blacklist |
| 206 | event/461 | internt möte |
| 210 | event/430 | inte en PE |
| 213 | event/467 | beslut i riksdagen |
| 214 | event/466 | inte PE (466–471 samma) |
| 215 | event/465 | inte PE (465–471 samma) |
| 216 | event/464 | inte PE |
| 217 | event/462 | inte PE; *sammanträde till blacklist |
| 218 | event/471 | inte PE (465–471 samma) |
| 219 | event/470 | inte PE (465–471 samma) |
| 220 | event/470 | inte PE (465–471 samma) |
| 221 | event/469 | inte PE (465–471 samma) |
| 222 | event/468 | inte PE (465–471 samma) |
| 229 | event/509 | inte en PE; *sammanträde till blacklist |
| 232 | event/498 | strejker avgränsade bort |
| 233 | event/522 | inte PE |
| 234 | event/521 | inte PE |
| 236 | event/517 | karneval, inte en PE |
| 241 | event/525 | inte PE; *fest till blacklist |
| 242 | event/524 | internt möte |
| 243 | event/574 | inget faktiskt möte nämns |
| 244 | event/573 | partiinternt möte |
| 245 | event/551 | valmöte |
| 246 | event/548 | internt möte |
| 247 | event/602 | internt möte |
| 253 | event/609 | inte en PE |
| 255 | event/606 | internt möte |
| 260 | event/612 | valmöte |
| 269 | event/631 | inte en PE |
| 274 | event/640 | internt möte |
| 277 | event/655 | internt möte |
| 285 | event/661 | inte en PE |
| 290 | event/728 | internt möte |
| 291 | event/727 | bildande av fackförening |
| 293 | event/720 | internt möte |
| 296 | event/737 | inte PE; *kongress till blacklist |
| 298 | event/733 | inte PE; begravning till blacklist |
| 299 | event/729 | inte en PE |
| 304 | event/743 | internt möte |
| 313 | event/764 | internt möte |
| 314 | event/763 | internt möte |
| 318 | event/778 | internt möte |
| 319 | event/777 | internt möte |
| 320 | event/777 | internt möte |
| 321 | event/818 | internt möte |
| 324 | event/801 | inte PE; årssammankomst till blacklist |
| 329 | event/819 | internt möte |
| 330 | event/854 | internt möte |
| 331 | event/853 | internt möte |
| 336 | event/865 | kommunalstämma; *stämma till blacklist |
| 341 | event/884 | internt möte |
| 344 | event/876 | agiterande text, inget PE |
| 345 | event/875 | agiterande text, ingen PE |

</details>

## All Report Descriptions

<details>
<summary>64 report issues with descriptions</summary>

| # | Entity | Description |
|---|---|---|
| 36 | authoritativeevent/2509 | Osäker på hantering av tillbakablickande vaga beskrivningar |
| 39 | authoritativeevent/920 | actors är fel, inte nationerna |
| 41 | authoritativeevent/4122 | Mötet i Ramlösa, slå ihop med befintlig post |
| 42 | authoritativeevent/4125 | Mötet i Ramlösa, slå ihop; modellen missar talare |
| 43 | authoritativeevent/811 | 120 folkmöten 1845 — för allmänt |
| 47 | authoritativeevent/3918 | Bör slås samman; korrekt datum 6 mars 1864 |
| 51 | authoritativeevent/2476 | Korrekt möte men inget i artikeltexten visar det |
| 52 | authoritativeevent/2475 | Korrekt möte men inget i artikeltexten pekar på det |
| 59 | authoritativeevent/1900 | timestamp Ringsjön inte rätt |
| 60 | authoritativeevent/1526 | Osäker på om tiden är rätt |
| 62 | authoritativeevent/1612 | Tiden 6 aug, rätt datum 4 aug |
| 63 | authoritativeevent/2806 | Datumet fel, ska vara 4 aug; bör slås ihop |
| 64 | authoritativeevent/1898 | Kombinat av tre separata händelser |
| 71 | event/19 | Rätt men plockar inte ut talarna som Actors |
| 74 | event/25 | Oklart om detta är ett möte |
| 91 | event/91 | Antagligen rätt, behövs mer kontext för ort |
| 98 | authoritativeevent/1898 | Hallucination, tre möten sammanslagna |
| 99 | event/109 | För vag plats, behöver ort |
| 101 | event/122 | Osäker om PE — enbart nominering |
| 107 | event/131 | Datum fel (bör vara 1 maj), aktörer saknas |
| 111 | event/146 | För vagt — oklart antal möten föregående år |
| 124 | event/221 | Framåtsyftande håller som event; plats saknas (Kristianstad) |
| 125 | event/220 | Samma händelse som 221 |
| 131 | event/228 | Ralmö bör vara Malmö (OCR-problem) |
| 135 | event/265 | Överallt för vag plats |
| 139 | event/277 | Normaliseringen fel, bör vara 1 maj |
| 140 | event/274 | Bör delas i två möten |
| 170 | event/400 | Timestamp fel, ska vara 1 maj |
| 171 | event/396 | Oklart om PE — tivolipublik |
| 173 | event/389 | Två folkmöten, saknar tid och plats |
| 176 | event/411 | Fel tid/plats; rätt: 15 aug, Ladugårdsgärdet |
| 188 | event/425 | Oklart om folkmöte — Operans scen |
| 193 | event/429 | Ordförande ≠ bevis för möte |
| 197 | event/441 | Troligen inte PE — tryckfrihetsåtal |
| 200 | event/436 | Tiden fel, bör vara 1 maj |
| 204 | event/446 | För vag plats |
| 205 | event/444 | För vag plats; fenomen snarare än demos |
| 207 | event/460 | Bör delas — två demonstrationer |
| 209 | event/458 | Tiden fel, framåtsyftande |
| 228 | event/516 | Tiden troligen fel |
| 231 | event/501 | Bör delas per plats |
| 249 | event/590 | Timestamp bör vara 1 maj |
| 250 | event/588 | Bör delas på tre platser; saknar tid |
| 259 | event/615 | Plats bör framgå; actor ska vara arbetarekommunen |
| 266 | event/634 | Tiden bör vara 1 maj |
| 272 | event/645 | Tydligare plats behövs |
| 273 | event/643 | Platsen problematisk, bör vara Lund |
| 276 | event/659 | Platsen bör vara Eslöv |
| 278 | event/654 | Agitationsmöten behöver delas upp |
| 279 | event/653 | Samma som event 654 |
| 280 | event/652 | Samma som event 654 |
| 283 | event/669 | Rätt plats för demonstrationen är Malmö |
| 284 | event/662 | Normaliserad tid fel, bör vara 1 april |
| 295 | event/740 | Ryssland borde vara blacklist |
| 308 | event/755 | För vagt — fenomen snarare än folkmöten |
| 316 | event/788 | Modellen prioriterar specifik plats framför stad |
| 317 | event/784 | Malmö/Landskrona sammanslagna; ska vara Malmö |
| 326 | event/842 | För vagt, saknar specifika möten |
| 334 | event/850 | Beslut bör kopplas till 1 maj; tid fel |
| 335 | event/843 | Tiden troligen fel |
| 337 | event/864 | Oklart om PE |
| 346 | event/868 | Excerpten nämner bara skrivelse |
| 348 | event/891 | Avsaknad av PE genom förbud |
| 349 | event/890 | PE som inte hände pga förbud |

</details>
