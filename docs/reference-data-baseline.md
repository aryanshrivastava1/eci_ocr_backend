# PRAMAAN Reference Data Baseline

Snapshot of the **current working reference data**, taken before the India-wide
State → District → Assembly Constituency system is introduced.

This is a preservation step. Nothing was changed: no models, no APIs, no migrations, no seeder, and no
database rows. See [Safety verification](#safety-verification).

Companion document: [reference-data-research.md](reference-data-research.md).

---

## Export date

**2026-09-11**

Recorded in the `source_version` column of every exported row.

---

## Database source

| Item | Value |
|---|---|
| Engine | PostgreSQL (Supabase, `aws-0-ap-south-1.pooler.supabase.com:5432/postgres`) |
| Connection | `DATABASE_URL` from `.env`, read via `python-dotenv`; same URL the app uses in `app/db/session.py` |
| Tables **read** | `districts`, `constituency` (full row export); `voters` (row **count and checksum only** — never selected into the export, never written) |
| Access mode | `SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY`, verified as `on` before any query ran |

The read-only mode was asserted and confirmed by the export script before it issued a single `SELECT`. Had the
setting failed to apply, the script was written to abort rather than continue.

### Source tables as they exist today

```
districts
  district_id       integer  PK, auto-increment (nextval)
  district_name_en  varchar  nullable
  district_name_hi  varchar  nullable
  mandala_id        integer  nullable

constituency
  id                  integer  PK, auto-increment (nextval)
  "Constituency"      varchar  NOT NULL   -> model attr `constituency`
  "District"          varchar  NOT NULL   -> model attr `district`      (denormalised text)
  "Constituency_Hindi" varchar NOT NULL   -> model attr `constituency_hindi`
  district_id         integer  nullable, FK -> districts.district_id
```

`Constituency` references `District` **twice**: through the real foreign key `district_id`, and through the
duplicated NOT NULL text column `"District"`. The export uses the **foreign key** as the authoritative link
(`LEFT JOIN districts ON district_id`); the text column was checked for agreement and matched on all 9 rows.

Models: [app/models/districts.py](../app/models/districts.py), [app/models/constituency.py](../app/models/constituency.py).
Connection: [app/db/session.py](../app/db/session.py).

---

## Exported records

| Table | Expected | **Actual (verified from DB)** | Exported |
|---|---|---|---|
| Districts | 75 | **75** ✅ | 75 |
| Constituencies | 9 | **9** ✅ | 9 |
| Voters | 8 | **8** ✅ | **0 — not exported, not touched** |

Counts were read from the database, not assumed. All three matched expectation exactly.

### Files created

| File | Rows | Encoding |
|---|---|---|
| `data/reference/districts.csv` | 75 + header | UTF-8 **with BOM** (`utf-8-sig`) |
| `data/reference/constituencies.csv` | 9 + header | UTF-8 **with BOM** (`utf-8-sig`) |

BOM presence was verified byte-level (`ef bb bf`). Both files re-parse cleanly with `utf-8-sig` and the first
header field reads as `state_code` (i.e. no BOM contamination of the header name).

---

## ⚠️ Schema note — deviation from the task brief

The task specified this header for `districts.csv`:

```
state_code,state_name_en,state_name_hi,lgd_district_code,source,source_version
```

That is the **states** schema from the research document. It contains `state_name_en` / `state_name_hi` but no
district-name columns, while the same task requires *"preserve the current database's English and Hindi
district names exactly as stored."* Under the literal header there is nowhere to put them, so the two
instructions cannot both be satisfied.

**Resolution applied:** the districts schema from
[reference-data-research.md §7](reference-data-research.md) was used instead —

```
state_code,district_name_en,district_name_hi,lgd_district_code,source,source_version
```

— which is the only reading that preserves the district names as instructed. `constituencies.csv` uses the
brief's header **verbatim, unchanged**.

---

## Field mapping

### `data/reference/districts.csv`

| Field | Source | Direct from DB? | Notes |
|---|---|---|---|
| `state_code` | — | ❌ | **BLANK.** No state data of any kind exists in this database — the `districts` table has no `state_id` or state name column, and there is no `states` table. The code scheme itself (LGD vs iGOD vs Census vs ISO) is still an open decision. **Not invented.** |
| `district_name_en` | `districts.district_name_en` | ✅ | **Verbatim.** No trimming, casing, or normalisation |
| `district_name_hi` | `districts.district_name_hi` | ✅ | **Verbatim.** Devanagari preserved; round-trip verified against the DB |
| `lgd_district_code` | — | ❌ | **BLANK.** The authoritative LGD export has not been acquired yet (research doc, Step 2). **Not invented.** |
| `source` | this export | ✅ | Constant `pramaan-db-baseline` — factual provenance of the row, not a data value |
| `source_version` | this export | ✅ | Constant `2026-09-11` — the export date |

### `data/reference/constituencies.csv`

| Field | Source | Direct from DB? | Notes |
|---|---|---|---|
| `state_code` | — | ❌ | **BLANK.** Same reason as above |
| `district_name_en` | `districts.district_name_en` via FK `constituency.district_id` | ✅ | Resolved through the foreign key. All 9 rows resolved; value is `Lucknow` for every row |
| `ac_number` | — | ❌ | **BLANK.** The database has no AC-number column. `constituency.id` is a Postgres sequence surrogate (current range 13–21) and is **not** an official AC number — writing it here would fabricate electoral data. Official numbers come from the ECI delimitation orders. **Not invented.** |
| `constituency` | `constituency."Constituency"` | ✅ | **Verbatim** English name |
| `constituency_hindi` | `constituency."Constituency_Hindi"` | ✅ | **Verbatim** Hindi name; round-trip verified |
| `reservation` | — | ❌ | **BLANK.** No reservation column exists in the database. GEN/SC/ST status is defined by the ECI orders. **Not invented.** |
| `mapping_confidence` | — | ❌ | **BLANK.** The provenance of these 9 rows is unknown — they were loaded by a seeder run whose input CSVs were never committed and are now lost. Their district mapping cannot be asserted as `confirmed` against any authoritative source, and marking them `needs_review` would equally be an unverified claim. Left blank until reconciled against the ECI order. **Not invented.** |
| `source` | this export | ✅ | Constant `pramaan-db-baseline` |
| `source_version` | this export | ✅ | Constant `2026-09-11` |

**Populated: 4 of 6** district fields, **5 of 9** constituency fields. Every blank is blank because the value
does not exist in this database and could only have been supplied by guessing.

---

## Existing data observations

Reported only. **Nothing was fixed, normalised, or cleaned during this step.**

### ✅ Clean

| Check | Result |
|---|---|
| NULL `district_name_en` | 0 of 75 |
| NULL `district_name_hi` | 0 of 75 |
| Duplicate district names (case-insensitive) | **none** |
| Duplicate constituency English names | **none** |
| Duplicate constituency Hindi names | **none** |
| Constituencies with an unresolved `district_id` FK (orphans) | **0 of 9** |
| `"District"` text column vs FK-resolved `district_name_en` | **agree on all 9 rows** |
| Duplicate rows in either exported CSV | **none** |

### ⚠️ Observations worth recording

**1. `mandala_id` is NULL for all 75 districts (75/75).**
There is no `mandals` table. The `mandal` role branch in `get_base_query`
([app/services/vote_service.py](../app/services/vote_service.py)) filters on `Voter.mandal_id`, which is
derived from `districts.mandala_id` at save time — so a `mandal`-role user can never match a single voter.
The column is not represented in the baseline CSV schema; **no data is lost, because there is no data.**

**2. Primary keys do not start at 1 and carry no real-world meaning.**
`district_id` runs **79–153** for 75 rows; `constituency.id` runs **13–21** for 9 rows. Both are Postgres
sequence artifacts left over from an earlier load that was deleted. They are not official codes.

**3. 🔴 The baseline CSVs cannot restore the current IDs.**
Neither requested schema has a column for `district_id` or `constituency.id`. This matters because
`voters.assembly_constituency_id` is **half the voters table's primary key and has no foreign key
constraint** — the 8 live voters point at constituency IDs **14** and **16**. Re-importing from these CSVs
would assign fresh sequence IDs and silently mis-link those voters, with no error raised.

**These files are therefore a faithful snapshot of the reference *data*, but not a restore point for the
reference *identifiers*.** Recommended follow-up: capture a separate raw ID snapshot (`district_id`,
`constituency.id`, and the voters' `assembly_constituency_id`) before any reload. Not created here — it is
outside the two files this step authorised.

**4. Coverage is Uttar Pradesh only, and constituencies are Lucknow only.**
All 75 districts are UP districts. All 9 constituencies map to the single district `Lucknow`. Against the
~403 ACs that UP actually has, this is roughly **2%** coverage — the Constituency dropdown will appear empty
or broken for any district other than Lucknow.

**5. No state information exists anywhere in the reference tables.**
Confirmed again here: no `states` table, no `state_id` column on `districts`. The only state data in the
system is the free-text `voters.state` column populated by OCR.

---

## Safety verification

| Item | Status |
|---|---|
| Database modified | **NO** — session forced to `TRANSACTION READ ONLY`, verified `on` before any query |
| Voters modified | **NO** — `voters` was only `COUNT`ed and checksummed; never selected into the export, never written |
| Models modified | **NO** |
| APIs modified | **NO** |
| Migrations created or modified | **NO** |
| Seeder modified | **NO** |
| Seeder executed | **NO** |
| Data imported into the database | **NO** |
| Anything deleted | **NO** |
| Committed / pushed | **NO** |

**Post-export verification** (independent second connection, also read-only):

```
districts    = 75   (unchanged)
constituency =  9   (unchanged)
voters       =  8   (unchanged)
voters content md5 = ed119d2378c6ef301cb30619fb4575a2
```

The voters checksum covers `id, epic, name, assembly_constituency_id, district_id, state` across all 8 rows
and is recorded here so a future step can prove the rows were still untouched at that point.

No ORM objects were instantiated and no `commit()` of a data change was ever issued. All export and validation
scripts live in the session scratchpad, **not** in the repository.

### Validation results

24 automated checks, **all passed**: BOM presence, `utf-8-sig` re-parse, header cleanliness, counts matching
the database, absence of duplicate rows, byte-exact round-trip equality of all English and Hindi names against
the database, every constituency carrying its current district, blank-field policy honoured on all six
intentionally blank fields, and unchanged table counts afterwards.

Devanagari round trip confirmed on 75/75 district rows (sample: `आगरा`, `अलीगढ़`, `अम्बेडकर नगर`).

---

## Git status

Untracked, uncommitted, unpushed:

```
?? data/reference/constituencies.csv
?? data/reference/districts.csv
?? docs/reference-data-baseline.md
?? docs/reference-data-research.md
```

`git diff --stat` is empty — no tracked file was modified. Branch `main` at `b28f344`, unchanged.

Note: `data/` is **not** covered by `.gitignore`, so these CSVs can be committed normally. That is the point —
the previous reference CSVs were lost precisely because they were never added to version control.

---

## Next step

Per [reference-data-research.md §13](reference-data-research.md), Step 2: acquire the authoritative LGD
export (States/UTs and Districts **with LGD codes**) and confirm whether a populated Hindi name column exists.
That resolves `state_code` and `lgd_district_code`, the two blank fields in `districts.csv`.
