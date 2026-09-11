# LGD State and District Data Research

**Step 2 of the PRAMAAN India-wide reference-data project — COMPLETE.**
Data acquisition and validation only. No models, APIs, migrations, seeder, database rows or baseline CSVs were
modified. The database was never connected to. Nothing was committed or pushed.

**Outcome:** State/UT and District data have both now been **acquired from LGD and fully validated**.
36 States/UTs and **784 districts**, with LGD codes, reconciling perfectly against each other.

**Two headline findings:**

1. ✅ **LGD codes are confirmed suitable as PRAMAAN's stable geographic identifiers** — complete, unique,
   and demonstrably retired rather than recycled at both State and District level.
2. ❌ **LGD cannot supply Hindi names at all.** The district report has **no local-language column whatsoever**,
   and the State-level local-language column is ~81% English placeholder. `state_name_hi` and
   `district_name_hi` need a different source. **Nothing was transliterated or invented.**

Companion documents: [reference-data-research.md](reference-data-research.md) ·
[reference-data-baseline.md](reference-data-baseline.md)

---

## 1. Source

| Item | Value |
|---|---|
| Authority | **Local Government Directory (LGD)**, Ministry of Panchayati Raj, Government of India |
| Site | https://lgdirectory.gov.in/ |
| Hosting | Designed, hosted and maintained by **National Informatics Centre (NIC)**. Contents owned, updated and managed by the Panchayats and State Panchayati Raj Departments (per the site footer) |
| **States/UTs — page used** | **https://lgdirectory.gov.in/globalviewstateforcitizen.do** — public "View State/UT" citizen page |
| **Districts — page used** | **https://lgdirectory.gov.in/downloadDirectory.do** — bulk "Download Directory" report, **CAPTCHA-gated, downloaded manually by the user** |

Why LGD is authoritative is established in [reference-data-research.md §2](reference-data-research.md): it is
the Government's mandated standard location-code directory (adoption mandated by the Cabinet Secretariat,
letter dated 4 November 2016), maintained jointly with the Office of the Registrar General of India.

**No third-party or scraped dataset was used as a source of record.** A GitHub mirror of LGD data exists; it
was never read. `data.gov.in`'s LGD resource was **rejected** — its metadata shows
`published_date` = `1658488727` → **22 July 2022**, which predates the December 2024 Rajasthan district
changes and is therefore stale (see §8, anomaly 8).

---

## 2. Retrieval

| Item | States/UTs | Districts |
|---|---|---|
| Retrieval date | **2026-09-11** | **2026-09-11** |
| Report name | "View State/UT" citizen listing | **"All Districts of India"** (title row of the file itself) |
| Method | Direct HTTP GET (`curl`), HTTP 200, 135,253 bytes HTML | **Manual browser download** (CAPTCHA-gated) |
| File received | *(HTML, parsed in-session)* | `data/reference/source/lgd_districts_raw.xlsx` — 34,834 bytes |
| Format | HTML only, no export button | **Genuine XLSX** (verified: `PK\x03\x04` magic bytes; OOXML zip containing `xl/worksheets/sheet1.xml`, 234,650 bytes) |
| Rows | 36 | **786 total = 1 title + 1 header + 784 data** |
| Source version / "as on" field | ❌ **NONE** | ❌ **NONE** |

⚠️ **Neither source carries a data-version or snapshot field.** The retrieval date is the only version
information available, which is why `source_version` exists in the PRAMAAN schemas. LGD is a live directory.

### ✅ Evidence the snapshot is genuinely current

**Rajasthan returns exactly 41 districts.** Rajasthan reduced its districts from 50 to 41 in **December 2024**
when 9 newly created districts were cancelled. This snapshot reflects the post-reversal state, confirming it is
current and **not** the stale July 2022 OGD data.

### Parsing method

The XLSX was read with a **dependency-free reader** (`zipfile` + `xml.etree`, handling inline strings, shared
strings and numerics). No package was installed into the project venv. Scripts live only in the session
scratchpad.

⚠️ **Float artefact:** LGD's XLSX export writes every integer as a float — `State Code` arrives as `"35.0"`,
`District Code` as `"603.0"`. **Any tool reading this file naively will produce codes like `35.0`.** The
normalised extract (§3) fixes this; nothing else was altered.

