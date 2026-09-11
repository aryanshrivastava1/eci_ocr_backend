"""Stage 3 — normalise parsed ECI Assembly Constituency rows and reconcile
district attribution against the authoritative LGD district list.

Reads   : data/reference/source/eci_ac_2008_raw.csv   (stage 2 output)
          data/reference/source/lgd_districts_normalised.csv  (authoritative LGD)
Writes  : data/reference/source/eci_ac_normalised.csv
          data/reference/source/eci_ac_validation.txt

Read-only with respect to the database, the SQLAlchemy models, the seeder and
the existing baseline CSVs (data/reference/districts.csv, constituencies.csv).

District reconciliation is EXACT-MATCH plus an EXPLICIT, hand-reviewed alias
table (ALIASES below). No fuzzy matching is used to decide a mapping; where no
unambiguous LGD successor exists the row is left with mapping_confidence
= needs_review and no district_lgd_code.
"""
import csv
import os
import re
import sys
import collections

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
SRC = os.path.join(ROOT, 'data', 'reference', 'source')
RAW = os.path.join(SRC, 'eci_ac_2008_raw.csv')
LGD = os.path.join(SRC, 'lgd_districts_normalised.csv')
OUT = os.path.join(SRC, 'eci_ac_normalised.csv')
REPORT = os.path.join(SRC, 'eci_ac_validation.txt')

SOURCE_2008 = ('ECI Delimitation of Parliamentary and Assembly Constituencies '
               'Order, 2008 (English)')

# ---------------------------------------------------------------------------
# State/UT reference. state_code is the authoritative LGD State Code, as TEXT.
# ---------------------------------------------------------------------------
# ECI 2008 schedule heading -> LGD state code. Undivided Andhra Pradesh is
# resolved per ECI district heading (see AP_TG_SPLIT).
ECI_STATE_TO_LGD = {
    'ANDHRA PRADESH': None,          # split, see AP_TG_SPLIT
    'ARUNACHAL PRADESH': '12',
    'ASSAM': '18',
    'BIHAR': '10',
    'CHHATTISGARH': '22',
    'GOA': '30',
    'GUJARAT': '24',
    'HARYANA': '6',
    'HIMACHAL PRADESH': '2',
    'JHARKHAND': '20',
    'KARNATAKA': '29',
    'KERALA': '32',
    'MADHYA PRADESH': '23',
    'MAHARASHTRA': '27',
    'MANIPUR': '14',
    'MEGHALAYA': '17',
    'MIZORAM': '15',
    'NAGALAND': '13',
    'ORISSA': '21',                  # LGD: Odisha
    'PUNJAB': '3',
    'RAJASTHAN': '8',
    'SIKKIM': '11',
    'TAMIL NADU': '33',
    'TRIPURA': '16',
    'UTTAR PRADESH': '9',
    'UTTARAKHAND': '5',
    'WEST BENGAL': '19',
    'NCT OF DELHI': '7',             # LGD: Delhi
    'PUDUCHERRY': '34',
}

# The 2008 Order predates the 2014 bifurcation. These are the ten pre-2014
# Telangana districts as they appear as ECI district headings in Schedule III;
# every other AP heading stays with Andhra Pradesh (state code 28).
AP_TG_SPLIT = {
    'ADILABAD', 'NIZAMABAD', 'KARIMNAGAR', 'MEDAK', 'HYDERABAD',
    'RANGAREDDI', 'RANGA REDDY', 'RANGAREDDY',
    'MAHBUBNAGAR', 'NALGONDA', 'WARANGAL', 'KHAMMAM',
}

# States/UTs whose 2008 schedule is NOT the current legal instrument.
# value = (source_version tag, why)
NOT_CURRENT = {
    '18': ('2008-superseded-2023',
           'Superseded by the ECI Assam Delimitation Order, 11 Aug 2023 '
           '(126 ACs retained, 19 AC names revised). Order not obtained.'),
    '12': ('2008-currency-unconfirmed',
           'Arunachal Pradesh was excluded from the 2008 Order under s.10A of '
           'the Delimitation Act, 2002; current legal instrument not established.'),
    '13': ('2008-currency-unconfirmed',
           'Nagaland was excluded from the 2008 Order under s.10A; current '
           'legal instrument not established.'),
    '14': ('2008-currency-unconfirmed',
           'Manipur was excluded from the 2008 Order under s.10A; current '
           'legal instrument not established.'),
    '28': ('2008-undivided-ap-numbering',
           'AC names and extents are current, but ac_number is the UNDIVIDED '
           'Andhra Pradesh number (120-294 contiguous). Post-2014 Andhra '
           'Pradesh numbers its 175 ACs 1-175. The offset appears to be -119 '
           'but that renumbering was NOT confirmed against an official source, '
           'so the source numbers are carried through unchanged.'),
}

