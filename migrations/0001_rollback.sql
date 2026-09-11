-- =====================================================================
-- ROLLBACK for migration 0001 — India-wide reference data.
--
-- Run ONLY with intent. This is not part of any successful migration path.
--
-- Two important facts about what can and cannot be undone automatically:
--
--  (a) EVERYTHING ADDITIVE IS REVERSIBLE HERE. The states table, the added
--      columns, the foreign keys and the indexes are dropped below. The rows
--      inserted into districts and constituency are removed by the ONE
--      identity rule that cannot touch legacy data: district_id > 153 and
--      constituency.id > 21. Those ranges are provably disjoint from the
--      legacy rows (districts 79-153, constituency 13-21) because both
--      sequences were already past them before the migration ran.
--
--  (b) ONE CHANGE IS NOT AUTOMATICALLY REVERSIBLE: Phase 5 rewrote
--      districts.district_name_en for 6 rows to the LGD canonical spelling.
--      The pre-migration values are recorded in
--          migrations/snapshots/0001_india_wide_reference_data_pre.json
--      and are restored by section R4 below. Do not skip R4 if the legacy
--      spellings matter to a consumer.
--
-- The voters table is not referenced anywhere in this file. No voter row is
-- read, written or deleted by the rollback.
-- =====================================================================

BEGIN;

-- R1 — drop the constraints and indexes added by the migration.
ALTER TABLE districts    DROP CONSTRAINT IF EXISTS districts_state_id_fkey;
ALTER TABLE constituency DROP CONSTRAINT IF EXISTS constituency_state_id_fkey;

DROP INDEX IF EXISTS ux_constituency_state_ac;
DROP INDEX IF EXISTS ux_districts_lgd_district_code;
DROP INDEX IF EXISTS ix_constituency_ac_number;
DROP INDEX IF EXISTS ix_constituency_state_id;
DROP INDEX IF EXISTS ix_districts_state_id;

ALTER TABLE districts    ALTER COLUMN state_id          DROP NOT NULL;
ALTER TABLE districts    ALTER COLUMN lgd_district_code DROP NOT NULL;
ALTER TABLE constituency ALTER COLUMN state_id          DROP NOT NULL;
ALTER TABLE constituency ALTER COLUMN ac_number         DROP NOT NULL;

-- R2 — remove the rows this migration inserted, and only those.
--      Guard first: this must delete exactly the rows the migration added.
--      Run the two SELECTs and confirm the counts before the DELETEs.
--        select count(*) from constituency where id > 21;            -- expect 3542
--        select count(*) from districts    where district_id > 153;  -- expect 709
--      Constituency rows must go first: districts is their FK parent.
DELETE FROM constituency WHERE id > 21;
DELETE FROM districts    WHERE district_id > 153;

-- R3 — drop the added columns and the states table.
ALTER TABLE constituency DROP COLUMN IF EXISTS mapping_confidence;
ALTER TABLE constituency DROP COLUMN IF EXISTS source_version;
ALTER TABLE constituency DROP COLUMN IF EXISTS source;
ALTER TABLE constituency DROP COLUMN IF EXISTS ac_number;
ALTER TABLE constituency DROP COLUMN IF EXISTS lgd_district_code;
ALTER TABLE constituency DROP COLUMN IF EXISTS state_id;

ALTER TABLE districts DROP COLUMN IF EXISTS source_version;
ALTER TABLE districts DROP COLUMN IF EXISTS source;
ALTER TABLE districts DROP COLUMN IF EXISTS lgd_district_code;
ALTER TABLE districts DROP COLUMN IF EXISTS state_id;

DROP TABLE IF EXISTS states;

-- R4 — restore the 6 district English names Phase 5 rewrote, and the two
--      NOT NULL constraints Phase 3 relaxed. These values come from
--      migrations/snapshots/0001_india_wide_reference_data_pre.json.
UPDATE districts SET district_name_en = 'Barabanki'                    WHERE district_id = 92;
UPDATE districts SET district_name_en = 'Bhadohi (Sant Ravidas Nagar)' WHERE district_id = 95;
UPDATE districts SET district_name_en = 'Lakhimpur Kheri'              WHERE district_id = 125;
UPDATE districts SET district_name_en = 'Maharajganj'                  WHERE district_id = 128;
UPDATE districts SET district_name_en = 'Raebareli'                    WHERE district_id = 140;
UPDATE districts SET district_name_en = 'Siddharth Nagar'              WHERE district_id = 148;

ALTER TABLE constituency ALTER COLUMN "Constituency_Hindi" SET NOT NULL;
ALTER TABLE constituency ALTER COLUMN "District"           SET NOT NULL;

-- R5 — deregister the migration.
DELETE FROM schema_migrations WHERE version = '0001_india_wide_reference_data';

-- Verify before committing:
--   select count(*) from districts;     -- expect 75
--   select count(*) from constituency;  -- expect 9
--   select count(*) from voters;        -- expect 8
--   select assembly_constituency_id, count(*) from voters group by 1;  -- 14->3, 16->5
COMMIT;
