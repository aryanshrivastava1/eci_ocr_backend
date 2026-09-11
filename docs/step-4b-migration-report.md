# Step 4B — India-wide reference-data schema + migration

Date: 2026-09-11. Migration **applied and committed**. The 8 existing voters are
intact, byte-for-byte, and were never written to.

---

## 1. Migration

| Item | Value |
|---|---|
| Version | `0001_india_wide_reference_data` |
| DDL | `migrations/0001_india_wide_reference_data.sql` |
| Runner | `migrations/run_migration_0001.py` |
| Rollback | `migrations/0001_rollback.sql` |
| Pre-migration snapshot | `migrations/snapshots/0001_india_wide_reference_data_pre.json` |
| Applied at | `2026-09-11 07:09:48 UTC`, recorded in the new `schema_migrations` table |

There is no Alembic in this project and no package may be installed, so the
migration is a versioned SQL file driven by a Python runner that records applied
versions in `schema_migrations`. The runner supports:

```
python migrations/run_migration_0001.py            # dry run — full rehearsal, then ROLLBACK
python migrations/run_migration_0001.py --apply    # commit
```

**Everything runs inside one transaction.** Any failed assertion raises, which
rolls the whole transaction back, so a partially-applied migration is not
reachable. The dry run executes every statement against real data and then rolls
back, so it is a rehearsal rather than a simulation.

It was run as a dry run first: **62 assertions, 0 failures, rolled back**. Then
applied: the same 62 assertions, 0 failures, committed. The two runs' assertion
lists were diffed and are identical — nothing was skipped on the applied run.

---

## 2. Models changed

| File | Change |
|---|---|
| `app/models/states.py` | **new** — `State` (`state_id`, `state_code`, `state_name_en`, `state_name_hi`, `source`, `source_version`) |
| `app/models/districts.py` | added `state_id` (FK → `states.state_id`), `lgd_district_code` (unique), `source`, `source_version` |
| `app/models/constituency.py` | added `state_id` (FK), `ac_number`, `lgd_district_code`, `source`, `source_version`, `mapping_confidence`; `district` and `constituency_hindi` relaxed to nullable; `UniqueConstraint("state_id", "ac_number")` declared |
| `app/db/base_model.py` | registers `State` |
| `app/models/voter.py` | **untouched** |

No API file was modified.

---

## 3. Exact schema changes

**New table**

```sql
CREATE TABLE states (
    state_id       INTEGER PRIMARY KEY,   -- LGD State Code as an integer
    state_code     TEXT    NOT NULL,      -- the same LGD code as TEXT: UP = "9"
    state_name_en  TEXT    NOT NULL,
    state_name_hi  TEXT,                  -- NULL everywhere; nothing fabricated
    source         TEXT,
    source_version TEXT
);
CREATE UNIQUE INDEX ux_states_state_code ON states (state_code);
```

`state_id` is the LGD State Code rather than a fresh serial. That keeps it
stable and meaningful and makes the migration re-runnable — a second run derives
the same `state_id` for the same State/UT. No postal abbreviation, ISO code or
Census code is used as the identifier.

**`districts`** — added `state_id INTEGER`, `lgd_district_code TEXT`,
`source TEXT`, `source_version TEXT`. `district_id` unchanged.

**`constituency`** — added `state_id INTEGER`, `ac_number INTEGER`,
`lgd_district_code TEXT`, `source TEXT`, `source_version TEXT`,
`mapping_confidence TEXT`. `id` unchanged and still the primary key.

**Two NOT NULL constraints relaxed** (both blocked the load outright):

```sql
ALTER TABLE constituency ALTER COLUMN "Constituency_Hindi" DROP NOT NULL;
ALTER TABLE constituency ALTER COLUMN "District"           DROP NOT NULL;
```

The ECI 2008 Order contains zero Devanagari, so 3,542 incoming rows have no
Hindi name. They are stored as **NULL, not `''`** — `''` would poison
`resolve_constituency()`, which fuzzy-matches on exactly that column.

**Foreign keys** (added `NOT VALID`, then `VALIDATE` as a separate statement, so
the exclusive lock covers only the catalogue change):

```sql
districts.state_id    -> states.state_id         (districts_state_id_fkey)
constituency.state_id -> states.state_id         (constituency_state_id_fkey)
```

