# PRAMAAN Reference Data Research — State/UT → District → Assembly Constituency

**Status:** Research and validation only. No database models, APIs, migrations, seeders, or production data
have been changed. No dataset has been generated yet.

**Date of research:** 11 September 2026
**Scope:** Establish authoritative sources, verify structure and counts, and design the CSV schemas for an
India-wide geographic reference dataset for the Voter List filter hierarchy.

**Reading note.** Every numeric claim below is tagged:

| Tag | Meaning |
|---|---|
| ✅ **VERIFIED** | Extracted directly from the primary source document during this research, and shown here with the method used |
| 🟡 **REPORTED** | Stated by an official or reputable secondary source but not yet confirmed against a primary document |
| ❌ **NOT ESTABLISHED** | Could not be confirmed. Must be acquired before implementation. **Never to be filled in by guessing.** |

Nothing in this document was fabricated. Where a figure could not be confirmed it is marked ❌ rather than
estimated.

---

## 1. Sources used

### Primary sources

| # | Source | URL | Used for | Retrieved |
|---|---|---|---|---|
| S1 | **iGOD** — Integrated Government Online Directory, NIC | https://igod.gov.in/index.php/sg/district/states | State/UT canonical list | ✅ Retrieved successfully |
| S2 | **Delimitation of Parliamentary and Assembly Constituencies Order, 2008** (English), ECI | https://www.eci.gov.in/Documents/Delimitation/DelimitationofParliamentaryAssemblyConstituenciesOrder-2008(English).pdf | AC numbers, AC names, SC/ST reservation, **district↔AC mapping**, per-state seat allocation | ✅ Retrieved and parsed (572 pages, 1.34 MB) |
| S3 | **LGD** — Local Government Directory, Ministry of Panchayati Raj | https://lgdirectory.gov.in/ | District list, stable codes, local-language names | ✅ Retrieved (landing page + report inventory) |
| S4 | **ECI / PIB** — J&K Delimitation Commission final order, 2022 | https://www.pib.gov.in/PressReleasePage.aspx?PRID=1822939 | J&K's 90 ACs | ✅ Retrieved |
| S5 | **ECI / PIB** — Assam final delimitation order, 11 Aug 2023 | https://www.pib.gov.in/PressReleaseIframePage.aspx?PRID=1947865 | Assam's 126 ACs and 19 renamed ACs | ✅ Retrieved |

### Sources attempted that did not yield data

| Source | URL | Outcome |
|---|---|---|
| ECI Delimitation landing page | https://www.eci.gov.in/delimitation | ❌ JavaScript-rendered; returned only the page title, no document list |
| ECI Publications landing page | https://www.eci.gov.in/eci-publication | ❌ JavaScript-rendered; no publication list retrievable |
| iGOD per-state district pages | `igod.gov.in/.../sg/UP/district/states` and variants | ❌ HTTP 404 — the URL pattern for district listings was not discovered |
| data.gov.in LGD States resource | https://www.data.gov.in/resource/local-government-directory-lgd-states | ❌ HTTP 403 Forbidden to automated fetch |

**Consequence:** the ECI site's own document indexes are not machine-readable without a browser. Documents
must be reached by direct PDF URL (as with S2) or downloaded manually. This is an operational constraint on
how the dataset gets assembled, and is carried into §13.

### Secondary sources (cross-check only — never authoritative)

Used solely to corroborate figures already obtained from primary sources: PRS India, Internet Archive's copy
of the 2008 Order, India Code, and press reporting on the J&K and Assam orders. **No GitHub repository was
used as a source of record.** Machine-readable GitHub datasets may later be used to *bootstrap* typing effort,
but every row must be diffed against S2/S3 before acceptance (see §13, Step 4).

---

## 2. Why each source is authoritative

**iGOD (S1)** is the Government of India's official directory of government entities, maintained by NIC. It is
authoritative for *"what administrative units exist and what are they called"* at the State/UT level. It is a
directory, not a statute — so it is correct for names and existence, but it carries no electoral meaning.

**The 2008 Delimitation Order (S2)** is a statutory instrument made under the Delimitation Act, 2002. It is not
a report or a dataset — it is **the law that defines the constituencies themselves**. For AC number, AC name,
reservation status and territorial extent, nothing else outranks it. This is the correct source of record for
PRAMAAN's constituency table.

**LGD (S3)** is the Government of India's mandated standard location-code directory. Adoption of LGD codes as
the standard location code across all Ministries/Departments/States was **mandated by the Cabinet Secretariat
by letter dated 4 November 2016** (🟡 REPORTED, per S3 and MoHUA documentation). LGD is maintained jointly with
the Office of the Registrar General of India. It is therefore the correct authority for *district identity and
stable district/state codes* — and importantly, it is kept current as districts are created and renamed, which
the 2008 Order is not.

**The J&K (S4) and Assam (S5) orders** are later statutory instruments that **supersede** S2 for those two
territories. Using S2 alone for J&K or Assam would encode legally obsolete constituencies into a production
electoral application.

### The division of authority PRAMAAN should adopt

```
State/UT identity + name   →  iGOD (S1), codes from LGD (S3)
District identity + name   →  LGD (S3)          ← current, maintained
AC number/name/reservation →  ECI Orders (S2 + S4 + S5)   ← statutory
AC → District mapping      →  ECI Orders (S2 + S4 + S5), reconciled onto LGD districts
```