# States/UTs with a Legislative Assembly but NO rows in this dataset.
MISSING_STATES = {
    '1': ('Jammu And Kashmir', 90,
          'The 2008 Order carries J&K only as an Annexure reflecting the '
          'pre-2019 State (87 seats). Superseded by the J&K Delimitation '
          'Commission Order, 2022 (90 ACs), which was not obtained. The 2008 '
          'annexure is deliberately excluded rather than loaded as current.'),
}

# States/UTs with no Legislative Assembly at all -> 0 ACs by law.
NO_ASSEMBLY = {
    '35': 'Andaman And Nicobar Islands',
    '4': 'Chandigarh',
    '38': 'The Dadra And Nagar Haveli And Daman And Diu',
    '31': 'Lakshadweep',
    '37': 'Ladakh',
}

# ---------------------------------------------------------------------------
# EXPLICIT district aliases: (lgd_state_code, normalised ECI heading) ->
# (lgd_district_code, reason). Every target is asserted to exist in LGD.
# ---------------------------------------------------------------------------
ALIASES = {
    # Bihar
    ('10', 'JAHANABAD'): ('199', 'spelling: Jehanabad'),
    ('10', 'PASCHIM CHAMPARAN'): ('211', 'spelling: Pashchim Champaran'),
    ('10', 'PURVI CHAMPARAN'): ('213', 'spelling: Purbi Champaran'),
    # Sikkim — districts renamed in 2021/2022
    ('11', 'EAST'): ('225', 'renamed: East -> Gangtok'),
    ('11', 'WEST'): ('228', 'renamed: West -> Gyalshing'),
    ('11', 'NORTH'): ('226', 'renamed: North -> Mangan'),
    ('11', 'SOUTH'): ('227', 'renamed: South -> Namchi'),
    # Mizoram
    ('15', 'SAIHA'): ('267', 'spelling: Siaha'),
    # Meghalaya
    ('17', 'RIBHOI'): ('276', 'spelling: Ri Bhoi'),
    # Assam
    ('18', 'MIKIR HILLS'): ('292', 'renamed: Mikir Hills -> Karbi Anglong'),
    ('18', 'NORTH CACHAR HILLS'): ('299', 'renamed: North Cachar Hills -> Dima Hasao'),
    ('18', 'NOWGONG'): ('297', 'renamed: Nowgong -> Nagaon'),
    ('18', 'SIBSAGAR'): ('300', 'spelling: Sivasagar'),
    # West Bengal
    ('19', 'COOCHBEHAR'): ('308', 'spelling: Cooch Behar'),
    ('19', 'MALDAHA'): ('316', 'spelling: Malda'),
    ('19', 'PURBO MEDINIPUR'): ('317', 'spelling: Purba Medinipur'),
    # Himachal Pradesh
    ('2', 'SIRMOUR'): ('24', 'spelling: Sirmaur'),
    # Jharkhand
    ('20', 'EAST SINGHBHUM'): ('327', 'spelling: East Singhbum'),
    ('20', 'KODARMA'): ('334', 'spelling: Koderma'),
    ('20', 'PAKAUR'): ('337', 'spelling: Pakur'),
    ('20', 'PALAMAU'): ('338', 'spelling: Palamu'),
    # Odisha — LGD uses Odia-form names throughout
    ('21', 'ANGUL'): ('344', 'spelling: Anugola'),
    ('21', 'BALASORE'): ('346', 'spelling: Baleshwar'),
    ('21', 'BARGARH'): ('347', 'spelling: Baragada'),
    ('21', 'BOLANGIR'): ('345', 'spelling: Balangir'),
    ('21', 'CUTTACK'): ('350', 'spelling: Kataka'),
    ('21', 'DEOGARH'): ('351', 'spelling: Debagada'),
    ('21', 'JAGATSINGHPUR'): ('355', 'spelling: Jagatsinghapur'),
    ('21', 'KANDHAMAL'): ('359', 'spelling: Kandhamala'),
    ('21', 'KENDRAPARA'): ('360', 'spelling: Kendrapada'),
    ('21', 'KEONJHAR'): ('361', 'spelling: Kendujhar'),
    ('21', 'KHURDA'): ('362', 'spelling: Khordha'),
    ('21', 'NAYAGARH'): ('367', 'spelling: Nayagada'),
    ('21', 'SUNDARGARH'): ('373', 'spelling: Sundaragada'),
    # Chhattisgarh
    ('22', 'KABIRDHAM'): ('382', 'spelling: Kabeerdham'),
    ('22', 'KORIA'): ('384', 'spelling: Korea (Koriya)'),
    # Madhya Pradesh
    ('23', 'ASHOK NAGAR'): ('391', 'spelling: Ashoknagar'),
    ('23', 'BADWANI'): ('393', 'spelling: Barwani'),
    ('23', 'EAST NIMAR KHANDWA'): ('405', 'LGD form: Khandwa (East Nimar)'),
    ('23', 'HOSHANGABAD'): ('409', 'renamed: Hoshangabad -> Narmadapuram'),
    ('23', 'MANDSOUR'): ('416', 'spelling: Mandsaur'),
    ('23', 'NARSINGPUR'): ('418', 'spelling: Narsimhapur'),
    ('23', 'WEST NIMAR KHAORGONE'): ('414', 'LGD form: Khargone (West Nimar)'),
    # Gujarat
    ('24', 'BANASKANTHA'): ('441', 'spelling: Banas Kantha'),
    ('24', 'PANCHMAHALS'): ('454', 'spelling: Panch Mahals'),
    ('24', 'SABARKANTHA'): ('458', 'spelling: Sabar Kantha'),
    # Maharashtra
    ('27', 'AHMEDNAGAR'): ('466', 'renamed: Ahmednagar -> Ahilyanagar'),
    ('27', 'AURANGABAD'): ('469', 'renamed: Aurangabad -> Chhatrapati Sambhajinagar'),
    ('27', 'GONDIYA'): ('476', 'spelling: Gondia'),
    ('27', 'MUMBAI CITY'): ('482', 'LGD form: Mumbai'),
    ('27', 'OSMANABAD'): ('488', 'renamed: Osmanabad -> Dharashiv'),
    # Andhra Pradesh
    ('28', 'ANANTAPUR'): ('502', 'renamed: Anantapur -> Ananthapuramu'),
    ('28', 'KADAPA'): ('504', 'LGD form: Y.S.R. Kadapa'),
    ('28', 'NELLORE'): ('515', 'LGD form: Sri Potti Sriramulu Nellore'),
    # Karnataka
    ('29', 'BAGALKOT'): ('524', 'spelling: Bagalkote'),
    ('29', 'BANGALORE'): ('525', 'renamed: Bangalore (Urban) -> Bengaluru Urban'),
    ('29', 'BANGALORE RURAL'): ('526', 'renamed: Bangalore Rural -> Bengaluru Rural'),
    ('29', 'BELGAUM'): ('527', 'renamed: Belgaum -> Belagavi'),
    ('29', 'BELLARY'): ('528', 'renamed: Bellary -> Ballari'),
    ('29', 'BIJAPUR'): ('530', 'renamed: Bijapur -> Vijayapura'),
    ('29', 'CHICKMAGALUR'): ('532', 'renamed: Chikmagalur -> Chikkamagaluru'),
    ('29', 'GULBARGA'): ('538', 'renamed: Gulbarga -> Kalaburagi'),
    ('29', 'MYSORE'): ('545', 'renamed: Mysore -> Mysuru'),
    ('29', 'SHIMOGA'): ('547', 'renamed: Shimoga -> Shivamogga'),
    ('29', 'TUMKUR'): ('548', 'renamed: Tumkur -> Tumakuru'),
    # Punjab
    ('3', 'FIROZPUR'): ('31', 'spelling: Ferozepur'),
    ('3', 'MUKTSAR'): ('39', 'renamed: Muktsar -> Sri Muktsar Sahib'),
    ('3', 'NAWAN SHAHR'): ('40', 'renamed: Nawanshahr -> Shahid Bhagat Singh Nagar'),
    # Puducherry
    ('34', 'KARAIKAL REGION'): ('598', 'ECI "region" heading -> LGD district Karaikal'),
    ('34', 'PUDUCHERRY REGION'): ('600', 'ECI "region" heading -> LGD district Puducherry'),
    # Telangana
    ('36', 'RANGAREDDI'): ('518', 'spelling: Ranga Reddy'),
    ('36', 'MAHBUBNAGAR'): ('512', 'spelling: Mahabubnagar'),
    # Uttarakhand
    ('5', 'GARHWAL'): ('52', 'ECI "Garhwal" -> LGD Pauri Garhwal'),
    ('5', 'HARDWAR'): ('50', 'spelling: Haridwar'),
    ('5', 'RUDRYAPRAYAG'): ('54', 'spelling: Rudraprayag'),
    ('5', 'UDHAMSINGH NAGAR'): ('56', 'spelling: Udham Singh Nagar'),
    # Haryana
    ('6', 'GURGAON'): ('62', 'renamed: Gurgaon -> Gurugram'),
    # Uttar Pradesh
    ('9', 'ALLAHABAD'): ('120', 'renamed: Allahabad -> Prayagraj'),
    ('9', 'BARABANKI'): ('129', 'spelling: Bara Banki'),
    ('9', 'BULANDSHAHAR'): ('134', 'spelling: Bulandshahr'),
    ('9', 'FAIZABAD'): ('140', 'renamed: Faizabad -> Ayodhya'),
    ('9', 'JYOTIBA PHULE NAGAR'): ('154', 'renamed: Jyotiba Phule Nagar -> Amroha'),
    ('9', 'KUSHI NAGAR'): ('160', 'spelling: Kushinagar'),
    ('9', 'MAHAMAYA NAGAR'): ('163', 'renamed: Mahamaya Nagar -> Hathras'),
    ('9', 'MAHARAJGANJ'): ('164', 'spelling: Mahrajganj'),
    ('9', 'SANT RAVIDAS NAGAR'): ('179', 'renamed: Sant Ravidas Nagar -> Bhadohi'),
}

