# ECI Assembly Constituency reference data — Step 3 research record

Date: 2026-09-11. Scope: produce an authoritative, machine-readable ECI Assembly
Constituency dataset for PRAMAAN, reconciled to LGD, with the genuine gaps named
rather than filled in.

Nothing in this step touched the database, the SQLAlchemy models, the APIs,
migrations, the seeder, the voters table, or the existing baseline CSVs.

---

## 1. Source of record

| # | Source | Used for | Outcome |
|---|---|---|---|
| S2 | **ECI, Delimitation of Parliamentary and Assembly Constituencies Order, 2008 (English)** — `https://www.eci.gov.in/Documents/Delimitation/DelimitationofParliamentaryAssemblyConstituenciesOrder-2008(English).pdf` | AC number, AC English name, SC/ST reservation, district heading, extent, per-State AC totals (Schedule II) | ✅ Retrieved (1,340,728 bytes, 572 pages) and fully parsed |
| LGD | `data/reference/source/lgd_districts_normalised.csv` (36 States/UTs, 784 districts) | authoritative State Code, District Code, canonical English district names | ✅ Used as the reconciliation target |

Attempted and **not** obtained inside the time box:

| Target | Attempts | Result |
|---|---|---|
| ECI Assam Delimitation Order, 11 Aug 2023 | `eci.gov.in/delimitation-assam`, `eci.gov.in/files/file/14664-…`, `eci.gov.in/eci-backend/public/api/download?…`, web search | All ECI paths return a 1,279-byte JavaScript shell. Press coverage (PIB) confirms 126 ACs and 19 renamed ACs but carries no AC list. **Not obtained.** |
| J&K Delimitation Commission Order, 2022 | `jkelection.in` (connection refused), ECI paths as above | **Not obtained.** |

No third-party dataset was used as a source of record. No source of record other
than S2 contributed a single row.

---

## 2. Parser

Three standalone scripts, no new packages installed (the repo venv has no PDF
library, so the extractor is dependency-free — `zlib` + `re` only):

| Script | Does |
|---|---|
| `scripts/eci_ac/extract_pdf_layout.py` | Inflates the PDF's FlateDecode content streams and replays the text operators (`Tm`/`Td`/`TD`/`T*`/`TL`/`Tj`/`TJ`/`'`/`"`) to recover every text fragment **with its x/y position**, then groups fragments into lines. Output: `do2008.json`, 572 pages, 992,010 characters. |
| `scripts/eci_ac/parse_delimitation_2008.py` | Walks the layout, finds the 32 `SCHEDULE - <roman>` sections and the J&K `ANNEXURE - I`, bounds each state's AC table between its `PART A`/`TABLE A - ASSEMBLY CONSTITUENCIES` heading and its `PART B`/`TABLE B - PARLIAMENTARY CONSTITUENCIES`, `APPENDIX` or note terminator, derives the name/extent column boundary **per state** from the geometry of its own numbered rows, and emits one row per AC. Output: `data/reference/source/eci_ac_2008_raw.csv`. |
| `scripts/eci_ac/build_eci_ac_normalised.py` | Assigns LGD state codes, splits undivided Andhra Pradesh, reconciles district headings against LGD, and writes `eci_ac_normalised.csv` plus `eci_ac_validation.txt`. |

Positional extraction is what makes this work. The Order is a two-column table
whose cells wrap over many physical lines; a plain text dump interleaves AC
names with extent prose and cannot be parsed reliably. Recovering x-positions
lets the AC-name column be separated from the extent column state by state.

### Format variants the parser handles

Confirmed present in S2 and handled explicitly:

- `PART A - ASSEMBLY CONSTITUENCIES`, `PART A—ASSEMBLY CONSTITUENCIES`,
  `TABLE A - ASSEMBLY CONSTITUENCIES`, `TABLE A - ASSEMBLY CONSTITUENCIES & THEIR EXTENT`,
  `TABLE - A ASSEMBLY CONSTITUENCIES & THEIR EXTENT`
- District headings: `1 – DISTRICT : SAHARANPUR`, `7 - DISTRICT: SOUTH GARO HILLS`,
  `1 – District : Kasaragod`, `1 – DISTRICT :COOCHBEHAR`, `01 – DISTRICT : KACHCHH`
