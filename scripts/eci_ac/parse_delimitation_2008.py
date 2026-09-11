"""Stage 2: parse layout JSON of the 2008 Delimitation Order into AC rows."""
import json, re, sys, csv, collections

ROMAN = ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X', 'XI', 'XII', 'XIII',
         'XIV', 'XV', 'XVI', 'XVII', 'XVIII', 'XIX', 'XX', 'XXI', 'XXII', 'XXIII', 'XXIV',
         'XXV', 'XXVI', 'XXVII', 'XXVIII', 'XXIX', 'XXX', 'XXXI', 'XXXII']

DASH = r'[-‐-―:.–—]'
RE_SCHED = re.compile(r'^\s*SCHEDULE\s*[-–—]?\s*(' + '|'.join(ROMAN) + r')\s*$', re.I)
RE_ANNEX1 = re.compile(r'^\s*ANNEXURE\s*[-–—]?\s*I\s*$', re.I)
RE_PARTA = re.compile(r'(PART|TABLE)\s*[-–—]?\s*A\s*[-–—]?\s*ASSEMBLY\s+CONSTITUENC', re.I)
RE_PARTA2 = re.compile(r'TABLE\s*[-–—]\s*A\s+ASSEMBLY\s+CONSTITUENC', re.I)
RE_ANNEX_ACS = re.compile(r'^\s*ASSEMBLY\s+CONSTITUENCIES\s*&\s*THEIR\s+EXTENT\s*$', re.I)
RE_PARTB = re.compile(r'(PART|TABLE)\s*[-–—]?\s*B\s*[-–—]?\s*\s*PARLIAMENTARY', re.I)
RE_DISTRICT = re.compile(r'^\s*(?:(\d+)\s*[-–—]?\s*)?DISTRICT\s*[:\-–—]\s*([^,;]{2,60}?)\s*$', re.I)
RE_ACNUM = re.compile(r'^\s*(\d{1,3})\s*(?:' + DASH + r'\s*)?(.*)$')
RE_HDR = re.compile(r'Sl\.?\s*No\.?\s*&\s*Name', re.I)
RE_STOP = re.compile(r'^\s*(NOTE\s*[.:\-]|Abbreviations?\s*[:\-]|The above Order)', re.I)
RE_NOTE = re.compile(r'^\s*NOTE\s*[:\-]', re.I)
RE_ANNEXA = re.compile(r'^\s*(ANNEXURE\s*[-–—]?\s*A|APPENDIX)\s*$', re.I)

SCHED_STATE = {}  # roman -> state name, discovered from the PDF


def joined(frs):
    return ' '.join(t for x, t in frs).strip()


def norm(s):
    s = s.replace('–', '-').replace('—', '-').replace('’', "'")
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def find_sections(pages):
    """-> list of dicts: {name, roman, pages:[idx], ...} state AC sections."""
    marks = []  # (page_idx, kind, value)
    for pi, p in enumerate(pages):
        for y, frs in p[:8]:
            line = norm(joined(frs))
            m = RE_SCHED.match(line)
            if m:
                # state name = next non-empty line(s) on this page before the PART/TABLE line
                name = None
                started = False
                for y2, frs2 in p:
                    l2 = norm(joined(frs2))
                    if l2 == line:
                        started = True
                        continue
                    if not started:
                        continue
                    if not l2:
                        continue
                    if RE_PARTA.search(l2) or RE_PARTA2.search(l2) or 'PARLIAMENTARY' in l2.upper():
                        break
                    name = l2
                    break
                marks.append((pi, 'sched', m.group(1), name))
            elif RE_ANNEX1.match(line):
                marks.append((pi, 'annex1', 'ANNEX-I', 'JAMMU AND KASHMIR'))
    return marks


