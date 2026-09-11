-- =====================================================================
-- Migration 0001 — India-wide reference data: states table + authoritative
--                  LGD/ECI identity columns on districts and constituency.
--
-- Applied by: migrations/run_migration_0001.py (single transaction)
-- Rollback   : migrations/0001_rollback.sql
--
-- PROPERTIES
--   * Additive only. No DROP TABLE, TRUNCATE or DELETE anywhere.
--   * Every statement is IF NOT EXISTS / idempotent, so a re-run is a no-op.
--   * districts.district_id, constituency.id and the voters table are never
--     modified by this file. voters is not referenced at all.
--
-- The file is split into numbered sections. The runner executes sections
-- DDL_EARLY and DDL_LATE at different points, with data backfill, the
-- Phase 7 validation gate and the Phase 8 load in between.
-- =====================================================================


-- ---------------------------------------------------------------------
-- @section DDL_EARLY  (Phase 2 + Phase 3)
-- ---------------------------------------------------------------------

-- Migration bookkeeping. There is no Alembic in this project and no package
-- may be installed, so applied migrations are recorded here instead.
CREATE TABLE IF NOT EXISTS schema_migrations (
    version     TEXT PRIMARY KEY,
    applied_at  TIMESTAMP NOT NULL DEFAULT now(),
    description TEXT
);

-- Phase 2 — states.
-- state_id is the LGD State Code as an integer, and state_code is the same
-- code as TEXT. Using the LGD code rather than a fresh serial keeps state_id
-- stable and meaningful, and makes this migration re-runnable: a second run
-- computes the same state_id for the same State/UT. No ISO code, no postal
-- abbreviation, no Census code is used as the identifier.
CREATE TABLE IF NOT EXISTS states (
    state_id       INTEGER PRIMARY KEY,
    state_code     TEXT    NOT NULL,
    state_name_en  TEXT    NOT NULL,
    state_name_hi  TEXT,
    source         TEXT,
    source_version TEXT
);

-- Phase 10 (safe to create now — the table is empty or already correct).
CREATE UNIQUE INDEX IF NOT EXISTS ux_states_state_code
    ON states (state_code);

-- Phase 3 — nullable identity/provenance columns on districts.
ALTER TABLE districts ADD COLUMN IF NOT EXISTS state_id          INTEGER;
ALTER TABLE districts ADD COLUMN IF NOT EXISTS lgd_district_code TEXT;
ALTER TABLE districts ADD COLUMN IF NOT EXISTS source            TEXT;
ALTER TABLE districts ADD COLUMN IF NOT EXISTS source_version    TEXT;

-- Phase 3 — nullable identity/provenance columns on constituency.
-- constituency.id is deliberately left as the primary key: voters reference
-- it through voters.assembly_constituency_id, which is half the voters
-- primary key. The authoritative AC identity is (state_id, ac_number),
-- carried alongside, never replacing the surrogate key.
ALTER TABLE constituency ADD COLUMN IF NOT EXISTS state_id           INTEGER;
ALTER TABLE constituency ADD COLUMN IF NOT EXISTS lgd_district_code  TEXT;
ALTER TABLE constituency ADD COLUMN IF NOT EXISTS ac_number          INTEGER;
ALTER TABLE constituency ADD COLUMN IF NOT EXISTS source             TEXT;
ALTER TABLE constituency ADD COLUMN IF NOT EXISTS source_version     TEXT;
ALTER TABLE constituency ADD COLUMN IF NOT EXISTS mapping_confidence TEXT;

-- constituency.district_id already exists and is already nullable, with
-- FK constituency_district_id_fkey -> districts(district_id). Kept as is.

-- Two NOT NULL constraints block the Phase 8 load and must be relaxed.
--
--   "Constituency_Hindi": the ECI 2008 Order contains zero Devanagari
--   characters, so none of the incoming rows has a Hindi name. Inserting
--   them would fail outright, and inserting '' instead would poison
--   constituency_resolver.resolve_constituency(), which fuzzy-matches on
--   exactly this column. NULL is the honest value; no Hindi is fabricated.
--
--   "District": free-text duplicate of the district name. ECI gives Delhi no
--   district at all, and 34 further headings have no unambiguous LGD
--   successor, so this cannot be populated for every incoming row.
ALTER TABLE constituency ALTER COLUMN "Constituency_Hindi" DROP NOT NULL;
ALTER TABLE constituency ALTER COLUMN "District"           DROP NOT NULL;


-- ---------------------------------------------------------------------
-- @section DDL_LATE  (Phase 9 + Phase 10)
-- Executed only after Phase 7 validation and the Phase 8 load have both
-- passed. Splitting it this way means no constraint is ever added over
-- data that has not been verified.
-- ---------------------------------------------------------------------

-- Phase 9 — foreign keys, added NOT VALID then validated separately so the
-- exclusive lock is held only for the catalogue change and validation can
-- fail without blocking writes.
-- constituency.district_id -> districts.district_id already exists.
ALTER TABLE districts
    ADD CONSTRAINT districts_state_id_fkey
    FOREIGN KEY (state_id) REFERENCES states (state_id) NOT VALID;
ALTER TABLE districts VALIDATE CONSTRAINT districts_state_id_fkey;

ALTER TABLE constituency
    ADD CONSTRAINT constituency_state_id_fkey
    FOREIGN KEY (state_id) REFERENCES states (state_id) NOT VALID;
ALTER TABLE constituency VALIDATE CONSTRAINT constituency_state_id_fkey;

-- No FK is added on voters.assembly_constituency_id. It is half the voters
-- composite primary key and is exposed as the ac_id query parameter on
-- PUT /voters/{voter_id}; constraining it is a separate, reviewable change.
-- The voters primary key structure is untouched by this migration.

-- Supporting indexes for the state/district-scoped lookups that Step 4C needs
-- (see PHASE 11 in docs/step-4b-migration-report.md). Without these, a
-- state-scoped constituency query over 3,551 rows is a sequential scan.
CREATE INDEX IF NOT EXISTS ix_districts_state_id     ON districts (state_id);
CREATE INDEX IF NOT EXISTS ix_constituency_state_id  ON constituency (state_id);
CREATE INDEX IF NOT EXISTS ix_constituency_ac_number ON constituency (ac_number);

-- Phase 10 — uniqueness on the authoritative identities.
--
-- districts: LGD District Code is globally unique. District NAMES are not
-- unique across states, so no name-based constraint is created.
CREATE UNIQUE INDEX IF NOT EXISTS ux_districts_lgd_district_code
    ON districts (lgd_district_code);

-- constituency: the authoritative AC identity. Written as a partial index so
-- that any row which has not yet been given an identity can coexist during a
-- future transition instead of blocking the constraint. The runner asserts
-- that zero rows are currently excluded by the predicate.
-- Constituency NAMES are deliberately left non-unique.
CREATE UNIQUE INDEX IF NOT EXISTS ux_constituency_state_ac
    ON constituency (state_id, ac_number)
    WHERE state_id IS NOT NULL AND ac_number IS NOT NULL;


-- ---------------------------------------------------------------------
-- @section DDL_NOT_NULL  (Phase 10, last)
-- Promoted to NOT NULL only after the runner has verified that every row in
-- each table carries the value. Guarded per statement by the runner.
-- ---------------------------------------------------------------------
ALTER TABLE districts    ALTER COLUMN state_id          SET NOT NULL;
ALTER TABLE districts    ALTER COLUMN lgd_district_code SET NOT NULL;
ALTER TABLE constituency ALTER COLUMN state_id          SET NOT NULL;
ALTER TABLE constituency ALTER COLUMN ac_number         SET NOT NULL;
