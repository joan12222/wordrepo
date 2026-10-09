"""《名校名师高考英语词汇全攻略（新）》扫描 PDF → 默写库候选词（v2 流程）。
收词口径、流程和验收标准见 CLAUDE.md「OCR 候选词提取」。

用法：
  python ocr_candidates.py extract <起页> <止页>     OCR（有缓存则复用）+ 机器提取 + 复核条带图
  python ocr_candidates.py extract 60,75,165          也可以给逗号分隔的页列表
  python ocr_candidates.py show <页>                 打印候选清单和报警，供复核
  python ocr_candidates.py crop <页> <y0> <y1> [x0 x1] [dpi]   无标记原图局部（坐标为该页 200dpi 转正后的像素）
  python ocr_candidates.py build <起页> <止页>        汇总 review.json → 候选_pA-B.json + 待核_pA-B.md
  python ocr_candidates.py eval <页列表> root|v2      与标准答案对比（root=项目根目录旧候选，v2=候选v2/truth/）
"""
import json, os, re, subprocess, sys, tempfile, time
import cv2, fitz, numpy as np

ROOT = os.path.dirname(os.path.abspath(__file__))
PDF = os.path.join(ROOT, '名校名师高考英语词汇全攻略（新）.pdf')
OUT = os.path.join(ROOT, '候选v2')
WORK = os.path.join(OUT, 'work')
OCR_KW = dict(text_score=0.0, box_thresh=0.3, unclip_ratio=1.6)  # rapidocr 默认 text_score=0.5 会静默丢行
DPI, DPI_HI, N_STRIPS, N_REVIEW = 200, 300, 7, 4

POS = r'(?:vt|vi|vl|adj|adv|ad|prep|conj|pron|num|int|aux|art|n|v|a)'  # vl 是 vt 的常见误读
POS_SET = {'vt', 'vi', 'vl', 'adj', 'adv', 'ad', 'prep', 'conj', 'pron', 'num', 'int', 'aux', 'art', 'n', 'v', 'a'}
# 词性后跟 . 或 ,；或者丢了点、直接接括号/中文（如 "*darken v(使)"）
POS_TAIL = r"(?:\s*[\.,．，]|(?=\s*[\(\[〔（一-鿿]))"
POS_AFTER = re.compile(r"\s*(?:/[^/]{1,40}/\s*)?(?:\(=?[^)]{0,30}\)\s*)?(" + POS + r")" + POS_TAIL)
POS_ANY = re.compile(r"(?<![A-Za-z])" + POS + POS_TAIL)
TOKEN = re.compile(r"\*?[A-Za-z][A-Za-z'’\-]*")
PHON = re.compile(r"/[^/\s一-鿿][^/一-鿿]{0,30}/")  # 音标段不含中文、斜杠后不接空格（排除 "A/ B a.感到/使人" 这类斜杠并列）
ABBR = {'sb', 'sth', 'pl', 'etc', 'eg', 'ie', 'sb\'s', 'one\'s'}
CJK = re.compile(r'[　-ヿ一-鿿＀-￯〔〕（）]')
CONT = re.compile(r'[\[\(【［〔（　-ヿ一-鿿]')  # 释义续行的开头：中文或括号
HAN = re.compile(r'[一-鿿]')
RANK = {'H': 0, 'D': 1, 'U': 2}


def page_dir(p):
    return os.path.join(WORK, f'p{p:04d}')


def save_img(path, rgb, ext='.jpg', params=(cv2.IMWRITE_JPEG_QUALITY, 92)):
    """cv2.imwrite 在 Windows 上不支持中文路径且会静默失败，改用 imencode 自己写。"""
    ok, buf = cv2.imencode(ext, cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), list(params))
    if not ok:
        raise RuntimeError(f'图片编码失败：{path}')
    buf.tofile(path)


def render(doc, p, dpi, rot):
    pix = doc[p - 1].get_pixmap(dpi=dpi)
    img = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)[:, :, :3]
    return np.ascontiguousarray(np.rot90(img, rot)) if rot else img.copy()


def cyan_mask(img):
    c = img.astype(np.int16)
    r, g, b = c[..., 0], c[..., 1], c[..., 2]
    return (np.minimum(np.minimum(r, g), b) < 170) & (b - r > 45) & (g - r > 35)


def dark_mask(img):
    return img.min(axis=2) < 130


