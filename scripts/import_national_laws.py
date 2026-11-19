# -*- coding: utf-8 -*-
"""导入国家法律法规数据库中现行有效的宪法和法律正文。

不含地方性法规、行政法规和司法解释，也不重复导入已经在库里的同一部法律。
修正案、修改决定和废止决定不单独入库，正文以现行文本为准。
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.import_official_statutes import (  # noqa: E402
    CORPUS,
    download_lines,
    gaps_ok,
    law_record,
    parse_articles,
    session,
    strip_tags,
    title_key,
    to_records,
    update_max_table,
)

REPORT_PATH = ROOT / "data" / "legal" / "national_law_import_report.json"

# 宪法 + 法律分编。不含地方性法规、司法解释。
LAW_CODES = {
    100: "宪法",
    110: "宪法相关",
    120: "民商",
    130: "行政",
    140: "经济",
    150: "社会",
    155: "环境",
    160: "刑事",
    170: "程序",
}

SKIP_WORDS = ("修正案", "草案", "的决定", "的决议", "关于修改", "关于废止", "修正决定")


def fetch_catalog(http) -> list[dict]:
    found = []
    for code, domain in LAW_CODES.items():
        page = 1
        total = None
        while page < 20:
            payload = {
                "searchRange": 1,
                "sxrq": [],
                "gbrq": [],
                "searchType": 1,
                "sxx": [3],
                "gbrqYear": [],
                "flfgCodeId": [code],
                "zdjgCodeId": [],
                "searchContent": "",
                "pageNum": page,
                "pageSize": 100,
            }
            data = http.post(
                "https://flk.npc.gov.cn/law-search/search/list",
                json=payload,
                timeout=40,
            ).json()
            total = data.get("total") or 0
            rows = data.get("rows") or []
            for row in rows:
                row["_domain"] = domain
                found.append(row)
            if not rows or page * 100 >= total:
                break
            page += 1
        print(f"catalog {domain} {total}", flush=True)
    return found


def is_statute(title: str) -> bool:
    if any(word in title for word in SKIP_WORDS):
        return False
    key = title_key(title)
    return key.endswith("法") or key.endswith("法典") or key.endswith("宪法")


def existing_keys() -> set[str]:
    keys = set()
    if not CORPUS.is_dir():
        return keys
    for path in CORPUS.glob("*.json"):
        try:
            bundle = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for law in bundle.get("laws") or []:
            keys.add(title_key(law.get("full_name") or ""))
    return keys


def short_name_of(title: str) -> str:
    key = title_key(title)
    prefix = "中华人民共和国"
    if key.startswith(prefix):
        key = key[len(prefix) :]
    return key or strip_tags(title)


def choose_latest(rows: list[dict]) -> list[dict]:
    best: dict[str, dict] = {}
    for row in rows:
        title = strip_tags(row.get("title") or "")
        if not is_statute(title):
            continue
        key = title_key(title)
        prev = best.get(key)
        if prev is None or (row.get("sxrq") or "") > (prev.get("sxrq") or ""):
            row = dict(row)
            row["_title"] = title
            best[key] = row
    return list(best.values())


def main() -> None:
    CORPUS.mkdir(parents=True, exist_ok=True)
    http = session()
    chosen = choose_latest(fetch_catalog(http))
    already = existing_keys()
    print(f"statutes {len(chosen)} already {len(already)}", flush=True)
    report = []
    successes = []
    for index, row in enumerate(chosen, start=1):
        title = row["_title"]
        key = title_key(title)
        bbbs = row.get("bbbs") or ""
        item = {"title": title, "bbbs": bbbs, "sxrq": row.get("sxrq"), "domain": row.get("_domain")}
        if key in already:
            item["status"] = "skipped"
            report.append(item)
            continue
        out = CORPUS / f"flk_{bbbs}.json"
        if out.exists():
            item["status"] = "skipped"
            report.append(item)
            continue
        try:
            lines = download_lines(http, bbbs)
            parsed = parse_articles(lines, allow_numbered=False)
            target = {
                "law_id": f"flk_{bbbs}",
                "full_name": key,
                "short_name": short_name_of(title),
                "hierarchy": 1,
                "domain": row.get("_domain") or "法律",
                "promulgated_by": row.get("zdjgName") or "",
                "min_articles": 1,
                "min_max": 1,
                "loose_gaps": True,
            }
            ok, max_no, missing = gaps_ok(parsed, target)
            item.update({"paragraphs": len(lines), "articles": len(parsed), "max_no": max_no, "missing_sample": missing})
            if not ok:
                item["status"] = "failed"
                item["error"] = "未能切出条文"
                report.append(item)
                print(f"FAIL {index}/{len(chosen)} {title} lines={len(lines)}", flush=True)
                time.sleep(0.8)
                continue
            source_url = f"https://flk.npc.gov.cn/detail?bbbs={bbbs}"
            bundle = {
                "laws": [law_record(target, row)],
                "articles": to_records(target, parsed, source_url),
            }
            out.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
            item["status"] = "imported"
            successes.append({
                "full_name": key,
                "max_no": max_no,
                "effective_date": (row.get("sxrq") or "")[:10],
            })
            print(f"OK {index}/{len(chosen)} {target['short_name']} {len(parsed)}", flush=True)
        except Exception as exc:
            item["status"] = "failed"
            item["error"] = f"{type(exc).__name__}: {exc}"
            print(f"ERR {index}/{len(chosen)} {title} {item['error']}", flush=True)
        report.append(item)
        if index % 15 == 0:
            REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            if successes:
                update_max_table(successes)
                successes = []
        time.sleep(0.8)
    if successes:
        update_max_table(successes)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    imported = sum(1 for row in report if row.get("status") == "imported")
    failed = sum(1 for row in report if row.get("status") == "failed")
    skipped = sum(1 for row in report if row.get("status") == "skipped")
    print(f"done imported={imported} skipped={skipped} failed={failed}", flush=True)


if __name__ == "__main__":
    main()
