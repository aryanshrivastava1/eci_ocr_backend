# Step 4A — Legacy reference-data identity audit

Date: 2026-09-11. **Read-only.** Every database query ran inside a session with
`SET TRANSACTION READ ONLY`, verified `on` before the first query. Table counts
were re-checked from a second independent read-only connection afterwards and
were unchanged (`districts` 75, `constituency` 9, `voters` 8).

Nothing was modified: no schema change, no migration, no seeder run, no voter
touched, no reference CSV or baseline altered, no commit, no push.

---

## 1. Current schema findings

### 1.1 Tables present

`booths`, `constituency`, `districts`, `jobs`, `users`, `voters`.
Row counts: `districts` **75**, `constituency` **9**, `voters` **8**,
`booths` **0**, `users` **2** (both `superadmin`, all scoping columns NULL).

### 1.2 `districts`

| # | Column | Type | Null | Default |
|---|---|---|---|---|
| 1 | `district_id` | integer | NO | `nextval('districts_district_id_seq')` |
| 2 | `district_name_en` | varchar | YES | — |
| 3 | `district_name_hi` | varchar | YES | — |
| 4 | `mandala_id` | integer | YES | — |

- PK `districts_pkey (district_id)`. No other index, **no unique constraint on the name**.
- **No state column of any kind.** No `states` table exists.
- IDs occupy **79–153**, contiguous, 75 rows, 75 distinct English names, 0 missing Hindi, `mandala_id` NULL on all 75.
- Sequence `districts_district_id_seq` `last_value = 153, is_called = true`.

### 1.3 `constituency`

| # | Column | Type | Null | Default |
|---|---|---|---|---|
| 1 | `id` | integer | NO | `nextval('constituency_id_seq')` |
| 2 | `"Constituency"` | varchar | **NO** | — |
| 3 | `"District"` | varchar | **NO** | — |
| 4 | `"Constituency_Hindi"` | varchar | **NO** | — |
| 5 | `district_id` | integer | YES | — |

- PK `constituency_pkey (id)`; FK `constituency_district_id_fkey (district_id) → districts(district_id)`.
- Indexes on `"Constituency"`, `"Constituency_Hindi"`, `"District"`, `id`. **No unique constraint on any name or on `(district_id, name)`.**
- Three columns are quoted mixed-case identifiers, mapped in the model to `constituency`, `district`, `constituency_hindi`.
- `"District"` duplicates the district name as free text alongside the `district_id` FK.
- IDs occupy **13–21**. Sequence `constituency_id_seq` `last_value = 21, is_called = true`.

### 1.4 `voters`

| # | Column | Type | Null |
|---|---|---|---|
| 1 | `id` | uuid | NO |
| 2 | `user_id` | uuid | YES |
| 3–8 | `name`, `epic`, `mobile`, `address`, `serial_number`, `part_number_and_name` | text/varchar/int | YES |
| 9 | `assembly_constituency_id` | integer | **NO** |
| 10 | `assembly_constituency_name` | varchar | YES |
| 11–12 | `district`, `state` | varchar | YES |
| 13–15 | `mandal_id`, `district_id`, `booth_id` | integer | YES |

- PK `voters_pkey (id, assembly_constituency_id)` — **`assembly_constituency_id` is half the primary key.**
- FK only to `users(id)`. **No FK from `assembly_constituency_id` to `constituency(id)`, and none from `district_id` to `districts(district_id)`.**
- Indexes: `assembly_constituency_id`, `epic`, `user_id`. `epic` is **not** unique.
- `app/db/base_model.py` imports `User`, `Job`, `Constituency`, `District`, `Booth` — **`Voter` is absent**, so `voters` is not in the metadata a `create_all()` would see.

### 1.5 What `assembly_constituency_id` actually holds

It holds `constituency.id` — a DB surrogate key — **not** an ECI AC number. Proven
by the live write path:

- `app/api/routes/voter.py:190-237` resolves the posted `assembly_constituency_name`
  against `lower("Constituency_Hindi")` or `lower("Constituency")`, then writes
  `data["assembly_constituency_id"] = constituency.id` and
  `data["district_id"] = constituency.district_id`.
- `app/api/routes/voter.py:213` de-duplicates EPICs with
  `Voter.assembly_constituency_id == constituency.id`.

