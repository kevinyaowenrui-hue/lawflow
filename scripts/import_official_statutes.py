# -*- coding: utf-8 -*-
"""从国家法律法规数据库下载现行全文，按条写入 data/legal/corpus。

种子库里已经人工核对的条文不会被覆盖（加载时种子优先）。
新条文标记 OFFICIAL_SOURCE：可检索，引用核对为待抽核。
"""
from __future__ import annotations

import io
import json
import re
import sys
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from gateway.utils.article_text import trim_glued_section_heading

CORPUS = ROOT / "data" / "legal" / "corpus"
MAX_PATH = ROOT / "data" / "legal" / "statute_max_articles.json"
REPORT_PATH = ROOT / "data" / "legal" / "corpus_import_report.json"

W_T = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t"
W_P = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p"

ART_LINE = re.compile(
    r"^第([〇零一二三四五六七八九十百千]+)条(之([一二三四五六七八九十]+))?(.*)$"
)
NUM_LINE = re.compile(r"^(\d{1,3})[\.、．]\s*(.*)$")
PART_LINE = re.compile(r"^第[〇零一二三四五六七八九十百千]+编")
CHAP_LINE = re.compile(r"^第[〇零一二三四五六七八九十百千]+章")
SEC_LINE = re.compile(r"^第[〇零一二三四五六七八九十百千]+节")
CN_NUM = {"零": 0, "〇": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
CN_UNIT = {"十": 10, "百": 100, "千": 1000}
SUFFIX = {"一": "1", "二": "2", "三": "3", "四": "4", "五": "5", "六": "6", "七": "7", "八": "8", "九": "9", "十": "10"}

IMPORTED_AT = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

TARGETS = [
    {"law_id": "civil_code_2021", "query": "中华人民共和国民法典", "full_name": "中华人民共和国民法典", "short_name": "民法典", "hierarchy": 1, "domain": "民商", "promulgated_by": "全国人民代表大会", "min_articles": 1200, "min_max": 1260},
    {"law_id": "company_law_2024", "query": "中华人民共和国公司法", "full_name": "中华人民共和国公司法", "short_name": "新公司法(2024)", "hierarchy": 1, "domain": "公司", "promulgated_by": "全国人民代表大会常务委员会", "min_articles": 250, "min_max": 260},
    {"law_id": "criminal_law_2024", "query": "中华人民共和国刑法", "full_name": "中华人民共和国刑法", "short_name": "刑法(修正案十二)", "hierarchy": 1, "domain": "刑事", "promulgated_by": "全国人民代表大会常务委员会", "min_articles": 400, "min_max": 450, "loose_gaps": True},
    {"law_id": "civil_procedure_2023", "query": "中华人民共和国民事诉讼法", "full_name": "中华人民共和国民事诉讼法", "short_name": "民事诉讼法(2023修正)", "hierarchy": 1, "domain": "民诉程序", "promulgated_by": "全国人民代表大会常务委员会", "min_articles": 280, "min_max": 300},
    {"law_id": "labor_contract_2013", "query": "中华人民共和国劳动合同法", "full_name": "中华人民共和国劳动合同法", "short_name": "劳动合同法", "hierarchy": 1, "domain": "劳动", "promulgated_by": "全国人民代表大会常务委员会", "min_articles": 90, "min_max": 98},
    {"law_id": "labor_law", "query": "中华人民共和国劳动法", "full_name": "中华人民共和国劳动法", "short_name": "劳动法", "hierarchy": 1, "domain": "劳动", "promulgated_by": "全国人民代表大会常务委员会", "min_articles": 100, "min_max": 107},
    {"law_id": "admin_procedure_law", "query": "中华人民共和国行政诉讼法", "full_name": "中华人民共和国行政诉讼法", "short_name": "行政诉讼法", "hierarchy": 1, "domain": "行政", "promulgated_by": "全国人民代表大会常务委员会", "min_articles": 90, "min_max": 100},
    {"law_id": "labor_mediation_law", "query": "中华人民共和国劳动争议调解仲裁法", "full_name": "中华人民共和国劳动争议调解仲裁法", "short_name": "劳动争议调解仲裁法", "hierarchy": 1, "domain": "劳动", "promulgated_by": "全国人民代表大会常务委员会", "min_articles": 50, "min_max": 54},
    {"law_id": "pipl", "query": "中华人民共和国个人信息保护法", "full_name": "中华人民共和国个人信息保护法", "short_name": "个人信息保护法", "hierarchy": 1, "domain": "数据", "promulgated_by": "全国人民代表大会常务委员会", "min_articles": 70, "min_max": 74},
    {"law_id": "anti_unfair_competition", "query": "中华人民共和国反不正当竞争法", "full_name": "中华人民共和国反不正当竞争法", "short_name": "反不正当竞争法", "hierarchy": 1, "domain": "竞争", "promulgated_by": "全国人民代表大会常务委员会", "min_articles": 35, "min_max": 40},
    {"law_id": "data_security_law", "query": "中华人民共和国数据安全法", "full_name": "中华人民共和国数据安全法", "short_name": "数据安全法", "hierarchy": 1, "domain": "数据", "promulgated_by": "全国人民代表大会常务委员会", "min_articles": 50, "min_max": 55},
    {"law_id": "cybersecurity_law", "query": "中华人民共和国网络安全法", "full_name": "中华人民共和国网络安全法", "short_name": "网络安全法", "hierarchy": 1, "domain": "数据", "promulgated_by": "全国人民代表大会常务委员会", "min_articles": 70, "min_max": 79},
    {"law_id": "consumer_protection_law", "query": "中华人民共和国消费者权益保护法", "full_name": "中华人民共和国消费者权益保护法", "short_name": "消费者权益保护法", "hierarchy": 1, "domain": "民商", "promulgated_by": "全国人民代表大会常务委员会", "min_articles": 55, "min_max": 63},
    {"law_id": "contract_interp_2023", "query": "合同编通则若干问题的解释", "full_name": "最高人民法院关于适用〈中华人民共和国民法典〉合同编通则若干问题的解释", "short_name": "合同编通则解释", "hierarchy": 2, "domain": "合同", "promulgated_by": "最高人民法院", "min_articles": 60, "min_max": 65, "title_contains": "合同编通则若干问题的解释"},
    {"law_id": "guarantee_interp_2021", "query": "有关担保制度的解释", "full_name": "最高人民法院关于适用〈中华人民共和国民法典〉有关担保制度的解释", "short_name": "担保制度解释", "hierarchy": 2, "domain": "民商", "promulgated_by": "最高人民法院", "min_articles": 65, "min_max": 70, "title_contains": "有关担保制度的解释"},
    {"law_id": "private_lending_2020", "query": "审理民间借贷案件适用法律若干问题的规定", "full_name": "最高人民法院关于审理民间借贷案件适用法律若干问题的规定", "short_name": "民间借贷规定", "hierarchy": 2, "domain": "民商", "promulgated_by": "最高人民法院", "min_articles": 24, "min_max": 28, "title_contains": "民间借贷案件适用法律若干问题的规定", "loose_gaps": True},
    {"law_id": "general_provisions_interp", "query": "总则编若干问题的解释", "full_name": "最高人民法院关于适用〈中华人民共和国民法典〉总则编若干问题的解释", "short_name": "总则编解释", "hierarchy": 2, "domain": "民商", "promulgated_by": "最高人民法院", "min_articles": 30, "min_max": 35, "title_contains": "总则编若干问题的解释"},
    {"law_id": "temporal_effect_rules", "query": "民法典〉时间效力的若干规定", "full_name": "最高人民法院关于适用〈中华人民共和国民法典〉时间效力的若干规定", "short_name": "时间效力规定", "hierarchy": 2, "domain": "民商", "promulgated_by": "最高人民法院", "min_articles": 20, "min_max": 25, "title_contains": "时间效力的若干规定"},
    {"law_id": "civil_procedure_interp", "query": "适用《中华人民共和国民事诉讼法》的解释", "full_name": "最高人民法院关于适用〈中华人民共和国民事诉讼法〉的解释", "short_name": "民诉法解释", "hierarchy": 2, "domain": "民诉程序", "promulgated_by": "最高人民法院", "min_articles": 480, "min_max": 540, "title_contains": "适用中华人民共和国民事诉讼法的解释", "title_excludes": ["执行程序", "审判监督"]},
    {"law_id": "labor_dispute_interp_1", "query": "审理劳动争议案件适用法律问题的解释", "full_name": "最高人民法院关于审理劳动争议案件适用法律问题的解释（一）", "short_name": "劳动争议解释一", "hierarchy": 2, "domain": "劳动", "promulgated_by": "最高人民法院", "min_articles": 40, "min_max": 50, "title_contains": "劳动争议案件适用法律问题的解释（一）"},
    {"law_id": "evidence_rules", "query": "民事诉讼证据的若干规定", "full_name": "最高人民法院关于民事诉讼证据的若干规定", "short_name": "证据规定", "hierarchy": 2, "domain": "民诉程序", "promulgated_by": "最高人民法院", "min_articles": 80, "min_max": 90, "title_contains": "民事诉讼证据的若干规定"},
    {"law_id": "nine_minutes_2019", "query": "全国法院民商事审判工作会议纪要", "full_name": "全国法院民商事审判工作会议纪要", "short_name": "九民纪要", "hierarchy": 4, "domain": "民商", "promulgated_by": "最高人民法院", "min_articles": 100, "min_max": 120, "title_contains": "民商事审判工作会议纪要", "allow_numbered": True},
    {"law_id": "additional_parties_2020", "query": "民事执行中变更、追加当事人若干问题的规定", "full_name": "最高人民法院关于民事执行中变更、追加当事人若干问题的规定", "short_name": "追加规定", "hierarchy": 2, "domain": "民诉程序", "promulgated_by": "最高人民法院", "min_articles": 20, "min_max": 25, "title_contains": "变更、追加当事人若干问题的规定"},
    {"law_id": "case_retrieval_2020", "query": "统一法律适用加强类案检索的指导意见", "full_name": "最高人民法院关于统一法律适用加强类案检索的指导意见（试行）", "short_name": "类案检索指导意见", "hierarchy": 4, "domain": "民诉程序", "promulgated_by": "最高人民法院", "min_articles": 4, "min_max": 4, "title_contains": "类案检索的指导意见"},
    {"law_id": "prosecution_standards_2022", "query": "立案追诉标准的规定（二）", "full_name": "最高人民检察院、公安部关于公安机关管辖的刑事案件立案追诉标准的规定（二）", "short_name": "经济犯罪立案追诉标准(二)", "hierarchy": 2, "domain": "刑事", "promulgated_by": "最高人民检察院、公安部", "min_articles": 40, "min_max": 50, "title_contains": "立案追诉标准的规定（二）"},
    {"law_id": "labor_arbitration_rules", "query": "劳动人事争议仲裁办案规则", "full_name": "劳动人事争议仲裁办案规则", "short_name": "劳动人事争议仲裁办案规则", "hierarchy": 3, "domain": "劳动", "promulgated_by": "人力资源和社会保障部", "min_articles": 50, "min_max": 60, "title_contains": "劳动人事争议仲裁办案规则"},
]


def session() -> requests.Session:
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://flk.npc.gov.cn",
            "Referer": "https://flk.npc.gov.cn/search",
        }
    )
    s.get("https://flk.npc.gov.cn/", timeout=20)
    return s


