# Step 4D — Hierarchical geo APIs + voter filtering

Date: 2026-09-11. **Application code, tests and documentation only.** No
migration, no schema change, no data write. Every database query in this step
ran inside a `SET TRANSACTION READ ONLY` session.

---

## 1. Audit of the existing geo APIs

The router is mounted at `/geo` (`app/main.py:48`). Before this step it had
three endpoints:

| Endpoint | Query params | Behaviour | Response |
|---|---|---|---|
| `GET /geo/districts` | `search` | `db.query(District)`, `ilike` on English/Hindi name, ordered by name then id | `{districts: [...], total}` with `district_id`, `district_name_en`, `district_name_hi`, `mandal_id` |
| `GET /geo/constituencies` | `district_id`, `search` | `db.query(Constituency)`, optional `district_id` filter, ordered **by name** then id | `{constituencies: [...], total}` with `id`, `constituency`, `constituency_hindi`, `district`, `district_id` |
| `GET /geo/filters` | none | Both queries unfiltered, in one response | `{districts: [...], constituencies: [...]}` |

Findings:

- There was **no states endpoint** and no way to scope districts by State/UT.
- `/geo/constituencies` exposed `id` (the legacy DB primary key) but **not
  `ac_number`**, so a client had no way to show "AC 168" — only "ID 13".
- `/geo/filters` is referenced nowhere in this repository other than its own
  definition. The Flutter client is a separate codebase, so it may still call
  it — **it has been kept working**.
- Unscoped, `/geo/districts` now means 784 rows and `/geo/filters` means
  784 + 3,551 = 4,335 objects in one response.
- All three used the project's existing `success_response(data=…)` envelope and
  `AppException` error convention, which this step reuses unchanged.

---

## 2. Endpoints

All responses use the existing envelope: `{"success": true, "message": "Success", "data": {...}}`.
All require the existing bearer auth (`get_current_user`), unchanged.

### `GET /geo/states` — NEW

| Param | Type | Notes |
|---|---|---|
| `search` | str, optional | Case-insensitive match on English or Hindi name, or an exact `state_code` |

Returns all 36 States/UTs ordered by `state_name_en`, with `state_id` as a
deterministic tiebreaker.

| Field | Notes |
|---|---|
| `state_id` | Primary key; equals the LGD State Code as an integer |
| `state_code` | **Authoritative LGD State Code as TEXT** — `"9"` = Uttar Pradesh |
| `state_name_en` | |
| `state_name_hi` | **`null` for all 36.** No authoritative Hindi source exists and none was fabricated |

### `GET /geo/districts` — UPDATED

| Param | Type | Notes |
|---|---|---|
| `state_id` | int, optional | Restrict to one State/UT. Validated — unknown id → **404 `STATE_NOT_FOUND`** |
| `search` | str, optional | English or Hindi district name, or an exact `lgd_district_code`. **Always applied after the state scope** |

Ordered by `district_name_en`, then `district_id`.

| Field | New? | Notes |
|---|---|---|
| `district_id` | existing | Legacy DB primary key; `voters.district_id` references it |
| `district_name_en`, `district_name_hi`, `mandal_id` | existing | unchanged |
| `lgd_district_code` | **new** | Authoritative LGD District Code, TEXT, globally unique |
| `state_id`, `state_code`, `state_name_en` | **new** | District names are **not** unique across states, so the state is now always visible |

### `GET /geo/constituencies` — UPDATED

| Param | Type | Notes |
|---|---|---|
| `district_id` | int, optional | The normal cascading call. Validated — unknown id → **404 `DISTRICT_NOT_FOUND`** |
| `state_id` | int, optional | **new.** ANDed with `district_id` |
| `ac_number` | int, optional | **new.** Filter by the official ECI AC number |
| `search` | str, optional | English or Hindi AC name, **always scoped to the parent filters** |

**Ordered by `ac_number` ascending**, then `id`.

| Field | New? | Notes |
|---|---|---|
| `id` | existing | Database primary key. **NOT the AC number — never display it as one** |
| `ac_number` | **new** | **The number to display: AC 168, AC 169, …** |
| `constituency`, `constituency_hindi`, `district`, `district_id` | existing | unchanged |
| `state_id`, `state_code`, `lgd_district_code`, `district_name_en` | **new** | |
| `reservation` | **new** | Always `null` today — see §8 |