### 1.6 Columns the existing APIs depend on

| Surface | Depends on |
|---|---|
| `GET /districts`, `GET /filters` | `districts.district_id`, `district_name_en`, `district_name_hi`, `mandala_id` (returned as `mandal_id`) |
| `GET /constituencies`, `GET /filters` | `constituency.id`, `constituency`, `constituency_hindi`, `district`, `district_id`; filtered by `district_id`, ordered by name then `id` |
| `POST /voters/save` | exact case-insensitive match on `"Constituency"` / `"Constituency_Hindi"`, then `.first()`; writes `constituency.id` into the voter |
| `PUT /voters/{voter_id}` | **`ac_id` is a required query parameter** — `update_voter(db, voter_id, ac_id, data)` targets the row by `(id, assembly_constituency_id)` (`voter_repo.py:23-28`) |
| `GET /voters` list / export / count | `assembly_constituency_id` and `district_id` as filters; `assembly_constituency_id` in `SORTABLE_FIELDS`; `_serialize_voter` returns both |
| `vote_service.py:17-22` | scopes non-admin users by `Voter.assembly_constituency_id == current_user.constituency_id` and `Voter.district_id == current_user.district_id` |
| `constituency_resolver.resolve_constituency()` | loads the **entire** `constituency` table, fuzzy-matches `constituency_hindi` at threshold 65, returns `(None, None)` if the top two scores tie |

**Consequence: `assembly_constituency_id` is part of the public API contract**
(the `ac_id` URL parameter), not merely an internal key. Renumbering it is a
breaking API change on top of a data change.

---

## 2. The 9 existing constituency rows

All 9 belong to the single district `Lucknow` (`district_id = 127`,
`district_name_en = 'Lucknow'`, `district_name_hi = 'लखनऊ'`, `mandala_id = NULL`).

| `id` (PK) | `"Constituency"` | `"Constituency_Hindi"` | `"District"` | `district_id` |
|---|---|---|---|---|
| 13 | Bakshi Kaa Talab | बक्शी का तालाब | Lucknow | 127 |
| 14 | Lucknow North | लखनऊ उत्तर | Lucknow | 127 |
| 15 | Lucknow East | लखनऊ पूर्व | Lucknow | 127 |
| 16 | Lucknow Central | लखनऊ मध्य | Lucknow | 127 |
| 17 | Lucknow West | लखनऊ पश्चिम | Lucknow | 127 |
| 18 | Lucknow Cantonment | लखनऊ छावनी | Lucknow | 127 |
| 19 | Mohanlalganj | मोहनलालगंज | Lucknow | 127 |
| 20 | Malihabad | मलिहाबाद | Lucknow | 127 |
| 21 | Sarojini Nagar | सरोजिनी नगर | Lucknow | 127 |

No `ac_number`, no state, no reservation, no source column exists on this table.

### The 8 voters and the constituency ID each references

| voter `id` (prefix) | `epic` | `name` | `assembly_constituency_id` | `assembly_constituency_name` | `district` | `state` | `district_id` | `mandal_id` | `booth_id` |
|---|---|---|---|---|---|---|---|---|---|
| 35c7f119 | DQB4713103 | अमित मुटनी | **14** | लखनऊ उत्तर | लखनऊ | उत्तर प्रदेश | 127 | NULL | NULL |
| 2e3beab9 | TD05141585 | SHIVKASHY | **14** | लखनऊ उत्तर | लखनऊ | उत्तर प्रदेश | 127 | NULL | NULL |
| 49a4f922 | TDQ3664409 | Mala Bhutani | **14** | लखनऊ उत्तर | लखनऊ | उत्तर प्रदेश | 127 | NULL | NULL |
| 8496774b | UP/20/103/0684005 | मानय रस्तोगी | **16** | लखनऊ मध्य | लखनऊ | उत्तर प्रदेश | 127 | NULL | NULL |
| b2b6caa5 | XGF0193425 | मो इरफान | **16** | लखनऊ मध्य | लखनऊ | उत्तर प्रदेश | 127 | NULL | NULL |
| 54472274 | XGF0739839 | विशाल | **16** | लखनऊ मध्य | लखनऊ | उत्तर प्रदेश | 127 | NULL | NULL |
| 803df057 | XGF0963355 | सरवर जहे | **16** | लखनऊ मध्य | लखनऊ | उत्तर प्रदेश | 127 | NULL | NULL |
| 199253c6 | XGF2343002 | माधा रस्तोगी | **16** | लखनऊ मध्य | लखनऊ | उत्तर प्रदेश | 127 | NULL | NULL |