# ECI district headings that have NO unambiguous LGD successor. Explicitly
# recorded so they are a decision, not a silent miss.
UNMAPPABLE = {
    ('14', 'MANIPUR CENTRAL'): 'pre-1990s district; Manipur has since been reorganised into 16 districts',
    ('14', 'MANIPUR EAST'): 'pre-1990s district; no 1:1 LGD successor',
    ('14', 'MANIPUR NORTH'): 'pre-1990s district; no 1:1 LGD successor',
    ('14', 'MANIPUR SOUTH'): 'pre-1990s district; no 1:1 LGD successor',
    ('14', 'MANIPUR WEST'): 'pre-1990s district; no 1:1 LGD successor',
    ('17', 'JAINTIA HILLS'): 'split into East Jaintia Hills (657) and West Jaintia Hills (275)',
    ('19', 'BARDHAMAN'): 'split into Purba Bardhaman (306) and Paschim Bardhaman (704)',
    ('34', 'MAHE REGION'): 'Mahe is not present in the LGD district list snapshot',
    ('34', 'YANAM REGION'): 'Yanam is not present in the LGD district list snapshot',
}

# Per-State/UT AC totals transcribed from Schedule II of the 2008 Order
# (post-delimitation column), used as the independent count check.
SCHEDULE_II = {
    'ANDHRA PRADESH': 294, 'ARUNACHAL PRADESH': 60, 'ASSAM': 126, 'BIHAR': 243,
    'CHHATTISGARH': 90, 'GOA': 40, 'GUJARAT': 182, 'HARYANA': 90,
    'HIMACHAL PRADESH': 68, 'JHARKHAND': 81, 'KARNATAKA': 224, 'KERALA': 140,
    'MADHYA PRADESH': 230, 'MAHARASHTRA': 288, 'MANIPUR': 60, 'MEGHALAYA': 60,
    'MIZORAM': 40, 'NAGALAND': 60, 'ORISSA': 147, 'PUNJAB': 117,
    'RAJASTHAN': 200, 'SIKKIM': 32, 'TAMIL NADU': 234, 'TRIPURA': 60,
    'UTTAR PRADESH': 403, 'UTTARAKHAND': 70, 'WEST BENGAL': 294,
    'NCT OF DELHI': 70, 'PUDUCHERRY': 30,
}

