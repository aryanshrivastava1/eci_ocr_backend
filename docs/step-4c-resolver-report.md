# Step 4C — India-wide constituency resolution

Date: 2026-09-11. Application code, tests and documentation only. **The database
was not modified** — every query in this step ran in a `SET TRANSACTION READ ONLY`
session.

One correction to the brief: the resolver is at **`app/core/constituency_resolver.py`**,
not `app/services/`. There is no `app/services/constituency_resolver.py`.

---

## 1. Old unsafe behaviour

### 1.1 `resolve_constituency()` — `app/core/constituency_resolver.py`

```python
rows = db.query(Constituency).all()              # line 31 — every row
hindi_names = [r.constituency_hindi for r in rows]
top = process.extract(raw_value, hindi_names, scorer=fuzz.partial_ratio, limit=5)
if not top or top[0][1] < 65: return None, None
if len(top) >= 2 and top[1][1] == top[0][1]: return None, None
```

- Loaded **all 3,551 constituency rows into Python on every OCR job**.
- Fuzzy-matched globally at threshold 65, with no state or district filter.
- Took the top score with no check on which State/UT it belonged to.
- Received no state or district even though `parse_smart()` already extracts both.

Measured, not assumed: `rapidfuzz.process.extract` silently **skips `None`
choices**, so after Step 4B this function did not crash — it could only ever
match the 9 Lucknow rows that carry Hindi, while paying to fetch 3,551 rows per
job. The latent danger was the moment Hindi gets loaded nationwide, at which
point a global fuzzy match would start crossing state boundaries.

### 1.2 `POST /voters/save` — `app/api/routes/voter.py`

```python
name = payload.assembly_constituency_name.strip().lower()
constituency = (db.query(Constituency)
                  .filter(or_(func.lower(Constituency.constituency_hindi) == name,
                              func.lower(Constituency.constituency) == name))
                  .first())                      # arbitrary row
```

This was a **live correctness risk**, not a latent one. Measured against the
loaded data: **83 English AC names are duplicated across States/UTs, spanning
185 rows.** `Ramnagar` and `Patan` each exist in 4 states; `Pratapgarh`,
`Fatehpur`, `Bilaspur`, `Islampur`, `Khanapur`, `Chhatarpur`, `Rajnagar`,
`Gopalpur` and `Dharampur` each in 3. For any of those, `.first()` picked an
arbitrary row and wrote its `constituency.id` into
`voters.assembly_constituency_id` **and** its `district_id` into the voter — so a
voter could be attached to a same-named constituency in the wrong State,
silently. Line 215's EPIC de-duplication check inherited the same wrong id.

`Kalyanpur` was worse still: it exists once in Uttar Pradesh and **twice in
Bihar, in two different districts**, so even a State was not enough to pick it.

---

## 2. New resolution hierarchy

A single shared resolver, used by both the OCR workers and voter save:

```
1. state     — explicit LGD state_code wins; else the state name
               (states.state_name_en / states.state_name_hi)
2. district  — explicit LGD district code wins; else the district name
               (district_name_en / district_name_hi), restricted to the state
               when one is known. A resolved district determines its state, so
               a district name alone yields a full state+district scope.
3. exact constituency-name match, evaluated in PostgreSQL, inside that scope
4. fuzzy match — inside that scope only
```

Authoritative identifiers throughout: `states.state_code` (LGD State Code,
TEXT), `districts.lgd_district_code` (LGD District Code, TEXT), and
`(state_id, ac_number)` for an AC. `constituency.id` remains the primary key
that `voters.assembly_constituency_id` references. **The resolver never writes
to any table.**

### Scoping rules, exactly as implemented

| Available | Candidate set |
|---|---|
| district (code or name) | that district only — 9 rows for Lucknow |
| state only | that State/UT only — at most 403 rows (Uttar Pradesh) |
| neither | exact match only if globally unique; fuzzy only via a SQL-narrowed pool whose plausible candidates all belong to one state |