def shade_mask(img):
    """「辨析」等浅青色底纹框（底色约 (225~233, 238~247, 246~252)），返回大块底纹区域的掩码。"""
    c = img.astype(np.int16)
    r, g, b = c[..., 0], c[..., 1], c[..., 2]
    m = ((r < 242) & (b > 235) & (b - r >= 10) & (g - r >= 6)).astype(np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((25, 25), np.uint8))
    h, w = m.shape
    n, lab, st, _ = cv2.connectedComponentsWithStats(m)
    keep = [i for i in range(1, n) if st[i][4] > 0.02 * w * h and st[i][2] > 0.4 * w]
    return np.isin(lab, keep)


def run_ocr(ocr, img):
    res, _ = ocr(img, **OCR_KW)
    return [[[[float(x), float(y)] for x, y in box], text, float(s)] for box, text, s in (res or [])]


def bbox(poly):
    xs = [q[0] for q in poly]; ys = [q[1] for q in poly]
    return [min(xs), min(ys), max(xs), max(ys)]


def choose_rotation(ocr, doc, p):
    """横版页（宽>高）试 90°/270° 两个方向，比较有效英文框数和左侧青色词头列；指标冲突则报警。"""
    r = doc[p - 1].rect
    if r.width <= r.height:
        return 0, None
    stats = {}
    for rot in (1, 3):
        img = render(doc, p, 100, rot)
        boxes = run_ocr(ocr, img)
        good = sum(1 for b, t, s in boxes if s > 0.8 and len(re.findall(r'[A-Za-z]', t)) >= 4)
        cm = cyan_mask(img)
        heads = [round(bbox(b)[0] / 10) for b, t, s in boxes
                 if cm[int(bbox(b)[1]):int(bbox(b)[3]), int(bbox(b)[0]):int(bbox(b)[0]) + 40].mean() > 0.15]
        col = max((heads.count(v) for v in set(heads)), default=0)
        stats[rot] = (good, col)
    a, b = stats[1], stats[3]
    rot = 1 if a[0] >= b[0] else 3
    other = 3 if rot == 1 else 1
    alarm = None if stats[rot][1] >= stats[other][1] else f'方向指标冲突 {stats}'
    return rot, alarm


