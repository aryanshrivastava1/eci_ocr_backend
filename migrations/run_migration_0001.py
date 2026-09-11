"""Runner for migration 0001 — India-wide reference data.

    python migrations/run_migration_0001.py            # dry run, rolls back
    python migrations/run_migration_0001.py --apply    # commits

Everything runs inside ONE transaction. Any failed check raises, which rolls
the whole transaction back, so a partial migration is not possible. Without
--apply the transaction is rolled back even on success, which makes the dry
run a full rehearsal against real data rather than a simulation.

Safety properties, enforced in code and not merely intended:
  * voters is never written to, and is not even opened for update. The word
    UPDATE/INSERT/DELETE never appears against it.
  * No DROP TABLE, TRUNCATE or DELETE is issued at any point.
  * districts.district_id and constituency.id are never assigned or changed;
    new rows take their ids from the existing sequences.
  * All new-row inserts are INSERT ... WHERE NOT EXISTS on the authoritative
    identity, so the migration is idempotent and can never overwrite an
    existing row because a name differs.
  * A pre-migration snapshot of every legacy identifier and of the district
    English names this migration rewrites is written to disk BEFORE any
    change, so the one non-additive edit is reversible.
"""
import argparse
import csv
import json
import os
import sys
from datetime import datetime, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)

from dotenv import load_dotenv                      # noqa: E402
from sqlalchemy import create_engine, text          # noqa: E402

load_dotenv(os.path.join(ROOT, '.env'))

# The log prints Devanagari (district and AC Hindi names). On a cp1252 console
# that raises UnicodeEncodeError mid-run, which would roll back an otherwise
# healthy migration, so stdout is forced to UTF-8.
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

VERSION = '0001_india_wide_reference_data'
SQL_FILE = os.path.join(ROOT, 'migrations', VERSION + '.sql')
SRC = os.path.join(ROOT, 'data', 'reference', 'source')
LGD_STATES = os.path.join(SRC, 'lgd_states_raw.csv')
LGD_DISTRICTS = os.path.join(SRC, 'lgd_districts_normalised.csv')
ECI_ACS = os.path.join(SRC, 'eci_ac_normalised.csv')
SNAPSHOT_DIR = os.path.join(ROOT, 'migrations', 'snapshots')

LGD_SOURCE = 'LGD — Local Government Directory, Ministry of Panchayati Raj'
LGD_VERSION = '2026-09-11'
ECI_SOURCE = ('ECI Delimitation of Parliamentary and Assembly Constituencies '
              'Order, 2008 (English)')

# ---------------------------------------------------------------------------
# States/UTs whose current AC data is UNRESOLVED. Their ECI rows are NOT
# loaded: presenting them as current would misrepresent superseded or
# legally unconfirmed constituencies in a live electoral application.
# See docs/eci-ac-source-matrix.md.
# ---------------------------------------------------------------------------
EXCLUDED_AC_STATES = {
    '18': 'Assam — 2008 schedule superseded by the ECI Assam Delimitation '
          'Order, 11 Aug 2023 (19 AC names revised); that order was not obtained',
    '12': 'Arunachal Pradesh — excluded from the 2008 Order under s.10A; '
          'current legal instrument not established',
    '13': 'Nagaland — excluded from the 2008 Order under s.10A; current '
          'legal instrument not established',
    '14': 'Manipur — excluded from the 2008 Order under s.10A; current legal '
          'instrument not established',
    '28': 'Andhra Pradesh — ac_number values are undivided-AP numbers '
          '120-294, not the current 1-175; numbering unresolved',
}
# Jammu & Kashmir (state_code 1) has no rows in the dataset at all: the 2008
# annexure is superseded and the 2022 Commission order was not obtained.

# ---------------------------------------------------------------------------
# Explicit, hand-reviewed legacy district name -> LGD English name.
# From docs/legacy-reference-identity-audit.md §3. NOT fuzzy matching.
# ---------------------------------------------------------------------------
LEGACY_DISTRICT_ALIASES = {
    'Barabanki': 'Bara Banki',
    'Bhadohi (Sant Ravidas Nagar)': 'Bhadohi',
    'Lakhimpur Kheri': 'Kheri',
    'Maharajganj': 'Mahrajganj',
    'Raebareli': 'Rae Bareli',
    'Siddharth Nagar': 'Siddharthnagar',
}