def strip_tags(title: str) -> str:
    return re.sub(r"<[^>]+>", "", title or "").strip()


def title_key(title: str) -> str:
    text = strip_tags(title)
    text = text.replace("〈", "").replace("〉", "").replace("《", "").replace("》", "")
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"（\d{4}[^）]{0,12}）", "", text)
    text = re.sub(r"\(\d{4}[^)]{0,12}\)", "", text)
    return text


def int_to_cn(num: int) -> str:
    digits = "零一二三四五六七八九"
    if num <= 0:
        return str(num)
    if num < 10:
        return digits[num]
    if num < 20:
        return "十" + (digits[num % 10] if num % 10 else "")
    units = ["", "十", "百", "千"]
    s = str(num)
    res = ""
    n = len(s)
    for i, ch in enumerate(s):
        d = int(ch)
        if d:
            res += digits[d] + units[n - 1 - i]
        elif not res.endswith("零"):
            res += "零"
    return res.rstrip("零")


def cn_to_int(cn_str: str) -> int:
    total = 0
    temp = 0
    for char in cn_str:
        if char in CN_UNIT:
            unit = CN_UNIT[char]
            if temp == 0:
                temp = 1
            total += temp * unit
            temp = 0
        elif char in CN_NUM:
            temp = CN_NUM[char]
        else:
            return 0
    return total + temp