### `GET /geo/filters` — DEPRECATED, still working

Marked `deprecated=True` so Swagger shows it struck through. Two **optional**
params were added (`state_id`, `district_id`) to scope the payload; with no
params it behaves exactly as before, returning everything. A `states` key was
added alongside the pre-existing `districts` and `constituencies` keys.

---

## 3. Hierarchy

```
State/UT        states.state_id        identity: state_code        (LGD, TEXT)
   |
District        districts.district_id  identity: lgd_district_code (LGD, TEXT)
   |
Assembly        constituency.id        identity: (state_id, ac_number)
Constituency                           display:  ac_number
```

`constituency.id` remains the database primary key because
`voters.assembly_constituency_id` stores it and it is half the voters composite
primary key. Both are returned, separately and unambiguously.

Invariants asserted in tests, on both the fixture and the real data:

- every returned `district.state_id` equals the requested `state_id`
- every returned `constituency.district_id` equals the requested `district_id`
- every returned `constituency.state_id` equals its district's `state_id`
- `state_id` and `district_id` are ANDed, so a mismatched pair returns `[]`, never a leak
- across all 3,551 live rows: 0 constituencies whose `state_id` disagrees with their district's

Worked example, verified live: Uttar Pradesh (`state_code "9"`, `state_id 9`)
→ Lucknow (`district_id 127`, `lgd_district_code "162"`) → **9 ACs, numbers
168–176**, database ids 13–21.

---

## 4. Example requests and responses

Captured from the live database, read-only.

**`GET /geo/states`**

```json
{"success": true, "message": "Success", "data": {
  "states": [
    {"state_id": 35, "state_code": "35", "state_name_en": "Andaman And Nicobar Islands", "state_name_hi": null},
    {"state_id": 28, "state_code": "28", "state_name_en": "Andhra Pradesh", "state_name_hi": null}
  ],
  "total": 36
}}
```

**`GET /geo/districts?state_id=9&search=Lucknow`**

```json
{"success": true, "message": "Success", "data": {
  "districts": [
    {"district_id": 127, "lgd_district_code": "162", "district_name_en": "Lucknow",
     "district_name_hi": "लखनऊ", "state_id": 9, "state_code": "9",
     "state_name_en": "Uttar Pradesh", "mandal_id": null}
  ],
  "total": 1
}}
```

**`GET /geo/constituencies?district_id=127`** — note `id` 20 carries `ac_number` 168

```json
{"success": true, "message": "Success", "data": {
  "constituencies": [
    {"id": 20, "ac_number": 168, "constituency": "Malihabad", "constituency_hindi": "मलिहाबाद",
     "reservation": null, "state_id": 9, "state_code": "9", "district_id": 127,
     "lgd_district_code": "162", "district": "Lucknow", "district_name_en": "Lucknow"},
    {"id": 13, "ac_number": 169, "constituency": "Bakshi Kaa Talab", "constituency_hindi": "बक्शी का तालाब",
     "reservation": null, "state_id": 9, "state_code": "9", "district_id": 127,
     "lgd_district_code": "162", "district": "Lucknow", "district_name_en": "Lucknow"}
  ],
  "total": 9
}}
```

**`GET /geo/districts?state_id=999999`** → HTTP **404**

```json
{"detail": {"code": "STATE_NOT_FOUND", "message": "No State/UT with state_id 999999", "field": "state_id"}}
```

**`GET /geo/constituencies?district_id=999999`** → HTTP **404**,
`{"detail": {"code": "DISTRICT_NOT_FOUND", ...}}`.

A valid-but-empty scope (e.g. `state_id=9&district_id=2404`, a Bihar district)
returns HTTP **200** with `total: 0` — an empty result, not an error.

---

## 5. Voter filter behaviour

`GET /voter/getVoters`, `GET /voter/count` and `GET /voter/export` all gained
the same three **optional** parameters. Every filter is ANDed, as before, and
`apply_voter_filters` is still chained after `get_base_query`, so a filter can
only narrow what the caller's role already permits.