`constituency.district_id → districts.district_id` already existed and was kept.
**No FK was added on `voters.assembly_constituency_id`** — it is half the voters
composite primary key and is exposed as the `ac_id` query parameter on
`PUT /voters/{voter_id}`, so constraining it is a separate reviewable change.
The voters primary key structure is untouched.

**Uniqueness**

```sql
CREATE UNIQUE INDEX ux_districts_lgd_district_code ON districts (lgd_district_code);
CREATE UNIQUE INDEX ux_constituency_state_ac ON constituency (state_id, ac_number)
    WHERE state_id IS NOT NULL AND ac_number IS NOT NULL;
```

The constituency index is partial so a future row without an identity can
coexist instead of blocking the constraint; the runner asserted that **0 rows are
currently excluded by the predicate**. District and constituency **names are
deliberately left non-unique** — 83 English AC names recur across states, and
district names are not unique across states either.

**Supporting indexes** for the state-scoped lookups Step 4C needs:
`ix_districts_state_id`, `ix_constituency_state_id`, `ix_constituency_ac_number`.

**NOT NULL promoted last**, each guarded by a preceding `count(*) WHERE col IS NULL = 0`
assertion: `districts.state_id`, `districts.lgd_district_code`,
`constituency.state_id`, `constituency.ac_number`.

---

## 4. Data loaded

### States inserted — 36

All 36 LGD States/UTs, from `lgd_states_raw.csv`. `state_name_hi` is **NULL on all
36**. The LGD "State Name (In Local language)" column holds an upper-case Latin
transliteration (`UTTAR PRADESH`), not Devanagari, so it is not Hindi and was
deliberately not copied. Verified: `count(*) WHERE state_name_hi IS NOT NULL = 0`.

### Districts — 75 updated, 709 inserted, 784 total

**Updated (75)** — `UPDATE ... WHERE district_id = ?`, no inserts in that phase.
Each got `state_id = 9`, its `lgd_district_code`, and `source`/`source_version`.
`district_name_hi` was **not in the SET list**, so the existing Hindi could not be
touched; verified byte-identical against the pre-migration snapshot for all 75.

69 legacy names matched LGD exactly. The 6 reviewed differences were applied from
an explicit table, not fuzzy matching, and the English name rewritten to the LGD
canonical form:

| district_id | was | now | LGD code |
|---|---|---|---|
| 92 | Barabanki | Bara Banki | 129 |
| 95 | Bhadohi (Sant Ravidas Nagar) | Bhadohi | 179 |
| 125 | Lakhimpur Kheri | Kheri | 159 |
| 128 | Maharajganj | Mahrajganj | 164 |
| 140 | Raebareli | Rae Bareli | 175 |
| 148 | Siddharth Nagar | Siddharthnagar | 182 |

The runner asserted 75 mapped, exactly 6 via alias, and a 75↔75 bijection over
LGD UP district codes. It raises rather than guessing if a legacy name has no
reviewed mapping.

**Inserted (709)** — the remaining LGD districts, `INSERT ... WHERE NOT EXISTS`
on `lgd_district_code`. `district_id` came from the sequence, so ids 79–153 were
untouched. `district_name_hi` is NULL for new rows: no Hindi was fabricated.

### Constituencies — 9 updated, 3,542 inserted, 3,551 total

**Updated (9)** — `UPDATE ... WHERE id = ?`. Each received
`state_id = 9`, `district_id = 127`, `lgd_district_code = '162'`, its official
`ac_number`, `source`, `source_version = '2008'`,
`mapping_confidence = 'exact'`.

`"Constituency"` and `"Constituency_Hindi"` were **not in the SET list** — the
legacy English names and the legacy Hindi (the only AC Hindi that exists
anywhere) are preserved exactly. Verified byte-identical against the snapshot.

Before writing, the runner re-verified each row's current English name against
the reviewed mapping and would have aborted on a mismatch:

| id | name | ac_number |
|---|---|---|
| 20 | Malihabad | 168 |
| 13 | Bakshi Kaa Talab | 169 |
| 21 | Sarojini Nagar | 170 |
| 17 | Lucknow West | 171 |
| **14** | **Lucknow North** | **172** |
| 15 | Lucknow East | 173 |
| **16** | **Lucknow Central** | **174** |
| 18 | Lucknow Cantonment | 175 |
| 19 | Mohanlalganj | 176 |