- AC row forms: `1 Behat`, `1. Sirpur`, `1-LUMLA (ST)`, `1 - Abdasa`,
  `01. MEKLIGANJ (SC)`, `1–Sadulshahar`, and the case where the name column holds
  only the number and the name wraps to the next line (accepted only when the
  number continues the state's sequence)
- Assam and Manipur carry a village-level `APPENDIX` between Part A and Part B;
  parsing stops at it. Without this the Assam schedule yields 998 spurious rows.
- Nagaland and Manipur have no `TABLE B`, so the section boundary falls back to
  the next `SCHEDULE` heading.
- Delhi's `TABLE A` has **no district headings at all**.

### Caveats

- The 2008 Order contains **zero Devanagari characters** (verified over the full
  572-page extraction). `constituency_hindi` is blank in every row. No name was
  transliterated. Hindi AC names need a separate authoritative source.
- `extent` is the Order's extent prose, recovered as wrapped text. The PDF
  itself breaks some words across positioned fragments, so joining them inserts
  a space mid-word (the Order's `4- Tal|heri Bujurg` comes back as
  `4- Tal heri Bujurg`). The extent column is usable as a reference string but is
  **not** a clean parsed territorial structure, and should not be tokenised
  without cleaning.
- `district_name_eci` is kept in the CSV alongside `district_name_en` so every
  mapping decision stays auditable against the source.

---

## 3. Validation

Full machine output: `data/reference/source/eci_ac_validation.txt`
(regenerate with `python scripts/eci_ac/build_eci_ac_normalised.py`).

| Check | Result |
|---|---|
| 1. Total rows | **4,032** |
| 2. Rows by State/UT vs Schedule II | **28 of 29** entities match the Order's own Schedule II exactly. Sikkim is 31 vs 32 — the one non-territorial seat (below). |
| 3. Duplicate `(state_code, ac_number)` | **0** |
| 4. Missing AC numbers | **none** — every State/UT is an unbroken run. Andhra Pradesh runs 120–294 (see §4). |
| 5. Missing English names | **0 blank**; longest name 27 chars (`BHUBANESWAR CENTRAL(MADHYA)`) |
| 6. District reconciliation vs LGD | 3,231 `exact` + 637 `mapped` = **3,868 rows resolved**; 94 `needs_review`; 70 `no_district_in_source` (Delhi). 534 of 544 distinct ECI district headings resolved to an LGD District Code. |
| 7. Unmatched ECI district headings | **9 headings**, all explained in the source matrix |
| 8. Cross-district extent cases | 37 rows whose extent prose names a district other than its own heading |
| 9. Hindi availability | **0 of 4,032** — by design, source contains none |
| 10. Source coverage, all 36 States/UTs | 25 VERIFIED, 6 UNRESOLVED, 5 no-Assembly. See `docs/eci-ac-source-matrix.md`. |

### Independent cross-checks that passed

1. **Per-state totals.** 28 of 29 state schedules parse to exactly the count
   printed in Schedule II of the same document — an internal consistency check
   the parser cannot fake.
2. **Andhra/Telangana split.** Splitting undivided AP on its ECI district
   headings yields **Telangana 119** (AC 1–119, contiguous) and **Andhra Pradesh
   175** (AC 120–294, contiguous), summing to the Order's 294. The split was not
   tuned to hit those numbers — the ten pre-2014 Telangana districts were listed
   first, and the counts fell out.
3. **National reconciliation.** 4,032 rows + 90 J&K + 1 Sikkim Sangha = **4,123**,
   the accepted national total. The shortfall is fully accounted for, not
   residual.

---

## 4. Findings that affect Step 4

1. **Andhra Pradesh AC numbers are undivided-AP numbers (120–294).** Post-2014
   Andhra Pradesh numbers its 175 ACs 1–175. The offset looks like −119, but that
   renumbering was **not confirmed against an official AP source**, so the source
   numbers are carried through unchanged and AP is flagged
   `source_version = 2008-undivided-ap-numbering`. Since the identifier is
   `(state_code, ac_number)`, loading AP as-is would store numbers that do not
   match AP voter rolls. **AP must be resolved before it is loaded.**
   Telangana is unaffected — its 1–119 already matches.

2. **Sikkim AC 32, Sangha, does not exist in the Order's Table A.** It is a
   non-territorial constituency (electors are monks of registered monasteries),
   so it has no extent and no district. Schedule II counts it in Sikkim's 32.
   Recorded as an expected missing row; **not fabricated**.

3. **Sikkim's reservation categories exceed SC/ST** (1 Sangha, 2 SC, 12 for
   Sikkimese of Bhutia-Lepcha origin under s.7(1A) RPA 1950). The `reservation`
   column only carries what the Order prints next to the AC name (`SC`/`ST`/blank).

4. **Puducherry's Mahe and Yanam are absent from the LGD district snapshot.**
   LGD lists only Karaikal (598) and Puducherry (600) for state code 34, so two
   AC rows cannot be reconciled. This is an **LGD gap**, not a parse failure.

5. **Delhi has no district attribution in the Order.** All 70 rows carry
   `mapping_confidence = no_district_in_source`. Delhi district attribution needs
   a separate source if the hierarchy must be complete.