A district name that matches in more than one state without a state scope
(`Bilaspur` exists in both Himachal Pradesh and Chhattisgarh) is reported
ambiguous and the district scope is dropped rather than guessed. A state and a
district that contradict each other (`state_code=9` with a Bihar district code)
returns `unresolved_scope_conflict` — no winner is picked.

### Threshold

`_MATCH_THRESHOLD` is **unchanged at 65**, and the original "an exact tie at the
top means ambiguous" rule is preserved verbatim. Scoping, not a looser
threshold, is what makes resolution work at national scale. Nothing was lowered
to increase the match rate.

---

## 3. Ambiguity handling

`resolve()` returns a `Resolution` with one of five statuses. `.first()` is never
used to break a tie, and `match` is `None` on every unresolved status.

| Status | When |
|---|---|
| `resolved` | exactly one candidate survived |
| `unresolved_not_found` | nothing matched within the scope |
| `unresolved_ambiguous` | several candidates survived — they are all returned |
| `unresolved_scope_required` | the unscoped search would be too broad to answer safely |
| `unresolved_scope_conflict` | the supplied state and district contradict each other |

Every unresolved result carries `reason` (what went wrong) and `required` (which
identity the caller should supply — never a guess at its value) plus the full
candidate list, so the caller can present a choice.

### Task 5 — OCR with a constituency name and nothing else

| Case | Behaviour |
|---|---|
| exact unique global match | **resolves** (`Bakshi Kaa Talab` → AC 169) |
| multiple global matches | `unresolved_ambiguous`, all candidates returned |
| fuzzy match plausible in several states | `unresolved_ambiguous`, `required: ["state_code"]` |
| misspelling with no scope | `unresolved_not_found` with `required: ["state_code"]` — the SQL pool is narrowed by a token of the input, so a misspelling finds nothing rather than being matched across four states |
| arbitrary `.first()` | **never** |

No State or District is ever fabricated to make a lookup succeed.

---

## 4. Performance

Filtering happens in PostgreSQL; only the narrowed set reaches Python.

| Scenario | Rows into Python — before | after |
|---|---|---|
| District-scoped (Lucknow, the live OCR path) | 3,551 | **9** |
| State-scoped (Uttar Pradesh, the largest) | 3,551 | **403** |
| Exact match at any scope | 3,551 | **1** (resolved in SQL) |
| Unscoped | 3,551 | SQL-narrowed, hard-capped at 200 — refused if broader |

Measured against the live database (read-only), on the current remote connection:

```
district-scoped (Lucknow, Hindi)   4 queries  129.9ms -> resolved AC 174
state-scoped exact (UP)            2 queries   58.2ms -> resolved AC 211
state-scoped fuzzy (UP)            3 queries  141.7ms -> resolved AC 211
unscoped globally-unique           1 query     32.0ms -> resolved AC 169
unscoped duplicate (refused)       1 query     30.0ms -> unresolved_ambiguous
```

An exact match — the common case — is now a single indexed query returning one
row. The Step 4B indexes `ix_constituency_state_id`, `ix_constituency_ac_number`
and `ix_districts_state_id` support these lookups.

---

## 5. API compatibility impact

**No breaking change. No endpoint, path, method or required field changed.**

| Surface | Change |
|---|---|
| `POST /voters/save` | Same path and same required fields. `VoterCreate` gains two **optional** fields, `state_code` and `district_lgd_code`. Existing callers that send only names keep working |
| `PUT /voters/{voter_id}` | Unchanged, `ac_id` still the query parameter |
| `GET /voters`, export, count | Unchanged |
| `GET /districts`, `/constituencies`, `/filters` | Unchanged |
| OCR job result shape | Unchanged. `resolve_constituency()` keeps its `(constituency_hindi, district_name_hi)` return and its two-argument signature; state/district are additive keyword arguments |
| `AppException` | Gains an optional `data` kwarg. It is added to `detail` **only when supplied**, so every existing error response keeps its exact previous shape |