| Param | Meaning |
|---|---|
| `assembly_constituency_id` | **Unchanged.** The legacy `constituency.id` that voters already store. **Not** reinterpreted as an ECI AC number |
| `state_id` | **new.** Voters whose constituency belongs to this State/UT |
| `state_code` | **new.** The same, by LGD State Code (`"9"`) |
| `ac_number` | **new.** Official ECI AC number, offered *separately* so the legacy filter is untouched |

`voters` has no `state_id` column, so the State filter is expressed as a
subquery — "the voter's constituency belongs to this State" — evaluated in the
database against `ix_constituency_state_id`. No row is fetched into Python to
be filtered.

An AC number is only unique **within** a State/UT. Combined with
`state_id`/`state_code` it is exact; on its own it matches that AC number in
every loaded State/UT, which is the correct AND semantics for an independent
filter. Verified live:

| Filter | Voters |
|---|---|
| none | 8 |
| `assembly_constituency_id=14` | **3** |
| `assembly_constituency_id=16` | **5** |
| `ac_number=172` (Lucknow North) | **3** |
| `ac_number=174` (Lucknow Central) | **5** |
| `assembly_constituency_id=172` | **0** — proves the two are not conflated |
| `state_id=9` / `state_code="9"` | 8 |
| every other State/UT | **0 each, all 35 checked** |
| `state_id=<other state>&ac_number=172` | **0** |
| `state_id=9&district_id=127&ac_number=174` | 5 |
| `assembly_constituency_id=14&ac_number=174` | 0 (contradiction, no leak) |

`appliedFilters` in the `getVoters` response now echoes the three new
parameters when supplied, using the existing `_collect_filters` helper that
drops unset values — so a request that omits them produces the identical
payload it did before.

---

## 6. Backward compatibility

**No endpoint removed, no path or method changed, no previously-optional
parameter made required, no response key removed.**

| Change | Impact |
|---|---|
| `GET /geo/states` added | New — no impact |
| `state_id` on `/geo/districts` | Optional; omitting it behaves as before (now 784 rows rather than 75) |
| New fields on districts and constituencies | Additive; existing keys keep their names, types and meaning |
| `/geo/filters` | Still returns `districts` and `constituencies` with the same shape; `states` added; new params optional |
| Voter filters | Three optional params added; `assembly_constituency_id` semantics untouched |

Two deliberate behaviour changes, both explicitly required:

1. **`/geo/constituencies` ordering changed** from `constituency` (name) to
   **`ac_number` ascending**. A client that relied on alphabetical order will
   see a different order. This is required by Task 4 and is the order a user
   expects in an AC picker.
2. **404 on an unknown scoping parent.** `/geo/districts?state_id=` with an
   unknown id, and `/geo/constituencies?district_id=` with an unknown id, now
   return `404` instead of `200` with an empty list. A *valid* parent with no
   children still returns `200` and an empty list.

---

## 7. Performance

All filtering is done in the database. Measured against the live data with
`EXPLAIN ANALYZE`, warm:

| Query | Plan | Time |
|---|---|---|
| districts by `state_id` | index scan on `ix_districts_state_id` | **0.18 ms** |
| constituencies by `district_id` | seq scan over 3,551 rows, 9 returned | **0.5–0.8 ms** |
| constituencies by `state_id` | index scan on `ix_constituency_state_id` | sub-ms |

`constituency.district_id` has **no index** — Postgres does not index FK
columns automatically. I measured before deciding: a cold first touch cost
102 ms, but warm repeats are **0.47–0.75 ms** over a 3,551-row table. That is
well inside a dropdown budget, so **no index was added and no migration was
created**, per Task 11's instruction to inspect first and prefer no schema
change. If the AC table grows by an order of magnitude, the smallest safe
change would be `CREATE INDEX CONCURRENTLY ix_constituency_district_id ON constituency (district_id);`.

No endpoint loads a table into Python to filter it, and none does fuzzy
matching — fuzzy matching remains confined to OCR resolution in
`app/core/constituency_resolver.py`.

---

## 8. Unresolved limitations