# ---------------------------------------------------------------------------
# The 9 legacy constituency rows -> official ECI identity.
# From docs/legacy-reference-identity-audit.md §3, a verified 9<->9 bijection
# against ECI AC 168-176 in LGD district 162 (Lucknow), state_code 9 (UP).
# legacy constituency.id -> (ac_number, expected legacy English name)
# ---------------------------------------------------------------------------
LEGACY_AC_MAP = {
    13: (169, 'Bakshi Kaa Talab'),
    14: (172, 'Lucknow North'),
    15: (173, 'Lucknow East'),
    16: (174, 'Lucknow Central'),
    17: (171, 'Lucknow West'),
    18: (175, 'Lucknow Cantonment'),   # ECI spells this "Lucknow Cantt"
    19: (176, 'Mohanlalganj'),
    20: (168, 'Malihabad'),
    21: (170, 'Sarojini Nagar'),
}
LEGACY_AC_STATE_CODE = '9'
LEGACY_AC_DISTRICT_ID = 127
LEGACY_AC_LGD_DISTRICT = '162'

# Voter references that must be identical before and after.
EXPECTED_VOTER_REFS = {14: 3, 16: 5}
EXPECTED_VOTER_COUNT = 8


class MigrationFailed(Exception):
    pass


def load_sections(path):
    """Split the .sql file on '-- @section NAME' markers."""
    sections, name, buf = {}, None, []
    for line in open(path, encoding='utf-8'):
        if line.lstrip().startswith('-- @section'):
            if name:
                sections[name] = ''.join(buf)
            name = line.split('@section', 1)[1].split()[0]
            buf = []
        elif name:
            buf.append(line)
    if name:
        sections[name] = ''.join(buf)
    return sections


def statements(sql):
    """Yield non-empty statements, stripping comment-only lines."""
    cleaned = []
    for line in sql.splitlines():
        s = line.strip()
        if s.startswith('--') or not s:
            continue
        cleaned.append(line)
    for stmt in ' '.join(cleaned).split(';'):
        if stmt.strip():
            yield stmt.strip()