The existing state and district information was already available and is now
simply used: `VoterCreate` already had `district` and `state`, and
`parse_smart()` already emits `state` and `district`. The two new optional
fields are the smallest addition that lets a caller be unambiguous where a name
alone cannot be.

### New error code

`POST /voters/save` previously answered every failure with
`INVALID_CONSTITUENCY`. It still does when the name genuinely does not exist.
Ambiguity, over-broad scope and state/district conflict now return
**`AMBIGUOUS_CONSTITUENCY`** (also HTTP 400) with the candidate list.

---

## 6. Exact API behaviour for ambiguous constituency resolution

`POST /voters/save` with `assembly_constituency_name: "Ramnagar"` and no state
or district — real response, generated against the live data:

```json
{
  "detail": {
    "code": "AMBIGUOUS_CONSTITUENCY",
    "message": "Assembly constituency could not be resolved unambiguously: 4 constituencies share the name 'Ramnagar' within global scope. Supply state_code or district_lgd_code to disambiguate.",
    "field": "assembly_constituency_name",
    "data": {
      "status": "unresolved_ambiguous",
      "scope": "global",
      "state_code": null,
      "district_lgd_code": null,
      "method": "exact",
      "score": null,
      "reason": "4 constituencies share the name 'Ramnagar' within global scope",
      "required": ["state_code", "district_lgd_code"],
      "match": null,
      "candidates": [
        {"constituency_id": 11337, "state_code": "10", "state_name_en": "Bihar",
         "ac_number": 2, "constituency": "Ramnagar", "constituency_hindi": null,
         "district_lgd_code": "211", "district_name_en": "Pashchim Champaran"},
        {"constituency_id": 11594, "state_code": "16", "state_name_en": "Tripura",
         "ac_number": 7, "constituency": "RAMNAGAR", "constituency_hindi": null,
         "district_lgd_code": "272", "district_name_en": "West Tripura"},
        {"constituency_id": 11872, "state_code": "19", "state_name_en": "West Bengal",
         "ac_number": 217, "constituency": "RAMNAGAR", "constituency_hindi": null,
         "district_lgd_code": "317", "district_name_en": "Purba Medinipur"},
        {"constituency_id": 13138, "state_code": "5", "state_name_en": "Uttarakhand",
         "ac_number": 61, "constituency": "Ramnagar", "constituency_hindi": null,
         "district_lgd_code": "51", "district_name_en": "Nainital"}
      ]
    }
  }
}
```

HTTP status **400**. `match` is `null` and no voter row is written. Re-sending
the same request with `"state_code": "5"` resolves to Uttarakhand AC 61 and
saves normally.

The OCR path returns `(None, None)` for the same input, which the workers
already handle by clearing `assembly_constituency` and setting its confidence
to `0.0` — the existing "retake the scan / pick a constituency" behaviour.

---

## 7. Tests

`tests/test_constituency_resolver.py` — **34 hermetic tests**, in-memory SQLite.
They never open `DATABASE_URL` and never create a `voters` table, so no voter
row can be read or written by them. The fixture mirrors rows that really exist,
so the ambiguity under test is the real ambiguity.

`tests/test_resolver_live_readonly.py` — **14 read-only tests** against the
production data, skipped unless `PRAMAAN_LIVE_DB_TESTS=1`. Each sets
`SET TRANSACTION READ ONLY` and asserts it is `on` before querying; teardown
rolls back. No `INSERT`/`UPDATE`/`DELETE` appears in the file.

```
$ venv/Scripts/python.exe -m unittest discover -s tests -t .
Ran 48 tests in 0.141s
OK (skipped=14)

$ PRAMAAN_LIVE_DB_TESTS=1 venv/Scripts/python.exe -m unittest tests.test_resolver_live_readonly
Ran 14 tests in 6.270s
OK

$ venv/Scripts/python.exe -m compileall -q app tests migrations scripts
OK
```