The reconciliation arrow in the last line is the hard part of this project. See §5 and §12.

---

## 3. Current State/UT list

✅ **VERIFIED — 36 entries**, retrieved from iGOD (S1), alphabetical, exactly as spelled by the source:

| # | Name (iGOD spelling) | Type | Legislative Assembly? |
|---|---|---|---|
| 1 | Andaman and Nicobar Islands | UT | **No** |
| 2 | Andhra Pradesh | State | Yes |
| 3 | Arunachal Pradesh | State | Yes |
| 4 | Assam | State | Yes |
| 5 | Bihar | State | Yes |
| 6 | Chandigarh | UT | **No** |
| 7 | Chhattisgarh | State | Yes |
| 8 | Dadra and Nagar Haveli and Daman and Diu | UT | **No** |
| 9 | Delhi | UT (NCT) | Yes |
| 10 | Goa | State | Yes |
| 11 | Gujarat | State | Yes |
| 12 | Haryana | State | Yes |
| 13 | Himachal Pradesh | State | Yes |
| 14 | Jammu and Kashmir | UT | Yes |
| 15 | Jharkhand | State | Yes |
| 16 | Karnataka | State | Yes |
| 17 | Kerala | State | Yes |
| 18 | Ladakh | UT | **No** |
| 19 | Lakshadweep | UT | **No** |
| 20 | Madhya Pradesh | State | Yes |
| 21 | Maharashtra | State | Yes |
| 22 | Manipur | State | Yes |
| 23 | Meghalaya | State | Yes |
| 24 | Mizoram | State | Yes |
| 25 | Nagaland | State | Yes |
| 26 | Odisha | State | Yes |
| 27 | Puducherry | UT | Yes |
| 28 | Punjab | State | Yes |
| 29 | Rajasthan | State | Yes |
| 30 | Sikkim | State | Yes |
| 31 | Tamil Nadu | State | Yes |
| 32 | Telangana | State | Yes |
| 33 | Tripura | State | Yes |
| 34 | Uttar Pradesh | State | Yes |
| 35 | Uttarakhand | State | Yes |
| 36 | West Bengal | State | Yes |

**28 States + 8 UTs = 36.** ✅ Independently corroborated by LGD (S3), which also reports 36 States/UTs.

**Assembly-bearing entities: 31** — 28 States + Delhi + Puducherry + Jammu & Kashmir.
**Entities with NO Assembly Constituencies: 5** — Andaman & Nicobar Islands, Chandigarh,
Dadra & Nagar Haveli and Daman & Diu, Ladakh, Lakshadweep.

### ⚠️ Name drift between iGOD (2026) and the 2008 Order

✅ **VERIFIED** by reading Schedule I and Schedule II of S2 directly. The 2008 Order pre-dates several
reorganisations and **uses names and entities that no longer exist**:

| 2008 Order says | Reality in 2026 | Cause |
|---|---|---|
| `Orissa` | `Odisha` | Renamed 2011 |
| `Andhra Pradesh` (294 ACs, undivided) | `Andhra Pradesh` (175) + `Telangana` (119) | Telangana formed 2014 |
| `Dadra and Nagar Haveli` and `Daman and Diu` as **two separate UTs** | One merged UT | Merged 2020 |
| `Jammu and Kashmir` as a **State** (76/87 seats) | UT of J&K (90 ACs) + UT of Ladakh (0 ACs) | Reorganisation 2019 |
| No `Ladakh` | Ladakh exists | Created 2019 |
| No `Telangana` | Telangana exists | Created 2014 |

✅ **VERIFIED arithmetic:** 175 (AP) + 119 (Telangana) = **294** = the 2008 Order's undivided Andhra Pradesh
figure. The Telangana split reassigned existing ACs rather than creating new ones. This is a useful validation
hook and is reused in §8.

**This is the single most important finding in this document.** Any pipeline that reads the 2008 Order and
writes state names verbatim will produce a dataset containing "Orissa", no Telangana, and a State of Jammu &
Kashmir. For a production electoral application this would be a serious data-integrity defect.

---

## 4. District source methodology

### Recommended source: LGD (S3), not the 2008 Order

🟡 **REPORTED** by LGD's own landing page: **36 States/UTs, 784 Districts**, 7,092 sub-districts, 7,323 blocks,
677,527 villages. LGD assigns every unit a unique LGD code and supports local-language names.

### Why not take districts from the 2008 Order