---

## 3. Files produced by this step

| Path | Contents | Tracked? |
|---|---|---|
| `data/reference/source/lgd_states_raw.csv` | 36 State/UT rows, LGD column names **verbatim** | Untracked |
| `data/reference/source/lgd_districts_raw.xlsx` | The original downloaded file, **unmodified** | Untracked *(user-supplied)* |
| `data/reference/source/lgd_districts_normalised.csv` | 784 district rows, LGD column names **verbatim**, float artefact removed only | Untracked |

All three are UTF-8 with BOM where CSV. **These are source extracts, not PRAMAAN datasets** — no renaming, no
added columns, no inferred values. The baseline CSVs were not touched (§12).

---

## 4. State/UT schema

**Exact column headers as published by LGD** (read from the page's `<th>` cells):

| # | Exact LGD column name | Meaning |
|---|---|---|
| 0 | `* Note : UT-Union Territory` | Legend cell, not data |
| 1 | `S No` | Alphabetical display counter. ⚠️ **Not an identifier** — shifts when entities are added |
| 2 | **`State LGD Code`** | **The LGD identifier for the State/UT** |
| 3 | `State Name (In English)` | Official English name |
| 4 | `State Name (In Local language)` | Generic local-language field — **NOT a Hindi field**, see §6 |
| 5 | `State or UT` | Literal values `State` / `UT` |
| 6 | `Census 2001 Code` | Census 2001 state code |
| 7 | `Census2011 Code` | Census 2011 state code (LGD spells this without a space) |
| 8–11 | `View Details`, `View History`, `View Government Order`, `View Map` | Action links, empty in extract — dropped |

`View History` and `View Government Order` are notable: LGD tracks entity changes and links the government
order that authorised each — exactly the provenance trail a refresh procedure needs.

---

## 5. District schema

✅ **NOW ESTABLISHED.** Exact column headers, read from the file's own header row:

| # | Exact LGD column name | Meaning | Notes |
|---|---|---|---|
| 0 | `S.No.` | Display counter | ⚠️ **Not an identifier** |
| 1 | `State Code` | Parent State/UT LGD code | ⚠️ Note the name differs from the State file's `State LGD Code` |
| 2 | `State Name (In English)` | Parent State/UT English name | Identical spelling to the State file — verified, zero mismatches |
| 3 | **`District Code`** | **The LGD district identifier** | Globally unique across all India |
| 4 | `District Name(In English)` | Official English district name | ⚠️ No space before `(` in LGD's header |
| 5 | `Census 2001 Code` | Census 2001 district code | `0` where the district post-dates 2001 |
| 6 | `Census 2011 Code` | Census 2011 district code | `0` where the district post-dates 2011 |

Title row above the header: `All Districts of India`.

### ❌ There is NO local-language or Hindi column

The district report has **7 columns and not one of them is a local-language field.** Verified two ways:
no header contains "local" or "hindi", and **0 of 784** district names contain any Devanagari character.

This is a stronger negative than at State level, where at least a (mostly placeholder) column exists.

---

## 6. Language fields

### State/UT level — one generic column, mostly placeholder

LGD publishes **`State Name (In Local language)`**. It is a **generic local-language field, not a Hindi field.**
Measured across all 36 rows:

| Measurement | Count |
|---|---|
| Values containing **Devanagari** | **3 / 36** |
| Values in other Indic scripts | **4 / 36** |
| Values in **Roman** script | **33 / 36** |
| of which **ALL-CAPS Roman** | 32 |
| Values **identical to the English name** | **29 / 36** |
| Empty | 0 |

**The 3 Devanagari values:** Chhattisgarh `छत्तीसगढ़` · Jharkhand `झारखंड` · Maharashtra `महाराष्ट्र`
**The 4 other-script values:** Karnataka `ಕರ್ನಾಟಕ` · Odisha `ଓଡ଼ିଶା` · Telangana `తెలంగాణ` · Tripura `ত্রিপুরা`

Everything else — **including Uttar Pradesh, whose value is the Roman string `UTTAR PRADESH`** — is the English
name in capitals.

### District level — no column at all

| Measurement | Count |
|---|---|
| Local-language / Hindi columns in the report | **0** |
| District names containing Devanagari | **0 / 784** |

### Answers to the questions posed

| Question | States/UTs | Districts |
|---|---|---|
| 1. Column exists? | ✅ Yes (generic) | ❌ **No** |
| 2. Values populated? | Technically 36/36 non-empty | ❌ N/A |
| 3. All rows have a real local-language name? | ❌ **No — only 7/36** | ❌ N/A |
| 4. Only some States populated? | ✅ 7 States | ❌ N/A |
| 5. Language varies by State? | ✅ **Yes** — Devanagari, Kannada, Odia, Telugu, Bengali in one column | ❌ N/A |
| 6. Hindi-specific field or generic? | **Generic. No Hindi column exists** | **No field at all** |

### ⚠️ Devanagari ≠ Hindi

Even the 3 Devanagari values are not necessarily *Hindi*. `महाराष्ट्र` is the **Marathi** name for Maharashtra;
Marathi shares the script. **Script detection does not establish language.**

### Verdict

> ❌ **LGD cannot populate `state_name_hi`.** For Uttar Pradesh — the only state PRAMAAN currently operates in
> — LGD's local-language value is the Roman string `UTTAR PRADESH`. Copying that into a `_hi` column would be
> wrong; inferring `उत्तर प्रदेश` from it would be fabrication. **Neither was done.**

> ❌ **LGD cannot populate `district_name_hi`.** The column does not exist. This is now a settled fact, not a
> pessimistic expectation.

### ✅ Consequence: the existing baseline is the better Hindi source

PRAMAAN's baseline **already holds genuine Hindi names for all 75 UP districts** (`आगरा`, `अलीगढ़`,
`अम्बेडकर नगर`, …) — verified Devanagari on **75/75** rows. These came from the lost seeder CSVs.