Bijection onto ECI 168–176 asserted. Note `id = 18` keeps its legacy English
name `Lucknow Cantonment`; the ECI source spells it `Lucknow Cantt`. The legacy
name was preserved deliberately — the identity is carried by `ac_number = 175`,
not by the string.

**Inserted (3,542)** — `INSERT ... WHERE NOT EXISTS` on `(state_id, ac_number)`,
so an existing row can never be overwritten because a name differs. Loaded via a
`TEMP ... ON COMMIT DROP` staging table and one set-based `INSERT ... SELECT`,
which keeps the transaction — and its locks on the live database — short.

District FK policy, applied without exception:

| `mapping_confidence` | Rows loaded | `district_id` |
|---|---|---|
| `exact` | 2,879 | resolved from `lgd_district_code` |
| `mapped` | 568 | resolved from `lgd_district_code` |
| `needs_review` | 34 | **NULL** — never silently assigned |
| `no_district_in_source` | 70 | **NULL** — the Order gives Delhi no districts |

104 rows carry a deliberately NULL `district_id`, and `lgd_district_code` is NULL
on exactly those rows. Verified: 0 rows where `district_id` disagrees with
`lgd_district_code`.

### Not loaded — 481 ECI rows for 5 unresolved States/UTs

| state_code | State/UT | Rows withheld | Why |
|---|---|---|---|
| 18 | Assam | 126 | 2008 schedule superseded by the ECI Assam Delimitation Order, 11 Aug 2023 (19 AC names revised); that order was not obtained |
| 28 | Andhra Pradesh | 175 | `ac_number` values are undivided-AP numbers 120–294, not the current 1–175 |
| 12 | Arunachal Pradesh | 60 | Excluded from the 2008 Order under s.10A; current legal instrument not established |
| 13 | Nagaland | 60 | Same s.10A exclusion |
| 14 | Manipur | 60 | Same s.10A exclusion |

Verified 0 AC rows for each. Loading them would have presented superseded or
legally unconfirmed constituencies as current in a live electoral application.

**Coverage:** 25 States/UTs carry AC rows; 11 carry zero — 5 unresolved above,
J&K (no rows exist in the dataset), and the 5 UTs with no Legislative Assembly
(Chandigarh, Lakshadweep, Andaman & Nicobar, Ladakh, DNH & DD). All 36 have
their districts loaded, since LGD district data is fully resolved regardless of
delimitation status.

---

## 5. Voters — before and after

| | Before | After |
|---|---|---|
| Row count | **8** | **8** |
| Column list | 15 columns | **identical** |
| Primary key | `PRIMARY KEY (id, assembly_constituency_id)` | **identical** |
| `assembly_constituency_id` → 14 | 3 voters | **3 voters** |
| `assembly_constituency_id` → 16 | 5 voters | **5 voters** |
| Dangling constituency refs | 0 | **0** |
| Dangling district refs | 0 | **0** |

Primary keys, unchanged and verified byte-for-byte against the pre-migration
snapshot from an independent read-only connection:

| voter `id` | `assembly_constituency_id` |
|---|---|
| `2e3beab9-917d-42f8-a044-643bffcfd693` | 14 |
| `35c7f119-854c-4afd-a8d8-193266d71b12` | 14 |
| `49a4f922-3b20-4ae7-a5bc-c9751ad4d92b` | 14 |
| `199253c6-49cd-438c-bc0b-6898a83abef7` | 16 |
| `54472274-ce21-4090-bdef-e3382a3ec07c` | 16 |
| `803df057-8d8e-4998-ac34-ab6d01423a7d` | 16 |
| `8496774b-e627-4ece-9e7a-b916cfdb810b` | 16 |
| `b2b6caa5-e41f-4081-b635-350a4a8a222d` | 16 |

`voters` was never written to. No `UPDATE`, `INSERT` or `DELETE` was issued
against it at any point; it appears only in `SELECT` assertions.

---

## 6. Validation results

Phase 7 gate (before any new row was inserted) and Phase 12 (after) both passed
in full. The migration was then re-verified from a **separate read-only
connection** after commit — all checks passed, no failures:

| Check | Result |
|---|---|
| `states` / `districts` / `constituency` / `voters` counts | 36 / 784 / 3,551 / 8 ✅ |
| Voter PKs identical to snapshot | ✅ |
| Voter reference distribution `{14:3, 16:5}` | ✅ |
| Voters column list and PK definition unchanged | ✅ |
| Dangling voter → constituency / district refs | 0 / 0 ✅ |
| `constituency` ids 13–21 intact | ✅ |
| `districts` ids 79–153 intact (75 rows) | ✅ |
| Legacy AC Hindi byte-identical | ✅ |
| Legacy district Hindi byte-identical (all 75) | ✅ |
| Legacy ACs map onto 168–176 | ✅ |
| Duplicate `(state_id, ac_number)` | 0 ✅ |
| Duplicate `lgd_district_code` | 0 ✅ |
| `districts.state_id` / `constituency.ac_number` NULLs | 0 / 0 ✅ |
| Fabricated Hindi on new AC rows | 0 ✅ |
| Fabricated `state_name_hi` | 0 ✅ |
| `district_id` disagreeing with `lgd_district_code` | 0 ✅ |
| AC rows for each of the 11 withheld / no-Assembly States/UTs | 0 each ✅ |

---

## 7. Rollback strategy

`migrations/0001_rollback.sql`, in five sections. Everything additive is
reversible: the `states` table, the added columns, the two FKs, the five indexes
and the four NOT NULLs are all dropped.

Inserted rows are removed by the one identity rule that provably cannot touch
legacy data — `constituency.id > 21` and `districts.district_id > 153`. Those
ranges are disjoint from the legacy rows (13–21 and 79–153) because both
sequences were already past them before the migration ran. Constituency rows are
deleted before districts, since districts is their FK parent. The script prints
the two guard `SELECT`s to confirm 3,542 and 709 before the deletes.

**One change is not automatically reversible:** Phase 5 rewrote
`districts.district_name_en` for 6 rows. Their prior values are recorded in the
pre-migration snapshot and are restored explicitly by section R4.

`voters` is not referenced anywhere in the rollback. No voter row is read,
written or deleted by it.

---

## 8. Unresolved reference-data gaps

| Gap | Status |
|---|---|
| **Andhra Pradesh, 175 ACs** | Withheld. `ac_number` is the undivided-AP 120–294; current AP numbers its 175 ACs 1–175. The offset looks like −119 but was not confirmed against an official AP source |
| **Assam, 126 ACs** | Withheld. Needs the ECI Assam Delimitation Order, 11 Aug 2023 |
| **Jammu & Kashmir, 90 ACs** | No rows exist. Needs the J&K Delimitation Commission Order, 2022 |
| **Arunachal Pradesh / Nagaland / Manipur, 180 ACs** | Withheld. Current legal instrument not established |
| **Sikkim AC 32, Sangha** | Absent. Non-territorial seat with no extent; Sikkim loaded with 31 of 32 |
| **Hindi for 3,542 AC rows** | NULL. No authoritative bilingual source; nothing transliterated |
| **Hindi for 709 new districts** | NULL. Only the original 75 UP districts have Hindi |
| **`state_name_hi` for all 36 States/UTs** | NULL |
| **34 `needs_review` district attributions** | Loaded with NULL `district_id`: WB `BARDHAMAN` (25, splits into Purba/Paschim), Meghalaya `JAINTIA HILLS` (7, splits into East/West), Puducherry `MAHE`/`YANAM` (2, absent from the LGD snapshot) |
| **70 Delhi AC rows** | NULL `district_id` — the 2008 Order gives Delhi no district headings at all |
| **`mandala_id` / `mandal_id`** | NULL everywhere; no mandal table and no source |

Loaded total is **3,551 of the 4,123** national universe. The 572-row difference
is fully itemised above, not residual.

---

## 9. PHASE 11 — resolver work required in Step 4C

Not changed in this step, as instructed. Both unsafe operations are located
precisely below. **Both must be scoped by state, and preferably district.**

### 9.1 `resolve_constituency()` — `app/core/constituency_resolver.py`