def docx_paragraphs(blob: bytes) -> list[str]:
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        xml = zf.read("word/document.xml")
    root = ET.fromstring(xml)
    lines = []
    for para in root.iter(W_P):
        text = "".join((node.text or "") for node in para.iter(W_T)).strip()
        if text:
            lines.append(text)
    return lines


def _is_toc_article(body: str) -> bool:
    body = body.strip()
    if not body:
        return True
    if re.fullmatch(r"\d{1,4}", body):
        return True
    if len(body) < 12 and re.search(r"\d{1,4}$", body):
        return True
    return False


def parse_articles(lines: list[str], allow_numbered: bool) -> list[dict]:
    part = chapter = section = ""
    articles: dict[str, dict] = {}
    order: list[str] = []
    current = None

    def flush():
        nonlocal current
        current = None

    def store(key: str, article_no_cn: str, article_no_int: int, body: str, numbered: bool, allow_empty: bool = False):
        body = body.strip()
        if not allow_empty and _is_toc_article(body):
            return
        prev = articles.get(key)
        if prev and len(prev["content"]) >= len(body) and prev["content"]:
            return
        item = {
            "key": key,
            "article_no_cn": article_no_cn,
            "article_no_int": article_no_int,
            "content": body,
            "part_name": part,
            "chapter_name": chapter,
            "section_name": section,
            "numbered": numbered,
        }
        articles[key] = item
        if key not in order:
            order.append(key)

    def start_article(key, article_no_cn, article_no_int, body, numbered=False):
        nonlocal current
        flush()
        store(key, article_no_cn, article_no_int, body, numbered, allow_empty=not body.strip())
        current = key

    numbered_hits = 0
    article_hits = 0
    for line in lines:
        if line in {"目录", "目 录"}:
            flush()
            current = None
            continue
        if PART_LINE.match(line) and not ART_LINE.match(line):
            flush()
            part = line
            chapter = section = ""
            continue
        if CHAP_LINE.match(line) and not ART_LINE.match(line):
            flush()
            chapter = line
            section = ""
            continue
        if SEC_LINE.match(line):
            flush()
            section = line
            continue
        if line == "附则":
            flush()
            chapter = "附则"
            section = ""
            continue
        m = ART_LINE.match(line)
        if m:
            article_hits += 1
            base = cn_to_int(m.group(1))
            suffix = m.group(3)
            body = (m.group(4) or "").strip()
            if suffix:
                key = f"{base}_{SUFFIX.get(suffix, suffix)}"
                label = f"第{m.group(1)}条之{suffix}"
            else:
                key = str(base)
                label = f"第{m.group(1)}条"
            if base <= 0:
                continue
            start_article(key, label, base, body)
            continue
        nm = NUM_LINE.match(line) if allow_numbered else None
        if nm:
            numbered_hits += 1
            num = int(nm.group(1))
            if 1 <= num <= 400:
                start_article(str(num), f"第{int_to_cn(num)}条", num, (nm.group(2) or "").strip(), numbered=True)
                continue
        if current and current in articles:
            articles[current]["content"] = (articles[current]["content"] + "\n" + line).strip()

    if allow_numbered and numbered_hits > article_hits:
        articles = {k: v for k, v in articles.items() if v.get("numbered")}
        order = [k for k in order if k in articles]
    articles = {k: v for k, v in articles.items() if not _is_toc_article(v["content"])}
    order = [k for k in order if k in articles]
    cleaned = []
    for key in order:
        item = articles[key]
        item["content"] = trim_glued_section_heading(item["content"])
        if _is_toc_article(item["content"]):
            continue
        cleaned.append(item)
    return cleaned


