"""Dependency-free, layout-aware text extractor for the ECI 2008 Delimitation Order."""
import re, zlib, sys, json

BS = chr(92)  # backslash


def load_objects(data):
    objs = {}
    for m in re.finditer(rb'(\d+)\s+(\d+)\s+obj\b', data):
        num = int(m.group(1)); start = m.end()
        e = data.find(b'endobj', start)
        if e == -1:
            continue
        objs[num] = data[start:e]
    return objs


def get_stream(body):
    m = re.search(rb'stream\r?\n?', body)
    if not m:
        return None
    raw = body[m.end():]
    raw = re.sub(rb'\s*endstream\s*$', b'', raw)
    dic = body[:m.start()]
    if b'FlateDecode' in dic:
        try:
            return zlib.decompress(raw)
        except Exception:
            try:
                return zlib.decompressobj().decompress(raw)
            except Exception:
                return None
    return raw


def page_order(objs):
    kids_of = {}
    pages = set()
    for n, b in objs.items():
        if re.search(rb'/Type\s*/Page[^s]', b):
            pages.add(n)
        if re.search(rb'/Type\s*/Pages\b', b):
            km = re.search(rb'/Kids\s*\[(.*?)\]', b, re.S)
            kids = [int(x) for x in re.findall(rb'(\d+)\s+\d+\s+R', km.group(1))] if km else []
            kids_of[n] = kids
    allkids = set(k for v in kids_of.values() for k in v)
    roots = [n for n in kids_of if n not in allkids]
    order = []

    def walk(n, seen=set()):
        if n in seen:
            return
        seen.add(n)
        if n in kids_of:
            for k in kids_of[n]:
                walk(k, seen)
        elif n in pages:
            order.append(n)

    for r in roots:
        walk(r)
    if not order:
        order = sorted(pages)
    return order


PDF_ESC = {'n': '\n', 'r': '\r', 't': '\t', 'b': '\b', 'f': '\f',
           '(': '(', ')': ')', BS: BS}


def unescape(s):
    out = bytearray(); i = 0
    bsb = BS.encode()
    while i < len(s):
        c = s[i:i + 1]
        if c == bsb and i + 1 < len(s):
            nx = s[i + 1:i + 2]
            key = nx.decode('latin-1')
            if key in PDF_ESC:
                out += PDF_ESC[key].encode('latin-1'); i += 2; continue
            if nx.isdigit():
                j = i + 1; oct_ = b''
                while j < len(s) and len(oct_) < 3 and s[j:j + 1].isdigit():
                    oct_ += s[j:j + 1]; j += 1
                out.append(int(oct_, 8) & 0xFF); i = j; continue
            if nx in (b'\n', b'\r'):
                i += 2; continue
            out += nx; i += 2; continue
        out += c; i += 1
    return bytes(out)


TOK = re.compile(rb"""
   \( (?: [^()\\] | \\. | \( (?: [^()\\] | \\. )* \) )* \)
 | < [0-9A-Fa-f\s]* >
 | \[ | \]
 | [-+]?[0-9]*\.?[0-9]+
 | /[^\s/\[\]<>(){}]+
 | [A-Za-z'"*]+
""", re.X | re.S)


def decode_str(tok):
    if tok.startswith(b'('):
        b = unescape(tok[1:-1])
    else:
        h = re.sub(rb'\s', b'', tok[1:-1])
        if len(h) % 2:
            h += b'0'
        try:
            b = bytes.fromhex(h.decode('ascii'))
        except Exception:
            return ''
    return b.decode('cp1252', errors='replace')


def extract_page(content):
    frags = []
    tm = [1, 0, 0, 1, 0, 0]; tlm = tm[:]
    leading = 0.0
    toks = [m.group(0) for m in TOK.finditer(content)]
    i = 0

    def num(t):
        try:
            return float(t)
        except Exception:
            return 0.0

    while i < len(toks):
        t = toks[i]
        if t == b'BT':
            tm = [1, 0, 0, 1, 0, 0]; tlm = tm[:]
        elif t == b'Tm' and i >= 6:
            tm = [num(x) for x in toks[i - 6:i]]; tlm = tm[:]
        elif t == b'Td' and i >= 2:
            dx, dy = num(toks[i - 2]), num(toks[i - 1])
            tlm = [tlm[0], tlm[1], tlm[2], tlm[3],
                   tlm[0] * dx + tlm[2] * dy + tlm[4], tlm[1] * dx + tlm[3] * dy + tlm[5]]
            tm = tlm[:]
        elif t == b'TD' and i >= 2:
            dx, dy = num(toks[i - 2]), num(toks[i - 1])
            leading = -dy
            tlm = [tlm[0], tlm[1], tlm[2], tlm[3],
                   tlm[0] * dx + tlm[2] * dy + tlm[4], tlm[1] * dx + tlm[3] * dy + tlm[5]]
            tm = tlm[:]
        elif t == b'TL' and i >= 1:
            leading = num(toks[i - 1])
        elif t == b'T*':
            dy = -leading
            tlm = [tlm[0], tlm[1], tlm[2], tlm[3], tlm[2] * dy + tlm[4], tlm[3] * dy + tlm[5]]
            tm = tlm[:]
        elif t in (b'Tj', b"'", b'"'):
            for j in range(i - 1, max(-1, i - 4), -1):
                if toks[j].startswith(b'(') or toks[j].startswith(b'<'):
                    if t != b'Tj':
                        dy = -leading
                        tlm = [tlm[0], tlm[1], tlm[2], tlm[3],
                               tlm[2] * dy + tlm[4], tlm[3] * dy + tlm[5]]
                        tm = tlm[:]
                    frags.append((round(tm[5], 1), round(tm[4], 1), decode_str(toks[j])))
                    break
        elif t == b'TJ':
            depth = 0; j = i - 1; parts = []
            while j >= 0:
                if toks[j] == b']':
                    depth += 1
                elif toks[j] == b'[':
                    depth -= 1
                    if depth == 0:
                        break
                elif toks[j].startswith(b'(') or toks[j].startswith(b'<'):
                    parts.append(decode_str(toks[j]))
                j -= 1
            frags.append((round(tm[5], 1), round(tm[4], 1), ''.join(reversed(parts))))
        i += 1
    return frags


def page_lines(frags, ytol=2.0):
    if not frags:
        return []
    rows = {}
    for y, x, s in frags:
        if not s.strip():
            continue
        key = None
        for k in rows:
            if abs(k - y) <= ytol:
                key = k; break
        if key is None:
            key = y; rows[key] = []
        rows[key].append((x, s))
    out = []
    for y in sorted(rows, reverse=True):
        out.append([y, sorted(rows[y], key=lambda p: p[0])])
    return out


def main(path, out):
    data = open(path, 'rb').read()
    objs = load_objects(data)
    order = page_order(objs)
    pages = []
    for on in order:
        body = objs[on]
        cm = re.search(rb'/Contents\s+(?:(\d+)\s+\d+\s+R|\[(.*?)\])', body, re.S)
        content = b''
        if cm:
            refs = [int(cm.group(1))] if cm.group(1) else [int(x) for x in re.findall(rb'(\d+)\s+\d+\s+R', cm.group(2))]
            for r in refs:
                if r in objs:
                    s = get_stream(objs[r])
                    if s:
                        content += s + b'\n'
        pages.append(page_lines(extract_page(content)))
    json.dump(pages, open(out, 'w', encoding='utf-8'))
    nchar = sum(len(t) for p in pages for ln in p for _, t in ln[1])
    print('pages:', len(pages), 'chars:', nchar)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