Reference distribution: **`id = 14` (Lucknow North) → 3 voters**,
**`id = 16` (Lucknow Central) → 5 voters**. Both target rows exist. All 8 point at
`district_id = 127`, which exists. `mandal_id` and `booth_id` are NULL on all 8
(`booths` is empty). **Zero dangling references.**

---

## 3. Identity mapping of the 9 constituencies

Source: `data/reference/source/eci_ac_normalised.csv`, filtered to
`state_code = '9'` (LGD Uttar Pradesh) and `district_name_en = 'Lucknow'`
(`district_lgd_code = '162'`). That filter returns **exactly 9 rows**, AC numbers
**168–176**, every one already `mapping_confidence = exact` against LGD.

| legacy_id | legacy_name | legacy_district_id | legacy_district_name | state_code | ECI ac_number | ECI constituency | reservation | LGD district_code | LGD district_name | confidence | evidence / reason |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 13 | Bakshi Kaa Talab | 127 | Lucknow | 9 | **169** | Bakshi Kaa Talab | — | 162 | Lucknow | **high** | Byte-exact English name match, including the idiosyncratic double-`a` "Kaa" spelling that both the legacy row and the 2008 Order use |
| 14 | Lucknow North | 127 | Lucknow | 9 | **172** | Lucknow North | — | 162 | Lucknow | **high** | Byte-exact English name match within the district |
| 15 | Lucknow East | 127 | Lucknow | 9 | **173** | Lucknow East | — | 162 | Lucknow | **high** | Byte-exact English name match within the district |
| 16 | Lucknow Central | 127 | Lucknow | 9 | **174** | Lucknow Central | — | 162 | Lucknow | **high** | Byte-exact English name match within the district |
| 17 | Lucknow West | 127 | Lucknow | 9 | **171** | Lucknow West | — | 162 | Lucknow | **high** | Byte-exact English name match within the district |
| 18 | Lucknow Cantonment | 127 | Lucknow | 9 | **175** | Lucknow Cantt | — | 162 | Lucknow | **high** | Explicit reviewed abbreviation `Cantonment` = ECI `Cantt`; it is the sole residual of a closed 9↔9 set once the other 8 match exactly |
| 19 | Mohanlalganj | 127 | Lucknow | 9 | **176** | Mohanlalganj | SC | 162 | Lucknow | **high** | Byte-exact English name match within the district |
| 20 | Malihabad | 127 | Lucknow | 9 | **168** | Malihabad | SC | 162 | Lucknow | **high** | Byte-exact English name match within the district |
| 21 | Sarojini Nagar | 127 | Lucknow | 9 | **170** | Sarojini Nagar | — | 162 | Lucknow | **high** | Byte-exact English name match within the district |

**No fuzzy matching was used.** Eight identities rest on exact string equality;
the ninth rests on one explicitly declared abbreviation plus a closure argument.

**Bijection verified:** 9 legacy rows, 9 ECI rows, 9 matches, 0 unmatched legacy
rows, 0 unclaimed ECI rows. Because the set is closed, no legacy row could be
matched to more than one ECI row and no ECI row is left over — which is stronger
evidence than any individual name comparison.

**Unresolved mappings: none.** Nothing needed `needs_review`.

Note: the legacy `id` values 13–21 bear **no relationship** to the AC numbers
168–176. `id = 13` is AC 169, `id = 21` is AC 170. Any assumption that the
existing IDs encode AC numbers is wrong.

### Legacy district identity (context for the same migration)

All 75 legacy districts reconcile to the 75 LGD Uttar Pradesh districts —
**69 exact + 6 explicit reviewed differences**, bijective with nothing left over:

| legacy_district_id | legacy name | LGD code | LGD name |
|---|---|---|---|
| 92 | Barabanki | 129 | Bara Banki |
| 95 | Bhadohi (Sant Ravidas Nagar) | 179 | Bhadohi |
| 125 | Lakhimpur Kheri | 159 | Kheri |
| 128 | Maharajganj | 164 | Mahrajganj |
| 140 | Raebareli | 175 | Rae Bareli |
| 148 | Siddharth Nagar | 182 | Siddharthnagar |

`Bhadohi (Sant Ravidas Nagar)` was the one name no normalisation rule caught; it
resolves to LGD 179 `Bhadohi` as the only unclaimed LGD UP district, and the
legacy name contains `Bhadohi` literally. This matches the 69 + 6 figure already
recorded in `docs/reference-data-baseline.md`.

The relevant row here is legacy `district_id = 127` `Lucknow` → **LGD `162`
`Lucknow`**, exact.

---

## 4. Voter impact

| voter `id` (prefix) | `epic` | current AC id | current AC name | → state_code | → ac_number | → district_lgd_code | safe? |
|---|---|---|---|---|---|---|---|
| 35c7f119 | DQB4713103 | 14 | Lucknow North | 9 | 172 | 162 | ✅ safe |
| 2e3beab9 | TD05141585 | 14 | Lucknow North | 9 | 172 | 162 | ✅ safe |
| 49a4f922 | TDQ3664409 | 14 | Lucknow North | 9 | 172 | 162 | ✅ safe |
| 8496774b | UP/20/103/0684005 | 16 | Lucknow Central | 9 | 174 | 162 | ✅ safe |
| b2b6caa5 | XGF0193425 | 16 | Lucknow Central | 9 | 174 | 162 | ✅ safe |
| 54472274 | XGF0739839 | 16 | Lucknow Central | 9 | 174 | 162 | ✅ safe |
| 803df057 | XGF0963355 | 16 | Lucknow Central | 9 | 174 | 162 | ✅ safe |
| 199253c6 | XGF2343002 | 16 | Lucknow Central | 9 | 174 | 162 | ✅ safe |

Safe **on the strict condition that `voters.assembly_constituency_id` keeps the
values 14 and 16**. The official identity is recorded on the `constituency` row
those IDs already point at; it is never written into the voter's key.

Two things make this workable rather than lucky:

1. `constituency_id_seq.last_value = 21`, so inserting the remaining ACs
   allocates `id ≥ 22`. IDs 13–21 are never reissued, and 14 and 16 keep meaning
   Lucknow North and Lucknow Central.
2. `districts_district_id_seq.last_value = 153`, so inserting non-UP districts
   allocates `district_id ≥ 154` and 127 keeps meaning Lucknow.

### What would break the 8 voters

| Action | Effect |
|---|---|
| `TRUNCATE`/`DELETE` + reload `constituency` | New sequence IDs. Voters would silently re-point at whatever now occupies 14 and 16 — **no error raised**, because there is no FK |
| Setting `assembly_constituency_id` to the ECI `ac_number` (14 → 172, 16 → 174) | Rewrites half the primary key of all 8 rows, and breaks the `PUT /voters/{voter_id}?ac_id=` contract for every stored client reference |
| `ALTER TABLE voters` recreation | Composite PK `(id, assembly_constituency_id)` must be preserved exactly; `epic` is not unique, so rows cannot be re-identified by EPIC alone if order is lost |
| Adding the FK before backfill completes | 8 rows would be validated against a table mid-load |

---

## 5. Proposed migration sequence

Additive throughout. No table is dropped, truncated or recreated; no existing ID
changes; the voters table is not written to at all.

**Phase 0 — capture a rollback point (do first, once)**
1. Snapshot the raw identifiers to a file outside the DB: `districts.district_id`,
   `constituency.id`, and the 8 `(voters.id, voters.assembly_constituency_id)`
   tuples. The baseline CSVs deliberately omit IDs, so they are **not** a restore
   point for identifiers. This audit's tables serve as that record.