def parse(pages, out_csv):
    marks = find_sections(pages)
    # section page ranges
    sections = []
    for i, (pi, kind, rom, name) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(pages)
        sections.append({'start': pi, 'end': end, 'roman': rom, 'name': name, 'kind': kind})
    rows = []
    diag = []
    for sec in sections:
        st = sec['name']
        if not st:
            diag.append(('NO_STATE_NAME', sec['roman'], sec['start'] + 1))
            continue
        st = st.upper()
        if 'PARLIAMENT' in st:
            continue
        # ---- determine AC page range: from Part/Table A to Part/Table B
        a_start = None
        a_end = sec['end'] - 1
        for pi in range(sec['start'], sec['end']):
            for y, frs in pages[pi]:
                line = norm(joined(frs))
                if a_start is None and (RE_PARTA.search(line) or RE_PARTA2.search(line)
                                        or (sec['kind'] == 'annex1' and RE_ANNEX_ACS.match(line))):
                    a_start = pi
                elif a_start is not None and (RE_PARTB.search(line) or RE_ANNEXA.match(line)):
                    a_end = pi
                    break
            if a_end != sec['end'] - 1:
                break
        if a_start is None:
            diag.append(('NO_PART_A', sec['roman'], st, sec['start'] + 1))
            continue
        # ---- column geometry from AC-numbered lines within the AC range
        pairs = []
        for pi in range(a_start, min(a_end + 1, len(pages))):
            for y, frs in pages[pi]:
                if len(frs) < 2:
                    continue
                t0 = norm(frs[0][1])
                if RE_ACNUM.match(t0) and not RE_DISTRICT.match(t0) and len(t0) < 60:
                    x0, x1 = frs[0][0], frs[1][0]
                    if x1 - x0 > 40:
                        pairs.append((x0, x1))
        if not pairs:
            diag.append(('NO_COLUMNS', sec['roman'], st))
            continue
        name_left = min(p[0] for p in pairs)
        ext_left = collections.Counter(p[1] for p in pairs).most_common(1)[0][0]
        if ext_left <= name_left + 40:
            ext_left = min(p[1] for p in pairs if p[1] > name_left + 40)
        boundary = name_left + 0.62 * (ext_left - name_left)

        district = ''
        cur = None  # current AC row dict
        for pi in range(a_start, min(a_end + 1, len(pages))):
            for y, frs in pages[pi]:
                line = norm(joined(frs))
                if not line:
                    continue
                if RE_HDR.search(line) or RE_NOTE.match(line) or RE_PARTA.search(line) \
                        or RE_PARTA2.search(line) or RE_SCHED.match(line) or RE_ANNEX1.match(line):
                    continue
                if RE_PARTB.search(line) or RE_ANNEXA.match(line) or RE_STOP.match(line):
                    break
                if line == st or line.replace(' ', '') == st.replace(' ', ''):
                    continue
                if re.fullmatch(r'\d{1,4}', line):  # page number
                    continue
                dm = RE_DISTRICT.match(line)
                if dm and len(line) < 90 and re.search(r'[A-Za-z]{2}', dm.group(2)):
                    district = norm(dm.group(2)).rstrip('.').strip()
                    district = re.sub(r'\s*\(.*?contd.*?\)\s*$', '', district, flags=re.I).strip()
                    continue
                namep = [t for x, t in frs if x < boundary]
                extp = [t for x, t in frs if x >= boundary]
                ntxt = norm(' '.join(namep))
                etxt = norm(' '.join(extp))
                am = RE_ACNUM.match(ntxt) if ntxt else None
                # A bare number in the name column starts a new AC row only when it
                # continues the state's AC sequence (the name then wraps to the next line).
                if am and not am.group(2).strip():
                    nxt = (cur['ac_number'] + 1) if cur is not None else 1
                    if int(am.group(1)) != nxt:
                        am = None
                if am:
                    cur = {'state': st, 'district_eci': district, 'ac_number': int(am.group(1)),
                           'name_parts': [am.group(2).strip()], 'extent': [etxt], 'page': pi + 1}
                    rows.append(cur)
                elif cur is not None:
                    # A wrapped AC name is short and word-like; anything longer or
                    # numeric that lands in the name column is really extent text.
                    if ntxt:
                        if (len(ntxt) <= 30 and len(ntxt.split()) <= 4
                                and not re.search(r'\d', ntxt)
                                and (ntxt[0].isupper() or not ntxt[0].isalpha())):
                            cur['name_parts'].append(ntxt)
                        else:
                            cur['extent'].append(ntxt)
                    if etxt:
                        cur['extent'].append(etxt)
                elif etxt or ntxt:
                    diag.append(('ORPHAN', st, pi + 1, (ntxt + ' ' + etxt)[:60]))
    # finalise
    out = []
    for r in rows:
        nm = norm(' '.join(r['name_parts']))
        res = ''
        m = re.search(r'\((SC|ST)\)', nm, re.I)
        if m:
            res = m.group(1).upper()
            nm = norm(re.sub(r'\((SC|ST)\)', '', nm, flags=re.I))
        nm = nm.strip(' .-–—')
        out.append({'state_name_eci': r['state'], 'district_eci': r['district_eci'],
                    'ac_number': r['ac_number'], 'constituency': nm, 'reservation': res,
                    'extent': norm(' '.join(r['extent'])), 'page': r['page']})
    with open(out_csv, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
        w.writeheader()
        w.writerows(out)
    cnt = collections.Counter(r['state_name_eci'] for r in out)
    for k in sorted(cnt):
        print('%-22s %4d' % (k, cnt[k]))
    print('TOTAL', len(out))
    print('--- diagnostics (first 40) ---')
    for d in diag[:40]:
        print(d)
    print('diag total', len(diag))


if __name__ == '__main__':
    parse(json.load(open('do2008.json', encoding='utf-8')), sys.argv[1])
