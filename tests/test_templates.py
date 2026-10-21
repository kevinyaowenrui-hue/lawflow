# -*- coding: utf-8 -*-
"""批次7：I-16 文书模板要素验收。"""
from __future__ import annotations

from pathlib import Path

import docx
import pytest
from docxtpl import DocxTemplate

from gateway.core.paths import get_base_dir


TEMPLATES = get_base_dir() / "templates"


def _full_text(path: Path) -> str:
    d = docx.Document(str(path))
    parts = [p.text for p in d.paragraphs]
    for table in d.tables:
        for row in table.rows:
            for cell in row.cells:
                parts.append(cell.text)
    return "\n".join(parts)


def test_complaint_templates_have_evidence_and_copies():
    for name in (
        "civil_complaint_loan_template.docx",
        "civil_complaint_sales_template.docx",
        "civil_complaint_template.docx",
    ):
        full = _full_text(TEMPLATES / name)
        assert "证据和证据来源" in full, name
        assert "副本" in full, name


def test_preservation_template_no_picc_has_types():
    full = _full_text(TEMPLATES / "property_preservation_template.docx")
    assert "中国人民财产保险股份有限公司" not in full
    assert "诉前保全" in full
    assert "诉中保全" in full


def test_service_address_agree_disagree():
    full = _full_text(TEMPLATES / "service_address_template.docx")
    assert "□同意" in full
    assert "□不同意" in full
    assert "【同意】" not in full


def test_power_of_attorney_special_auth_checkboxes():
    full = _full_text(TEMPLATES / "power_of_attorney_template.docx")
    assert "特别授权" in full
    assert "□" in full


def test_evidence_catalog_has_original_column():
    full = _full_text(TEMPLATES / "evidence_catalog_template.docx")
    assert "原件" in full