**Phase 1 — add identity columns, all nullable, codes as TEXT**
2. `ALTER TABLE districts ADD COLUMN lgd_state_code TEXT`, `ADD COLUMN lgd_district_code TEXT`, `ADD COLUMN state_name_en TEXT`.
3. `ALTER TABLE constituency ADD COLUMN state_code TEXT`, `ADD COLUMN ac_number INTEGER`, `ADD COLUMN reservation TEXT`, `ADD COLUMN district_lgd_code TEXT`, `ADD COLUMN source TEXT`, `ADD COLUMN source_version TEXT`, `ADD COLUMN mapping_confidence TEXT`.
   Nothing is NOT NULL yet, so both statements are metadata-only and safe on the live table.

**Phase 2 — relax the two blocking NOT NULLs before any bulk load**
4. `ALTER TABLE constituency ALTER COLUMN "Constituency_Hindi" DROP NOT NULL`.
   **This is a hard blocker, not a preference.** `"Constituency_Hindi"` is
   `NOT NULL` with no default and the ECI dataset has **no Hindi for any of the
   4,032 rows**. Inserting them would fail outright; inserting `''` instead would
   poison `resolve_constituency()`, which fuzzy-matches on exactly that column.
5. Decide the same for `"District"` (also `NOT NULL`): either keep populating it
   from `district_name_en` for every new row, or drop the NOT NULL. It duplicates
   what `district_id` already carries.

**Phase 3 — backfill the existing 84 rows only (UPDATE by legacy PK)**
6. `UPDATE districts` for the 75 UP rows: `lgd_state_code = '9'`, `lgd_district_code` per the table in §3, `state_name_en = 'Uttar Pradesh'` — keyed on `district_id`, one statement per row or a `VALUES` join. No inserts.
7. `UPDATE constituency` for ids 13–21 with the `state_code`, `ac_number`, `reservation`, `district_lgd_code`, `source`, `source_version`, `mapping_confidence` from the §3 table — keyed on `id`. **English and Hindi names are left exactly as they are**; the legacy Hindi is the only AC Hindi that exists anywhere and must not be overwritten with blanks from the ECI file.

**Phase 4 — verify voters before anything else happens**
8. Assert `SELECT count(*) FROM voters = 8`.
9. Assert the reference distribution is still `{14: 3, 16: 5}`.
10. Assert every `voters.assembly_constituency_id` resolves to a `constituency` row, and that ids 14 and 16 still carry `ac_number` 172 and 174 and `"Constituency"` `Lucknow North` / `Lucknow Central`.
11. Assert the 8 `(id, assembly_constituency_id)` tuples are byte-identical to the Phase 0 snapshot. **Stop and roll back if any assertion fails.**

**Phase 5 — load the rest of the reference data (inserts only)**
12. Insert the non-UP LGD districts (`district_id ≥ 154` from the sequence), each with `lgd_state_code`/`lgd_district_code` populated on the way in. Do **not** insert Hindi that does not exist.
13. Insert the ECI ACs **excluding the 9 already present** — match on `(state_code, ac_number)`, not on name. **Exclude Andhra Pradesh** for now (see Phase 7).
14. Re-run the Phase 4 assertions after the load.

**Phase 6 — fix the resolvers, in the same change as the load**
15. Scope `resolve_constituency()` by state and district before matching. It currently `SELECT`s the whole table and ties at threshold 65; at 4,032 rows with repeated AC names across states, the tie-break returns `(None, None)` and OCR constituency resolution quietly stops working.
16. Scope the `POST /voters/save` lookup the same way. It matches `lower(name)` across the whole table and takes `.first()` — with nationwide data it will attach a voter to a same-named AC in the wrong state. This is a correctness bug that appears the moment the data lands.
17. Add `Voter` to `app/db/base_model.py`, or confirm deliberately that `voters` is managed outside the metadata.

**Phase 7 — constraints and keys, last**
18. Add the missing FK: `ALTER TABLE voters ADD CONSTRAINT voters_ac_fkey FOREIGN KEY (assembly_constituency_id) REFERENCES constituency(id) NOT VALID`, then `VALIDATE CONSTRAINT` separately. `NOT VALID` first keeps the lock short and lets validation fail without blocking writes.
19. Add `FOREIGN KEY (district_id) REFERENCES districts(district_id)` on `voters` the same way.
20. Add uniqueness on the authoritative identity as a **partial** index first:
    `CREATE UNIQUE INDEX ... ON constituency (state_code, ac_number) WHERE ac_number IS NOT NULL`.
    A full constraint cannot be added while any row still has a NULL identity.