| Limitation | Detail |
|---|---|
| **`reservation` is always `null`** | The field is in the response contract so Flutter can code against it, but **the `constituency` table has no `reservation` column** — Step 4B did not add one. The data exists in `data/reference/source/eci_ac_normalised.csv` (596 SC, 530 ST of 4,032). Populating it needs `ALTER TABLE constituency ADD COLUMN reservation TEXT` plus a backfill keyed on `(state_id, ac_number)` — a migration, which this step was instructed not to create. **This is the one item that cannot be delivered without a follow-up migration.** |
| **`state_name_hi` is `null` for all 36** | No authoritative Hindi source; nothing fabricated. Also blocks Devanagari state matching in the resolver (see the Step 4C report) |
| **`district_name_hi` only for the 75 UP districts** | The other 709 have no Hindi, so a Hindi district search only finds UP districts |
| **`constituency_hindi` only for the 9 Lucknow rows** | The ECI 2008 Order contains no Devanagari, so a Hindi AC search only finds those 9 |
| **104 constituencies have `district_id = null`** | 70 Delhi (the Order gives no districts) + 34 with no unambiguous LGD successor. They are reachable via `state_id` but never via `district_id`. A Delhi district picker will appear empty |
| **481 ACs not loaded** | Assam, Andhra Pradesh, Arunachal Pradesh, Nagaland, Manipur; plus J&K's 90 which do not exist in the dataset. Those states return districts but zero constituencies |
| **`/geo/districts` and `/geo/filters` are unpaginated** | Unscoped they return 784 and 4,335 objects. Kept that way for backward compatibility; pagination would change the response shape |
| **`mandal_id` is `null` everywhere** | No mandal table and no source; the column is passed through unchanged |
| **`voters.state` free-text filter unchanged** | Still an `ilike` on the denormalised Devanagari string. The new `state_id`/`state_code` filters are the reliable ones |

---

## 9. Tests

```
$ venv/Scripts/python.exe -m unittest discover -s tests -t .
Ran 107 tests in 0.527s
OK (skipped=37)

$ PRAMAAN_LIVE_DB_TESTS=1 venv/Scripts/python.exe -m unittest discover -s tests -t .
Ran 107 tests in 15.201s
OK

$ venv/Scripts/python.exe -m compileall -q app tests
OK
```

70 hermetic tests run by default; the 37 live tests are opt-in via
`PRAMAAN_LIVE_DB_TESTS=1`.

New in this step: `tests/test_geo_api.py` (36 hermetic, in-memory SQLite +
FastAPI `TestClient`) and `tests/test_geo_voter_filters_live.py` (23 read-only
against production).

`tests/test_geo_api.py` deliberately does **not** import `app.main`: that would
run `Base.metadata.create_all(bind=engine)` against the production database. It
builds a minimal app carrying only the geo router and overrides `get_db` and
`get_current_user`.

Coverage against the brief's A–L:

| | Case | Test |
|---|---|---|
| A | `/geo/states` returns all states | `test_A_states_endpoint_returns_all_states`, `test_A2_states_are_ordered_by_english_name`, `test_A3_state_name_hi_is_null_not_fabricated`; live `test_states_query_returns_36` |
| B | UP present with `state_code "9"` | `test_B_uttar_pradesh_present_with_state_code_9`; live `test_uttar_pradesh_state_code` |
| C | Districts scoped to state | `test_C_districts_scoped_to_state`, `test_C2_other_state_districts_absent`, `test_C3_district_response_fields`, `test_C4_unknown_state_id_is_404`; live `test_up_districts_are_75_and_all_belong_to_up` |
| D | Lucknow LGD code `"162"` | `test_D_lucknow_has_lgd_code_162`; live `test_lucknow_lgd_code` |
| E | Lucknow returns exactly 9 ACs | `test_E_lucknow_returns_exactly_nine_constituencies`; live `test_lucknow_has_nine_acs_numbered_168_to_176` |
| F | AC numbers 168–176 | `test_F_ac_numbers_are_168_to_176_ascending`, `test_F2_id_is_exposed_separately_and_is_not_the_ac_number`, `test_F3_constituency_response_fields` |
| G | No AC from another district | `test_G_no_constituency_from_another_district`, `test_G2_no_constituency_from_another_state`, `test_G3_unknown_district_id_is_404`, `test_G4_state_and_district_are_anded_no_cross_scope_result`; live `test_no_cross_district_or_cross_state_leakage` |
| H | AC 172 filter returns 3 | live `test_filter_by_ac_number_172_returns_three` |
| I | AC 174 filter returns 5 | live `test_filter_by_ac_number_174_returns_five` |
| J | Combined filters do not leak | live `test_combined_filters_are_anded_and_do_not_leak`, `test_no_voter_appears_under_another_states_constituency` (all 36 States/UTs), `test_ac_number_in_another_state_returns_no_voters`, `test_legacy_assembly_constituency_id_is_not_the_ac_number` |
| K | Existing behaviour compatible | `test_K_districts_without_state_id_still_works`, `test_K2_legacy_district_fields_still_present`, `test_K3`, `test_K4_legacy_constituency_fields_still_present`, `test_K5_filters_endpoint_still_returns_its_original_keys`, `test_K6_filters_endpoint_can_be_scoped`, `test_K7_district_id_filter_on_constituencies_unchanged` |
| L | Search is parent-scoped | `test_L_district_search_is_scoped_to_the_state`, `test_L2_district_search_matches_hindi`, `test_L3_constituency_search_is_scoped_to_the_district`, `test_L4_constituency_search_is_scoped_to_the_state`, `test_L5_constituency_search_matches_hindi`, `test_L6_ac_number_filter`, `test_L7_state_search` |