✅ **VERIFIED by parsing S2:** the Order contains **528–540 `DISTRICT :` headers** (count varies by ±12 with
regex tolerance for the Order's inconsistent punctuation — see §8 for why both numbers appear).

Against LGD's 784 current districts, that is a shortfall of roughly **250 districts**. The 2008 Order reflects
the district map as it stood around the 2001 Census. Since then states have created, merged, split and renamed
districts extensively.

> **Methodology decision: districts come from LGD. The 2008 Order is used only to establish which
> constituency belongs to which district *as the Order defines it*, and that mapping is then reconciled
> forward onto the current LGD district list.**

### District-count volatility — a live risk

🟡 **REPORTED, and sources disagree:** LGD states 784; other current references report ~800–802. The
discrepancy is real and expected, because the district count changes continuously. A documented example:
**Rajasthan reduced its districts from 50 to 41 in December 2024**, when 9 newly created districts and 3
divisions were cancelled.

**Implication for PRAMAAN:** the district table is not a write-once dataset. It needs a refresh procedure and a
recorded `source_version`/snapshot date. A voter record captured under a district that later ceases to exist
must remain readable. This is a schema requirement, not just an ops concern — see §6 and §12.

### Hindi district names

❌ **NOT ESTABLISHED.** LGD advertises local-language name capability (S3 explicitly references updating names
in local language), but I did **not** retrieve an actual bilingual district export during this research. The
`data.gov.in` LGD resource returned HTTP 403 to automated fetch.

**Before implementation, someone must open LGD's "Download Directory" / report section in a browser and confirm
whether a Hindi (or local-language) name column is actually populated for districts, and for which states.**
Do not assume it is. See §11.

---

## 5. Assembly Constituency source methodology

### The 2008 Order is machine-extractable — verified, not assumed

I downloaded S2 and parsed it with a standalone, dependency-free script (zlib inflate of the PDF's FlateDecode
streams, then extraction of PDF text-showing operators). No library was installed into the project venv and no
project file was touched; the script lives only in the session scratchpad.

✅ **VERIFIED extraction results:**

| Metric | Value |
|---|---|
| Pages | 572 |
| Text characters recovered | 1,013,264 |
| `DISTRICT :` headers | 528–540 (regex-variant dependent) |
| `(SC)` markers | 1,298 |
| `(ST)` markers | 1,026 |
| Devanagari characters | **0** |

### ✅ The structure — a real example from the Order

This is verbatim extracted text from the Uttar Pradesh schedule of S2:

```
XXVIII UTTAR PRADESH    PART A - ASSEMBLY CONSTITUENCIES
Sl. No. & Name          Extent of Assembly Constituencies

1  DISTRICT : SAHARANPUR
  1 Behat                1-Behat Tehsil.
  2 Nakur                KCs 1-Nakur, 3-Sarsawa, 4-Sultanpur, Sarsawa NPP, Nakur NPP
                         and Chilkana Sultanpur NP of 3-Nakur-Tehsil.
  3 Saharanpur Nagar     Saharanpur NPP.
  6 Rampur Maniharan (SC) KCs 3-Nagal, 5-Rampur & Rampur Maniharan NP of 4-Deoband
                         Tehsil; PCs 4-Landhora Gujjar, ... of 1-Saharanpur KC of
                         2-Saharanpur Tehsil.
```

Every field PRAMAAN needs is present and structured:

- **AC number** — the serial number (`1`, `2`, `3`, `6`)
- **AC English name** — `Behat`, `Nakur`, `Saharanpur Nagar`
- **Reservation** — the `(SC)` / `(ST)` suffix on the name
- **District** — the `DISTRICT : SAHARANPUR` group header
- **Extent** — tehsils, Kanungo Circles (KC), Patwar Circles (PC), Nagar Palika Parishads (NPP), Nagar
  Panchayats (NP)

### ⚠️ Parsing caveats — verified, and they matter

The Order is **not** formatted consistently. Observed variants in the extracted text:

- `1 – DISTRICT : SAHARANPUR` (en-dash, spaced colon)
- `7 - DISTRICT: SOUTH GARO HILLS` (hyphen, unspaced colon)
- `PART A - ASSEMBLY CONSTITUENCIES` (most states) vs `TABLE A - ASSEMBLY CONSTITUENCIES` (Goa)
- State headings appear both as `XXVIII UTTAR PRADESH` and as `SCHEDULE - VIII GOA`

**Honest limitation:** my state-section detector matched only **16 of the ~32** state schedules because of these
variants. Consequently the per-state district counts my script produced were unreliable (it attributed 45
districts to Punjab and 50 to Uttarakhand — both obviously wrong, caused by bleed into the following section).
**Those numbers are therefore NOT reported as findings anywhere in this document.** A production parser must
handle every heading variant and be validated per state against Schedule II. This is called out in §13, Step 3.

### States/UTs where the 2008 Order is NOT current

🟡 **REPORTED** (from S4, S5 and corroborating press/PIB material):

| Territory | Status | What to use |
|---|---|---|
| **Jammu & Kashmir** | 2008 Order superseded. J&K Delimitation Commission (Justice Ranjana Prakash Desai) signed its final order 5 May 2022; the 14 Mar and 5 May orders took effect **20 May 2022**. **90 ACs** — 43 Jammu, 47 Kashmir. 9 ST-reserved seats for the first time in J&K's history. | **J&K Delimitation Commission Order, 2022** |
| **Assam** | 2008 Order superseded. ECI published the final delimitation order **11 August 2023**. **126 ACs retained**, 14 LS seats. SC seats 8→9; 19 ACs ST-reserved. **19 AC names were revised.** | **ECI Assam Delimitation Order, 2023** |
| **Arunachal Pradesh** | ❌ Excluded from the 2008 Order under s.10A of the Delimitation Act, 2002 (deferred 8 Feb 2008, rescinded 2020). Delimitation **reported as "under process"**, not complete. | ❌ **NOT ESTABLISHED** — current legal basis must be confirmed |
| **Nagaland** | ❌ Same exclusion; **"under process"**. Supreme Court has pressed the Centre on the delay. | ❌ **NOT ESTABLISHED** |
| **Manipur** | ❌ Same exclusion; **"nothing has started"**. 16 political parties have sought deferral to 2026. Seat count unchanged since the 1971 Census. | ❌ **NOT ESTABLISHED** |

**Critical:** five states — J&K, Assam, Arunachal Pradesh, Nagaland, Manipur — were **exempted** from the 2008
delimitation. Two have since been redone (J&K 2022, Assam 2023). **Three have not.** For Arunachal, Nagaland
and Manipur the constituencies in force still rest on 1970s-era delimitation, and the 2008 Order's schedules
for them must be treated as **unconfirmed** until the current legal instrument is identified.

⚠️ Note also the 84th Constitutional Amendment freeze on seat totals until after 2026. A nationwide
delimitation is anticipated. **The dataset PRAMAAN builds now has a foreseeable expiry.** Schema must tolerate
versioning (§6).

---

## 6. Special cases and exceptions

| Territory | Finding | Source | Action |
|---|---|---|---|
| **Jammu & Kashmir** | 90 ACs (43 Jammu / 47 Kashmir), effective 20 May 2022. S2 carries J&K only as an *Annexure* (pages 561–571, "Assembly Constituencies only") reflecting the **pre-2019 State** — ✅ verified present in S2's table of contents. | S4, S2 | **Use the 2022 order. Ignore S2's J&K annexure entirely.** |
| **Ladakh** | UT **without** legislature. **0 ACs.** Did not exist in 2008. | S1, 🟡 | Load as a State/UT with zero constituencies |
| **Assam** | 126 ACs; 19 AC **names revised** in 2023 | S5 | **Use the 2023 order.** Names from S2 are stale |
| **Delhi** | UT **with** legislature. ✅ **VERIFIED 70 ACs** from S2 Schedule II | S2 | S2 usable |
| **Puducherry** | UT **with** legislature. ✅ **VERIFIED 30 ACs** from S2 Schedule II. Note: geographically non-contiguous (Puducherry, Karaikal, Mahe, Yanam — enclaves inside TN, Kerala, AP) | S2 | S2 usable. Expect unusual district structure |
| **Andaman & Nicobar Islands** | No legislature. **0 ACs** | S1, 🟡 | Zero constituencies |
| **Chandigarh** | No legislature. **0 ACs** | S1, 🟡 | Zero constituencies |
| **Dadra & Nagar Haveli and Daman & Diu** | No legislature. **0 ACs.** Exists in S2 as **two separate UTs** — merged in 2020 | S1, S2 ✅ | Zero constituencies; **one** row, not two |
| **Lakshadweep** | No legislature. **0 ACs.** 🟡 Single district | S1, 🟡 | Zero constituencies |
| **Telangana** | Did not exist in 2008. 🟡 119 ACs, carved from undivided AP's 294. ✅ Arithmetic verified: 175 + 119 = 294 | derived | **Must be split out manually from S2's AP schedule** |
| **Sikkim** | ✅ **VERIFIED 32 ACs** from S2, with a footnote: 1 seat reserved for Sanghas, 2 for SC, 12 for Sikkimese of Bhutia-Lepcha origin (s.7(1A), RPA 1950) | S2 | **Reservation categories exceed plain SC/ST.** See §7 |
| **Arunachal / Nagaland / Manipur** | ❌ Delimitation incomplete | — | **Flag as unverified. Do not silently load 2008 data as current** |

---

## 7. Recommended CSV schemas

Location: `data/reference/`. All files **UTF-8 with BOM** (`utf-8-sig`) so Excel opens Devanagari correctly —
this matches the existing seeder, which already reads `utf-8-sig`.

### `data/reference/states.csv`

```csv
state_code,state_name_en,state_name_hi,has_assembly,source,source_version
```

| Column | Required | Why |
|---|---|---|
| `state_code` | ✅ | Stable join key used by both child files. **Must be copied from LGD/iGOD — never invented.** See §10 |
| `state_name_en` | ✅ | Display name for the Flutter filter; human-readable join key |
| `state_name_hi` | ⚠️ | Existing bilingual pattern. **May be empty for non-Hindi states** — see §11 |
| `has_assembly` | ✅ **added** | Distinguishes "this UT has zero ACs" from "we haven't loaded its ACs yet". Without it, Ladakh and Chandigarh are indistinguishable from an incomplete import. This is a correctness flag, not a convenience |
| `source` | ✅ **added** | e.g. `iGOD`, `LGD`. Provenance is mandatory in an electoral application |
| `source_version` | ✅ **added** | Retrieval date. Districts and ACs both change; without this, nobody can tell how stale a row is |

### `data/reference/districts.csv`

```csv
state_code,district_name_en,district_name_hi,lgd_district_code,source,source_version
```

| Column | Required | Why |
|---|---|---|
| `state_code` | ✅ | Parent link. **Also the disambiguator** — see §9 |
| `district_name_en` | ✅ | Display + natural key *within a state* |
| `district_name_hi` | ⚠️ | Bilingual. May be empty — §11 |
| `lgd_district_code` | ✅ **added** | The government's own stable identifier. Survives renames; the single most valuable column for future refreshes. §10 |
| `source`, `source_version` | ✅ **added** | As above. Rajasthan's 50→41 reversal shows why |

### `data/reference/constituencies.csv`

```csv
state_code,district_name_en,ac_number,constituency,constituency_hindi,reservation,mapping_confidence,source,source_version
```

| Column | Required | Why |
|---|---|---|
| `state_code` | ✅ | Disambiguates duplicate district names (Aurangabad, Bilaspur, Hamirpur — §9) |
| `district_name_en` | ✅ | Parent link, resolved to `district_id` by the seeder |
| `ac_number` | ✅ | The **official AC number within the state**, printed on every voter roll. `(state_code, ac_number)` is the real-world natural key and the basis for the recommended stable identifier (§10) |
| `constituency` | ✅ | English name — display |
| `constituency_hindi` | ⚠️ | **This is the column the OCR pipeline fuzzy-matches against** (`resolve_constituency`) and that `POST /voter/save` looks up. Functionally load-bearing, not cosmetic. §11 |
| `reservation` | ✅ **added** | `GEN` / `SC` / `ST` — ✅ verified present in S2 as `(SC)`/`(ST)` suffixes. It is free to capture at parse time and expensive to backfill later. **Sikkim needs extra values** (`BL` for Bhutia-Lepcha, `SANGHA`) per S2's footnote |
| `mapping_confidence` | ✅ **added** | `confirmed` / `needs_review`. **The most important governance column in the dataset.** The brief says: if a mapping cannot be established confidently, mark it — do not guess. This column is that mark. §9 |
| `source`, `source_version` | ✅ **added** | Distinguishes rows from the 2008 Order vs the J&K 2022 order vs the Assam 2023 order. Without it there is no way to audit which law a row came from |

**Deliberately NOT included:**

- `district_id` / `state_id` in child files — names + `state_code` are resolved by the seeder; that is the
  existing design and it works.
- The AC's full `extent` text — hundreds of words per AC (tehsils, KCs, PCs). Valuable for provenance but not
  needed by the Flutter filter. **Recommend retaining it in a separate `constituencies_extent.csv`** so the
  district mapping stays auditable without bloating the table the API serves.
- Any geometry/boundary data — out of scope.

---

## 8. Validation and count results

### ✅ VERIFIED — extracted directly from Schedule II of the 2008 Order (S2)

Assembly seats, post-2008 column:

| State | ACs | State | ACs |
|---|---|---|---|
| Andhra Pradesh (undivided) | 294 | Nagaland | 60 |
| Arunachal Pradesh | 60 | Orissa *(now Odisha)* | 147 |
| Assam | 126 | Punjab | 117 |
| Bihar | 243 | Rajasthan | 200 |
| Chhattisgarh | 90 | Sikkim | 32 |
| Goa | 40 | Tamil Nadu | 234 |
| Gujarat | 182 | Tripura | 60 |
| Haryana | 90 | Uttarakhand | 70 |
| Himachal Pradesh | 68 | Uttar Pradesh | 403 |
| Jharkhand | 81 | West Bengal | 294 |
| Karnataka | 224 | **UT: Delhi** | **70** |
| Kerala | 140 | **UT: Puducherry** | **30** |
| Madhya Pradesh | 230 | | |
| Maharashtra | 288 | | |
| Manipur | 60 | | |
| Meghalaya | 60 | | |
| Mizoram | 40 | | |

J&K appears in Schedule II as `76` with an asterisk; the footnote records 87 seats excluding 24 earmarked for
Pakistan-occupied territory. ✅ Verified verbatim. **Superseded by the 2022 order (90).**

### ✅ VERIFIED — national total reconciliation

Computed from the transcribed Schedule II figures:

```
2008 Order — 27 states (J&K excluded from Sched II) .... 3,933
2008 Order — UTs with legislature (Delhi 70 + Puducherry 30) ... 100
                                                     subtotal   4,033
+ Jammu & Kashmir per the 2022 Delimitation Commission order ...   90
                                                        TOTAL   4,123
```

**4,123 — MATCHES** the widely cited national total. Two independent cross-checks therefore pass:

1. **National total:** 3,933 + 100 + 90 = 4,123 ✅
2. **Telangana split:** 175 + 119 = 294 = the Order's undivided Andhra Pradesh ✅

This gives high confidence that Schedule II was transcribed correctly and that the J&K figure integrates
consistently. **It does not validate individual AC rows** — only the totals.

### Validation report against the brief's checklist

| Required metric | Result |
|---|---|
| Total State/UT count | ✅ **36** (28 States + 8 UTs) — iGOD, corroborated by LGD |
| Total District count | 🟡 **784** per LGD; other sources report ~800–802. **Sources disagree — must be pinned to one snapshot** |
| Total AC count | ✅ **4,123**, reconciled as above |
| AC count by State/UT | ✅ Available for 29 entities from Schedule II (above); ✅ J&K 90; 🟡 Telangana 119 / AP 175 needs manual split; ❌ Arunachal/Nagaland/Manipur legally unconfirmed |
| District count by State/UT | ❌ **NOT ESTABLISHED.** My parse was unreliable (16/32 state sections matched). Must come from LGD, not from my extraction |
| Duplicate district names | ✅ **CONFIRMED** — see §9 |
| Duplicate constituency names | ❌ Not yet computed — requires the full parsed AC list |
| Missing Hindi names | ❌ **100% missing from S2** — ✅ verified: **zero Devanagari characters** in the English Order |
| Missing state codes | ❌ Code values not yet retrieved from LGD/iGOD |
| Missing district mappings | 🟡 ~33 cross-district extents identified as candidates — see §9 |
| Suspicious/inconsistent records | ✅ Identified: Orissa/Odisha, undivided AP, two-part DNH&DD, J&K-as-State, Sikkim's non-SC/ST reservations, inconsistent Order formatting |

---

## 9. Duplicate-name handling strategy

### ✅ VERIFIED duplicates — found in the primary source, not hypothesised

Parsing the 2008 Order's district headers and attributing them to their state schedules produced:

| District name | Appears in | Status |
|---|---|---|
| **AURANGABAD** | Bihar, Maharashtra | ✅ Genuine cross-state duplicate |
| **BILASPUR** | Chhattisgarh, Himachal Pradesh | ✅ Genuine cross-state duplicate |
| **HAMIRPUR** | Himachal Pradesh, Uttar Pradesh | ✅ Genuine cross-state duplicate |
| MUMBAI | Maharashtra (×2) | ⚠️ Artifact of name truncation — Mumbai City / Mumbai Suburban |

An initial run also flagged `NORTH` and `SOUTH` as duplicates. ⚠️ **That was a false positive** caused by a
40-character capture limit in my regex; the real names are `SOUTH GOA`, `SOUTH GARO HILLS`, `SOUTH TRIPURA`,
`SOUTH 24 PARGANAS` and Sikkim's bare `SOUTH`. It is recorded here because it demonstrates the failure mode
this dataset is most exposed to: **a truncation or normalisation bug silently merges two genuinely different
districts.** Sikkim's districts really are named `North`/`South`/`East`/`West`, which really do collide with
other states' directional district names — so the risk is real even though this particular hit was an artifact.

This list is **not exhaustive** — it reflects only what the 2008 Order's ~528 headers contain. Against LGD's
784 current districts there will be more. Pratapgarh (UP and Rajasthan) and Balrampur (UP and Chhattisgarh) are
well-known additional cases that must be checked once the LGD list is in hand.

### Strategy

1. **Never treat a district name as globally unique.** The uniqueness key is `(state_code, district_name_en)`.
2. **Never treat an AC name as globally unique.** The key is `(state_code, ac_number)` — §10.
3. **Every child CSV carries `state_code`**, even where it looks redundant. `constituencies.csv` carries both
   `state_code` and `district_name_en` precisely so "Aurangabad" resolves deterministically.
4. **Enforce in the database, not only in the loader.** Add scoped unique constraints
   (`UNIQUE(state_id, district_name_en)`, `UNIQUE(district_id, constituency)`). The live tables currently have
   **no unique constraints at all** beyond their primary keys, so the database cannot today defend itself
   against a duplicate or half-finished load.
5. **Unicode-normalise (NFC) before comparing** any name. Devanagari permits multiple encodings of the same
   visible word (precomposed क़ vs क + nukta). Two files from different sources can look identical and compare
   unequal. The existing seeder's `_norm()` handles case and whitespace but **not** Unicode normalisation.
6. **The existing seeder's duplicate rule must be inverted before any India-wide load.** It currently aborts
   the entire import on *any* repeated English district name, and on any repeated Hindi constituency name.
   Fed real India data it will hard-fail on Aurangabad. Its duplicate detection must become scoped to the
   parent rather than global.

### Cross-district ACs — the "do not guess" cases

✅ **VERIFIED:** ~**33** AC extent descriptions in S2 contain the phrase pattern `... of <X> district`,
referencing a district other than their own group header. Observed examples include extents naming Sheohar,
Sitamarhi (Bihar) and Patan, Jamnagar, Surendranagar, Amreli, Rajkot, Dahod (Gujarat).

These are ACs whose territory crosses an administrative boundary. **The current schema allows exactly one
district per AC and cannot represent them.**

**Handling — per the brief's explicit instruction not to guess:**

- Assign the AC to the district under whose `DISTRICT :` header the Order places it (this *is* the Order's own
  primary attribution — it is not a guess).
- Set `mapping_confidence = needs_review` on every such row.
- Record the full extent text in `constituencies_extent.csv` so a human can adjudicate.
- **Do not silently drop, merge, or re-parent these rows.**

~33 rows out of 4,123 is a reviewable manual workload, not a blocker.

---

## 10. Recommended stable identifiers

The current database assigns IDs from Postgres sequences. ✅ Verified live: `districts.district_id` currently
runs **79–153** for 75 rows and `constituency.id` runs **13–21** for 9 rows — values that are artifacts of an
earlier load that was deleted, carrying **no real-world meaning**. Reloading reference data would reassign
them.

That is dangerous here, because `voters.assembly_constituency_id` is **half the voters table's primary key and
has no foreign key constraint**. If a reload changes constituency IDs, existing voter rows silently point at
the wrong constituency — no error, no constraint violation, just wrong data.

### Recommendation

| Entity | Recommended stable identifier | Rationale |
|---|---|---|
| **State/UT** | **LGD state code**, carried in `state_code` | Government-mandated standard location code (Cabinet Secretariat, 4 Nov 2016). Stable across renames |
| **District** | **LGD district code**, stored in a new `lgd_district_code` column | Survives renames and reorganisations; the only identifier that makes future refreshes diffable |
| **Assembly Constituency** | **`(state_code, ac_number)`** | The AC number is defined by statute and printed on every voter roll. This is the natural key the real world already uses |

**Do not invent codes.** iGOD displays two-letter abbreviations (AP, BR, DL) and LGD issues numeric codes;
Census 2011 and ISO 3166-2:IN define further schemes. ❌ **Which scheme to adopt, and the actual code values,
are NOT ESTABLISHED by this research** — the values must be exported from LGD/iGOD, not typed from memory. This
is a decision item (§12) and a task (§13, Step 2).

**Recommended transitional rule:** keep the surrogate integer primary keys the application already uses, but
add the stable codes as unique columns alongside, and make the seeder match on the stable code. Reference data
can then be refreshed repeatedly without ever reassigning an ID that a voter row depends on.

---

## 11. Hindi-name strategy

### ✅ VERIFIED: the ECI English Order contains no Hindi at all

Devanagari character count across all 1,013,264 extracted characters of S2: **0**.

So `constituency_hindi` — the column the OCR pipeline actually fuzzy-matches against, and that
`POST /voter/save` looks up — **cannot be populated from the English 2008 Order.** It requires a separate
source.

### Status of each Hindi requirement

| Need | Status | Note |
|---|---|---|
| Hindi **state** names | ❌ NOT ESTABLISHED | Not on iGOD's listing page; LGD local-language support not yet confirmed for states |
| Hindi **district** names | ❌ NOT ESTABLISHED | LGD advertises local-language names; not verified. data.gov.in returned 403 |
| Hindi **AC** names | ❌ NOT ESTABLISHED | ECI publishes Hindi/bilingual delimitation orders, but I could not retrieve one — the ECI document indexes are JavaScript-rendered and were not machine-readable |

### Strategy

1. **Treat Hindi as optional per row, not mandatory per file.** ⚠️ The existing seeder currently makes
   `district_name_hi` and `constituency_hindi` **mandatory and aborts if empty**. That rule cannot survive
   India-wide data: Tamil Nadu, Kerala, Nagaland and others do not natively use Devanagari, and demanding a
   Hindi name for every AC would either abort the import or invite someone to invent transliterations. **For a
   production electoral application, an empty cell is correct and a fabricated name is not.**
2. **Prefer official Hindi where it exists**; leave blank where it does not. Record which in `source`.
3. **Never auto-transliterate into `constituency_hindi`.** If transliteration is ever used, it must live in a
   separate clearly-labelled column so it can never be mistaken for an official name. This is the highest
   fabrication risk in the whole project — the field is load-bearing for OCR matching, so a wrong value causes
   silent mis-classification of real voters.
4. **Hindi is not required for the Flutter filter.** The requirement states the filter displays English. Hindi
   matters for the OCR pipeline, which currently operates on Uttar Pradesh. **A pragmatic, defensible phasing:
   require Hindi only for the Hindi-belt states where OCR actually runs; leave it blank elsewhere until an
   official source is confirmed.** This is a decision for the team (§12).
5. **Apply NFC normalisation** to all Devanagari on load (§9, point 5).

---

## 12. Risks and unresolved questions

### Risks

| # | Risk | Severity | Detail |
|---|---|---|---|
| R1 | **Reload reassigns IDs and corrupts existing voters** | 🔴 **Critical** | `voters.assembly_constituency_id` is half the PK with **no FK**. 8 live voters point at IDs 14 and 16. A reload silently mis-links them. **Must be resolved before any `--apply` run** |
| R2 | **Stale names from the 2008 Order** | 🔴 **Critical** | Loading S2 verbatim yields "Orissa", no Telangana, J&K as a State, DNH and DD as two UTs |
| R3 | **Arunachal / Nagaland / Manipur legally unconfirmed** | 🔴 **Critical** | Delimitation incomplete. Loading 2008 data as current would present legally superseded constituencies in a live electoral app |
| R4 | **Fabricated Hindi names** | 🔴 **Critical** | `constituency_hindi` drives OCR matching. A transliterated guess causes silent voter mis-classification |
| R5 | **OCR constituency resolution degrades at scale** | 🟠 High | `resolve_constituency()` loads the **entire** constituency table per OCR job and fuzzy-matches at a 65% threshold, returning `(None, None)` when the top two scores tie. At 9 rows this works; at 4,123 rows with repeated Hindi AC names across states, ties become common and resolution will quietly start returning null. **Must be scoped by state/district before loading India-wide data** |
| R6 | **Parser mis-attribution from inconsistent formatting** | 🟠 High | ✅ Demonstrated: my own parse matched only 16/32 state sections and produced nonsense per-state counts. A production parser must be validated per state against Schedule II |
| R7 | **District list drifts** | 🟠 High | 784 vs ~800 across sources; Rajasthan 50→41 in Dec 2024. Needs a refresh procedure and snapshot versioning |
| R8 | **No unique constraints in the database** | 🟠 High | Live tables have only primary keys. A half-finished or repeated load cannot be detected by the database |
| R9 | **`create_all()` cannot alter existing tables** | 🟠 High | There is **no Alembic** in the project. Adding `state_id` to `districts` in the model without an `ALTER TABLE` breaks `/geo/districts`, `/geo/filters` and `/voter/save` with `UndefinedColumn` |
| R10 | **Nationwide delimitation expected after 2026** | 🟡 Medium | The 84th Amendment freeze lapses. This dataset has a foreseeable expiry — build for versioning |
| R11 | **ECI indexes not machine-readable** | 🟡 Medium | Both ECI landing pages are JS-rendered. Documents must be fetched by direct URL or downloaded by hand — this limits automated refresh |
| R12 | **`/geo/filters` returns everything unpaginated** | 🟡 Medium | Today ~84 objects; India-wide ~4,900 in one response |

### Unresolved questions — must be decided before the dataset is built

| # | Question |
|---|---|
| Q1 | **Which code scheme for `state_code`?** LGD numeric, iGOD 2-letter, Census 2011, or ISO 3166-2:IN? Values must be exported from the source, not typed |
| Q2 | **What happens to the 8 existing voters** whose `assembly_constituency_id` (14, 16) would be invalidated by a reload? Remap, delete as demo data, or pin IDs? **Blocks any `--apply`** |
| Q3 | **Hindi scope** — all 36 States/UTs, or only Hindi-belt states where OCR runs? |
| Q4 | **Arunachal, Nagaland, Manipur** — load 2008 data marked `needs_review`, or omit until the current order is identified? |
| Q5 | **Scope and phasing** — all-India at once, or UP first to validate duplicate handling on a small blast radius? |
| Q6 | **ACs spanning districts** (~33) — accept the Order's primary district attribution, or model a many-to-many? |
| Q7 | **Alembic, or hand-written `ALTER TABLE`?** This is the second time schema drift has hurt; the first fix was an untracked script that was lost |
| Q8 | **Does `/geo/filters` stay one bulk call**, or become a cascading API? Changes the Flutter contract |
| Q9 | **Is `mandal` still part of the hierarchy?** `districts.mandala_id` is NULL for all 75 rows and there is no mandal table — so the `mandal` role can never match a voter |
| Q10 | **Should a `state` role** exist alongside mandal/district/constituency/booth? |
| Q11 | **Reservation values for Sikkim** — plain `GEN/SC/ST` cannot express Bhutia-Lepcha and Sangha seats. Extend the vocabulary or leave blank? |

---

## 13. Exact next implementation steps

Ordered. **Steps 1–5 produce no code changes.**

**Step 0 — Preserve what exists (do first, today).**
`git push origin backup/ocr-pipeline-updates`. The existing seeder lives on a single **local, unpushed** branch
and exists nowhere else. Until it is on the remote, it is one disk failure from being lost — which already
happened once to the populated CSVs.

**Step 1 — Rescue the current UP data.**
Export the live 75 districts and 9 Lucknow constituencies to `data/reference/` in the new schema and **commit
them**. They were never gitignored — only never added. This makes today's working data reproducible for the
first time and gives the new pipeline a regression baseline.

**Step 2 — Acquire the authoritative lists (manual, browser).**
Download from LGD: the States/UTs report and the Districts report **with LGD codes**, and confirm whether a
local-language (Hindi) name column is actually populated. Record the retrieval date as `source_version`.
**Resolves Q1 and the §11 unknowns.**

**Step 3 — Build the AC parser as a standalone, throwaway research script.**
Parse S2 into `state, district, ac_number, ac_name, reservation, extent`. Handle **every** heading variant
(`DISTRICT :` / `DISTRICT:`, en-dash and hyphen, `PART A` and `TABLE A`, roman-numeral and `SCHEDULE - N`
headings). **Validate each state's parsed AC count against Schedule II — the per-state counts in §8 are the
acceptance test.** Do not proceed past any state that does not reconcile exactly.

**Step 4 — Apply the corrections the 2008 Order cannot know about.**
Rename Orissa→Odisha; split undivided AP into AP (175) + Telangana (119); drop S2's J&K annexure and substitute
the 2022 order's 90 ACs; replace Assam with the 2023 order (126 ACs, 19 renamed); merge DNH and DD into one UT;
add Ladakh with zero ACs; flag Arunachal/Nagaland/Manipur per Q4. Cross-check totals against §8: the national
figure must come back to **4,123**. GitHub datasets may be used here to *cross-check*, never to supply a value
S2 does not contain.

**Step 5 — Reconcile the Order's ~528 districts onto LGD's 784 and produce the validation report.**
Emit the full §8 checklist: counts, duplicates, missing Hindi, missing codes, unmapped ACs. Every AC that
cannot be confidently attributed gets `mapping_confidence = needs_review` and a human reviews it.
**No unresolved row is guessed.**

**Step 6 — Only now, begin backend changes** (separate task, not authorised by this document):
`State` model and `districts.state_id`; scoped unique constraints; FK from `voters.assembly_constituency_id`;
Alembic or a reviewed `ALTER TABLE` (Q7); extend the seeder to three levels with scoped duplicate rules and NFC
normalisation; `GET /geo/states`, `state_id` on `/geo/districts`, `states` in `/geo/filters`, plus pagination;
scope and cache `resolve_constituency` (R5); derive `state_id` server-side in `create_voter_api`.

---

## Appendix — reproducing the extraction

The 2008 Order was parsed with a dependency-free script (zlib inflate of FlateDecode streams + extraction of
PDF text operators). **No package was installed into the project venv and no repository file was modified.**
The script and extracted text live only in the session scratchpad:

```
<scratchpad>/pdftext.py     PDF → text
<scratchpad>/analyse.py     district headers, reservation markers, cross-district extents
<scratchpad>/analyse3.py    duplicate district names by state section
<scratchpad>/counts.py      Schedule II totals reconciliation
<scratchpad>/delim2008.txt  1,013,264 characters of extracted text
```

Verified outputs: 572 pages · 1,013,264 characters · 528–540 `DISTRICT :` headers · 1,298 `(SC)` ·
1,026 `(ST)` · **0 Devanagari characters** · ~33 cross-district extent references ·
3,933 + 100 + 90 = **4,123**.