> **LGD must NOT overwrite the baseline's Hindi district names. LGD has none to offer.**
> The correct merge is: take **codes and English names** from LGD, **keep Hindi from the baseline** where it
> exists, and leave Hindi blank for the other 709 districts until a real source is found.

---

## 7. Counts

### ✅ States/UTs

| Metric | Value |
|---|---|
| **Total State/UT records** | **36** |
| **States** | **28** |
| **Union Territories** | **8** |
| LGD code range | 1–38 (25 and 26 retired) |

✅ **Matches the research report's 36 (28 + 8) exactly** — now upgraded from 🟡 REPORTED to ✅ **VERIFIED from
the primary source**, independently corroborating iGOD.

The 8 UTs: Jammu And Kashmir (1), Chandigarh (4), Delhi (7), Lakshadweep (31), Puducherry (34),
Andaman And Nicobar Islands (35), Ladakh (37), The Dadra And Nagar Haveli And Daman And Diu (38).

### ✅ Districts — 784 total

| Metric | Value |
|---|---|
| **Total district records** | **784** |
| Distinct State/UTs present | **36 / 36** — every State/UT has at least one district |
| Sum of per-State counts | **784** ✅ reconciles exactly |
| District code range | **1 – 796** (12 codes retired) |

✅ **This confirms LGD's own landing-page figure of 784**, which was previously only 🟡 REPORTED. It is now
✅ **VERIFIED** and adopted as the snapshot of record (retrieved 2026-09-11).

### District count by State/UT

| Code | State/UT | Districts | Code | State/UT | Districts |
|---:|---|---:|---:|---|---:|
| 1 | Jammu And Kashmir | 20 | 20 | Jharkhand | 24 |
| 2 | Himachal Pradesh | 12 | 21 | Odisha | 30 |
| 3 | Punjab | 23 | 22 | Chhattisgarh | 33 |
| 4 | Chandigarh | 1 | 23 | Madhya Pradesh | 55 |
| 5 | Uttarakhand | 13 | 24 | Gujarat | 34 |
| 6 | Haryana | 23 | 27 | Maharashtra | 36 |
| 7 | Delhi | 13 | 28 | Andhra Pradesh | 28 |
| 8 | Rajasthan | **41** | 29 | Karnataka | 31 |
| 9 | **Uttar Pradesh** | **75** | 30 | Goa | 3 |
| 10 | Bihar | 38 | 31 | Lakshadweep | 1 |
| 11 | Sikkim | 6 | 32 | Kerala | 14 |
| 12 | Arunachal Pradesh | 27 | 33 | Tamil Nadu | 38 |
| 13 | Nagaland | 17 | 34 | Puducherry | 2 |
| 14 | Manipur | 16 | 35 | Andaman And Nicobar Islands | 3 |
| 15 | Mizoram | 11 | 36 | Telangana | 33 |
| 16 | Tripura | 8 | 37 | Ladakh | 2 |
| 17 | Meghalaya | 12 | 38 | The Dadra And Nagar Haveli And Daman And Diu | 3 |
| 18 | Assam | 35 | | | |
| 19 | West Bengal | 23 | **Total** | | **784** |