def search_rows(s: requests.Session, query: str, search_type: int = 1) -> list[dict]:
    payload = {
        "searchRange": 1,
        "sxrq": [],
        "gbrq": [],
        "searchType": search_type,
        "sxx": [],
        "gbrqYear": [],
        "flfgCodeId": [],
        "zdjgCodeId": [],
        "searchContent": query,
        "pageNum": 1,
        "pageSize": 20,
    }
    resp = s.post("https://flk.npc.gov.cn/law-search/search/list", json=payload, timeout=40)
    resp.raise_for_status()
    data = resp.json()
    return list(data.get("rows") or [])


def pick_row(rows: list[dict], target: dict) -> dict | None:
    contains = target.get("title_contains")
    excludes = list(target.get("title_excludes") or [])
    excludes.extend(["草案", "决定", "答记者问", "解读", "修正案"])
    want = title_key(target["full_name"])
    ranked = []
    for row in rows:
        title = strip_tags(row.get("title") or "")
        key = title_key(title)
        exact = key == want
        if contains:
            if not exact and contains not in title and contains not in key:
                continue
        elif not exact:
            continue
        if any(bad in title for bad in excludes):
            continue
        sxx = int(row.get("sxx") or 0)
        if sxx == 1:
            continue
        ranked.append((0 if exact else 1, 0 if sxx == 3 else 1, row.get("sxrq") or "", row))
    if not ranked:
        return None
    ranked.sort(key=lambda item: (item[0], item[1], item[2]), reverse=False)
    # 精确标题优先，现行有效优先，施行日期取最新
    best_rank = (ranked[0][0], ranked[0][1])
    pool = [item for item in ranked if (item[0], item[1]) == best_rank]
    pool.sort(key=lambda item: item[2], reverse=True)
    return pool[0][3]


