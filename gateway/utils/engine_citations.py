# -*- coding: utf-8 -*-
"""
LawFlow 智律工作台 - 各引擎实际引用的条文清单
用于保证 data/legal 种子库至少覆盖引擎引用（允许 PENDING_HUMAN 占位）。
不得在此编造法条正文。
"""
from __future__ import annotations

from typing import Any, Dict, List

# law_id 与 seed_articles.json 中 laws.id 对齐；article_no_int 为阿拉伯数字条号
ENGINE_CITED_ARTICLES: List[Dict[str, Any]] = [
    # 保证 / 资金流水引擎
    {"law_id": "civil_code_2021", "article_no_int": 392, "engines": ["guarantee_and_cashflow"]},
    {"law_id": "civil_code_2021", "article_no_int": 561, "engines": ["guarantee_and_cashflow"]},
    {"law_id": "civil_code_2021", "article_no_int": 670, "engines": ["guarantee_and_cashflow"]},
    {"law_id": "civil_code_2021", "article_no_int": 679, "engines": ["guarantee_and_cashflow"]},
    {"law_id": "civil_code_2021", "article_no_int": 686, "engines": ["guarantee_and_cashflow", "statute_db"]},
    {"law_id": "civil_code_2021", "article_no_int": 687, "engines": ["guarantee_and_cashflow"]},
    {"law_id": "civil_code_2021", "article_no_int": 688, "engines": ["guarantee_and_cashflow", "statute_db"]},
    {"law_id": "civil_code_2021", "article_no_int": 689, "engines": ["guarantee_and_cashflow"]},
    {"law_id": "civil_code_2021", "article_no_int": 690, "engines": ["guarantee_and_cashflow"]},
    {"law_id": "civil_code_2021", "article_no_int": 691, "engines": ["guarantee_and_cashflow"]},
    {"law_id": "civil_code_2021", "article_no_int": 692, "engines": ["guarantee_and_cashflow", "cn_legal_calc"]},
    {"law_id": "civil_code_2021", "article_no_int": 693, "engines": ["guarantee_and_cashflow", "cn_legal_calc"]},
    {"law_id": "civil_code_2021", "article_no_int": 694, "engines": ["guarantee_and_cashflow"]},
    {"law_id": "company_law_2024", "article_no_int": 15, "engines": ["guarantee_and_cashflow"]},
    # 上诉 / 情势变更 / 违约金
    {"law_id": "civil_code_2021", "article_no_int": 533, "engines": ["appeal_and_precedent"]},
    {"law_id": "civil_code_2021", "article_no_int": 585, "engines": ["appeal_and_precedent", "cn_legal_calc"]},
    {"law_id": "contract_interp_2023", "article_no_int": 64, "engines": ["appeal_and_precedent"]},
    {"law_id": "contract_interp_2023", "article_no_int": 65, "engines": ["appeal_and_precedent"]},
    # 执行穿透
    {"law_id": "civil_code_2021", "article_no_int": 745, "engines": ["enforcement_and_asset"]},
    {"law_id": "company_law_2024", "article_no_int": 11, "engines": ["enforcement_and_asset"]},
    {"law_id": "company_law_2024", "article_no_int": 23, "engines": ["enforcement_and_asset"]},
    {"law_id": "company_law_2024", "article_no_int": 47, "engines": ["enforcement_and_asset"]},
    {"law_id": "company_law_2024", "article_no_int": 54, "engines": ["enforcement_and_asset"]},
    {"law_id": "company_law_2024", "article_no_int": 88, "engines": ["enforcement_and_asset"]},
    {"law_id": "additional_parties_2020", "article_no_int": 17, "engines": ["enforcement_and_asset"]},
    {"law_id": "additional_parties_2020", "article_no_int": 18, "engines": ["enforcement_and_asset"]},
    {"law_id": "additional_parties_2020", "article_no_int": 19, "engines": ["enforcement_and_asset"]},
    {"law_id": "additional_parties_2020", "article_no_int": 20, "engines": ["enforcement_and_asset"]},
    # 类案检索规范
    {"law_id": "case_retrieval_2020", "article_no_int": 4, "engines": ["appeal_and_precedent"]},
]


def engine_cited_article_ids() -> List[str]:
    return [f"{x['law_id']}:art_{x['article_no_int']}" for x in ENGINE_CITED_ARTICLES]