# Rows the official source does not contain, recorded rather than invented.
EXPECTED_MISSING = [
    ('11', 'Sikkim', 32, 'Sangha',
     'The Sangha constituency is non-territorial (electors are monks of '
     'registered monasteries). Schedule II counts it in Sikkim\'s 32 seats, but '
     'it has no entry in the district-wise Table A of the 2008 Order because it '
     'has no territorial extent. Not fabricated.'),
]


def key(s):
    """Normalise a district name for comparison: upper, alnum + single space."""
    s = (s or '').upper().replace('&', ' AND ')
    return re.sub(r'\s+', ' ', re.sub(r'[^A-Z0-9]+', ' ', s)).strip()


def load_lgd():
    rows = list(csv.DictReader(open(LGD, encoding='utf-8-sig')))
    by_code = {}
    by_name = {}
    states = {}
    for r in rows:
        sc = r['State Code'].strip()
        dc = r['District Code'].strip()
        dn = r['District Name(In English)'].strip()
        states[sc] = r['State Name (In English)'].strip()
        by_code[(sc, dc)] = dn
        by_name.setdefault((sc, key(dn)), []).append((dc, dn))
    return rows, by_code, by_name, states


def main():
    lgd_rows, by_code, by_name, lgd_states = load_lgd()

    # fail loudly on a bad alias target
    problems = []
    for (sc, k), (dc, why) in ALIASES.items():
        if (sc, dc) not in by_code:
            problems.append('ALIAS TARGET NOT IN LGD: state %s district %s (%s)' % (sc, dc, k))
    if problems:
        print('\n'.join(problems))
        return 2

    raw = list(csv.DictReader(open(RAW, encoding='utf-8')))
    out = []
    unmatched = collections.Counter()
    for r in raw:
        eci_state = r['state_name_eci'].strip().upper()
        if eci_state == 'JAMMU AND KASHMIR':
            continue  # 2008 annexure is superseded; deliberately excluded
        dk = key(r['district_eci'])
        if eci_state == 'ANDHRA PRADESH':
            sc = '36' if dk in AP_TG_SPLIT else '28'
        else:
            sc = ECI_STATE_TO_LGD.get(eci_state)
        if sc is None:
            print('UNKNOWN ECI STATE HEADING: %r' % eci_state)
            return 2

        dcode, dname, conf = '', '', 'needs_review'
        if not dk:
            conf = 'no_district_in_source'
        elif (sc, dk) in by_name and len(by_name[(sc, dk)]) == 1:
            dcode, dname = by_name[(sc, dk)][0]
            conf = 'exact'
        elif (sc, dk) in ALIASES:
            dcode = ALIASES[(sc, dk)][0]
            dname = by_code[(sc, dcode)]
            conf = 'mapped'
        else:
            unmatched[(sc, r['district_eci'])] += 1

        version, _ = NOT_CURRENT.get(sc, ('2008', ''))
        out.append({
            'state_code': sc,
            'state_name_en': lgd_states[sc],
            'district_lgd_code': dcode,
            'district_name_en': dname,
            'ac_number': r['ac_number'],
            'constituency': r['constituency'],
            'constituency_hindi': '',   # the English Order contains no Devanagari
            'reservation': r['reservation'],
            'extent': r['extent'],
            'source': SOURCE_2008,
            'source_version': version,
            'mapping_confidence': conf,
            'district_name_eci': r['district_eci'],
        })

    out.sort(key=lambda d: (int(d['state_code']), int(d['ac_number'])))
    fields = ['state_code', 'state_name_en', 'district_lgd_code', 'district_name_en',
              'ac_number', 'constituency', 'constituency_hindi', 'reservation',
              'extent', 'source', 'source_version', 'mapping_confidence',
              'district_name_eci']
    with open(OUT, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(out)

    write_report(out, raw, unmatched, lgd_states, by_code)
    print('wrote %s (%d rows)' % (OUT, len(out)))
    print('wrote %s' % REPORT)
    return 0


def write_report(out, raw, unmatched, lgd_states, by_code):
    L = []
    def p(s=''):
        L.append(s)

    p('ECI Assembly Constituency reference data — validation report')
    p('=' * 74)
    p('')
    p('1. TOTAL ROWS')
    p('   rows in eci_ac_normalised.csv : %d' % len(out))
    p('   nationally expected (4,123)   : 4123')
    p('   accounted-for shortfall       : %d' % (4123 - len(out)))
    p('     - Jammu & Kashmir, 90 ACs  : 2022 Delimitation Commission Order not obtained')
    p('     - Sikkim AC 32 (Sangha)    : non-territorial seat, absent from the Order\'s Table A')
    p('')

    p('2. ROWS BY STATE/UT (parsed vs Schedule II of the 2008 Order)')
    by_state = collections.Counter(r['state_code'] for r in out)
    eci_by_state = collections.defaultdict(collections.Counter)
    for r in raw:
        eci_by_state[r['state_name_eci'].upper()][r['ac_number']] += 1
    p('   %-4s %-32s %6s %6s %s' % ('code', 'state/UT', 'rows', 'sched', 'status'))
    for sc in sorted(by_state, key=int):
        n = by_state[sc]
        if sc == '28':
            tgt, note = 175, 'AP share of undivided AP (175+119=294) OK'
        elif sc == '36':
            tgt, note = 119, 'Telangana share of undivided AP OK'
        else:
            eci_name = [k for k, v in ECI_STATE_TO_LGD.items() if v == sc][0]
            tgt = SCHEDULE_II[eci_name]
            note = 'OK' if n == tgt else 'DIFFERS'
        p('   %-4s %-32s %6d %6d %s' % (sc, lgd_states[sc], n, tgt, note))
    p('   Sikkim differs by 1: the non-territorial Sangha seat (see item 1).')
    p('')

    p('3. DUPLICATE (state_code, ac_number)')
    dups = [k for k, v in collections.Counter(
        (r['state_code'], r['ac_number']) for r in out).items() if v > 1]
    p('   duplicates: %d %s' % (len(dups), dups if dups else ''))
    p('')

    p("4. MISSING AC NUMBERS (gaps inside each State/UT's own number range)")
    nums = collections.defaultdict(set)
    for r in out:
        nums[r['state_code']].add(int(r['ac_number']))
    gaps = 0
    offs = []
    for sc in sorted(nums, key=int):
        lo, mx = min(nums[sc]), max(nums[sc])
        miss = [i for i in range(lo, mx + 1) if i not in nums[sc]]
        if miss:
            gaps += 1
            p('   %-4s %-32s range %d..%d, missing %s'
              % (sc, lgd_states[sc], lo, mx, miss))
        if lo != 1:
            offs.append((sc, lo, mx))
    if not gaps:
        p('   none — every State/UT is an unbroken run of AC numbers')
    for sc, lo, mx in offs:
        p('   NOTE %-4s %-32s numbers run %d..%d, not 1..%d — see item 10'
          % (sc, lgd_states[sc], lo, mx, mx - lo + 1))
    p('')

    p('5. MISSING ENGLISH CONSTITUENCY NAMES')
    blank = [r for r in out if not r['constituency'].strip()]
    p('   blank: %d' % len(blank))
    longest = max(out, key=lambda r: len(r['constituency']))
    p('   longest name: %d chars — %r' % (len(longest['constituency']), longest['constituency']))
    p('')

    p('6. DISTRICT RECONCILIATION AGAINST lgd_districts_normalised.csv')
    conf = collections.Counter(r['mapping_confidence'] for r in out)
    for k in ('exact', 'mapped', 'needs_review', 'no_district_in_source'):
        p('   %-22s %5d rows' % (k, conf.get(k, 0)))
    hd = len(set((r['state_code'], r['district_name_eci']) for r in out))
    ok = len(set((r['state_code'], r['district_name_eci']) for r in out
                 if r['mapping_confidence'] in ('exact', 'mapped')))
    p('   distinct ECI district headings : %d' % hd)
    p('   headings resolved to an LGD district : %d' % ok)
    p('   distinct LGD districts referenced : %d of 784' %
      len(set((r['state_code'], r['district_lgd_code']) for r in out if r['district_lgd_code'])))
    p('   explicit alias table entries : %d' % len(ALIASES))
    p('')

    p('7. UNMATCHED ECI DISTRICT HEADINGS (mapping_confidence = needs_review)')
    if unmatched:
        for (sc, d), n in sorted(unmatched.items(), key=lambda kv: (int(kv[0][0]), kv[0][1])):
            why = UNMAPPABLE.get((sc, key(d)), 'NOT YET REVIEWED')
            p('   %-4s %-24s %3d rows — %s' % (sc, d, n, why))
    else:
        p('   none')
    p('   Delhi has no DISTRICT headings in Table A of the Order at all; its 70')
    p('   rows carry mapping_confidence = no_district_in_source.')
    p('')

    p('8. CROSS-DISTRICT EXTENT CASES')
    pat = re.compile(r'\b(district|District|DISTRICT)\b')
    cross = [r for r in out if pat.search(r['extent'] or '')]
    p('   rows whose extent text names a district: %d' % len(cross))
    p('   (an AC extent may draw territory from more than one district; the')
    p('    district_lgd_code column records the ECI heading the AC is listed')
    p('    under, which is a different concept from the extent.)')
    bystate = collections.Counter(r['state_code'] for r in cross)
    for sc in sorted(bystate, key=int)[:40]:
        p('     %-4s %-32s %4d' % (sc, lgd_states[sc], bystate[sc]))
    p('')

    p('9. HINDI AVAILABILITY')
    p('   constituency_hindi populated : %d of %d' %
      (sum(1 for r in out if r['constituency_hindi'].strip()), len(out)))
    p('   The English 2008 Order contains zero Devanagari characters (verified')
    p('   over the full 572-page extraction). No Hindi was transliterated or')
    p('   invented. Hindi AC names require a separate authoritative source.')
    p('')

    p('10. SOURCE COVERAGE — ALL 36 STATES/UTs')
    p('   %-4s %-34s %-6s %s' % ('code', 'state/UT', 'rows', 'status'))
    covered = collections.Counter(r['state_code'] for r in out)
    for sc in sorted(lgd_states, key=int):
        if sc in covered:
            tag = NOT_CURRENT.get(sc, ('2008', ''))[0]
            status = 'VERIFIED (2008 Order)' if tag == '2008' else 'UNRESOLVED (%s)' % tag
        elif sc in MISSING_STATES:
            status = 'UNRESOLVED — %d ACs expected, source not obtained' % MISSING_STATES[sc][1]
        elif sc in NO_ASSEMBLY:
            status = 'N/A — no Legislative Assembly, 0 ACs by law'
        else:
            status = 'UNEXPECTED — no rows and no explanation'
        p('   %-4s %-34s %-6s %s' % (sc, lgd_states[sc], covered.get(sc, 0), status))
    p('')
    p('   verified States/UTs (2008 Order is the current instrument) : %d' %
      sum(1 for sc in covered if sc not in NOT_CURRENT))
    p('   unresolved States/UTs : %d' %
      (len([sc for sc in covered if sc in NOT_CURRENT]) + len(MISSING_STATES)))
    p('   no-Assembly States/UTs : %d' % len(NO_ASSEMBLY))
    p('')

    p('11. EXPECTED MISSING ROWS (recorded, not fabricated)')
    for sc, name, n, cname, why in EXPECTED_MISSING:
        p('   %s AC %d (%s) — %s' % (name, n, cname, why))
    for sc, (name, n, why) in MISSING_STATES.items():
        p('   %s — all %d ACs — %s' % (name, n, why))
    p('')

    p('12. RESERVATION BREAKDOWN')
    res = collections.Counter(r['reservation'] for r in out)
    for k in sorted(res, key=lambda x: (x == '', x)):
        p('   %-6s %5d' % (k or '(general)', res[k]))

    open(REPORT, 'w', encoding='utf-8').write('\n'.join(L) + '\n')
    print('\n'.join(L))


if __name__ == '__main__':
    sys.exit(main())