def _download_blob(s: requests.Session, bbbs: str, fmt: str) -> bytes:
    last = ""
    for attempt in range(6):
        meta = s.get(
            "https://flk.npc.gov.cn/law-search/download/pc",
            params={"bbbs": bbbs, "format": fmt},
            timeout=40,
        )
        body = meta.text or ""
        try:
            payload = meta.json()
        except json.JSONDecodeError:
            last = f"HTTP {meta.status_code} {body[:80]!r}"
            s.get("https://flk.npc.gov.cn/", timeout=20)
            time.sleep(3 + attempt * 5)
            continue
        url = ((payload.get("data") or {}).get("url")) or ""
        if not url.startswith("https://"):
            last = f"无下载链接 {str(payload)[:120]}"
            time.sleep(2 + attempt * 4)
            continue
        blob = s.get(url, timeout=90).content
        if blob:
            return blob
        last = "下载文件为空"
        time.sleep(2 + attempt * 4)
    raise RuntimeError(f"官网下载失败：{last}")


def _pdf_lines(blob: bytes) -> list[str]:
    import pymupdf
    doc = pymupdf.open(stream=blob, filetype="pdf")
    lines = []
    for page in doc:
        lines.extend(ln.strip() for ln in page.get_text().splitlines() if ln.strip())
    doc.close()
    return lines


def download_lines(s: requests.Session, bbbs: str) -> list[str]:
    blob = _download_blob(s, bbbs, "docx")
    if blob.startswith(b"PK"):
        return docx_paragraphs(blob)
    if blob.startswith(b"\xd0\xcf\x11\xe0"):
        blob = _download_blob(s, bbbs, "pdf")
    if blob.startswith(b"%PDF"):
        return _pdf_lines(blob)
    raise RuntimeError(f"下载内容不是 docx 或 pdf（{len(blob)} 字节，开头 {blob[:16]!r}）")


def gaps_ok(articles: list[dict], target: dict) -> tuple[bool, int, list[int]]:
    nums = sorted({int(a["article_no_int"]) for a in articles})
    if not nums:
        return False, 0, []
    max_no = nums[-1]
    missing = [n for n in range(1, max_no + 1) if n not in set(nums)]
    if target.get("loose_gaps"):
        ok = len(articles) >= target["min_articles"] and max_no >= target["min_max"]
    else:
        allowance = max(3, int(max_no * 0.04))
        ok = (
            len(articles) >= target["min_articles"]
            and max_no >= target["min_max"]
            and len(missing) <= allowance
        )
    return ok, max_no, missing[:12]


def to_records(target: dict, parsed: list[dict], source_url: str) -> list[dict]:
    records = []
    for art in parsed:
        suffix = ""
        key = art["key"]
        if "_" in key:
            suffix = "_" + key.split("_", 1)[1]
            art_id = f"{target['law_id']}:art_{art['article_no_int']}{suffix}"
        else:
            art_id = f"{target['law_id']}:art_{art['article_no_int']}"
        records.append(
            {
                "id": art_id,
                "law_id": target["law_id"],
                "part_name": art["part_name"],
                "chapter_name": art["chapter_name"],
                "section_name": art["section_name"],
                "article_no_cn": art["article_no_cn"],
                "article_no_int": art["article_no_int"],
                "content": art["content"],
                "has_proviso": 1 if "但是" in art["content"] else 0,
                "key_terms": [],
                "claim_basis_type": "",
                "verification_status": "OFFICIAL_SOURCE",
                "source_url": source_url,
                "verified_at": "",
                "verified_by": "",
                "review_note": "来自国家法律法规数据库现行文本自动切条，未经逐条律师复核。",
            }
        )
    return records