def ocr_page(ocr, doc, p):
    """两路识别：整页 DPI 一路；DPI_HI 分 N_STRIPS 条带（上下重叠）一路，坐标换算回整页 DPI。缓存到 ocr.json。"""
    d = page_dir(p); os.makedirs(d, exist_ok=True)
    cache = os.path.join(d, 'ocr.json')
    if os.path.exists(cache):
        return json.load(open(cache, encoding='utf-8'))
    rot, rot_alarm = choose_rotation(ocr, doc, p)
    img = render(doc, p, DPI, rot)
    full = run_ocr(ocr, img)
    hi = render(doc, p, DPI_HI, rot)
    sx, sy = img.shape[1] / hi.shape[1], img.shape[0] / hi.shape[0]
    H = hi.shape[0]; step = H // N_STRIPS; strip = []
    for k in range(N_STRIPS):
        core0, core1 = k * step, (H if k == N_STRIPS - 1 else (k + 1) * step)
        a, b = max(0, core0 - step // 4), min(H, core1 + step // 4)
        for poly, t, s in run_ocr(ocr, hi[a:b]):
            cy = (min(q[1] for q in poly) + max(q[1] for q in poly)) / 2 + a
            if core0 <= cy < core1:  # 重叠区只保留中心落在本条带核心区的框，避免一处算两次
                strip.append([[[x * sx, (y + a) * sy] for x, y in poly], t, s])
    data = dict(page=p, rotation=rot * 90, rotation_alarm=rot_alarm, size=[img.shape[1], img.shape[0]],
                full=full, strip=strip)
    json.dump(data, open(cache, 'w', encoding='utf-8'), ensure_ascii=False)
    return data


def reading_order(items):
    """按行聚类（相邻 y 差 <15px 视为同一行）后从左到右排序。"""
    items = sorted(items, key=lambda e: e['y'])
    line, last = 0, None
    for e in items:
        if last is not None and e['y'] - last >= 15:
            line += 1
        e['_line'] = line; last = e['y']
    items.sort(key=lambda e: (e['_line'], e['x']))
    for e in items:
        del e['_line']
    return items


def char_weights(text):
    return [2.0 if CJK.match(ch) else 1.0 for ch in text]


def tokens_of_read(boxes, img, cm, ink, shade, w, h):
    """把一路识别结果拆成候选 token（H 词头 / D 派生词 / U 未解释英文）和排除记录。"""
    toks, excluded = [], []
    boxes = sorted(boxes, key=lambda b: (bbox(b[0])[1] + bbox(b[0])[3]) / 2)
    for bi, (poly, text, score) in enumerate(boxes):
        x0, y0, x1, y1 = bbox(poly)
        if y1 < h * 0.08:
            excluded.append(dict(text=text, reason='页眉', box=[x0, y0, x1, y1])); continue
        if shade[min(h - 1, int((y0 + y1) / 2)), min(w - 1, int((x0 + x1) / 2))]:
            excluded.append(dict(text=text, reason='辨析等底纹框内', box=[x0, y0, x1, y1])); continue
        if x0 > w * 0.85 and len(text.strip()) <= 4:
            excluded.append(dict(text=text, reason='侧边字母标签/页码', box=[x0, y0, x1, y1])); continue
        t = text.replace('’', "'")
        wts = char_weights(t); tot = sum(wts) or 1
        cum = np.concatenate([[0], np.cumsum(wts)])
        xpos = lambda i: x0 + (x1 - x0) * cum[min(i, len(t))] / tot
        phon = [(m.start(), m.end()) for m in PHON.finditer(t)]
        has_pos = POS_ANY.search(t) is not None
        found = list(TOKEN.finditer(t))
        first = found[0] if found else None
        lead_ok = first is not None and re.fullmatch(r'[\s\d→\-\*>]*', t[:first.start()]) is not None
        is_head = False
        if lead_ok:
            xa, xb = int(x0), int(max(xpos(first.end()), x0 + 20))
            reg = (ink | cm)[int(y0):int(y1), xa:xb]
            is_head = reg.sum() > 0 and cm[int(y0):int(y1), xa:xb].sum() / reg.sum() > 0.4
        # 以英文开头、无词性、且带中文译文的框才算明确的例句/短语行；没有中文的（如 "embarrassing/ embarrassed"，
        # 词性折到下一行）不排除，按未解释英文进待核
        # 行首是 * 开头的词，或首词粘着词性（"emotionallyad."、"*enterprisinga."），可能是派生词，不按例句排除
        star_lead = lead_ok and first.group(0).startswith('*')
        merged_lead = lead_ok and re.match(r'[\.,．，]', t[first.end():]) is not None and any(
            first.group(0).lstrip('*').endswith(s) and len(first.group(0).lstrip('*')) - len(s) >= 3 for s in POS_SET)
        # 明确的例句/短语行：带中文译文，或者是 3 个词以上的英文句子（译文在下一行）
        example_like = (lead_ok and not is_head and not has_pos and not star_lead and not merged_lead
                        and (HAN.search(t) is not None or len(found) >= 3))
        if example_like:
            excluded.append(dict(text=text, reason='例句/短语行（以英文开头、无词性、带中文）', box=[x0, y0, x1, y1])); continue
        for m in found:
            raw = m.group(0); word = raw.lstrip('*')
            if any(a <= m.start() < b for a, b in phon):
                excluded.append(dict(text=raw, reason='/…/ 音标内', box=[x0, y0, x1, y1])); continue
            after = t[m.end():]
            head_tok = m is first and is_head  # 词头先判，避免 art/ad 这类词头被当成词性标记跳过
            if not head_tok and word in POS_SET and re.match(POS_TAIL, after):
                continue  # 词性标记本身
            if not head_tok and word.lower() in ABBR:
                excluded.append(dict(text=raw, reason='缩写 sb/sth 等', box=[x0, y0, x1, y1])); continue
            if not head_tok and len(word) == 1:
                excluded.append(dict(text=raw, reason='单字母（多为〔C〕〔U〕等标记）', box=[x0, y0, x1, y1])); continue
            flags = []
            pm = POS_AFTER.match(after)
            # 词性和单词粘连（"*elevatevl."、"emotionallyad."）：词尾是词性且后面紧跟句点时拆开
            suf = None
            if not head_tok and not pm and re.match(r'[\.,．，]', after):
                suf = next((s for s in sorted(POS_SET, key=len, reverse=True)
                            if word.endswith(s) and len(word) - len(s) >= 3), None)
            if head_tok:
                kind = 'H'
                ph = next((b for a, b in phon if m.end() <= a <= m.end() + 3), m.end())  # 跳过紧跟词头的音标
                pa = POS_ANY.search(t, ph)
                mstart = pa.start() if pa else ph
            elif suf:
                kind = 'D'; mstart = m.end() - len(suf)
                word = word[:-len(suf)]
                flags.append('词性粘连拆分')
            elif pm:
                kind = 'D'; mstart = m.end() + pm.start(1)
            else:
                kind = 'U'; mstart = None
                prev = t[max(0, m.start() - 1):m.start()]
                if prev in ("'", 'ˈ', '/', ':'):
                    flags.append('疑似音标')
            if raw.startswith('*'):
                flags.append('星号')
            xa, xb = xpos(m.start()), xpos(m.end())
            toks.append(dict(word=word, kind=kind, box=bi, x=(xa + xb) / 2, xa=xa, xb=xb, y=(y0 + y1) / 2,
                             y1=y1, text=t, start=m.start(), end=m.end(), mstart=mstart, flags=flags, score=score))
    # 释义初稿：从词性开始，到同框下一个 H/D 为止；到框尾时接一行以中文/括号开头的续行
    hd = [k for k in toks if k['kind'] in 'HD']
    for k in hd:
        if k['mstart'] is None:
            k['meaning'] = ''; continue
        nxt = [o['start'] for o in hd if o['box'] == k['box'] and o['start'] > k['start']]
        end = min(nxt) if nxt else len(k['text'])
        mean = k['text'][k['mstart']:end].strip()
        if not nxt:
            # 该框是本行最右一个框时，下一行以中文/括号开头的框视为释义续行，接到下一个派生词之前
            bx0, by0, bx1, by1 = bbox(boxes[k['box']][0]); bh = by1 - by0
            peers = [bbox(b[0]) for b in boxes if abs((bbox(b[0])[1] + bbox(b[0])[3]) / 2 - (by0 + by1) / 2) < bh * 0.5]
            if bx0 >= max(q[0] for q in peers) - 1:
                for poly2, text2, s2 in boxes[k['box'] + 1:]:
                    cx0, cy0, cx1, cy1 = bbox(poly2)
                    if cy0 > by1 + bh * 1.2:
                        break
                    if cy0 > by0 + bh * 0.5:
                        if CONT.match(text2.strip()[:1] or 'a'):
                            d2 = next((q for q in TOKEN.finditer(text2) if POS_AFTER.match(text2[q.end():])), None)
                            mean += ' ' + (text2[:d2.start()] if d2 else text2).strip()
                        break
        k['meaning'] = re.sub(r'\s+', ' ', mean).strip(' ;；,，')
    return toks, excluded


def normalize_meaning(s):
    """统一 OCR 读出的括号和可数标记：【c] / ［C］ / [cJ → [C]，[u] → [U]。"""
    s = re.sub(r'[【［〔]', '[', s)
    s = re.sub(r'[】］〕]', ']', s)
    s = re.sub(r'\[\s*[cC]\s*[\]JjIl1]', '[C]', s)
    s = re.sub(r'\[\s*[uU]\s*[\]JjIl1)]', '[U]', s)
    return s


def merge_reads(tf, ts):
    """同位置一对一匹配两路 token（|dy|<18 且 |dx|<90，按距离贪心）。"""
    pairs = sorted(((abs(a['x'] - b['x']) + 3 * abs(a['y'] - b['y']), i, j)
                    for i, a in enumerate(tf) for j, b in enumerate(ts)
                    if abs(a['y'] - b['y']) < 18 and abs(a['x'] - b['x']) < 90))
    used_f, used_s, cands = set(), set(), []
    for dist, i, j in pairs:
        if i in used_f or j in used_s:
            continue
        used_f.add(i); used_s.add(j)
        cands.append((tf[i], ts[j]))
    cands += [(tf[i], None) for i in range(len(tf)) if i not in used_f]
    cands += [(None, ts[j]) for j in range(len(ts)) if j not in used_s]
    return cands


def spell_check(words):
    """Windows 自带拼写检查（en-US）。返回 {word: bool}，结果缓存到 work/spell_cache.json。"""
    cache_f = os.path.join(WORK, 'spell_cache.json')
    cache = json.load(open(cache_f, encoding='utf-8')) if os.path.exists(cache_f) else {}
    todo = sorted({w for w in words if w not in cache})
    if todo:
        cs = r'''
using System; using System.Runtime.InteropServices; using System.Runtime.InteropServices.ComTypes;
[ComImport, Guid("B7C82D61-FBE8-4B47-9B27-6C0D2E0DE0A3"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface ISpellingError { uint StartIndex{get;} uint Length{get;} int CorrectiveAction{get;} string Replacement{ [return: MarshalAs(UnmanagedType.LPWStr)] get;} }
[ComImport, Guid("803E3BD4-2828-4410-8290-418D1D73C762"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface IEnumSpellingError { [PreserveSig] int Next(out ISpellingError err); }
[ComImport, Guid("B6FD0B71-E2BC-4653-8D05-F197E412770B"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface ISpellChecker { [return: MarshalAs(UnmanagedType.LPWStr)] string get_LanguageTag(); IEnumSpellingError Check([MarshalAs(UnmanagedType.LPWStr)] string text); }
[ComImport, Guid("8E018A9D-2415-4677-BF08-794EA61F94BB"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface ISpellCheckerFactory { IEnumString get_SupportedLanguages(); int IsSupported([MarshalAs(UnmanagedType.LPWStr)] string tag); ISpellChecker CreateSpellChecker([MarshalAs(UnmanagedType.LPWStr)] string tag); }
public static class Spell {
  public static string Run(string path){
    var f=(ISpellCheckerFactory)Activator.CreateInstance(Type.GetTypeFromCLSID(new Guid("7AB36653-1796-484B-BDFA-E74F1DB7C1DC")));
    var c=f.CreateSpellChecker("en-US"); var sb=new System.Text.StringBuilder();
    foreach(var w in System.IO.File.ReadAllLines(path)){ if(w.Length==0) continue; ISpellingError e; sb.AppendLine(w+"\t"+(c.Check(w).Next(out e)!=0?"1":"0")); }
    return sb.ToString();
  }
}'''
        with tempfile.TemporaryDirectory() as td:
            wf = os.path.join(td, 'words.txt'); pf = os.path.join(td, 'spell.ps1')
            open(wf, 'w', encoding='utf-8').write('\n'.join(todo))
            open(pf, 'w', encoding='utf-8-sig').write("$src=@'\n" + cs + "\n'@\nAdd-Type -TypeDefinition $src\n[Spell]::Run($args[0])\n")
            r = subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', pf, wf],
                               capture_output=True, text=True, encoding='utf-8', errors='replace')
            got = dict(line.rsplit('\t', 1) for line in r.stdout.splitlines() if '\t' in line)
            missing = [w for w in todo if w not in got]
            if missing:
                raise RuntimeError(f'拼写检查失败（{len(missing)} 个词无结果）：{r.stderr[:500]}')
            cache.update({w: got[w] == '1' for w in todo})
        json.dump(cache, open(cache_f, 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
    return {w: cache[w] for w in words}


def alarms_for(data, img, cm, ink, cands, w, h):
    al = []
    if data['rotation_alarm']:
        al.append(dict(type='方向', note=data['rotation_alarm'], box=[0, 0, w, h]))
    # 1) 残余墨迹：有墨迹但两路识别都没框到
    cov = np.zeros((h, w), np.uint8)
    for poly, t, s in data['full'] + data['strip']:
        cv2.fillPoly(cov, [np.array(poly, np.int32)], 1)
    cov = cv2.dilate(cov, np.ones((9, 9), np.uint8))
    res = ((ink | cm) & (cov == 0)).astype(np.uint8)
    res[:int(h * 0.08)] = 0
    n, lab, st, _ = cv2.connectedComponentsWithStats(cv2.dilate(res, np.ones((5, 15), np.uint8)))
    for i in range(1, n):
        x, y, bw, bh, area = st[i]
        if area > 150 and 10 < bh < 120 and bw < w * 0.5:
            al.append(dict(type='残余墨迹', note='有墨迹但两路识别都没有框到', box=[int(x), int(y), int(x + bw), int(y + bh)]))
    # 2) 左侧青色词头块没有对应的 H 候选
    heads = [c for c in cands if c['kind'] == 'H']
    col = np.median([c['xa'] for c in heads]) if heads else w * 0.1
    blk = cv2.morphologyEx(cm.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((5, 25), np.uint8))
    n, lab, st, _ = cv2.connectedComponentsWithStats(blk)
    for i in range(1, n):
        x, y, bw, bh, area = st[i]
        if 15 < bh < 80 and bw > 30 and x < col + 80 and y > h * 0.08:
            if not any(x - 15 <= c['x'] <= x + bw + 15 and y - 15 <= c['y'] <= y + bh + 15 for c in heads):
                al.append(dict(type='青色词头未匹配', note='左侧青色块附近没有词头候选', box=[int(x), int(y), int(x + bw), int(y + bh)]))
    # 3) 字符密度：框很宽但识别出的字符很少（框在、字丢了）
    rat = []
    for poly, t, s in data['full']:
        L = sum(char_weights(t)); x0, y0, x1, y1 = bbox(poly)
        if L >= 8:
            rat.append((x1 - x0) / L)
    if rat:
        med = float(np.median(rat))
        for poly, t, s in data['full']:
            L = sum(char_weights(t)); x0, y0, x1, y1 = bbox(poly)
            if L >= 3 and (x1 - x0) / L > 2.2 * med and y0 > h * 0.08:
                al.append(dict(type='字符过稀', note=f'识别文本「{t}」相对框宽过短', box=[x0, y0, x1, y1]))
    for i, a in enumerate(al, 1):
        a['id'] = f'A{i}'
    return al


def postprocess(p, doc):
    d = page_dir(p)
    data = json.load(open(os.path.join(d, 'ocr.json'), encoding='utf-8'))
    w, h = data['size']
    img = render(doc, p, DPI, data['rotation'] // 90)
    cm, ink, shade = cyan_mask(img), dark_mask(img), shade_mask(img)
    tf, ef = tokens_of_read(data['full'], img, cm, ink, shade, w, h)
    ts, es = tokens_of_read(data['strip'], img, cm, ink, shade, w, h)
    raw = merge_reads(tf, ts)
    spell = spell_check([(a or b)['word'] for a, b in raw] + [b['word'] for a, b in raw if a and b])
    cands = []
    for a, b in raw:
        src = a or b
        kind = min((k['kind'] for k in (a, b) if k), key=RANK.get)
        wf, ws = (a['word'] if a else None), (b['word'] if b else None)
        if wf and ws and wf != ws:
            word = wf if spell.get(wf) or not spell.get(ws) else ws
        else:
            word = wf or ws
        flags = sorted(set((a['flags'] if a else []) + (b['flags'] if b else [])))
        if not (a and b): flags.append('单路识别')
        elif wf != ws: flags.append('两路不一致')
        if not spell.get(word): flags.append('拼写检查未过')
        if word != word.lower(): flags.append('含大写')
        if kind == 'U': flags.append('未解释英文')
        meaning = normalize_meaning(next((k['meaning'] for k in (a, b) if k and k['kind'] in 'HD' and k.get('meaning')), ''))
        if kind in 'HD' and not HAN.search(meaning): flags.append('释义无中文')
        status = 'machine_agree' if kind in 'HD' and set(flags) <= {'星号'} else 'pending'
        cands.append(dict(word=word, word_full=wf, word_strip=ws, kind=kind, x=round(src['x']), y=round(src['y']),
                          xa=round(src['xa']), xb=round(src['xb']), y1=round(src['y1']),
                          meaning=meaning, flags=flags, status=status))
    cands = reading_order(cands)
    for i, c in enumerate(cands, 1):
        c['id'] = i
    al = alarms_for(data, img, cm, ink, cands, w, h)
    # 复核条带图：按阅读顺序切 N_REVIEW 段（上下重叠 60px），下划线+编号标候选，红框标报警
    vis = img.copy()
    color = {'machine_agree': (0, 160, 0), 'pending': (255, 140, 0)}
    for c in cands:
        col = (220, 0, 220) if c['kind'] == 'U' else color[c['status']]
        cv2.line(vis, (c['xa'], c['y1'] + 3), (c['xb'], c['y1'] + 3), col, 2)
        cv2.putText(vis, str(c['id']), (c['xa'], c['y1'] + 17), cv2.FONT_HERSHEY_SIMPLEX, 0.5, col, 1, cv2.LINE_AA)
    for a in al:
        x0, y0, x1, y1 = map(int, a['box'])
        cv2.rectangle(vis, (x0, y0), (x1, y1), (230, 0, 0), 2)
        cv2.putText(vis, a['id'], (x0, max(12, y0 - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (230, 0, 0), 2, cv2.LINE_AA)
    strips, step = [], h // N_REVIEW
    for k in range(N_REVIEW):
        y0, y1 = max(0, k * step - 30), min(h, (k + 1) * step + 30)
        f = f'rv_{k + 1}.jpg'
        save_img(os.path.join(d, f), vis[y0:y1])
        strips.append(dict(n=k + 1, file=f, y0=y0, y1=y1))
    m = dict(page=p, rotation=data['rotation'], size=data['size'], strips=strips, candidates=cands, alarms=al,
             excluded=ef + [dict(e, read='strip') for e in es])
    json.dump(m, open(os.path.join(d, 'machine.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    return m


def parse_pages(args):
    if len(args) == 1:
        return [int(x) for x in args[0].split(',')]
    return list(range(int(args[0]), int(args[1]) + 1))


def cmd_extract(args):
    from rapidocr_onnxruntime import RapidOCR
    pages = parse_pages(args); doc = fitz.open(PDF); ocr = RapidOCR()
    for p in pages:
        t0 = time.time(); ocr_page(ocr, doc, p)
        m = postprocess(p, doc)
        pend = sum(c['status'] == 'pending' for c in m['candidates'])
        print(f'p{p}: {time.time() - t0:.0f}s 候选 {len(m["candidates"])}（待核 {pend}）报警 {len(m["alarms"])}', flush=True)


def cmd_show(args):
    p = int(args[0]); m = json.load(open(os.path.join(page_dir(p), 'machine.json'), encoding='utf-8'))
    print(f'p{p} rotation={m["rotation"]} strips=' + ' '.join(f'{s["n"]}:{s["y0"]}-{s["y1"]}' for s in m['strips']))
    for c in m['candidates']:
        two = '' if c['word_full'] == c['word_strip'] else f' [整页={c["word_full"]} 条带={c["word_strip"]}]'
        mark = '✓' if c['status'] == 'machine_agree' else '?'
        print(f'{c["id"]:>3} {mark} {c["kind"]} y={c["y"]:<5} {c["word"]}{two}  | {c["meaning"]}  {",".join(c["flags"])}')
    for a in m['alarms']:
        print(f'{a["id"]} {a["type"]} box={[int(v) for v in a["box"]]} {a["note"]}')


def cmd_crop(args):
    p, y0, y1 = int(args[0]), int(args[1]), int(args[2])
    x0, x1 = (int(args[3]), int(args[4])) if len(args) >= 5 else (0, None)
    dpi = int(args[5]) if len(args) >= 6 else 400
    m = json.load(open(os.path.join(page_dir(p), 'machine.json'), encoding='utf-8'))
    img = render(fitz.open(PDF), p, dpi, m['rotation'] // 90)
    s = dpi / DPI
    x1 = x1 if x1 is not None else int(m['size'][0])
    f = os.path.join(page_dir(p), f'crop_{y0}_{y1}_{x0}_{x1}.png')
    save_img(f, img[int(y0 * s):int(y1 * s), int(x0 * s):int(x1 * s)], '.png', ())
    print(f)


def final_entries(m, rv):
    """按 review.json 裁决得到该页最终条目，同时核对每个候选、报警、条带都有处置。"""
    ids = {c['id'] for c in m['candidates']}
    seen = list(rv.get('ok', [])) + [int(i) for i in rv.get('fix', {})] + \
        [int(i) for i in rv.get('undecided', {})] + [i for v in rv.get('reject', {}).values() for i in v]
    errs = []
    if sorted(seen) != sorted(ids):
        dup = sorted({i for i in seen if seen.count(i) > 1}); lack = sorted(ids - set(seen)); extra = sorted(set(seen) - ids)
        errs.append(f'候选处置对不上账：缺 {lack} 重复 {dup} 多余 {extra}')
    lack_a = [a['id'] for a in m['alarms'] if a['id'] not in rv.get('alarms', {})]
    if lack_a: errs.append(f'报警没有结论：{lack_a}')
    lack_s = [s['n'] for s in m['strips'] if s['n'] not in rv.get('strips_checked', [])]
    if lack_s: errs.append(f'条带没复核：{lack_s}')
    by_id = {c['id']: c for c in m['candidates']}
    out = []
    for c in m['candidates']:
        i = c['id']
        if i in rv.get('ok', []):
            out.append(dict(word=c['word'], meaning=c['meaning'], y=c['y'], x=c['x'], src=f'#{i}'))
        elif str(i) in rv.get('fix', {}):
            f = rv['fix'][str(i)]
            out.append(dict(word=f.get('word', c['word']), meaning=f.get('meaning', c['meaning']), y=c['y'], x=c['x'],
                            src=f'#{i} 改', note=f.get('note', '')))
    for a in rv.get('added', []):
        ref = by_id.get(a.get('after'))
        out.append(dict(word=a['word'], meaning=a['meaning'], y=(ref['y'] if ref else a.get('y', 0)),
                        x=(ref['x'] + 1 if ref else 0), src='复核新增', note=a.get('note', '')))
    out = reading_order(out)
    for e in out:
        e['word'] = e['word'].lstrip('*').strip()
        if not e['word'] or ' ' in e['word'] or not e['meaning'].strip():
            errs.append(f'不满足导入限制：{e}')
    return out, errs


def cmd_build(args):
    a, b = int(args[0]), int(args[1])
    rows, md, total_err, undecided = [], [], [], []
    for p in range(a, b + 1):
        d = page_dir(p)
        m = json.load(open(os.path.join(d, 'machine.json'), encoding='utf-8'))
        rf = os.path.join(d, 'review.json')
        if not os.path.exists(rf):
            total_err.append(f'p{p} 没有 review.json'); continue
        rv = json.load(open(rf, encoding='utf-8'))
        out, errs = final_entries(m, rv)
        total_err += [f'p{p} {e}' for e in errs]
        rows += [dict(word=e['word'], meaning=e['meaning'].strip(), page=p) for e in out]
        by_id = {c['id']: c for c in m['candidates']}
        md.append(f'## p{p}\n\n- 候选 {len(m["candidates"])}，收录 {len(out)}，复核新增 {len(rv.get("added", []))}，'
                  f'条带 {rv.get("strips_checked")}，复核用时 {rv.get("minutes", "?")} 分钟')
        for i, f in rv.get('fix', {}).items():
            c = by_id[int(i)]
            md.append(f'- 改 #{i} {c["word"]} → {f.get("word", c["word"])}｜{f.get("meaning", c["meaning"])}　{f.get("note", "")}')
        for e in rv.get('added', []):
            md.append(f'- 新增 {e["word"]}｜{e["meaning"]}　{e.get("note", "")}')
        for reason, ids in rv.get('reject', {}).items():
            md.append(f'- 排除（{reason}）：' + '、'.join(f'#{i} {by_id[i]["word"]}' for i in ids if i in by_id))
        for i, note in rv.get('undecided', {}).items():
            c = by_id[int(i)]
            undecided.append(f'p{p} #{i} {c["word"]}｜{c["meaning"]}　{note}（看图：work/p{p:04d}/）')
        for aid, note in rv.get('alarms', {}).items():
            md.append(f'- 报警 {aid}：{note}')
        if rv.get('notes'):
            md.append(f'- 备注：{rv["notes"]}')
        md.append('')
    if total_err:
        print('build 失败，以下问题需要先处理：'); print('\n'.join(total_err)); sys.exit(1)
    os.makedirs(OUT, exist_ok=True)
    json.dump(rows, open(os.path.join(OUT, f'候选_p{a}-{b}.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    head = [f'# 待核_p{a}-{b}', '', f'状态：{"完成" if not undecided else f"未完成，{len(undecided)} 项待用户裁决"}；'
            f'收录 {len(rows)} 条', '']
    if undecided:
        head += ['## 待用户裁决（不在候选 JSON 里）', ''] + [f'- {u}' for u in undecided] + ['']
    open(os.path.join(OUT, f'待核_p{a}-{b}.md'), 'w', encoding='utf-8').write('\n'.join(head + md))
    print(f'候选_p{a}-{b}.json：{len(rows)} 条；待用户裁决 {len(undecided)} 项')


def edit1(a, b):
    """编辑距离不超过 2 时返回距离，否则返回 3（只用于对齐，不算命中）。"""
    if abs(len(a) - len(b)) > 2: return 3
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return min(prev[-1], 3)


def cmd_eval(args):
    pages = parse_pages(args[:1]); src = args[1]
    truth = {}
    if src == 'root':
        import glob
        for f in glob.glob(os.path.join(ROOT, '候选_p*.json')):
            for x in json.load(open(f, encoding='utf-8')):
                truth.setdefault(x['page'], []).append(x['word'])
    for p in pages:
        if src == 'v2':
            truth[p] = json.load(open(os.path.join(OUT, 'truth', f'p{p:04d}.json'), encoding='utf-8'))
        t = [w.lstrip('*') for w in truth.get(p, [])]
        m = json.load(open(os.path.join(page_dir(p), 'machine.json'), encoding='utf-8'))
        stages = [('机器', [c['word'] for c in m['candidates']])]
        rf = os.path.join(page_dir(p), 'review.json')
        if os.path.exists(rf):
            out, errs = final_entries(m, json.load(open(rf, encoding='utf-8')))
            stages.append(('复核后', [e['word'] for e in out]))
        for name, got in stages:
            pool = list(got); exact = []
            for w in t:
                if w in pool: pool.remove(w); exact.append(w)
            rest = [w for w in t if w not in exact]
            near = []
            for w in rest:
                best = min(pool, key=lambda g: edit1(w, g), default=None)
                if best is not None and edit1(w, best) <= 2:
                    pool.remove(best); near.append(f'{w}≈{best}')
            miss = [w for w in rest if not any(n.startswith(w + '≈') for n in near)]
            print(f'p{p} {name}: 标准 {len(t)}  精确命中 {len(exact)}  近似对齐 {len(near)} {near}  '
                  f'未覆盖 {miss}  多出 {len(pool)}')


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    fn = dict(extract=cmd_extract, show=cmd_show, crop=cmd_crop, build=cmd_build, eval=cmd_eval).get(cmd)
    if not fn:
        print(__doc__); sys.exit(1)
    fn(sys.argv[2:])
