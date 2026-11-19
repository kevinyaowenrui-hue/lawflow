# -*- coding: utf-8 -*-
"""补录不在国家法律法规数据库中的官网全文：纪要、指导意见、立案标准、仲裁规则。"""
from __future__ import annotations

import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.import_official_statutes import (  # noqa: E402
    gaps_ok,
    int_to_cn,
    law_record,
    parse_articles,
    to_records,
    update_max_table,
)
CORPUS = ROOT / "data" / "legal" / "corpus"
REPORT_PATH = ROOT / "data" / "legal" / "corpus_import_report.json"


class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.skip += 1
        if tag in {"p", "br", "div", "h1", "h2", "h3", "tr", "li"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style"} and self.skip:
            self.skip -= 1
        if tag in {"p", "div", "li"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def fetch_text(url: str) -> str:
    resp = requests.get(
        url,
        timeout=40,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
    )
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding or "utf-8"
    parser = _Text()
    parser.feed(resp.text)
    return "".join(parser.parts)


def lines_of(text: str) -> list[str]:
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


def _split_own_articles(text: str) -> str:
    return re.sub(
        r"(?:^|[。；\n])\s*(第[〇零一二三四五六七八九十百千]+条)(?!之)",
        lambda m: "\n" + m.group(1),
        text,
    )


JOBS = [
    {
        "law_id": "private_lending_2020",
        "url": "http://gongbao.court.gov.cn/Details/94b6623974526df7d2430a3c73f050.html",
        "full_name": "最高人民法院关于审理民间借贷案件适用法律若干问题的规定",
        "short_name": "民间借贷规定",
        "hierarchy": 2,
        "domain": "民商",
        "promulgated_by": "最高人民法院",
        "min_articles": 24,
        "min_max": 28,
        "loose_gaps": True,
        "allow_numbered": False,
        "effective_date": "2021-01-01",
        "prepare": lambda text: _split_own_articles(text[text.find("第一条") :] if "第一条" in text else text),
    },
    {
        "law_id": "nine_minutes_2019",
        "url": "https://www.court.gov.cn/zixun/xiangqing/199691.html",
        "full_name": "全国法院民商事审判工作会议纪要",
        "short_name": "九民纪要",
        "hierarchy": 4,
        "domain": "民商",
        "promulgated_by": "最高人民法院",
        "min_articles": 120,
        "min_max": 130,
        "allow_numbered": True,
        "effective_date": "2019-11-08",
        "prepare": lambda text: text[text.find("1.【") :] if "1.【" in text else text,
    },
    {
        "law_id": "case_retrieval_2020",
        "url": "https://www.court.gov.cn/fabu/xiangqing/243981.html",
        "full_name": "最高人民法院关于统一法律适用加强类案检索的指导意见（试行）",
        "short_name": "类案检索指导意见",
        "hierarchy": 4,
        "domain": "民诉程序",
        "promulgated_by": "最高人民法院",
        "min_articles": 14,
        "min_max": 14,
        "allow_numbered": False,
        "effective_date": "2020-07-31",
        "prepare": lambda text: _enum_articles(text[text.find("一、本意见所称类案") :] if "一、本意见所称类案" in text else text),
    },
    {
        "law_id": "prosecution_standards_2022",
        "url": "https://www.spp.gov.cn/spp/xwfbh/wsfbt/202204/t20220429_555906.shtml",
        "full_name": "最高人民检察院、公安部关于公安机关管辖的刑事案件立案追诉标准的规定（二）",
        "short_name": "经济犯罪立案追诉标准(二)",
        "hierarchy": 2,
        "domain": "刑事",
        "promulgated_by": "最高人民检察院、公安部",
        "min_articles": 80,
        "min_max": 85,
        "allow_numbered": False,
        "effective_date": "2022-05-15",
        "prepare": lambda text: _split_bracket_articles(text[text.find("第一条 〔") :] if "第一条 〔" in text else text),
    },
    {
        "law_id": "labor_arbitration_rules",
        "url": "https://www.gov.cn/gongbao/content/2017/content_5232371.htm",
        "full_name": "劳动人事争议仲裁办案规则",
        "short_name": "劳动人事争议仲裁办案规则",
        "hierarchy": 3,
        "domain": "劳动",
        "promulgated_by": "人力资源和社会保障部",
        "min_articles": 80,
        "min_max": 81,
        "allow_numbered": False,
        "effective_date": "2017-07-01",
        "prepare": lambda text: text[text.find("第一条") :] if "第一条" in text else text,
    },
]

def _enum_articles(text: str) -> str:
    pairs = [("十四", 14), ("十三", 13), ("十二", 12), ("十一", 11), ("十", 10), ("九", 9), ("八", 8), ("七", 7), ("六", 6), ("五", 5), ("四", 4), ("三", 3), ("二", 2), ("一", 1)]
    for label, num in pairs:
        text = text.replace(label + "、", f"\n第{int_to_cn(num)}条 ")
    return text


def _split_bracket_articles(text: str) -> str:
    return re.sub(r"(第[〇零一二三四五六七八九十百千]+条)(〔)", r"\n\1\2", text)


def main() -> None:
    successes = []
    extra_report = []
    for job in JOBS:
        item = {"law_id": job["law_id"], "status": "failed", "source_url": job["url"]}
        try:
            raw = fetch_text(job["url"])
            prepared = job["prepare"](raw)
            parsed = parse_articles(lines_of(prepared), allow_numbered=job["allow_numbered"])
            ok, max_no, missing = gaps_ok(parsed, job)
            item.update({"articles": len(parsed), "max_no": max_no, "missing_sample": missing, "ok": ok})
            if not ok:
                item["error"] = "切条数量未达到预期，未写入"
                extra_report.append(item)
                continue
            target = dict(job)
            row = {"zdjgName": job["promulgated_by"], "sxrq": job["effective_date"]}
            bundle = {
                "laws": [law_record(target, row)],
                "articles": to_records(target, parsed, job["url"]),
            }
            path = CORPUS / f"{job['law_id']}.json"
            path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
            item["status"] = "imported"
            item["file"] = str(path.relative_to(ROOT)).replace("\\", "/")
            successes.append({"full_name": job["full_name"], "max_no": max_no, "effective_date": job["effective_date"]})
        except Exception as exc:
            item["error"] = f"{type(exc).__name__}: {exc}"
        extra_report.append(item)
    if successes:
        update_max_table(successes)
    if REPORT_PATH.exists():
        previous = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
        merged = {row.get("law_id"): row for row in previous}
        for row in extra_report:
            merged[row["law_id"]] = row
        REPORT_PATH.write_text(json.dumps(list(merged.values()), ensure_ascii=False, indent=2), encoding="utf-8")
    print("supplement", [(r["law_id"], r["status"], r.get("articles"), r.get("error")) for r in extra_report])


if __name__ == "__main__":
    main()