Coverage against the brief's A–H:

| | Case | Test |
|---|---|---|
| A | Existing Lucknow AC resolves | `test_A_existing_lucknow_ac_resolves`, `test_A2_all_nine_legacy_lucknow_acs_resolve` (all 9, by English and Hindi), `test_A3_legacy_cantonment_name_still_resolves` |
| B | Same name in two states, state provided | `test_B_same_name_two_states_state_selects_correctly`, `test_B2_state_by_english_name`, `test_B3_ramnagar_each_of_four_states`, `test_B4_state_alone_insufficient_when_name_repeats_in_state` |
| C | Same name in multiple districts, district provided | `test_C_same_name_two_districts_district_selects_correctly`, `test_C2_district_name_alone_carries_the_state`, `test_C3_duplicate_district_name_without_state_is_not_guessed`, `test_C4_state_district_conflict_is_refused` |
| D | Duplicate global name, no scope → ambiguous, never `.first()` | `test_D_duplicate_global_name_without_scope_is_ambiguous`, `test_D2_ramnagar_without_scope_is_ambiguous_across_four_states`, `test_D3_legacy_wrapper_returns_none_on_ambiguity`, and live `test_every_duplicate_english_name_is_refused_unscoped` — asserts **all 83 real duplicated names** refuse to resolve unscoped |
| E | Unique global constituency still resolves | `test_E_globally_unique_name_resolves_without_scope`, `test_E2_globally_unique_hindi_name_resolves_without_scope`, `test_E3_unknown_name_is_not_found` |
| F | Fuzzy candidates are state/district scoped | `test_F_fuzzy_candidates_are_state_scoped`, `test_F2_fuzzy_candidates_are_district_scoped`, `test_F3_noisy_hindi_resolves_within_the_district`, `test_F4_bare_lucknow_still_ties_and_stays_unresolved`, `test_F5_threshold_unchanged`, `test_F6_misspelling_without_scope_never_guesses`, `test_F6b_unscoped_fuzzy_spanning_states_is_ambiguous`, `test_F7_devanagari_is_preserved_not_transliterated`, `test_F8_nfc_normalisation_is_applied` |
| G | Existing voter save flow still works | `test_G_voter_save_payload_shape_resolves` (the exact payload the endpoint builds), `test_G2`, `test_G3_voter_save_ambiguous_payload_yields_actionable_error`, `test_G4_missing_name_is_rejected`, `test_G5_row_without_district_attribution_still_resolves`, and live `test_lucknow_voter_flow_resolves_to_the_live_rows` |
| H | No voter data changed | `test_H_no_voters_table_exists_in_the_test_database` (structural proof), `test_H2_test_database_is_in_memory_not_production`, `test_H3_reference_rows_unchanged_by_the_test_run` |

### Production verification (read-only)

| Check | Result |
|---|---|
| `states` | **36** ✅ |
| `districts` | **784** ✅ |
| `constituency` | **3,551** ✅ |
| `voters` | **8** ✅ |
| Voter PKs unchanged (all 8 UUID + `ac_id` pairs) | ✅ |
| Voter reference distribution `{14: 3, 16: 5}` | ✅ |
| Constituency ids 13–21 unchanged | ✅ |
| District ids 79–153 unchanged (75 rows) | ✅ |
| Counts re-checked after the whole class ran | ✅ |

---

## 8. Normalisation

`_norm()` NFC-normalises, collapses whitespace and case-folds — **for comparison
only**. No stored value is rewritten, nothing is transliterated, and Devanagari
is never stripped. `test_F7` asserts the matched Hindi comes back intact;
`test_F8` asserts an NFD-decomposed input matches its NFC-stored row.

Two Devanagari label prefixes are stripped before comparison, because OCR
routinely includes them: `जिला :` / `District:` on a district, and
`विधान सभा (निर्वाचन) क्षेत्र` / `Assembly Constituency` on an AC. Stripping is
applied to the *input* only.