Notable: **Rajasthan 41** (confirms the Dec 2024 reversal), **UP 75** (exactly matches the PRAMAAN baseline
count), Madhya Pradesh largest at 55, Chandigarh and Lakshadweep smallest at 1.

---

## 8. Validation

### ✅ Cross-file reconciliation — perfect

| Check | Result |
|---|---|
| State/UTs in states file | 36 |
| Distinct State/UTs in district file | 36 |
| State/UTs with **no** district rows | ✅ **none** |
| State codes in district file **not** in states file | ✅ **none** |
| State-name spelling mismatches between the two files | ✅ **none** |

The two independently-obtained files (one scraped from HTML, one downloaded as XLSX) agree on all 36 State
codes **and** all 36 State name spellings. Strong evidence both extracts are sound.

### ✅ Code validation

| Check | States/UTs | Districts |
|---|---|---|
| All codes numeric | ✅ Yes | ✅ Yes |
| Duplicate codes | ✅ **None** | ✅ **None** (784 unique) |
| Missing codes | ✅ **None** (36/36) | ✅ **None** (784/784) |
| Missing names | ✅ None | ✅ **None** |
| Missing parent State code | n/a | ✅ **None** |
| Code range | 1–38 | 1–796 |
| Unused codes in range | **2** (25, 26) | **12** |

**District codes are globally unique across all of India** — not scoped per State. UP's codes run 118–661
**non-contiguously**, because districts created later received high codes. So `District Code` alone is a
sufficient primary identifier; it does not need pairing with the State code.

### ✅ Code stability — direct evidence at both levels

**States:** codes `25` and `26` are absent. They belonged to the former UTs of Dadra & Nagar Haveli and
Daman & Diu, merged in 2020. The merged entity received the **new** code `38`; **the old codes were not
recycled.**

**Districts:** 12 codes unused within range 1–796 — `599, 601, 671, 769, 771, 773, 776, 778, 779, 780, 781, 783`.
The clustering in the 769–783 range is consistent with the **9 cancelled Rajasthan districts** of December 2024
being retired and their codes left vacant.

> ✅ **LGD retires codes rather than reusing them, at both State and District level.** This is precisely the
> property PRAMAAN needs, and it is self-evidencing from the data rather than taken on trust.

### ✅ Relationship to Census codes — verified

**States:** `State LGD Code` is **identical** to `Census2011 Code` for every State/UT that has one — zero
mismatches. Exceptions are post-Census entities: Telangana (36) and Ladakh (37) carry Census `00`; merged
DNH&DD (38) is empty.

**Districts:** **146 of 784 districts (19%) have `Census 2011 Code = 0`** and **169 have `Census 2001 Code = 0`**
— i.e. they were created after the respective census. Concentrated in Telangana (23), Andhra Pradesh (15),
Chhattisgarh (15), Arunachal Pradesh (11), Assam (8), Gujarat (8), Rajasthan (8), Manipur (7).

> ⚠️ **Therefore Census codes CANNOT serve as a district identifier** — 19% of districts have none.
> **LGD district codes are strictly necessary.** This settles the question decisively.

### ✅ Duplicate names

| Check | Result |
|---|---|
| Duplicate district names **within** the same State/UT | ✅ **None** |
| District names shared **across** different State/UTs | **3** |

The 3 genuine cross-State duplicates:

| District name | States | LGD codes |
|---|---|---|
| **Bilaspur** | Chhattisgarh, Himachal Pradesh | 375, 15 |
| **Hamirpur** | Himachal Pradesh, Uttar Pradesh | 17, 149 |
| **Pratapgarh** | Rajasthan, Uttar Pradesh | 629, 174 |

✅ `(state_code, district_name_en)` is therefore a **valid uniqueness key** — confirmed empirically, since no
State contains two districts of the same name. And `district_code` alone is unique nationally.

### ⚠️ Anomalies recorded

1. **🔴 Aurangabad is NO LONGER a cross-State duplicate — my earlier research was wrong on this.**
   [reference-data-research.md §9](reference-data-research.md) listed Aurangabad (Bihar + Maharashtra) as a
   confirmed duplicate, based on the 2008 ECI Order. **LGD shows Maharashtra's district is now
   `Chhatrapati Sambhajinagar` (code 469)**; only Bihar has `Aurangabad` (code 189).
   **This is a concrete mapping hazard for Step 3:** the 2008 ECI Order still says `AURANGABAD` for
   Maharashtra, so those ACs will **fail to match** LGD's current district name. The correction belongs in the
   ECI→LGD reconciliation, not in the LGD data.
2. **Balrampur near-collision** — UP has `Balrampur` (127); Chhattisgarh has `Balrampur-Ramanujganj` (649).
   Not an exact duplicate, but a fuzzy-matching hazard.
3. **🔴 XLSX float artefact** — every integer exports as a float (`35.0`, `603.0`). Naive readers will produce
   corrupt codes. Fixed in the normalised extract; **flagged for any future refresh.**
4. **Census `0` is a sentinel**, not a real code (146 districts). **Must never be treated as numeric zero.**
5. **Column-name inconsistency between LGD's own reports** — the State page says `State LGD Code`; the district
   report says `State Code`. Also `District Name(In English)` has no space before `(`, and the State page uses
   `Census2011 Code` while the district report uses `Census 2011 Code`. **Do not hard-code one spelling.**
6. **LGD English name `The Dadra And Nagar Haveli And Daman And Diu`** carries a leading definite article and
   differs from iGOD's `Dadra and Nagar Haveli and Daman and Diu`. LGD also title-cases `And` throughout
   (`Jammu And Kashmir`). ⚠️ **Any cross-source join on names will fail on these** — another argument for
   code-based joins.
7. **`S No` / `S.No.` are display counters**, not identifiers, in both files.
8. **No data-version field** in either source. Retrieval date is the only version marker.
9. **`data.gov.in` snapshot is stale** — `published_date` = 22 July 2022, predating the Rajasthan change.
   Correctly rejected as a source of record.

---

## 9. Comparison with PRAMAAN baseline

Non-destructive. The baseline files were **read only** and verified unchanged afterwards:

```
data/reference/districts.csv        md5=03a6b10df13e390daa740353437d1311   5,040 bytes
data/reference/constituencies.csv   md5=e3e275b684450db6a7f1288e8f545b37     925 bytes
```

### ✅ Counts agree exactly

| | Count |
|---|---|
| PRAMAAN baseline districts | **75** |
| LGD districts for Uttar Pradesh | **75** |

### ✅ What the acquired data resolves

| Blank baseline field | Now available from LGD |
|---|---|
| `state_code` | **`9`** (Uttar Pradesh) |
| `lgd_district_code` | Available for all 75 UP districts (codes 118–661) |
| `district_name_hi` | ❌ **Still unavailable from LGD** — keep the baseline's own values |

**None of these were written into the baseline.** Applying them is a later step.

### Name comparison — 69 exact, 6 spelling differences

| Category | Count |
|---|---|
| **Exact matches** (case-insensitive) | **69 / 75** |
| Matched but differing in case/spacing | 0 |
| In baseline but not in LGD | 6 |
| In LGD but not in baseline | 6 |
| **Genuinely missing districts either side** | **0** |

All 6 are **the same district under a different official spelling** — not renames, not missing data:

| PRAMAAN baseline | LGD official name | LGD code | Difference |
|---|---|---|---|
| `Barabanki` | `Bara Banki` | 129 | word split |
| `Bhadohi (Sant Ravidas Nagar)` | `Bhadohi` | 179 | baseline carries the alternate name in parentheses |
| `Lakhimpur Kheri` | `Kheri` | 159 | ⚠️ **materially different name**, not a typo |
| `Maharajganj` | `Mahrajganj` | 164 | spelling (`Maha` vs `Mah`) |
| `Raebareli` | `Rae Bareli` | 175 | word split |
| `Siddharth Nagar` | `Siddharthnagar` | 182 | word join |

Nearest-name matching identified 4 of the 6 automatically (`Barabanki`→`Bara Banki`,
`Maharajganj`→`Mahrajganj`, `Raebareli`→`Rae Bareli`, `Siddharth Nagar`→`Siddharthnagar`). Two —
`Bhadohi (Sant Ravidas Nagar)` and **`Lakhimpur Kheri`** — had **no close match** and were resolved by human
reading, not by algorithm.

> ⚠️ **This is the single most important operational lesson of Step 2.** A fuzzy matcher would have silently
> failed on `Lakhimpur Kheri` → `Kheri`. Automated name matching is **not** safe for this reconciliation:
> 2 of 75 rows (**2.7%**) require human judgement, and at 784 districts that is ~21 rows.
> **Mapping must be code-based, with name differences resolved by a reviewed mapping table.**

### ✅ Mapping ambiguity assessment

None of the 6 differences is ambiguous — each baseline district maps to **exactly one** LGD district, confirmed
by reading. There is no case where a baseline name could plausibly match two LGD districts. But the mapping
**must be recorded explicitly**, not recomputed by string similarity at load time.

---

## 10. Decision recommendation

| Question | Recommendation |
|---|---|
| **Should PRAMAAN use LGD State/UT codes?** | ✅ **YES — adopt.** Numeric, complete (36/36), unique, government-mandated, Census-2011-compatible, demonstrably retired not recycled. **Resolves open question Q1** |
| **Should PRAMAAN use LGD District codes?** | ✅ **YES — adopt.** Now confirmed: complete (784/784), **globally unique**, no duplicates, codes retired not recycled (12 vacant). And **necessary**, because 19% of districts have no Census code at all |
| **Can LGD safely provide district Hindi names?** | ❌ **NO — settled.** The district report has **no local-language column** and 0/784 names contain Devanagari. **Keep the baseline's 75 verified Hindi names; leave the other 709 blank** |
| **Can LGD safely provide state Hindi names?** | ❌ **NO — settled.** Generic multi-script column, 29/36 English placeholders, UP's value is `UTTAR PRADESH` |
| **Which fields remain unresolved?** | `state_name_hi` (**no LGD source — needs a different source entirely**) · `district_name_hi` for the 709 non-UP districts · everything AC-related (Step 3) |

### ✅ Both code questions are now answered — adopt LGD codes

Use `District Code` as the district identifier and `State LGD Code` as the State/UT identifier.

⚠️ **Schema implications to handle deliberately:**

1. **`state_code` is NUMERIC, not alpha.** The research report's CSV designs assumed a two-letter code
   (`UP`, `MH`). The authoritative value is `9`. Adopt the numeric code — but see the next point.
2. **Store codes as TEXT, not integers.** Census codes are published zero-padded (`09`) while LGD codes are
   not (`9`). Excel and naive CSV readers will strip padding and silently break joins. Combined with the
   **float artefact** (`9.0`), this is the most likely source of a quiet data-corruption bug in this project.
3. **Readability.** A numeric `state_code` makes CSVs harder to review by eye. Recommend carrying
   `state_name_en` alongside the code in child CSVs for reviewability — the **code** remains the join key.
4. **Do not hard-code LGD's column spellings** — they differ between LGD's own two reports (§8, anomaly 5).

### On the 6 UP naming differences

**Recommendation: adopt LGD's official English names as canonical** (`Kheri`, `Bara Banki`, `Rae Bareli`,
`Mahrajganj`, `Siddharthnagar`, `Bhadohi`), and record the baseline's spellings in an explicit, human-reviewed
alias/mapping table.

Rationale: LGD is the authority for district identity, and OCR-extracted voter data will encounter both
spellings in the wild. An alias table serves the OCR matcher; a silently-chosen "winner" would not.
⚠️ **`Lakhimpur Kheri` → `Kheri` in particular must be an explicit mapping entry, since no algorithm will
find it.**