6. **Two 1:N district splits cannot be resolved from the heading alone** —
   West Bengal `BARDHAMAN` (25 rows → Purba 306 / Paschim 704) and Meghalaya
   `JAINTIA HILLS` (7 rows → East 657 / West 275). These need per-AC review
   against the extent, not a heading-level guess.

7. **Manipur's five 2008 district headings no longer exist.** Manipur has since
   been reorganised into 16 districts; the 60 rows cannot be attributed 1:1.
   Manipur is unresolved on legal currency anyway.

8. **Reservation totals** across the 4,032 rows: 2,906 general, 596 SC, 530 ST.
   These will shift once Assam 2023 (SC 8→9) and J&K 2022 (9 ST seats, a first
   for J&K) are loaded.

9. **Naming differences confirmed.** The brief's seven required checks are all
   covered — `AURANGABAD → Chhatrapati Sambhajinagar` and
   `SANT RAVIDAS NAGAR → Bhadohi` as explicit aliases; `BARABANKI → Bara Banki`
   and `MAHARAJGANJ → Mahrajganj` as explicit aliases (LGD holds the shorter
   spellings); `KHERI`, `RAE BARELI` and `SIDDHARTHNAGAR` already match LGD
   exactly, so no alias is needed. Odisha needed 13 aliases — LGD uses Odia-form
   names throughout (`Cuttack → Kataka`, `Balasore → Baleshwar`, …), which the
   old ECI material does not.

---

## 5. Deliverables

| Path | What |
|---|---|
| `data/reference/source/eci_ac_normalised.csv` | 4,032 rows, UTF-8 with BOM, the Step 3 deliverable |
| `data/reference/source/eci_ac_2008_raw.csv` | parser output before normalisation, 4,120 rows incl. the excluded J&K annexure |
| `data/reference/source/eci_ac_validation.txt` | full machine validation report, all 10 checks |
| `docs/eci-ac-source-matrix.md` | per-State/UT source, status and the full alias table |
| `scripts/eci_ac/*.py` | the three-stage parser, re-runnable |

`data/reference/districts.csv` and `data/reference/constituencies.csv` are
untouched.

### CSV columns

`state_code` (TEXT, LGD State Code), `state_name_en`, `district_lgd_code` (TEXT,
LGD District Code, blank when unresolved), `district_name_en` (LGD canonical),
`ac_number`, `constituency`, `constituency_hindi` (always blank), `reservation`
(`SC`/`ST`/blank), `extent`, `source`, `source_version`, `mapping_confidence`,
`district_name_eci` (the ECI heading, kept for audit).

`mapping_confidence` values: `exact` (normalised exact match to the LGD English
name), `mapped` (explicit hand-reviewed alias), `needs_review` (no unambiguous
LGD successor), `no_district_in_source` (the Order gives no district — Delhi).

---

## 6. Exact next action for Step 4

**Do not load Andhra Pradesh yet.** Everything else in the CSV is loadable
subject to the usual identity decisions.

In order:

1. **Resolve AP numbering.** Confirm against an official Andhra Pradesh source
   (CEO Andhra Pradesh AC list, or the AP Reorganisation Act schedules) whether
   current AP AC numbers are `eci_ac_normalised.ac_number − 119`. If confirmed,
   renumber AP's 175 rows in the build script — not by hand — and re-run the
   validation. AP stays unresolved until then.
2. **Decide the identity policy for the 9 existing Lucknow AC rows and the 8
   voters that reference them**, before any write. `voters.assembly_constituency_id`
   is half the voters PK with no FK; the existing voter references must be
   preserved. This is the blocking decision for Step 4, not a data question.
3. **Reconcile the existing 75-district UP baseline Hindi** into the district
   layer, then decide the Hindi source for AC names. The 2008 Order provides
   none; `constituency_hindi` stays blank until an authoritative bilingual source
   is found. Do not transliterate.
4. **Load in three tiers**, keeping the unresolved set visibly separate:
   VERIFIED (25 States/UTs), UNRESOLVED-but-present (Assam, Arunachal, Nagaland,
   Manipur, and AP after step 1), and ABSENT (J&K 90 ACs, Sikkim Sangha).
5. **Leave the 94 `needs_review` and 70 `no_district_in_source` rows with a null
   district** rather than guessing. They are 4% of the dataset and none of them
   is in the UP/Lucknow path the app currently exercises.

Deferred, not blocking: obtaining the Assam 2023 and J&K 2022 orders. Both are
published as gazette notifications; the ECI web front end is JavaScript-rendered
and served nothing to an automated fetch. The e-Gazette archive or the
respective CEO offices are the next avenue.