def law_record(target: dict, row: dict) -> dict:
    return {
        "id": target["law_id"],
        "full_name": target["full_name"],
        "short_name": target["short_name"],
        "hierarchy": target["hierarchy"],
        "promulgated_by": row.get("zdjgName") or target["promulgated_by"],
        "promulgated_doc_no": "",
        "effective_date": (row.get("sxrq") or "")[:10],
        "status": "VALID",
        "domain": target["domain"],
        "summary": "国家法律法规数据库现行文本全文导入。",
        "version_note": "官网全文自动切条，待律师抽核。会议纪要、指导意见不得作为裁判依据直接援引。" if target["hierarchy"] == 4 else "官网全文自动切条，待律师抽核。",
        "verification_status": "OFFICIAL_SOURCE",
    }


def update_max_table(successes: list[dict]) -> None:
    table = json.loads(MAX_PATH.read_text(encoding="utf-8"))
    by_name = {item["law_name"]: item for item in table}
    for item in successes:
        entry = by_name.get(item["full_name"])
        version = {
            "effective_from": item["effective_date"] or "1970-01-01",
            "max_articles": item["max_no"],
            "source": "flk.npc.gov.cn",
            "verified": True,
        }
        if entry is None:
            entry = {"law_name": item["full_name"], "versions": [version]}
            table.append(entry)
            by_name[item["full_name"]] = entry
            continue
        versions = entry.setdefault("versions", [])
        matched = None
        for ver in versions:
            if int(ver.get("max_articles") or 0) == item["max_no"]:
                matched = ver
                break
        if matched:
            matched["source"] = "flk.npc.gov.cn"
            matched["verified"] = True
            if item["effective_date"] and str(matched.get("effective_from") or "").startswith("TODO"):
                matched["effective_from"] = item["effective_date"]
        else:
            versions.append(version)
    MAX_PATH.write_text(json.dumps(table, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    import sys
    only = {part.strip() for part in sys.argv[1:] if part.strip()}
    CORPUS.mkdir(parents=True, exist_ok=True)
    s = session()
    report = []
    successes = []
    for target in TARGETS:
        if only and target["law_id"] not in only:
            continue
        item = {"law_id": target["law_id"], "query": target["query"], "status": "failed"}
        try:
            rows = search_rows(s, target["query"])
            row = pick_row(rows, target)
            if row is None:
                rows = search_rows(s, target["query"], search_type=2)
                row = pick_row(rows, target)
            item["candidates"] = [
                {"title": strip_tags(r.get("title") or ""), "sxrq": r.get("sxrq"), "sxx": r.get("sxx")}
                for r in rows[:8]
            ]
            row = pick_row(rows, target)
            if not row:
                item["error"] = "未匹配到现行文本"
                report.append(item)
                continue
            title = strip_tags(row.get("title") or "")
            bbbs = row["bbbs"]
            item.update({"picked_title": title, "sxrq": row.get("sxrq"), "sxx": row.get("sxx"), "bbbs": bbbs})
            lines = download_lines(s, bbbs)
            parsed = parse_articles(lines, allow_numbered=bool(target.get("allow_numbered")))
            ok, max_no, missing = gaps_ok(parsed, target)
            item.update({"paragraphs": len(lines), "articles": len(parsed), "max_no": max_no, "missing_sample": missing, "ok": ok})
            if not ok:
                item["error"] = "切条数量或连续性未达到该法预期，未写入"
                report.append(item)
                time.sleep(0.3)
                continue
            source_url = f"https://flk.npc.gov.cn/detail?bbbs={bbbs}"
            bundle = {"laws": [law_record(target, row)], "articles": to_records(target, parsed, source_url)}
            out = CORPUS / f"{target['law_id']}.json"
            out.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
            item["status"] = "imported"
            item["file"] = str(out.relative_to(ROOT)).replace("\\", "/")
            successes.append(
                {
                    "full_name": target["full_name"],
                    "max_no": max_no,
                    "effective_date": (row.get("sxrq") or "")[:10],
                }
            )
        except Exception as exc:
            item["error"] = f"{type(exc).__name__}: {exc}"
        report.append(item)
        time.sleep(0.35)
    if only and REPORT_PATH.exists():
        previous = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
        merged = {row.get("law_id"): row for row in previous}
        for row in report:
            merged[row.get("law_id")] = row
        report = [merged[t["law_id"]] for t in TARGETS if t["law_id"] in merged]
    if successes:
        update_max_table(successes)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    imported = sum(1 for r in report if r.get("status") == "imported")
    print(f"imported {imported}/{len(TARGETS)} report={REPORT_PATH}")


if __name__ == "__main__":
    main()