class Runner:
    def __init__(self, conn, apply):
        self.c = conn
        self.apply = apply
        self.log = []
        self.report = {}

    def say(self, msg):
        print(msg)
        self.log.append(msg)

    def q(self, sql, **kw):
        return [dict(r._mapping) for r in self.c.execute(text(sql), kw)]

    def one(self, sql, **kw):
        return self.c.execute(text(sql), kw).scalar()

    @staticmethod
    def _brief(v, n=70):
        t = repr(v)
        return t if len(t) <= n else t[:n] + '... (%d chars)' % len(t)

    def check(self, label, got, want):
        ok = got == want
        self.say('   %s %-56s got=%s want=%s'
                 % ('PASS' if ok else 'FAIL', label,
                    self._brief(got), self._brief(want)))
        if not ok:
            raise MigrationFailed('%s: got %s, want %s'
                                  % (label, self._brief(got, 400),
                                     self._brief(want, 400)))
        return ok

    def bulk(self, table, cols, rows, chunk=500):
        """Multi-row VALUES insert into a staging table, in chunks.

        One round trip per chunk instead of one per row, which keeps the
        migration's transaction (and therefore its locks on a live database)
        short. Staging tables are TEMP ... ON COMMIT DROP.
        """
        for i in range(0, len(rows), chunk):
            part = rows[i:i + chunk]
            vals, params = [], {}
            for j, r in enumerate(part):
                vals.append('(' + ', '.join(':p%d_%s' % (j, c) for c in cols) + ')')
                for c in cols:
                    params['p%d_%s' % (j, c)] = r[c]
            self.c.execute(text('insert into %s (%s) values %s'
                                % (table, ', '.join(cols), ', '.join(vals))),
                           params)

    # -- Phase 0 ---------------------------------------------------------
    def phase0_snapshot(self):
        self.say('\nPHASE 0 — pre-migration snapshot (rollback point)')
        snap = {
            'taken_at': datetime.now(timezone.utc).isoformat(),
            'migration': VERSION,
            'counts': self.q("""
                select 'districts' t, count(*) n from districts
                union all select 'constituency', count(*) from constituency
                union all select 'voters', count(*) from voters"""),
            'districts': self.q('select district_id, district_name_en, '
                                'district_name_hi, mandala_id from districts '
                                'order by district_id'),
            'constituency': self.q('select id, "Constituency", "District", '
                                   '"Constituency_Hindi", district_id '
                                   'from constituency order by id'),
            'voter_pks': self.q('select id::text as id, '
                                'assembly_constituency_id from voters '
                                'order by assembly_constituency_id, id'),
            'voter_refs': self.q('select assembly_constituency_id, count(*) n '
                                 'from voters group by 1 order by 1'),
            'sequences': self.q("""
                select 'constituency_id_seq' s, last_value from constituency_id_seq
                union all select 'districts_district_id_seq', last_value
                          from districts_district_id_seq"""),
        }
        os.makedirs(SNAPSHOT_DIR, exist_ok=True)
        path = os.path.join(SNAPSHOT_DIR, VERSION + '_pre.json')
        json.dump(snap, open(path, 'w', encoding='utf-8'),
                  ensure_ascii=False, indent=1, default=str)
        self.pre = snap
        self.say('   wrote %s' % os.path.relpath(path, ROOT))
        self.say('   districts=%s constituency=%s voters=%s'
                 % tuple(r['n'] for r in snap['counts']))
        return snap

    # -- Phases 2 & 3 ----------------------------------------------------
    def phase23_ddl(self, sql):
        self.say('\nPHASE 2 + 3 — states table and nullable identity columns')
        for stmt in statements(sql):
            self.c.execute(text(stmt))
            self.say('   ok  %s' % (stmt[:88].replace('\n', ' ')))

    # -- Phase 4 ---------------------------------------------------------
    def phase4_states(self):
        self.say('\nPHASE 4 — insert the 36 LGD States/UTs')
        rows = list(csv.DictReader(open(LGD_STATES, encoding='utf-8-sig')))
        if len(rows) != 36:
            raise MigrationFailed('expected 36 LGD state rows, got %d' % len(rows))
        payload = []
        for r in rows:
            code = r['State LGD Code'].strip()
            payload.append({
                'state_id': int(code),
                'state_code': code,
                'state_name_en': r['State Name (In English)'].strip(),
                # state_name_hi stays NULL. The LGD "State Name (In Local
                # language)" column holds an upper-case Latin transliteration
                # ("UTTAR PRADESH"), not Devanagari, so it is NOT Hindi and is
                # deliberately not copied here. No Hindi is fabricated.
                'state_name_hi': None,
                'source': LGD_SOURCE,
                'source_version': LGD_VERSION,
            })
        self.c.execute(text("""
            insert into states (state_id, state_code, state_name_en,
                                state_name_hi, source, source_version)
            values (cast(:state_id as integer), cast(:state_code as text),
                    cast(:state_name_en as text), cast(:state_name_hi as text),
                    cast(:source as text), cast(:source_version as text))
            on conflict (state_id) do nothing
        """), payload)
        n = self.one('select count(*) from states')
        hi = self.one('select count(*) from states where state_name_hi is not null')
        self.say('   states rows=%d  state_name_hi populated=%d (expected 0)' % (n, hi))
        self.report['states_inserted'] = n
        self.check('states row count', n, 36)
        self.check('no fabricated state_name_hi', hi, 0)
        up = self.q("select state_id, state_code, state_name_en from states "
                    "where state_code = '9'")
        self.say('   Uttar Pradesh -> %s' % up)
        self.check("Uttar Pradesh state_code is '9'", len(up), 1)

    # -- Phase 5 ---------------------------------------------------------
    def phase5_districts_backfill(self):
        self.say('\nPHASE 5 — backfill the existing 75 districts (UPDATE by '
                 'district_id, no inserts)')
        lgd = [r for r in csv.DictReader(open(LGD_DISTRICTS, encoding='utf-8-sig'))
               if r['State Code'].strip() == '9']
        if len(lgd) != 75:
            raise MigrationFailed('expected 75 LGD UP districts, got %d' % len(lgd))
        by_name = {r['District Name(In English)'].strip(): r for r in lgd}

        legacy = self.q('select district_id, district_name_en, district_name_hi '
                        'from districts order by district_id')
        if len(legacy) != 75:
            raise MigrationFailed('expected 75 legacy districts, got %d' % len(legacy))

        updates, used, exact, aliased = [], set(), 0, 0
        for d in legacy:
            name = (d['district_name_en'] or '').strip()
            target, why = by_name.get(name), 'exact'
            if target is None and name in LEGACY_DISTRICT_ALIASES:
                target = by_name.get(LEGACY_DISTRICT_ALIASES[name])
                why = 'explicit alias -> %s' % LEGACY_DISTRICT_ALIASES[name]
            if target is None:
                raise MigrationFailed(
                    'legacy district %s %r has no reviewed LGD mapping — '
                    'refusing to guess' % (d['district_id'], name))
            code = target['District Code'].strip()
            if code in used:
                raise MigrationFailed('LGD district code %s claimed twice' % code)
            used.add(code)
            if why == 'exact':
                exact += 1
            else:
                aliased += 1
                self.say('   %-5s %-30s -> %-5s %-22s (%s)'
                         % (d['district_id'], name, code,
                            target['District Name(In English)'], why))
            updates.append({
                'district_id': d['district_id'],
                'state_id': 9,
                'lgd_district_code': code,
                'name_en': target['District Name(In English)'].strip(),
                'source': LGD_SOURCE,
                'source_version': LGD_VERSION,
            })

        self.check('legacy districts mapped', exact + aliased, 75)
        self.check('explicit alias count', aliased, 6)
        self.check('LGD UP districts claimed (bijection)', len(used), 75)

        # district_name_hi is NOT in the SET list, so the existing Hindi cannot
        # be touched. district_id is only ever a WHERE key.
        self.c.execute(text("""
            update districts set
                state_id          = :state_id,
                lgd_district_code = :lgd_district_code,
                district_name_en  = :name_en,
                source            = :source,
                source_version    = :source_version
            where district_id = :district_id
        """), updates)

        n = self.one('select count(*) from districts')
        self.check('districts still 75 (no inserts in this phase)', n, 75)
        hi = self.one("select count(*) from districts where district_name_hi "
                      "is null or district_name_hi = ''")
        self.check('districts with Hindi preserved (0 lost)', hi, 0)
        pre = {r['district_id']: r['district_name_en'] for r in self.pre['districts']}
        now = {r['district_id']: r['district_name_en']
               for r in self.q('select district_id, district_name_en from districts')}
        changed = sorted(k for k in pre if pre[k] != now[k])
        self.say('   English names rewritten to the LGD canonical form: %d %s'
                 % (len(changed), changed))
        self.check('district English names changed', len(changed), 6)
        self.report['districts_updated'] = 75
        self.report['district_names_rewritten'] = [
            {'district_id': k, 'from': pre[k], 'to': now[k]} for k in changed]

    # -- Phase 6 ---------------------------------------------------------
    def phase6_constituency_backfill(self):
        self.say('\nPHASE 6 — backfill the existing 9 constituency rows '
                 '(UPDATE by id, no inserts)')
        eci = {int(r['ac_number']): r
               for r in csv.DictReader(open(ECI_ACS, encoding='utf-8-sig'))
               if r['state_code'] == LEGACY_AC_STATE_CODE
               and r['district_name_en'] == 'Lucknow'}
        self.check('ECI rows for UP/Lucknow', len(eci), 9)
        self.check('ECI Lucknow AC numbers are 168..176',
                   sorted(eci), list(range(168, 177)))

        legacy = self.q('select id, "Constituency" as name from constituency '
                        'order by id')
        self.check('legacy constituency rows', len(legacy), 9)

        updates = []
        for row in legacy:
            if row['id'] not in LEGACY_AC_MAP:
                raise MigrationFailed('legacy constituency id %s is not in the '
                                      'reviewed mapping' % row['id'])
            ac, expected_name = LEGACY_AC_MAP[row['id']]
            if (row['name'] or '').strip() != expected_name:
                raise MigrationFailed(
                    'legacy constituency %s is named %r but the reviewed '
                    'mapping expects %r — refusing to backfill'
                    % (row['id'], row['name'], expected_name))
            src = eci[ac]
            updates.append({
                'id': row['id'],
                'state_id': int(LEGACY_AC_STATE_CODE),
                'district_id': LEGACY_AC_DISTRICT_ID,
                'lgd_district_code': LEGACY_AC_LGD_DISTRICT,
                'ac_number': ac,
                'source': ECI_SOURCE,
                'source_version': src['source_version'],
                'mapping_confidence': src['mapping_confidence'],
            })

        acs = sorted(u['ac_number'] for u in updates)
        self.check('legacy rows map bijectively onto ECI 168..176',
                   acs, list(range(168, 177)))

        # "Constituency" and "Constituency_Hindi" are NOT in the SET list: the
        # legacy English names and the legacy Hindi (the only AC Hindi that
        # exists anywhere) are preserved exactly.
        self.c.execute(text("""
            update constituency set
                state_id           = :state_id,
                district_id        = :district_id,
                lgd_district_code  = :lgd_district_code,
                ac_number          = :ac_number,
                source             = :source,
                source_version     = :source_version,
                mapping_confidence = :mapping_confidence
            where id = :id
        """), updates)

        self.check('constituency still 9 (no inserts in this phase)',
                   self.one('select count(*) from constituency'), 9)
        self.report['constituencies_updated'] = 9
        for r in self.q('select id, "Constituency", ac_number, state_id, '
                        'district_id, lgd_district_code, mapping_confidence '
                        'from constituency order by ac_number'):
            self.say('   id=%-3s ac=%-4s %-20s state=%-3s district=%-4s '
                     'lgd=%-4s conf=%s'
                     % (r['id'], r['ac_number'], r['Constituency'],
                        r['state_id'], r['district_id'],
                        r['lgd_district_code'], r['mapping_confidence']))

    # -- Phase 7 ---------------------------------------------------------
    def phase7_gate(self):
        self.say('\nPHASE 7 — VALIDATION GATE (rolls back and stops on any '
                 'failure)')
        self.check('states = 36', self.one('select count(*) from states'), 36)
        self.check('districts = 75',
                   self.one('select count(*) from districts'), 75)
        self.check('constituency = 9',
                   self.one('select count(*) from constituency'), 9)
        self.check('voters = 8',
                   self.one('select count(*) from voters'), EXPECTED_VOTER_COUNT)

        self.check('districts with a valid state_id', self.one("""
            select count(*) from districts d
            join states s on s.state_id = d.state_id"""), 75)
        self.check('districts with a non-null LGD district code', self.one("""
            select count(*) from districts
            where lgd_district_code is not null
              and lgd_district_code <> ''"""), 75)
        self.check('districts with a LGD code that exists in LGD UP',
                   self.one('select count(distinct lgd_district_code) '
                            'from districts'), 75)

        self.check('constituencies with a valid state_id', self.one("""
            select count(*) from constituency c
            join states s on s.state_id = c.state_id"""), 9)
        self.check('constituencies with a valid district_id', self.one("""
            select count(*) from constituency c
            join districts d on d.district_id = c.district_id"""), 9)
        self.check('constituencies with a valid AC number', self.one("""
            select count(*) from constituency
            where ac_number between 1 and 500"""), 9)
        self.check('duplicate (state_id, ac_number)', self.one("""
            select count(*) from (
              select state_id, ac_number from constituency
              group by 1, 2 having count(*) > 1) x"""), 0)

        # --- voters: read-only assertions, byte-compared to the snapshot ---
        refs = {r['assembly_constituency_id']: r['n'] for r in self.q(
            'select assembly_constituency_id, count(*) n from voters '
            'group by 1 order by 1')}
        self.check('voter -> constituency reference distribution',
                   refs, EXPECTED_VOTER_REFS)
        self.check('constituency 14 voter count', refs.get(14), 3)
        self.check('constituency 16 voter count', refs.get(16), 5)
        self.check('voters with a dangling constituency reference', self.one("""
            select count(*) from voters v
            left join constituency c on c.id = v.assembly_constituency_id
            where c.id is null"""), 0)
        self.check('voters with a dangling district reference', self.one("""
            select count(*) from voters v
            left join districts d on d.district_id = v.district_id
            where v.district_id is not null and d.district_id is null"""), 0)
        now_pks = self.q('select id::text as id, assembly_constituency_id '
                         'from voters order by assembly_constituency_id, id')
        self.check('voter primary keys identical to the pre-migration snapshot',
                   now_pks, self.pre['voter_pks'])

        # legacy identifiers must be untouched
        self.check('constituency ids still 13..21',
                   [r['id'] for r in self.q('select id from constituency '
                                            'order by id')],
                   list(range(13, 22)))
        self.check('district ids still 79..153',
                   [r['district_id'] for r in self.q('select district_id from '
                                                     'districts order by 1')],
                   list(range(79, 154)))
        self.say('   GATE PASSED — safe to load new reference rows')

    # -- Phase 8 ---------------------------------------------------------
    def phase8_load(self):
        self.say('\nPHASE 8 — load new authoritative reference rows '
                 '(INSERT-ONLY)')

        # ---- districts: all 784 LGD districts; the 75 UP rows already exist
        lgd = list(csv.DictReader(open(LGD_DISTRICTS, encoding='utf-8-sig')))
        self.check('LGD district rows in source', len(lgd), 784)
        payload = [{
            'state_id': int(r['State Code'].strip()),
            'code': r['District Code'].strip(),
            'name_en': r['District Name(In English)'].strip(),
            'source': LGD_SOURCE,
            'source_version': LGD_VERSION,
        } for r in lgd]

        # Insert-only on the authoritative identity. An existing row is never
        # updated here, however much its name differs. district_id comes from
        # the sequence, so ids 79..153 are untouched.
        # district_name_hi is left NULL for new rows: no Hindi is fabricated.
        self.c.execute(text("""
            create temp table _stage_lgd_districts (
                state_id integer, code text, name_en text
            ) on commit drop
        """))
        self.bulk('_stage_lgd_districts', ['state_id', 'code', 'name_en'], payload)
        self.check('staged LGD district rows',
                   self.one('select count(*) from _stage_lgd_districts'), 784)
        # INSERT-ONLY on the authoritative identity (LGD District Code). An
        # existing row is never updated here, however much its name differs.
        # district_id comes from the sequence, so ids 79..153 are untouched, and
        # district_name_hi is left NULL for new rows — no Hindi is fabricated.
        self.c.execute(text("""
            insert into districts (state_id, lgd_district_code,
                                   district_name_en, source, source_version)
            select t.state_id, t.code, t.name_en, :source, :source_version
              from _stage_lgd_districts t
             where not exists (select 1 from districts d
                                where d.lgd_district_code = t.code)
        """), {'source': LGD_SOURCE, 'source_version': LGD_VERSION})
        n_d = self.one('select count(*) from districts')
        self.say('   districts: 75 -> %d (inserted %d)' % (n_d, n_d - 75))
        self.check('districts total', n_d, 784)
        self.report['districts_inserted'] = n_d - 75

        # ---- constituencies: ECI ACs for resolved States/UTs only
        eci = list(csv.DictReader(open(ECI_ACS, encoding='utf-8-sig')))
        self.check('ECI rows in source', len(eci), 4032)
        excluded = [r for r in eci if r['state_code'] in EXCLUDED_AC_STATES]
        loadable = [r for r in eci if r['state_code'] not in EXCLUDED_AC_STATES]
        self.say('   excluded %d rows for %d unresolved States/UTs:'
                 % (len(excluded), len(EXCLUDED_AC_STATES)))
        for sc, why in sorted(EXCLUDED_AC_STATES.items(), key=lambda kv: int(kv[0])):
            cnt = sum(1 for r in excluded if r['state_code'] == sc)
            self.say('      state_code %-3s %4d rows — %s' % (sc, cnt, why))
        self.say('   loadable rows: %d' % len(loadable))

        # district FK policy:
        #   exact / mapped        -> resolve district_id from lgd_district_code
        #   needs_review          -> district_id AND lgd_district_code stay NULL
        #   no_district_in_source -> district_id AND lgd_district_code stay NULL
        # No district FK is ever silently assigned.
        payload = []
        conf_counts = {}
        for r in loadable:
            conf = r['mapping_confidence']
            conf_counts[conf] = conf_counts.get(conf, 0) + 1
            resolved = conf in ('exact', 'mapped') and r['district_lgd_code']
            payload.append({
                'state_id': int(r['state_code']),
                'ac_number': int(r['ac_number']),
                'name': r['constituency'],
                'district_text': r['district_name_en'] or None,
                'code': r['district_lgd_code'] if resolved else None,
                'source': r['source'],
                'source_version': r['source_version'],
                'conf': conf,
            })
        self.say('   district mapping confidence of the loadable rows: %s'
                 % conf_counts)

        self.c.execute(text("""
            create temp table _stage_eci_acs (
                state_id integer, ac_number integer, name text,
                district_text text, code text, source text,
                source_version text, conf text
            ) on commit drop
        """))
        self.bulk('_stage_eci_acs',
                  ['state_id', 'ac_number', 'name', 'district_text', 'code',
                   'source', 'source_version', 'conf'], payload)
        self.check('staged ECI AC rows',
                   self.one('select count(*) from _stage_eci_acs'), len(loadable))
        # INSERT-ONLY on the authoritative identity (state_id, ac_number).
        # "Constituency_Hindi" is NULL for every new row: the ECI source has no
        # Devanagari and nothing is transliterated. district_id is resolved only
        # from a non-NULL lgd_district_code, so a needs_review or
        # no_district_in_source row never receives a silently guessed district.
        self.c.execute(text("""
            insert into constituency ("Constituency", "District",
                                      "Constituency_Hindi", district_id,
                                      state_id, lgd_district_code, ac_number,
                                      source, source_version, mapping_confidence)
            select t.name,
                   case when t.code is null then null else t.district_text end,
                   null,
                   d.district_id,
                   t.state_id, t.code, t.ac_number,
                   t.source, t.source_version, t.conf
              from _stage_eci_acs t
              left join districts d on d.lgd_district_code = t.code
             where not exists (select 1 from constituency c
                                where c.state_id = t.state_id
                                  and c.ac_number = t.ac_number)
        """))

        n_c = self.one('select count(*) from constituency')
        self.say('   constituency: 9 -> %d (inserted %d)' % (n_c, n_c - 9))
        self.check('constituency total', n_c, len(loadable))
        self.report['constituencies_inserted'] = n_c - 9
        self.report['acs_excluded'] = len(excluded)

        # the excluded States/UTs must have no rows at all
        for sc in EXCLUDED_AC_STATES:
            self.check('no AC rows loaded for state_code %s' % sc,
                       self.one('select count(*) from constituency '
                                'where state_id = :s', s=int(sc)), 0)

        nulldist = self.one('select count(*) from constituency '
                            'where district_id is null')
        self.say('   constituency rows with a deliberately NULL district_id: %d'
                 % nulldist)
        self.report['constituencies_null_district'] = nulldist

    # -- Phases 9 & 10 ---------------------------------------------------
    def phase910_constraints(self, sql_late, sql_notnull):
        self.say('\nPHASE 9 + 10 — foreign keys and uniqueness')
        have = {r['conname'] for r in self.q("""
            select conname from pg_constraint con
            join pg_class rel on rel.oid = con.conrelid
            where rel.relname in ('districts','constituency')""")}
        for stmt in statements(sql_late):
            if 'ADD CONSTRAINT' in stmt.upper():
                cname = stmt.upper().split('ADD CONSTRAINT')[1].split()[0].lower()
                if cname in have:
                    self.say('   skip (exists)  %s' % cname)
                    continue
            if 'VALIDATE CONSTRAINT' in stmt.upper():
                cname = stmt.upper().split('VALIDATE CONSTRAINT')[1].split()[0].lower()
                if cname in have:
                    self.say('   skip (exists)  validate %s' % cname)
                    continue
            self.c.execute(text(stmt))
            self.say('   ok  %s' % stmt[:92].replace('\n', ' '))

        # Only promote to NOT NULL once every row demonstrably carries a value.
        guards = [
            ('districts', 'state_id'),
            ('districts', 'lgd_district_code'),
            ('constituency', 'state_id'),
            ('constituency', 'ac_number'),
        ]
        for tbl, col in guards:
            nulls = self.one('select count(*) from %s where %s is null' % (tbl, col))
            self.check('%s.%s rows still NULL' % (tbl, col), nulls, 0)
        excluded_by_index = self.one("""
            select count(*) from constituency
            where state_id is null or ac_number is null""")
        self.check('constituency rows excluded by the partial unique index',
                   excluded_by_index, 0)
        for stmt in statements(sql_notnull):
            self.c.execute(text(stmt))
            self.say('   ok  %s' % stmt[:92])

    # -- Phase 12 --------------------------------------------------------
    def phase12_tests(self):
        self.say('\nPHASE 12 — post-migration tests')
        self.check('voters = 8',
                   self.one('select count(*) from voters'), EXPECTED_VOTER_COUNT)
        now_pks = self.q('select id::text as id, assembly_constituency_id '
                         'from voters order by assembly_constituency_id, id')
        self.check('voter primary keys unchanged', now_pks, self.pre['voter_pks'])
        refs = {r['assembly_constituency_id']: r['n'] for r in self.q(
            'select assembly_constituency_id, count(*) n from voters group by 1')}
        self.check('voter reference distribution unchanged', refs,
                   EXPECTED_VOTER_REFS)
        self.check('voters with a dangling constituency reference', self.one("""
            select count(*) from voters v
            left join constituency c on c.id = v.assembly_constituency_id
            where c.id is null"""), 0)

        self.check('legacy constituency ids 13..21 present and unchanged',
                   [r['id'] for r in self.q('select id from constituency '
                                            'where id <= 21 order by id')],
                   list(range(13, 22)))
        self.check('legacy district ids 79..153 present and unchanged',
                   self.one('select count(*) from districts '
                            'where district_id between 79 and 153'), 75)
        pre_hi = {r['id']: r['Constituency_Hindi'] for r in self.pre['constituency']}
        now_hi = {r['id']: r['Constituency_Hindi'] for r in self.q(
            'select id, "Constituency_Hindi" from constituency where id <= 21')}
        self.check('legacy AC Hindi preserved byte-for-byte', now_hi, pre_hi)
        pre_dhi = {r['district_id']: r['district_name_hi']
                   for r in self.pre['districts']}
        now_dhi = {r['district_id']: r['district_name_hi'] for r in self.q(
            'select district_id, district_name_hi from districts '
            'where district_id between 79 and 153')}
        self.check('legacy district Hindi preserved byte-for-byte',
                   now_dhi, pre_dhi)

        self.check('duplicate (state_id, ac_number)', self.one("""
            select count(*) from (select state_id, ac_number from constituency
            group by 1,2 having count(*) > 1) x"""), 0)
        self.check('duplicate lgd_district_code', self.one("""
            select count(*) from (select lgd_district_code from districts
            group by 1 having count(*) > 1) x"""), 0)
        self.check('constituency rows whose district_id disagrees with its '
                   'lgd_district_code', self.one("""
            select count(*) from constituency c
            join districts d on d.district_id = c.district_id
            where c.lgd_district_code is not null
              and c.lgd_district_code <> d.lgd_district_code"""), 0)
        self.check('any fabricated Hindi on new rows', self.one("""
            select count(*) from constituency
            where id > 21 and "Constituency_Hindi" is not null"""), 0)
        self.check('states with fabricated Hindi',
                   self.one('select count(*) from states '
                            'where state_name_hi is not null'), 0)

        by_state = self.q("""
            select s.state_code, s.state_name_en, count(c.id) n
            from states s left join constituency c on c.state_id = s.state_id
            group by 1, 2 order by n desc, 1""")
        self.report['ac_rows_by_state'] = by_state
        self.say('   AC rows by State/UT (top 8): %s'
                 % [(r['state_name_en'], r['n']) for r in by_state[:8]])

        self.c.execute(text("""
            insert into schema_migrations (version, description)
            values (:v, :d) on conflict (version) do nothing
        """), {'v': VERSION,
               'd': 'states table; LGD/ECI identity columns on districts and '
                    'constituency; 36 states, 784 districts, ECI ACs for '
                    'resolved States/UTs only'})
        self.say('   recorded in schema_migrations')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true',
                    help='commit; without it the transaction is rolled back')
    args = ap.parse_args()

    sections = load_sections(SQL_FILE)
    eng = create_engine(os.environ['DATABASE_URL'])
    mode = 'APPLY (will COMMIT)' if args.apply else 'DRY RUN (will ROLLBACK)'
    print('migration %s — %s' % (VERSION, mode))

    with eng.connect() as conn:
        trans = conn.begin()
        r = Runner(conn, args.apply)
        try:
            r.phase0_snapshot()
            r.phase23_ddl(sections['DDL_EARLY'])
            r.phase4_states()
            r.phase5_districts_backfill()
            r.phase6_constituency_backfill()
            r.phase7_gate()
            r.phase8_load()
            r.phase910_constraints(sections['DDL_LATE'],
                                   sections['DDL_NOT_NULL'])
            r.phase12_tests()
        except Exception as e:
            trans.rollback()
            print('\n*** ROLLED BACK — %s: %s' % (type(e).__name__, e))
            return 1
        if args.apply:
            trans.commit()
            print('\n*** COMMITTED')
        else:
            trans.rollback()
            print('\n*** DRY RUN COMPLETE — transaction rolled back, '
                  'database unchanged')
        json.dump(r.report, open(os.path.join(
            SNAPSHOT_DIR, VERSION + ('_applied.json' if args.apply
                                     else '_dryrun.json')),
            'w', encoding='utf-8'), ensure_ascii=False, indent=1, default=str)
    return 0


if __name__ == '__main__':
    sys.exit(main())