Plus hierarchy invariants (`test_hierarchy_invariants_hold_for_every_state`,
`test_ac_numbers_unique_within_a_state`) and safety
(`test_no_voters_table_exists_in_the_test_database`,
`test_test_database_is_in_memory`).

### Production read-only verification

| Check | Result |
|---|---|
| `states` | **36** ✅ |
| `districts` | **784** ✅ |
| `constituency` | **3,551** ✅ |
| `voters` | **8** ✅ |
| Constituency ids 13–21 intact | ✅ |
| District ids 79–153 intact (75 rows) | ✅ |
| Voter PKs unchanged (all 8 UUID + `ac_id` pairs) | ✅ |
| Voter reference distribution `{14: 3, 16: 5}` | ✅ |
| Counts re-checked after the whole class ran | ✅ |
| Production voter writes | **none** |

---

## 10. OpenAPI / Swagger

FastAPI generates the schema automatically; no separate document was written.
Verified to generate cleanly (OpenAPI 3.1.0) with summaries, per-parameter
descriptions, and `/geo/filters` marked `deprecated`. Pydantic response models
(`StateOut`, `DistrictOut`, `ConstituencyOut`) document the shape of `data`,
including explicit notes that `id` is not the AC number and that
`reservation`, `state_name_hi` and the Hindi columns may be null.

---

## 11. Files changed

| File | Change |
|---|---|
| `app/api/routes/geo.py` | Rewritten: `/geo/states` added; `state_id` scoping on districts; `ac_number`/`state_id` on constituencies with `ac_number` ordering; parent validation; response models; `/geo/filters` deprecated but preserved |
| `app/services/vote_service.py` | `apply_voter_filters` gains `state_id`, `state_code`, `ac_number` as database-side subquery filters |
| `app/api/routes/voter.py` | The three filtering endpoints accept and pass through the new params; `appliedFilters` echoes them |
| `tests/test_geo_api.py` | New — 36 hermetic endpoint tests |
| `tests/test_geo_voter_filters_live.py` | New — 23 read-only live tests |
| `docs/step-4d-geo-api-report.md` | This document |

No model, migration, seeder, reference CSV or baseline CSV was touched.

---

## 12. Safety

| Item | Status |
|---|---|
| Database data modified | **NO** — all sessions `SET TRANSACTION READ ONLY`, verified `on` |
| Voters modified | **NO** — 8 rows, PKs verified identical |
| Reference rows modified | **NO** — 36 / 784 / 3,551 unchanged |
| Migration created | **NO** — measured first; existing indexes are sufficient |
| Seeder executed | **NO** |
| Baseline modified | **NO** |
| Reference CSVs modified | **NO** |
| Hindi fabricated | **NO** |
| Packages installed | **NO** — `fastapi.testclient`/`httpx` were already present |
| Committed | **NO** |
| Pushed | **NO** |