### On `state_name_hi`

No LGD source exists, and there are only **36 rows**. The practical path is a **small, manually curated,
individually sourced list** with the source recorded per row — not a bulk import, and explicitly **not**
transliteration. 36 rows is tractable by hand; fabricating them is not acceptable in an electoral application.

For the 709 districts without Hindi, the same applies but at a scale that is **not** hand-tractable — this
should be treated as a genuine open problem, and Hindi left blank rather than guessed. It is worth noting that
PRAMAAN's OCR pipeline currently operates only in Uttar Pradesh, where Hindi **is** already available from the
baseline. Hindi for the other 709 districts may simply not be needed yet.

---

## 11. Status of Step 2

✅ **COMPLETE.** Both datasets acquired and validated. No blocking items remain in Step 2.

| Deliverable | Status |
|---|---|
| State/UT list with official codes | ✅ 36 rows, verified |
| District list with official codes | ✅ 784 rows, verified |
| Code scheme determined | ✅ LGD numeric codes at both levels |
| Language fields assessed | ✅ Settled — LGD provides no usable Hindi |
| Counts validated | ✅ 36 and 784, reconciling exactly |
| Baseline comparison | ✅ 75 = 75, 69 exact + 6 spelling differences resolved |

### Sources deliberately NOT used

| Source | Why rejected |
|---|---|
| GitHub mirror of LGD data | ❌ Third-party — not a source of record. May be used later **only** to cross-check an LGD-downloaded file |
| `data.gov.in` LGD district resource | ⚠️ Official Government platform, but the snapshot is dated **22 July 2022** — predates the Dec 2024 Rajasthan change. Stale |

---

## 12. Safety verification

| Item | Status |
|---|---|
| Database modified | **NO** — **the database was not connected to at all in this step** |
| Voters modified | **NO** |
| Models modified | **NO** |
| APIs modified | **NO** |
| Migrations created/modified | **NO** |
| Seeder modified | **NO** |
| Seeder executed | **NO** |
| Data imported into the database | **NO** |
| **Baseline CSVs modified** | **NO** — verified by md5 before and after all reads |
| Codes invented | **NO** — every code copied verbatim from LGD |
| Hindi names invented / transliterated | **NO** |
| Census or ISO codes substituted for LGD codes | **NO** |
| Third-party dataset used as source of record | **NO** |
| CAPTCHA circumvented | **NO** — the district file was downloaded manually by the user |
| Final India-wide CSVs generated | **NO** — that is a later step |
| Packages installed into the project venv | **NO** — XLSX parsed with stdlib only |
| Committed / pushed | **NO** |

### Licensing note — why the source files are left untracked

LGD content is owned by the Panchayats and State Panchayati Raj Departments and hosted by NIC. **No explicit
open-data licence (e.g. GODL-India) was found stated on the pages used**, and no terms-of-use declaration
covering redistribution was located.

The files contain **factual government reference data** (names and codes) — the least licence-sensitive
category — and retaining them gives the repository genuine provenance value. But because the licence is
**unverified**, they are **left untracked with no commit made**. Confirm LGD's terms of use before adding them
to version control.

---

## 13. Next step

Step 2 is finished. Remaining work, in order:

1. **Decide the `state_code` representation** — numeric LGD code, stored as **text** to survive zero-padding
   and the float artefact (§10)
2. **Decide the UP naming policy** — recommended: adopt LGD's official English names, with a reviewed alias
   table for the 6 differences (`Lakhimpur Kheri` → `Kheri` must be explicit)
3. **Plan `state_name_hi`** separately — 36 rows, manually sourced, never transliterated
4. **Proceed to Step 3** of [reference-data-research.md §13](reference-data-research.md) — the ECI Assembly
   Constituency parser. ⚠️ Carry forward the **Aurangabad → Chhatrapati Sambhajinagar** finding (§8, anomaly 1):
   the 2008 ECI Order's district names are ~2001-era and **will not all match** LGD's current 784. That
   reconciliation is the hard part of Step 3, and this step has now established the target list it must
   reconcile onto.