| Line | Problem |
|---|---|
| **31** | `rows = db.query(Constituency).all()` — table-wide `SELECT` with no filter. This now loads **3,551 rows on every OCR job**, up from 9 |
| **35** | `hindi_names = [r.constituency_hindi for r in rows]` — 3,542 of those are now NULL |
| **16, 37–43** | `process.extract(..., scorer=fuzz.partial_ratio)` against `_MATCH_THRESHOLD = 65`. A 65% partial-ratio threshold over thousands of Devanagari names is far too loose |
| **52–59** | Tie handling: if the top two scores are equal it returns `(None, None)`. With nationwide data, ties become the common case, so resolution degrades to "usually null" |
| **67** | District lookup keyed only on `constituency.district_id`, which is now NULL for 104 rows |

Measured, not assumed: `rapidfuzz.process.extract` **skips `None` choices
gracefully** (verified against the real 9-Hindi + 3,542-NULL shape), so this
function is **not crashed** by the migration. But it can now only ever resolve
the 9 Lucknow rows that have Hindi, while paying to load 3,551 rows per job.

Required in 4C: filter by `state_id` (and `district_id` when known) before
matching, exclude rows with NULL Hindi explicitly rather than relying on
rapidfuzz's behaviour, raise the threshold, and reconsider the
tie-means-null rule once the candidate set is small.

### 9.2 `POST /voters/save` — `app/api/routes/voter.py`

| Line | Problem |
|---|---|
| **190–197** | `db.query(Constituency).filter(or_(func.lower(constituency_hindi) == name, func.lower(constituency) == name)).first()` — table-wide exact match on the lower-cased name, then `.first()` |

This one **is** a live correctness risk as of now. Measured against the loaded
data: **83 English AC names are duplicated across states, spanning 185 rows**
— `Ramnagar` and `Patan` each appear in 4 different states; `Pratapgarh`,
`Fatehpur`, `Bilaspur`, `Islampur`, `Khanapur`, `Chhatarpur`, `Rajnagar`,
`Gopalpur`, `Dharampur` each in 3. For any of those, `.first()` picks an
arbitrary row and writes its `constituency.id` into
`voters.assembly_constituency_id` **and** its `district_id` into the voter — so a
voter can be attached to a same-named constituency in the wrong state, silently.

Required in 4C: the endpoint must accept and apply a state (and ideally district)
scope, and must reject an ambiguous name rather than silently taking the first
match. Line **215** (`Voter.assembly_constituency_id == constituency.id`) inherits
the same wrong id for the EPIC de-duplication check.

### 9.3 Also carried forward

- `GET /districts` and `GET /filters` return every district unscoped. With 784
  districts, duplicate district names across states now appear in the dropdown
  with nothing to distinguish them. The serialiser should expose `state_id` /
  state name, and the endpoint should accept a state filter.
- `GET /constituencies` returns all 3,551 rows when no `district_id` is given.
- `_serialize_constituency` does not expose `state_id` or `ac_number`, so a
  client cannot yet see the authoritative identity.
- `app/db/base_model.py` still does not import `Voter`; `State` was added.

---

## 10. Safety

| Item | Status |
|---|---|
| Database modified | **YES** — only through migration `0001`, one transaction, dry-run rehearsed first |
| Voters modified | **NO** — `SELECT` only; 8 rows, PKs byte-identical, PK definition unchanged |
| Voter rows deleted | **NO** |
| `DROP TABLE` / `TRUNCATE` / `DELETE` used | **NO** — none appears in the applied path |
| Populated reference tables recreated | **NO** |
| Legacy IDs reseeded | **NO** — constituency 13–21 and districts 79–153 untouched; new rows took sequence ids |
| Models changed | **YES** — `State` added; identity columns on `District` and `Constituency`; `Voter` untouched |
| APIs changed | **NO** |
| Seeder executed | **NO** |
| Baseline CSVs modified | **NO** — `data/reference/districts.csv` and `constituencies.csv` untouched |
| Reference source CSVs modified | **NO** |
| Hindi fabricated | **NO** — verified 0 rows with invented Hindi on states or new ACs |
| Third-party source of record | **NO** — LGD and the ECI 2008 Order only |
| Packages installed | **NO** — used the existing `venv` for `psycopg2`; no Alembic |
| Committed / pushed | **NO** |