---

## 9. Unresolved cases

| Case | Status and why |
|---|---|
| **A Devanagari State name cannot scope a lookup** | `states.state_name_hi` is NULL for all 36 rows — no authoritative Hindi State source has been established, and none was invented here. The matching branch is already in place, so this starts working the moment authoritative Hindi is loaded. Until then the **district** name carries the state, which is the live UP/Lucknow path. |
| **AC Hindi exists for only 9 of 3,551 rows** | The ECI 2008 Order contains no Devanagari. A Hindi AC name can therefore only resolve inside Lucknow today. OCR reads Hindi cards, so nationwide OCR resolution needs an authoritative Hindi AC source — the single biggest remaining gap. |
| **Hindi for the 709 new districts** | NULL, so a Devanagari district name only scopes the 75 UP districts today. |
| **104 rows with NULL `district_id`** | 70 Delhi (the Order gives no districts) + 34 `needs_review`. They resolve by state and name; district scoping cannot reach them. `test_G5` covers this. |
| **481 withheld ACs** | Assam, Andhra Pradesh, Arunachal Pradesh, Nagaland and Manipur have no rows, so nothing in them can resolve. The live test asserts 0 rows for each. |
| **Unscoped misspellings** | Return `unresolved_not_found` with `required: ["state_code"]`. Safe, but a caller supplying only a misspelled name gets no fuzzy help — deliberate, since fuzzy across four states is exactly what must not happen. |
| **`GET /districts` / `GET /constituencies` are still unscoped** | Not in this step's scope. `/districts` returns all 784 with no state label, so duplicate district names are indistinguishable in a dropdown, and `/constituencies` returns all 3,551 without a `district_id`. Recommended next: expose `state_code`/`ac_number` in the serialisers and accept a state filter. |
| **`app/db/base_model.py` still omits `Voter`** | Unchanged from Step 4B; noted, not touched. |

---

## 10. Files changed

| File | Change |
|---|---|
| `app/core/constituency_resolver.py` | Rewritten: scoped resolution, `Resolution`/`Candidate`/`Scope` types, SQL-side filtering, ambiguity reporting; `resolve_constituency()` kept as a backward-compatible wrapper |
| `app/api/routes/voter.py` | `POST /voters/save` now uses the shared resolver instead of a table-wide `lower(name)` → `.first()`; returns `AMBIGUOUS_CONSTITUENCY` with candidates |
| `app/schemas/voter.py` | `VoterCreate` gains optional `state_code` and `district_lgd_code` |
| `app/utils/exceptions.py` | `AppException` gains an optional `data` kwarg, included in `detail` only when supplied |
| `app/workers/ocr_worker.py` | Passes the parser's `state` and `district` into the resolver |
| `app/workers/colab_ocr_worker.py` | Same |
| `tests/__init__.py` | New — makes `tests` a package for `unittest discover` |
| `tests/test_constituency_resolver.py` | New — 34 hermetic tests |
| `tests/test_resolver_live_readonly.py` | New — 14 read-only live-data tests |
| `docs/step-4c-resolver-report.md` | This document |

No model, migration, seeder, reference CSV or baseline CSV was touched.

---

## 11. Safety

| Item | Status |
|---|---|
| Database modified | **NO** — every session used `SET TRANSACTION READ ONLY`, verified `on` |
| Voters modified | **NO** — 8 rows, PKs verified identical |
| Models modified | **NO** |
| Migrations modified | **NO** |
| Seeders modified / executed | **NO** |
| Baseline CSVs modified | **NO** |
| Reference CSVs modified | **NO** |
| Production reference rows modified | **NO** — states 36, districts 784, constituency 3,551 unchanged |
| Hindi fabricated | **NO** — in particular, no Hindi State names were invented to make state scoping work |
| Packages installed | **NO** — `rapidfuzz` was already present; tests use stdlib `unittest` (no pytest available) |
| Committed | **NO** |
| Pushed | **NO** |