@pytest.mark.parametrize(
    "filename,context",
    [
        (
            "civil_complaint_template.docx",
            {
                "plaintiff_name": "甲",
                "plaintiff_gender": "男",
                "plaintiff_birth": "1990年1月1日",
                "plaintiff_ethnicity": "汉族",
                "plaintiff_id": "110101199003072375",
                "plaintiff_id_label": "公民身份号码",
                "plaintiff_address": "北京",
                "plaintiff_phone": "13800000000",
                "plaintiff_is_natural": True,
                "plaintiff_is_legal": False,
                "plaintiff_legal_rep": "",
                "plaintiff_rep_position": "",
                "defendant_name": "乙",
                "defendant_gender": "女",
                "defendant_birth": "1991年1月1日",
                "defendant_ethnicity": "汉族",
                "defendant_id": "110101199003072340",
                "defendant_id_label": "公民身份号码",
                "defendant_address": "北京",
                "defendant_phone": "13900000000",
                "defendant_is_natural": True,
                "defendant_is_legal": False,
                "defendant_legal_rep": "",
                "defendant_rep_position": "",
                "claims": ["判令被告还款"],
                "facts_and_reasons": "事实",
                "court_name": "北京市朝阳区人民法院",
                "filing_date": "2026年1月1日",
                "evidences": [{"name": "借条", "source": "原告", "witness_name": "", "witness_address": ""}],
                "copies": 1,
            },
        ),
        (
            "civil_complaint_loan_template.docx",
            {
                "plaintiff_name": "甲",
                "plaintiff_gender": "男",
                "plaintiff_birth": "1990年1月1日",
                "plaintiff_ethnicity": "汉族",
                "plaintiff_id": "1",
                "plaintiff_address": "北京",
                "plaintiff_phone": "1",
                "plaintiff_is_natural": True,
                "plaintiff_is_legal": False,
                "plaintiff_legal_rep": "",
                "plaintiff_rep_position": "",
                "defendant_name": "乙",
                "defendant_gender": "女",
                "defendant_birth": "1991年1月1日",
                "defendant_ethnicity": "汉族",
                "defendant_id": "2",
                "defendant_address": "北京",
                "defendant_phone": "2",
                "defendant_is_natural": True,
                "defendant_is_legal": False,
                "defendant_legal_rep": "",
                "defendant_rep_position": "",
                "claims": ["判令被告还款"],
                "facts_and_reasons": "事实",
                "interest_calc_statement": "",
                "court_name": "北京市朝阳区人民法院",
                "filing_date": "2026年1月1日",
                "evidences": [],
                "copies": 1,
                "loan_principal": "1",
                "loan_principal_capital": "壹元",
                "interest_start_date": "2023年1月1日",
                "interest_annual_rate": "12",
                "interest_base": "1",
            },
        ),
        (
            "civil_complaint_sales_template.docx",
            {
                "plaintiff_name": "甲公司",
                "plaintiff_address": "北京",
                "plaintiff_id": "91350100M000100Y43",
                "plaintiff_phone": "1",
                "plaintiff_is_natural": False,
                "plaintiff_is_legal": True,
                "plaintiff_legal_rep": "张三",
                "plaintiff_rep_position": "执行董事",
                "plaintiff_gender": "",
                "plaintiff_birth": "",
                "plaintiff_ethnicity": "",
                "defendant_name": "乙公司",
                "defendant_address": "北京",
                "defendant_id": "91350100M000100Y43",
                "defendant_phone": "2",
                "defendant_is_natural": False,
                "defendant_is_legal": True,
                "defendant_legal_rep": "李四",
                "defendant_rep_position": "经理",
                "defendant_gender": "",
                "defendant_birth": "",
                "defendant_ethnicity": "",
                "claims": ["判令被告支付货款"],
                "facts_and_reasons": "事实",
                "court_name": "北京市朝阳区人民法院",
                "filing_date": "2026年1月1日",
                "evidences": [],
                "copies": 1,
                "contract_arrears": "1",
                "contract_arrears_capital": "壹元",
                "liquidated_damages": "0",
                "overdue_rate_desc": "LPR",
            },
        ),
        (
            "labor_arbitration_template.docx",
            {
                "applicant_name": "甲",
                "applicant_gender": "女",
                "applicant_birth": "1990年3月7日",
                "applicant_address": "北京",
                "applicant_id": "1",
                "applicant_phone": "1",
                "applicant_is_natural": True,
                "applicant_is_legal": False,
                "applicant_legal_rep": "",
                "applicant_rep_position": "",
                "respondent_name": "乙公司",
                "respondent_address": "北京",
                "respondent_id": "91350100M000100Y43",
                "respondent_phone": "2",
                "respondent_legal_rep": "王",
                "respondent_is_natural": False,
                "respondent_is_legal": True,
                "respondent_rep_position": "经理",
                "respondent_gender": "",
                "respondent_birth": "",
                "arbitration_claims": ["裁决被申请人支付工资"],
                "facts_and_reasons": "事实",
                "arbitration_committee": "朝阳区劳动人事争议仲裁委员会",
                "filing_date": "2026年1月1日",
                "evidences": [],
                "arbitration_limitation_note": "仲裁时效一般为1年，具体以律师核实为准",
            },
        ),
        (
            "property_preservation_template.docx",
            {
                "applicant_name": "甲",
                "applicant_id": "1",
                "applicant_phone": "1",
                "applicant_address": "北京",
                "applicant_legal_rep": "【待填写】",
                "respondent_name": "乙",
                "respondent_id": "2",
                "respondent_address": "北京",
                "preservation_amount": "1",
                "preservation_amount_capital": "壹元",
                "cause_of_action": "借贷",
                "property_clues": "账户",
                "guarantee_method": "保函",
                "guarantee_institution": "某某保险公司",
                "case_number": "【待填写】",
                "court_name": "北京市朝阳区人民法院",
                "sign_date": "2026年1月1日",
            },
        ),
        (
            "service_address_template.docx",
            {
                "cause_of_action": "借贷",
                "recipient_name": "甲",
                "recipient_id": "1",
                "lawyer_name": "律师",
                "law_firm": "律所",
                "lawyer_phone": "1",
                "mail_address": "北京",
                "postal_code": "100000",
                "mobile_phone": "1",
                "email_address": "a@b.c",
                "electronic_methods": "短信、电子邮件",
                "sign_date": "2026年1月1日",
            },
        ),
        (
            "power_of_attorney_template.docx",
            {
                "client_name": "甲",
                "client_id": "1",
                "client_phone": "1",
                "opponent_name": "乙",
                "cause_of_action": "借贷",
                "lawyer_name": "律师",
                "law_firm": "律所",
                "lawyer_license": "1",
                "lawyer_phone": "1",
                "court_name": "北京市朝阳区人民法院",
                "authorization_scope": "□一般代理",
                "sign_date": "2026年1月1日",
            },
        ),
        (
            "evidence_catalog_template.docx",
            {
                "cause_of_action": "借贷",
                "plaintiff_name": "甲",
                "filing_date": "2026年1月1日",
                "evidence_items": [
                    {
                        "name": "借条",
                        "category": "书证",
                        "purpose": "证明借款",
                        "source": "原告",
                        "pages": "1",
                        "original_or_copy": "原件",
                    }
                ],
            },
        ),
    ],
)
def test_templates_render_with_minimal_context(filename, context, tmp_path):
    tpl = DocxTemplate(str(TEMPLATES / filename))
    out = tmp_path / filename
    tpl.render(context)
    tpl.save(str(out))
    assert out.is_file() and out.stat().st_size > 1000