21. Add `CREATE UNIQUE INDEX ... ON districts (lgd_state_code, lgd_district_code) WHERE lgd_district_code IS NOT NULL`.
22. Only once every row has an identity, promote the partial indexes to real constraints and consider `NOT NULL`.

**Phase 8 — what stays deferred**
23. **Andhra Pradesh** is excluded until its AC numbering is resolved. Per `docs/eci-ac-research.md` §4, its `ac_number` values are undivided-AP numbers 120–294, not the current 1–175. Loading them and then enforcing `UNIQUE (state_code, ac_number)` would enshrine numbers that do not match AP voter rolls.
24. **J&K (90 ACs) and the Sikkim Sangha seat** have no rows to load.
25. **Assam, Arunachal, Nagaland, Manipur** load with `source_version` marking their unresolved legal currency; that flag must survive into the table, which is why `source_version` is a real column and not a comment.
26. `GET /districts` returns every district unscoped. Once non-UP districts exist, duplicate district names across states will appear in the dropdown with nothing to tell them apart. A `states` table or at minimum `state_name_en` in the serialiser is needed before that endpoint is useful nationwide.

### What this sequence deliberately avoids

- No `DELETE`, `TRUNCATE` or table recreation anywhere.
- No change to `constituency.id`, `districts.district_id`, or any `voters` column.
- No FK or unique constraint added before its data is complete and verified.
- No Hindi invented for the 4,032 ECI rows, and no existing Hindi overwritten.

---

## 6. Unresolved mappings

**For the 9 constituencies and the 8 voters: none.** The set is closed and fully
identified.

Unresolved items that belong to later phases, carried forward from Step 3 and
recorded here so they are not rediscovered late:

| Item | Status |
|---|---|
| Andhra Pradesh `ac_number` (undivided 120–294 vs current 1–175) | **Blocks loading AP.** Needs an official AP source |
| J&K — 90 ACs | No rows; 2022 order not obtained |
| Sikkim AC 32 (Sangha) | No row; non-territorial seat absent from the Order |
| 94 ECI rows with `mapping_confidence = needs_review` | Load with NULL `district_lgd_code`; none is in the UP/Lucknow path |
| 70 Delhi rows, `no_district_in_source` | The Order gives Delhi no districts at all |
| `mandala_id` / `mandal_id` | NULL everywhere, no mandal table, no source. Out of scope |

---

## 7. Explicit statement on voter preservation

**All 8 voters can be preserved safely, with certainty, provided
`voters.assembly_constituency_id` is never rewritten.**

The basis:

- All 8 reference only `constituency.id` **14** and **16**, both of which exist.
- Those two rows are identified with high confidence as UP AC **172 Lucknow
  North** and UP AC **174 Lucknow Central**, LGD district **162 Lucknow**.
- The official identity is added to the `constituency` rows as new columns. The
  voters' key values do not change, so the voter→constituency relationship is
  preserved by construction rather than by remapping.
- Both sequences are already past the legacy ID ranges, so appending nationwide
  data cannot collide with ids 13–21 or district_ids 79–153.
- All 8 rows also carry `district_id = 127`, which exists and stays valid.

The one way to lose them is a reload that reassigns `constituency.id`. Because
`voters` has **no foreign key** to `constituency`, that corruption would be
silent — no error, just eight voters pointing at the wrong constituencies. The
additive sequence in §5 never creates that situation.

---

## 8. Safety report

| Item | Status |
|---|---|
| Database modified | **NO** — `SET TRANSACTION READ ONLY`, verified `on` before every query |
| Voters modified | **NO** — `SELECT` only |
| Models modified | **NO** |
| APIs modified | **NO** |
| Migrations created | **NO** |
| Migrations executed | **NO** |
| Seeder executed | **NO** |
| Baseline CSVs modified | **NO** |
| Reference CSVs modified | **NO** |
| Hindi fabricated | **NO** |
| Packages installed | **NO** — used the existing `venv` for `psycopg2` |
| Committed | **NO** |
| Pushed | **NO** |

Post-audit verification from a second read-only connection:
`districts = 75`, `constituency = 9`, `voters = 8` — unchanged.
All audit scripts live in the session scratchpad, not in the repository.
