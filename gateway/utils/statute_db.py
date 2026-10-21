"""
LawFlow 智律工作台 - 权威法典与子母法关系图谱数据库引擎 (SQLite FTS5 架构)
功能：
1. 权威法典与司法解释结构化存储（母法、司法解释、行政法规、会议纪要四级分层）
2. SQLite FTS5 毫秒级全文检索引擎 + 三路混合检索（精确条号直达 + FTS5法言法语 + 案情语义关联）
3. “母法 ⇄ 司法解释”子母法关系图谱与双向连带穿透召回（Parent-Child Relational Linking）
4. 包含预置导入的《民法典》《合同编通则解释》《新公司法》《刑法(修正案十二)》《劳动合同法》《民间借贷解释》《担保制度解释》《立案追诉标准(二)》等核心法条
5. 专用原子切片批量导入流水线（支持律所随时上传并切片入库新法规）
"""

import json
import logging
import re
import sqlite3
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional

from gateway.core.db import connect
from gateway.core.paths import get_laws_db_path

logger = logging.getLogger("lawflow.statute_db")


@contextmanager
def get_db_connection() -> Iterator[sqlite3.Connection]:
    with connect(get_laws_db_path(), row_factory=sqlite3.Row) as conn:
        yield conn


def init_statute_database(force_reseed: bool = False):
    """初始化数据库表结构与预置法规数据"""
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # 1. 法律法规元数据表
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS laws (
            id TEXT PRIMARY KEY,
            full_name TEXT NOT NULL,
            short_name TEXT NOT NULL,
            hierarchy INTEGER NOT NULL, -- 1:国家基本法律, 2:司法解释, 3:行政法规/司法规定, 4:会议纪要/高院指引
            promulgated_by TEXT NOT NULL,
            promulgated_doc_no TEXT,
            effective_date TEXT NOT NULL,
            abrogated_date TEXT,
            status TEXT NOT NULL DEFAULT 'VALID', -- VALID(现行有效), ABROGATED(已废止), AMENDED(已修订)
            domain TEXT NOT NULL, -- 民商, 合同, 公司, 劳动, 刑事, 民诉程序
            article_count INTEGER DEFAULT 0,
            summary TEXT
        );
        """)

        # 2. 法条正文与要件结构化表
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS articles (
            id TEXT PRIMARY KEY, -- e.g. civil_code_2021:art_585
            law_id TEXT NOT NULL,
            part_name TEXT,
            chapter_name TEXT,
            section_name TEXT,
            article_no_cn TEXT NOT NULL, -- 第五百八十五条
            article_no_int INTEGER,       -- 585
            content TEXT NOT NULL,
            has_proviso INTEGER DEFAULT 0, -- 1 if contains "但是" / "除外" / "另有约定的"
            key_terms TEXT,               -- JSON Array
            claim_basis_type TEXT,        -- 请求权规范, 抗辩权规范, 形成权规范, 定义规范
            FOREIGN KEY (law_id) REFERENCES laws(id) ON DELETE CASCADE
        );
        """)

        # 3. FTS5 全文索引虚拟表
        cursor.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS articles_fts USING fts5(
            article_id UNINDEXED,
            law_name,
            part_chapter,
            article_no_cn,
            content,
            key_terms,
            tokenize = 'unicode61'
        );
        """)

        # 4. 子母法双向关联图谱表 (Parent-Child Linking)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS parent_child_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            parent_article_id TEXT NOT NULL, -- e.g. civil_code_2021:art_585
            child_article_id TEXT NOT NULL,  -- e.g. contract_interp_2023:art_64
            relation_type TEXT NOT NULL,     -- 细化裁量标准, 举证责任分配, 适用前提界定, 除外例外规定, 追诉门槛标准
            notes TEXT,                      -- 实务办案指引要点
            FOREIGN KEY (parent_article_id) REFERENCES articles(id) ON DELETE CASCADE,
            FOREIGN KEY (child_article_id) REFERENCES articles(id) ON DELETE CASCADE,
            UNIQUE(parent_article_id, child_article_id)
        );
        """)

        # 5. 废止旧法拦截与替换索引表
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS abrogated_laws (
            name TEXT PRIMARY KEY,
            full_name TEXT NOT NULL,
            abrogated_date TEXT NOT NULL,
            replaced_by TEXT NOT NULL,
            risk_tip TEXT NOT NULL
        );
        """)

        conn.commit()

        # 检查是否已有基础数据，若无或强制重置则灌入种子数据
        cursor.execute("SELECT COUNT(*) FROM laws;")
        law_count = cursor.fetchone()[0]
        if law_count == 0 or force_reseed:
            logger.info("法规库为空或触发重新灌装，开始注入权威中国法典与司法解释全集...")
            _seed_statutes_corpus(conn)
            conn.commit()
            logger.info("权威法典与司法解释全集注入完成！")


# ==============================================================================
# 权威预置法典与子母法图谱全量种子数据集
# ==============================================================================
SEED_LAWS = [
    {
        "id": "civil_code_2021",
        "full_name": "中华人民共和国民法典",
        "short_name": "民法典",
        "hierarchy": 1,
        "promulgated_by": "全国人民代表大会",
        "promulgated_doc_no": "第十三届全国人大三次会议通过",
        "effective_date": "2021-01-01",
        "status": "VALID",
        "domain": "民商",
        "summary": "新中国成立以来第一部以法典命名的法律，涵盖总则、物权、合同、人格权、婚姻家庭、继承、侵权责任七编，民商事请求权基础总源泉。"
    },
    {
        "id": "contract_interp_2023",
        "full_name": "最高人民法院关于适用〈中华人民共和国民法典〉合同编通则若干问题的解释",
        "short_name": "合同编通则解释",
        "hierarchy": 2,
        "promulgated_by": "最高人民法院",
        "promulgated_doc_no": "法释〔2023〕13号",
        "effective_date": "2023-12-05",
        "status": "VALID",
        "domain": "合同",
        "summary": "2023年底最新颁布的合同编综合司法解释，全面规范了合同解释、表见代理、以物抵债、违约金30%上限调减标准及举证分配。"
    },
    {
        "id": "guarantee_interp_2021",
        "full_name": "最高人民法院关于适用〈中华人民共和国民法典〉有关担保制度的解释",
        "short_name": "担保制度解释",
        "hierarchy": 2,
        "promulgated_by": "最高人民法院",
        "promulgated_doc_no": "法释〔2020〕28号",
        "effective_date": "2021-01-01",
        "status": "VALID",
        "domain": "民商",
        "summary": "全面对接民法典担保新规，落实未约定保证方式推定为一般保证、公司法定代表人越权对外担保效力等重大实务规则。"
    },
    {
        "id": "private_lending_2020",
        "full_name": "最高人民法院关于审理民间借贷案件适用法律若干问题的规定",
        "short_name": "民间借贷司法解释",
        "hierarchy": 2,
        "promulgated_by": "最高人民法院",
        "promulgated_doc_no": "法释〔2020〕17号",
        "effective_date": "2020-08-20",
        "status": "VALID",
        "domain": "民商",
        "summary": "确立民间借贷利率以合同成立时一年期 LPR 四倍为法定司法保护上限红线，规制转贷套利无效。"
    },
    {
        "id": "company_law_2024",
        "full_name": "中华人民共和国公司法",
        "short_name": "新公司法(2024)",
        "hierarchy": 1,
        "promulgated_by": "全国人民代表大会常务委员会",
        "promulgated_doc_no": "国家主席令第十五号",
        "effective_date": "2024-07-01",
        "status": "VALID",
        "domain": "公司",
        "summary": "2024年7月1日施行的全新公司法，重大确立五年认缴出资制、加速到期、一人公司混同举证责任倒置与横向穿透刺破公司面纱。"
    },
    {
        "id": "labor_contract_2013",
        "full_name": "中华人民共和国劳动合同法",
        "short_name": "劳动合同法",
        "hierarchy": 1,
        "promulgated_by": "全国人民代表大会常务委员会",
        "promulgated_doc_no": "主席令第七十三号（2012修正）",
        "effective_date": "2013-07-01",
        "status": "VALID",
        "domain": "劳动",
        "summary": "中国劳动法律基石，明确劳动合同解除、N/N+1经济补偿金精算标准、社平三倍封顶与用人单位违法解除2N赔偿金。"
    },
    {
        "id": "criminal_law_2024",
        "full_name": "中华人民共和国刑法",
        "short_name": "刑法(修正案十二)",
        "hierarchy": 1,
        "promulgated_by": "全国人民代表大会常务委员会",
        "promulgated_doc_no": "主席令第十八号（刑法修正案十二）",
        "effective_date": "2024-03-01",
        "status": "VALID",
        "domain": "刑事",
        "summary": "现行最新刑法典（含修正案十一、十二），涵盖涉企经济犯罪、骗取贷款罪、非法集资、合同诈骗罪及民企高管侵占背信等关键罪名。"
    },
    {
        "id": "prosecution_standards_2022",
        "full_name": "最高人民检察院、公安部关于公安机关管辖的刑事案件立案追诉标准的规定（二）",
        "short_name": "经济犯罪立案追诉标准(二)",
        "hierarchy": 2,
        "promulgated_by": "最高人民检察院、公安部",
        "promulgated_doc_no": "公通字〔2022〕12号",
        "effective_date": "2022-05-15",
        "status": "VALID",
        "domain": "刑事",
        "summary": "刑民交叉案件立案分水岭，明确骗取贷款罪（造成直接经济损失20万元以上）、非法吸存、合同诈骗罪立案数额标准。"
    },
    {
        "id": "civil_procedure_2023",
        "full_name": "中华人民共和国民事诉讼法",
        "short_name": "民事诉讼法(2023修正)",
        "hierarchy": 1,
        "promulgated_by": "全国人民代表大会常务委员会",
        "promulgated_doc_no": "主席令第十一号（2023年9月修正）",
        "effective_date": "2024-01-01",
        "status": "VALID",
        "domain": "民诉程序",
        "summary": "民事诉讼程序基本法，规范举证责任分配、管辖异议、诉前与诉讼财产保全、涉外民商事诉讼及强制执行查控措施。"
    },
    {
        "id": "nine_minutes_2019",
        "full_name": "全国法院民商事审判工作会议纪要",
        "short_name": "九民纪要",
        "hierarchy": 4,
        "promulgated_by": "最高人民法院",
        "promulgated_doc_no": "法发〔2019〕25号",
        "effective_date": "2019-11-14",
        "status": "VALID",
        "domain": "民商",
        "summary": "最高院民商事审判统一裁判尺度的重磅文件，明确看人不看章、越权代表效力、法人人格否认（纵向与横向穿透）及让与担保清算。"
    }
]

SEED_ARTICLES = [
    # ------------------ 民法典 (civil_code_2021) ------------------
    {
        "id": "civil_code_2021:art_188",
        "law_id": "civil_code_2021",
        "part_name": "第一编 总则",
        "chapter_name": "第九章 诉讼时效",
        "section_name": "",
        "article_no_cn": "第一百八十八条",
        "article_no_int": 188,
        "content": "向人民法院请求保护民事权利的诉讼时效期间为三年。法律另有规定的，依照其规定。\n诉讼时效期间自权利人知道或者应当知道权利受到损害以及义务人之日起计算。法律另有规定的，依照其规定。但是，自权利受到损害之日起超过二十年的，人民法院不予保护，有特殊情况的，人民法院可以根据权利人的申请决定延长。",
        "has_proviso": 1,
        "key_terms": ["诉讼时效", "三年时效", "知道或应当知道", "二十年最长时效", "除外规定"],
        "claim_basis_type": "抗辩权抗辩规范"
    },
    {
        "id": "civil_code_2021:art_195",
        "law_id": "civil_code_2021",
        "part_name": "第一编 总则",
        "chapter_name": "第九章 诉讼时效",
        "section_name": "",
        "article_no_cn": "第一百九十五条",
        "article_no_int": 195,
        "content": "有下列情形之一的，诉讼时效中断，从中断、有关程序终结时起，诉讼时效期间重新计算：\n（一）权利人向义务人提出履行请求；\n（二）义务人同意履行义务；\n（三）权利人提起诉讼或者申请仲裁；\n（四）与提起诉讼或者申请仲裁具有同等法律效力的其他情形。",
        "has_proviso": 0,
        "key_terms": ["诉讼时效中断", "重新计算", "提出履行请求", "同意履行", "提起诉讼"],
        "claim_basis_type": "抗辩对抗规范"
    },
    {
        "id": "civil_code_2021:art_509",
        "law_id": "civil_code_2021",
        "part_name": "第三编 合同",
        "chapter_name": "第四章 合同的履行",
        "section_name": "",
        "article_no_cn": "第五百零九条",
        "article_no_int": 509,
        "content": "当事人应当按照约定全面履行自己的义务。\n当事人应当遵循诚信原则，根据合同的性质、目的和交易习惯履行通知、协助、保密等义务。\n当事人在履行合同过程中，应当避免浪费资源、污染环境和破坏生态。",
        "has_proviso": 0,
        "key_terms": ["全面履行", "附随义务", "诚信原则", "合同目的"],
        "claim_basis_type": "义务规范"
    },
    {
        "id": "civil_code_2021:art_538",
        "law_id": "civil_code_2021",
        "part_name": "第三编 合同",
        "chapter_name": "第五章 合同的保全",
        "section_name": "",
        "article_no_cn": "第五百三十八条",
        "article_no_int": 538,
        "content": "债务人以放弃其债权、放弃债权担保、无偿转让财产等方式无偿处分财产权益，或者恶意延长其到期债权的履行期限，影响债权人的债权实现的，债权人可以请求人民法院撤销债务人的行为。",
        "has_proviso": 0,
        "key_terms": ["债权人撤销权", "无偿转让财产", "放弃债权", "恶意延长到期期限", "撤销之诉"],
        "claim_basis_type": "形成权请求权规范"
    },
    {
        "id": "civil_code_2021:art_563",
        "law_id": "civil_code_2021",
        "part_name": "第三编 合同",
        "chapter_name": "第七章 合同的权利义务终止",
        "section_name": "",
        "article_no_cn": "第五百六十三条",
        "article_no_int": 563,
        "content": "有下列情形之一的，当事人可以解除合同：\n（一）因不可抗力致使不能实现合同目的；\n（二）在履行期限届满前，当事人一方明确表示或者以自己的行为表明不履行主要债务；\n（三）当事人一方迟延履行主要债务，经催告后在合理期限内仍未履行；\n（四）当事人一方迟延履行债务或者有其他违约行为致使不能实现合同目的；\n（五）法律规定的其他情形。\n以持续履行的债务为内容的不定期合同，当事人可以随时解除合同，但是应当在合理期限之前通知对方。",
        "has_proviso": 1,
        "key_terms": ["法定解除权", "根本违约", "迟延履行催告", "合同目的不能实现", "预期违约"],
        "claim_basis_type": "形成权规范"
    },
    {
        "id": "civil_code_2021:art_577",
        "law_id": "civil_code_2021",
        "part_name": "第三编 合同",
        "chapter_name": "第八章 违约责任",
        "section_name": "",
        "article_no_cn": "第五百七十七条",
        "article_no_int": 577,
        "content": "当事人一方不履行合同义务或者履行合同义务不符合约定的，应当承担继续履行、采取补救措施或者赔偿损失等违约责任。",
        "has_proviso": 0,
        "key_terms": ["违约责任", "继续履行", "补救措施", "赔偿损失"],
        "claim_basis_type": "请求权基础核心规范"
    },
    {
        "id": "civil_code_2021:art_579",
        "law_id": "civil_code_2021",
        "part_name": "第三编 合同",
        "chapter_name": "第八章 违约责任",
        "section_name": "",
        "article_no_cn": "第五百七十九条",
        "article_no_int": 579,
        "content": "当事人一方未支付价款、报酬、租金、利息，或者不履行其他金钱债务的，对方可以请求其支付。",
        "has_proviso": 0,
        "key_terms": ["支付价款", "报酬", "租金", "利息", "金钱债务强制履行"],
        "claim_basis_type": "给付请求权基础规范"
    },
    {
        "id": "civil_code_2021:art_585",
        "law_id": "civil_code_2021",
        "part_name": "第三编 合同",
        "chapter_name": "第八章 违约责任",
        "section_name": "",
        "article_no_cn": "第五百八十五条",
        "article_no_int": 585,
        "content": "当事人可以约定一方违约时应当根据违约情况向对方支付一定数额的违约金，也可以约定因违约产生的损失赔偿额的计算方法。\n约定的违约金低于造成的损失的，人民法院或者仲裁机构可以根据当事人的请求予以增加；约定的违约金过分高于造成的损失的，人民法院或者仲裁机构可以根据当事人的请求予以适当减少。\n当事人就迟延履行约定违约金的，违约方支付违约金后，还应当履行债务。",
        "has_proviso": 1,
        "key_terms": ["约定违约金", "过分高于造成的损失", "司法调减", "迟延履行违约金", "损失赔偿计算方法"],
        "claim_basis_type": "请求权与抗辩兼具规范"
    },
    {
        "id": "civil_code_2021:art_667",
        "law_id": "civil_code_2021",
        "part_name": "第三编 合同",
        "chapter_name": "第十二章 借款合同",
        "section_name": "",
        "article_no_cn": "第六百六十七条",
        "article_no_int": 667,
        "content": "借款合同是借款人向贷款人借款，到期返还借款并支付利息的合同。",
        "has_proviso": 0,
        "key_terms": ["借款合同", "返还借款", "支付利息", "民间借贷"],
        "claim_basis_type": "定义规范"
    },
    {
        "id": "civil_code_2021:art_675",
        "law_id": "civil_code_2021",
        "part_name": "第三编 合同",
        "chapter_name": "第十二章 借款合同",
        "section_name": "",
        "article_no_cn": "第六百七十五条",
        "article_no_int": 675,
        "content": "借款人应当按照约定的期限返还借款。对借款期限没有约定或者约定不明确，依据本法第五百一十条的规定仍不能确定的，借款人可以随时返还；贷款人可以催告借款人在合理期限内返还。",
        "has_proviso": 1,
        "key_terms": ["返还借款", "借款期限", "合理期限催告", "不定期借款"],
        "claim_basis_type": "给付请求权规范"
    },
    {
        "id": "civil_code_2021:art_676",
        "law_id": "civil_code_2021",
        "part_name": "第三编 合同",
        "chapter_name": "第十二章 借款合同",
        "section_name": "",
        "article_no_cn": "第六百七十六条",
        "article_no_int": 676,
        "content": "借款人未按照约定的期限返还借款的，应当按照约定或者国家有关规定支付逾期利息。",
        "has_proviso": 0,
        "key_terms": ["逾期利息", "逾期还款责任", "借款利息"],
        "claim_basis_type": "请求权基础规范"
    },
    {
        "id": "civil_code_2021:art_686",
        "law_id": "civil_code_2021",
        "part_name": "第三编 合同",
        "chapter_name": "第十三章 保证合同",
        "section_name": "",
        "article_no_cn": "第六百八十六条",
        "article_no_int": 686,
        "content": "保证的方式包括一般保证和连带责任保证。\n当事人在保证合同中对保证方式没有约定或者约定不明确的，按照一般保证承担保证责任。",
        "has_proviso": 0,
        "key_terms": ["保证方式", "一般保证推定", "连带责任保证", "先诉抗辩权"],
        "claim_basis_type": "法定推定与责任规范"
    },
    {
        "id": "civil_code_2021:art_688",
        "law_id": "civil_code_2021",
        "part_name": "第三编 合同",
        "chapter_name": "第十三章 保证合同",
        "section_name": "",
        "article_no_cn": "第六百八十八条",
        "article_no_int": 688,
        "content": "当事人在保证合同中约定保证人和债务人对债务承担连带责任的，为连带责任保证。\n连带责任保证的债务人不履行到期债务或者发生当事人约定的情形时，债权人可以请求债务人履行债务，也可以请求保证人在其保证范围内承担保证责任。",
        "has_proviso": 0,
        "key_terms": ["连带责任保证", "共同清偿", "保证范围", "履行债务"],
        "claim_basis_type": "请求权基础规范"
    },
    {
        "id": "civil_code_2021:art_985",
        "law_id": "civil_code_2021",
        "part_name": "第三编 合同",
        "chapter_name": "第二十九章 不当得利",
        "section_name": "",
        "article_no_cn": "第九百八十五条",
        "article_no_int": 985,
        "content": "得利人没有法律根据取得不当利益的，受损失的人可以请求得利人返还取得的利益，但是有下列情形之一的除外：\n（一）为履行道德义务进行的给付；\n（二）债务到期之前的清偿；\n（三）明知无给付义务而进行的债务清偿。",
        "has_proviso": 1,
        "key_terms": ["不当得利", "返还请求权", "没有法律根据", "除外情形", "明知无义务清偿"],
        "claim_basis_type": "返还请求权规范"
    },

    # ------------------ 最高法民法典合同编通则解释 (contract_interp_2023) ------------------
    {
        "id": "contract_interp_2023:art_64",
        "law_id": "contract_interp_2023",
        "part_name": "第七部分 违约责任",
        "chapter_name": "",
        "section_name": "",
        "article_no_cn": "第六十四条",
        "article_no_int": 64,
        "content": "当事人依据民法典第五百八十五条第二款的规定，请求人民法院增加或者适当减少违约金的，应当在第一审法庭辩论终结前提出。\n被告在第一审庭审中抗辩主张违约金过高请求调整，但在举证期限届满前未提交违约金过高的证据的，人民法院应当向其释明举证责任；经释明后仍未提供初步证据的，人民法院可以不予调整。",
        "has_proviso": 1,
        "key_terms": ["违约金调减期限", "一审法庭辩论终结前", "法官释明", "举证责任分配", "初步证据"],
        "claim_basis_type": "程序衔接与举证分配规范"
    },
    {
        "id": "contract_interp_2023:art_65",
        "law_id": "contract_interp_2023",
        "part_name": "第七部分 违约责任",
        "chapter_name": "",
        "section_name": "",
        "article_no_cn": "第六十五条",
        "article_no_int": 65,
        "content": "当事人主张约定的违约金过分高于造成的损失请求予以适当减少的，应当承担举证责任；相对人主张违约金合理的，也应当提供相应证据。\n约定的违约金超过造成损失的百分之三十的，人民法院一般可以认定为民法典第五百八十五条第二款规定的“过分高于造成的损失”。\n人民法院认定违约金是否过高，应当以违约造成的实际损失为基准，兼顾合同的履行情况、当事人的过错程度以及预期利益等综合因素确定。",
        "has_proviso": 0,
        "key_terms": ["违约金30%上限", "过分高于造成的损失", "实际损失基准", "举证责任", "预期利益综合衡量"],
        "claim_basis_type": "细化裁量标准规范"
    },
    {
        "id": "contract_interp_2023:art_66",
        "law_id": "contract_interp_2023",
        "part_name": "第七部分 违约责任",
        "chapter_name": "",
        "section_name": "",
        "article_no_cn": "第六十六条",
        "article_no_int": 66,
        "content": "当事人既约定违约金，又约定定金，一方违约时，对方可以选择适用违约金或者定金条款。\n定金不足以弥补一方违约造成的损失的，对方可以请求赔偿超过定金数额的损失，但定金与损失赔偿额的总和不应超过因违约所造成的实际损失。",
        "has_proviso": 1,
        "key_terms": ["违约金与定金并存", "择一适用", "定金补足损失", "总额不超过实际损失"],
        "claim_basis_type": "请求权竞合处理规范"
    },

    # ------------------ 最高法民间借贷司法解释 (private_lending_2020) ------------------
    {
        "id": "private_lending_2020:art_13",
        "law_id": "private_lending_2020",
        "part_name": "",
        "chapter_name": "",
        "section_name": "",
        "article_no_cn": "第十三条",
        "article_no_int": 13,
        "content": "具有下列情形之一的，人民法院应当认定民间借贷合同无效：\n（一）套取金融机构贷款转贷的；\n（二）以向其他营利法人借贷、向本单位职工集资，或者以向公众非法吸收存款等方式取得的资金转贷的；\n（三）未依法取得放贷资格的出借人，以营利为目的向社会不特定对象提供借款的；\n（四）出借人事先知道或者应当知道借款人借款用于违法犯罪活动仍然提供借款的；\n（五）违反法律、行政法规强制性规定的；\n（六）违背公序良俗的。",
        "has_proviso": 0,
        "key_terms": ["民间借贷合同无效", "套取金融机构贷款转贷", "职业放贷人", "非法吸存转贷", "公序良俗"],
        "claim_basis_type": "合同效力阻断规范"
    },
    {
        "id": "private_lending_2020:art_25",
        "law_id": "private_lending_2020",
        "part_name": "",
        "chapter_name": "",
        "section_name": "",
        "article_no_cn": "第二十五条",
        "article_no_int": 25,
        "content": "出借人请求借款人按照合同约定利率支付利息的，人民法院应予支持，但是以不超过合同成立时一年期贷款市场报价利率四倍为限。\n前款所称“一年期贷款市场报价利率”，是指中国人民银行授权全国银行间同业拆借中心自2019年8月20日起每月20日发布的一年期贷款市场报价利率（LPR）。",
        "has_proviso": 1,
        "key_terms": ["一年期LPR四倍", "约定利率上限", "民间借贷利率红线", "超额利息不予支持"],
        "claim_basis_type": "裁量上限与部分无效规范"
    },
    {
        "id": "private_lending_2020:art_28",
        "law_id": "private_lending_2020",
        "part_name": "",
        "chapter_name": "",
        "section_name": "",
        "article_no_cn": "第二十八条",
        "article_no_int": 28,
        "content": "借贷双方对逾期利率有约定的，从其约定，但是以不超过合同成立时一年期贷款市场报价利率四倍为限。\n未约定逾期利率或者约定不明的，人民法院可以区分不同情况处理：\n（一）既未约定借期内利率，也未约定逾期利率，出借人主张借款人自逾期还款之日起承担逾期还款违约责任的，人民法院应予支持；\n（二）约定了借期内利率但未约定逾期利率，出借人主张借款人自逾期还款之日起按照借期内利率支付资金占用期间利息的，人民法院应予支持。\n出借人与借款人既约定了逾期利率，又约定了违约金或者其他费用，出借人可以选择主张逾期利息、违约金或者其他费用，也可以一并主张，但是总计超过合同成立时一年期贷款市场报价利率四倍的部分，人民法院不予支持。",
        "has_proviso": 1,
        "key_terms": ["逾期利息与违约金并存", "利息违约金总计上限", "一年期LPR四倍穿透", "综合资金成本"],
        "claim_basis_type": "综合费用封顶规范"
    },

    # ------------------ 最高法担保制度解释 (guarantee_interp_2021) ------------------
    {
        "id": "guarantee_interp_2021:art_25",
        "law_id": "guarantee_interp_2021",
        "part_name": "第二部分 保证合同",
        "chapter_name": "",
        "section_name": "",
        "article_no_cn": "第二十五条",
        "article_no_int": 25,
        "content": "当事人在保证合同中约定了保证人在债务人不能履行债务或者无力偿还债务时，才承担保证责任的，为一般保证。\n债权人仅起诉一般保证人的，人民法院应当向债权人释明申请追加债务人为共同被告；债权人拒绝追加的，人民法院应当裁定驳回起诉。\n债权人同时起诉债务人和一般保证人的，人民法院可以在判决书主文中明确：保证人仅在对债务人财产依法强制执行后仍不能履行债务时，才承担保证责任。",
        "has_proviso": 1,
        "key_terms": ["一般保证", "先诉抗辩权程序实现", "追加共同被告", "裁判主文先执行债务人"],
        "claim_basis_type": "程序衔接规范"
    },
    {
        "id": "guarantee_interp_2021:art_32",
        "law_id": "guarantee_interp_2021",
        "part_name": "第二部分 保证合同",
        "chapter_name": "",
        "section_name": "",
        "article_no_cn": "第三十二条",
        "article_no_int": 32,
        "content": "保证合同约定保证人承担保证责任直至主债务本息还清时为止等类似内容的，视为约定不明，保证期间为主债务履行期限届满之日起六个月。\n一般保证的债权人在保证期间届满前对债务人提起诉讼或者申请仲裁的，从判决或者仲裁裁决生效之日起，开始计算保证债务的诉讼时效。\n连带责任保证的债权人在保证期间届满前请求保证人承担保证责任的，从债权人请求保证人承担保证责任之日起，开始计算保证债务的诉讼时效。",
        "has_proviso": 0,
        "key_terms": ["保证期间约定不明", "六个月法定保证期间", "保证期间除斥期间", "保证债务诉讼时效起算"],
        "claim_basis_type": "除斥期间与时效转换规范"
    },

    # ------------------ 中华人民共和国公司法 (2024最新施行版) ------------------
    {
        "id": "company_law_2024:art_10",
        "law_id": "company_law_2024",
        "part_name": "第一章 总则",
        "chapter_name": "",
        "section_name": "",
        "article_no_cn": "第十条",
        "article_no_int": 10,
        "content": "公司的法定代表人按照公司章程的规定，由代表公司执行公司事务的董事或者经理担任。\n担任法定代表人的董事或者经理辞任的，视为同时辞去法定代表人。\n法定代表人以公司名义从事的民事活动，其法律后果由公司承受。公司章程或者股东会对法定代表人职权的限制，不得对抗善意相对人。\n法定代表人因执行职务造成他人损害的，由公司承担民事责任；公司承担民事责任后，依照法律或者公司章程的规定，可以向有过错的法定代表人追偿。",
        "has_proviso": 1,
        "key_terms": ["法定代表人职务行为", "公司责任承受", "越权代表不得对抗善意相对人", "过错追偿"],
        "claim_basis_type": "代表权效力规范"
    },
    {
        "id": "company_law_2024:art_23",
        "law_id": "company_law_2024",
        "part_name": "第一章 总则",
        "chapter_name": "",
        "section_name": "",
        "article_no_cn": "第二十三条",
        "article_no_int": 23,
        "content": "公司股东滥用公司法人独立地位和股东有限责任，逃避债务，严重损害公司债权人利益的，应当对公司债务承担连带责任。\n股东利用其控制的两个以上公司实施前款规定行为的，各公司应当对任一公司的债务承担连带责任。\n只有一个股东的公司，股东不能证明公司财产独立于股东自己的财产的，应当对公司债务承担连带责任。",
        "has_proviso": 0,
        "key_terms": ["刺破公司面纱", "纵向人格否认", "横向人格否认", "一人有限责任公司混同举证责任倒置", "股东连带清偿"],
        "claim_basis_type": "法人人格穿透追索规范"
    },
    {
        "id": "company_law_2024:art_47",
        "law_id": "company_law_2024",
        "part_name": "第二章 有限责任公司的设立和组织机构",
        "chapter_name": "",
        "section_name": "",
        "article_no_cn": "第四十七条",
        "article_no_int": 47,
        "content": "有限责任公司的注册资本为在公司登记机关登记的全体股东认缴的出资额。全体股东认缴的出资额由股东按照公司章程的规定自公司成立之日起五年内缴足。\n法律、行政法规以及国务院决定对有限责任公司注册资本实缴、出资期限另有规定的，从其规定。",
        "has_proviso": 1,
        "key_terms": ["五年实缴认缴制", "出资期限五年限制", "注册资本实缴", "出资实缴红线"],
        "claim_basis_type": "股东法定义务规范"
    },
    {
        "id": "company_law_2024:art_54",
        "law_id": "company_law_2024",
        "part_name": "第二章 有限责任公司的设立和组织机构",
        "chapter_name": "",
        "section_name": "",
        "article_no_cn": "第五十四条",
        "article_no_int": 54,
        "content": "公司不能清偿到期债务的，公司或者已到期债权的债权人有权要求已认缴出资但未届出资期限的股东提前缴纳出资。",
        "has_proviso": 0,
        "key_terms": ["出资加速到期", "不能清偿到期债务", "债权人代位追索出资", "执行异议追索"],
        "claim_basis_type": "追索股东出资请求权规范"
    },

    # ------------------ 中华人民共和国劳动合同法 ------------------
    {
        "id": "labor_contract_2013:art_10",
        "law_id": "labor_contract_2013",
        "part_name": "第二章 劳动合同的订立",
        "chapter_name": "",
        "section_name": "",
        "article_no_cn": "第十条",
        "article_no_int": 10,
        "content": "建立劳动关系，应当订立书面劳动合同。\n已建立劳动关系，未同时订立书面劳动合同的，应当自用工之日起一个月内订立书面劳动合同。\n用人单位与劳动者在用工前订立劳动合同的，劳动关系自用工之日起建立。",
        "has_proviso": 0,
        "key_terms": ["书面劳动合同", "建立劳动关系", "一个月宽限期", "用工之日"],
        "claim_basis_type": "法定义务规范"
    },
    {
        "id": "labor_contract_2013:art_47",
        "law_id": "labor_contract_2013",
        "part_name": "第四章 劳动合同的解除和终止",
        "chapter_name": "",
        "section_name": "",
        "article_no_cn": "第四十七条",
        "article_no_int": 47,
        "content": "经济补偿按劳动者在本单位工作的年限，每满一年支付一个月工资的标准向劳动者支付。六个月以上不满一年的，按一年计算；不满六个月的，向劳动者支付半个月工资的经济补偿。\n劳动者月工资高于用人单位所在直辖市、设区的市级人民政府公布的本地区上年度职工月平均工资三倍的，向其支付经济补偿的标准按职工月平均工资三倍的数额支付，向其支付经济补偿的年限最高不超过十二年。\n本条所称月工资是指劳动者在劳动合同解除或者终止前十二个月的平均工资。",
        "has_proviso": 1,
        "key_terms": ["经济补偿金", "工作年限N", "社平工资三倍封顶", "最高十二年封顶", "离职前12个月平均工资"],
        "claim_basis_type": "法定补偿金给付规范"
    },
    {
        "id": "labor_contract_2013:art_87",
        "law_id": "labor_contract_2013",
        "part_name": "第七章 法律责任",
        "chapter_name": "",
        "section_name": "",
        "article_no_cn": "第八十七条",
        "article_no_int": 87,
        "content": "用人单位违反本法规定解除或者终止劳动合同的，应当依照本法第四十七条规定的经济补偿标准的二倍向劳动者支付赔偿金。",
        "has_proviso": 0,
        "key_terms": ["违法解除赔偿金", "2N赔偿金", "双倍补偿", "非法开除"],
        "claim_basis_type": "法定惩罚性赔偿给付规范"
    },

    # ------------------ 中华人民共和国刑法 (经济与商事核心罪名) ------------------
    {
        "id": "criminal_law_2024:art_175_1",
        "law_id": "criminal_law_2024",
        "part_name": "分则 第三章 破坏社会主义市场经济秩序罪",
        "chapter_name": "第四节 破坏金融管理秩序罪",
        "section_name": "",
        "article_no_cn": "第一百七十五条之一",
        "article_no_int": 175,
        "content": "以欺骗手段取得银行或者其他金融机构贷款、票据承兑、信用证、保函等，给银行或者其他金融机构造成重大损失的，处三年以下有期徒刑或者拘役，并处或者单处罚金；给银行或者其他金融机构造成特别重大损失或者有其他特别严重情节的，处三年以上七年以下有期徒刑，并处罚金。\n单位犯前款罪的，对单位判处罚金，并对其直接负责的主管人员和其他直接责任人员，依照前款的规定处罚。",
        "has_proviso": 0,
        "key_terms": ["骗取贷款罪", "欺骗手段", "重大损失立案标准", "刑民交叉", "单位犯罪"],
        "claim_basis_type": "刑事罪名要件规范"
    },
    {
        "id": "criminal_law_2024:art_176",
        "law_id": "criminal_law_2024",
        "part_name": "分则 第三章 破坏社会主义市场经济秩序罪",
        "chapter_name": "第四节 破坏金融管理秩序罪",
        "section_name": "",
        "article_no_cn": "第一百七十六条",
        "article_no_int": 176,
        "content": "非法吸收公众存款或者变相吸收公众存款，扰乱金融秩序的，处三年以下有期徒刑或者拘役，并处或者单处罚金；数额巨大或者有其他严重情节的，处三年以上十年以下有期徒刑，并处罚金；数额特别巨大或者有其他特别严重情节的，处十年以上有期徒刑，并处罚金。\n单位犯前款罪的，对单位判处罚金，并对其直接负责的主管人员和其他直接责任人员，依照第一款的规定处罚。\n有前两款行为，在提起公诉前积极退赃退赔，减少财产损失或者挽回损害后果的，可以从轻或者减轻处罚。",
        "has_proviso": 0,
        "key_terms": ["非法吸收公众存款罪", "非吸", "向公众集资", "利息承诺", "退赃退赔从轻"],
        "claim_basis_type": "刑事罪名要件规范"
    },
    {
        "id": "criminal_law_2024:art_224",
        "law_id": "criminal_law_2024",
        "part_name": "分则 第三章 破坏社会主义市场经济秩序罪",
        "chapter_name": "第八节 扰乱市场秩序罪",
        "section_name": "",
        "article_no_cn": "第二百二十四条",
        "article_no_int": 224,
        "content": "有下列情形之一，以非法占有为目的，在签订、履行合同过程中，骗取对方当事人财物，数额较大的，处三年以下有期徒刑或者拘役，并处或者单处罚金；数额巨大或者有其他严重情节的，处三年以上十年以下有期徒刑，并处罚金；数额特别巨大或者有其他特别严重情节的，处十年以上有期徒刑或者无期徒刑，并处罚金或者没收财产：\n（一）以虚构的单位或者冒用他人名义签订合同的；\n（二）以伪造、变造、作废的票据或者其他虚假的产权证明作担保的；\n（三）没有实际履行能力，以先履行小额合同或者部分履行合同的方法，诱骗对方当事人继续签订和履行合同的；\n（四）收受对方当事人给付的货物、货款、预付款或者担保财产后逃匿的；\n（五）以其他方法骗取对方当事人财物的。",
        "has_proviso": 0,
        "key_terms": ["合同诈骗罪", "非法占有目的", "假冒他人名义", "卷款逃匿", "合同诈骗与民事违约界限"],
        "claim_basis_type": "刑事罪名要件规范"
    },
    {
        "id": "criminal_law_2024:art_313",
        "law_id": "criminal_law_2024",
        "part_name": "分则 第九章 渎职罪与妨害司法罪",
        "chapter_name": "第二节 妨害司法罪",
        "section_name": "",
        "article_no_cn": "第三百一十三条",
        "article_no_int": 313,
        "content": "对人民法院的判决、裁定有能力执行而拒不执行，情节严重的，处三年以下有期徒刑、拘役或者罚金；情节特别严重的，处三年以上七年以下有期徒刑，并处罚金。\n单位犯前款罪的，对单位判处罚金，并对其直接负责的主管人员和其他直接责任人员，依照前款的规定处罚。",
        "has_proviso": 0,
        "key_terms": ["拒不执行判决裁定罪", "拒执罪", "有能力执行而拒不执行", "转移隐藏财产", "执行攻坚刑事追责"],
        "claim_basis_type": "刑事执行保障规范"
    },

    # ------------------ 经侦立案追诉标准(二) ------------------
    {
        "id": "prosecution_standards_2022:art_19",
        "law_id": "prosecution_standards_2022",
        "part_name": "",
        "chapter_name": "",
        "section_name": "",
        "article_no_cn": "第十九条",
        "article_no_int": 19,
        "content": "〔骗取贷款、票据承兑、金融票证案（刑法第一百七十五条之一）〕以欺骗手段取得银行或者其他金融机构贷款、票据承兑、信用证、保函等，给银行或者其他金融机构造成直接经济损失数额在五十万元以上的，或者具有其他严重情节的，应予立案追诉。",
        "has_proviso": 0,
        "key_terms": ["骗取贷款立案门槛", "五十万元直接经济损失", "立案追诉标准", "经侦立案门槛"],
        "claim_basis_type": "立案追诉标准规范"
    },
    {
        "id": "prosecution_standards_2022:art_69",
        "law_id": "prosecution_standards_2022",
        "part_name": "",
        "chapter_name": "",
        "section_name": "",
        "article_no_cn": "第六十九条",
        "article_no_int": 69,
        "content": "〔合同诈骗案（刑法第二百二十四条）〕以非法占有为目的，在签订、履行合同过程中，骗取对方当事人财物，数额在二万元以上的，应予立案追诉。",
        "has_proviso": 0,
        "key_terms": ["合同诈骗立案标准", "二万元以上立案", "立案追诉门槛", "非法占有为目的"],
        "claim_basis_type": "立案追诉标准规范"
    },

    # ------------------ 民事诉讼法 (2023修正) ------------------
    {
        "id": "civil_procedure_2023:art_67",
        "law_id": "civil_procedure_2023",
        "part_name": "第一编 总则",
        "chapter_name": "第六章 证据",
        "section_name": "",
        "article_no_cn": "第六十七条",
        "article_no_int": 67,
        "content": "当事人对自己提出的主张，有责任提供证据。\n当事人及其诉讼代理人因客观原因不能自行收集的证据，或者人民法院认为审理案件需要的证据，人民法院应当调查收集。\n人民法院应当按照法定程序，全面地、客观地审查核实证据。",
        "has_proviso": 0,
        "key_terms": ["谁主张谁举证", "举证证明责任", "法院调查收集证据", "律师调查令申请"],
        "claim_basis_type": "证据与举证责任分配规范"
    },
    {
        "id": "civil_procedure_2023:art_103",
        "law_id": "civil_procedure_2023",
        "part_name": "第一编 总则",
        "chapter_name": "第九章 保全和先予执行",
        "section_name": "",
        "article_no_cn": "第一百零三条",
        "article_no_int": 103,
        "content": "人民法院对于可能因当事人一方的行为或者其他原因，使判决难以执行或者造成当事人其他损害的案件，根据对方当事人的申请，可以裁定对其财产进行保全、责令其作出一定行为或者禁止其作出一定行为；当事人没有提出申请的，人民法院在必要时也可以裁定采取保全措施。\n人民法院采取保全措施，可以责令申请人提供担保，申请人不提供担保的，裁定驳回申请。\n人民法院接受申请后，对情况紧急的，必须在四十八小时内作出裁定；裁定采取保全措施的，应当立即开始执行。",
        "has_proviso": 1,
        "key_terms": ["财产保全", "行为保全", "提供担保", "四十八小时紧急裁定", "诉讼保全"],
        "claim_basis_type": "诉讼保全救济规范"
    },

    # ------------------ 九民纪要 (nine_minutes_2019) ------------------
    {
        "id": "nine_minutes_2019:art_46",
        "law_id": "nine_minutes_2019",
        "part_name": "二、关于合同纠纷案件的审理",
        "chapter_name": "",
        "section_name": "",
        "article_no_cn": "第四十六条",
        "article_no_int": 46,
        "content": "【违约金调整的释明】当事人主张约定的违约金过高请求予以适当减少的，应当在第一审法庭辩论终结前提出。\n债务人未主张调整，但依据合同约定违约金计算出的数额过分高于债权人因违约造成的损失的，人民法院应当向当事人释明是否提出调整违约金的请求。\n经释明，债务人请求调整的，由债务人对违约金过高承担举证责任，人民法院应当根据合同履行情况、当事人过错程度等综合认定。",
        "has_proviso": 0,
        "key_terms": ["违约金调整法官释明", "举证责任由债务人承担", "综合考量过错", "九民纪要裁判尺度"],
        "claim_basis_type": "审判指导规范"
    },
    {
        "id": "nine_minutes_2019:art_53",
        "law_id": "nine_minutes_2019",
        "part_name": "二、关于合同纠纷案件的审理",
        "chapter_name": "",
        "section_name": "",
        "article_no_cn": "第五十三条",
        "article_no_int": 53,
        "content": "【看人不看章】法定代表人或者其授权的代理人以法人名义从事民事活动，法律后果由法人承受。\n当事人主张合同对法人不发生效力的，人民法院应当审查盖章之人是否享有代表权或者代理权。如果盖章之人有代表权或者代理权，即便使用的是伪造或者私刻的印章，或者虽为真实印章但未经内部审批，该民事法律行为依然对法人发生法律效力。\n反之，盖章之人既无代表权也无代理权，即便使用的是真实印章，也不能当然对法人发生法律效力，除构成表见代理外，合同对法人不发生效力。",
        "has_proviso": 1,
        "key_terms": ["看人不看章", "盖章人代表权审查", "私刻假章效力", "表见代理外观", "越权盖章"],
        "claim_basis_type": "裁判规则与代表权认定"
    }
]

# 子母法双向关联图谱关系表 (Parent ⇄ Child Linking)
SEED_PARENT_CHILD_LINKS = [
    {
        "parent_article_id": "civil_code_2021:art_585",
        "child_article_id": "contract_interp_2023:art_64",
        "relation_type": "程序衔接与举证分配",
        "notes": "《民法典》第585条只规定可调减，本条进一步锁死程序截止线：必须在一审辩论终结前提出，未在举证期提交证据的由法官释明并承担不举证后果。"
    },
    {
        "parent_article_id": "civil_code_2021:art_585",
        "child_article_id": "contract_interp_2023:art_65",
        "relation_type": "细化裁量标准",
        "notes": "【核心裁判硬指标】确立违约金调减的“30% 损失上限红线”：超过造成损失30%的一般认定为过分高于，主张过高方承担举证责任。"
    },
    {
        "parent_article_id": "civil_code_2021:art_585",
        "child_article_id": "nine_minutes_2019:art_46",
        "relation_type": "审判指导规范",
        "notes": "确立民商事审判中法官对显失公平畸高违约金的主动释明义务与综合考量规则。"
    },
    {
        "parent_article_id": "civil_code_2021:art_667",
        "child_article_id": "private_lending_2020:art_13",
        "relation_type": "效力阻断与反洗钱转贷规制",
        "notes": "套取金融机构贷款转贷、以向公众非法吸收存款等方式取得资金转贷的，借贷合同直接认定为法定无效。"
    },
    {
        "parent_article_id": "civil_code_2021:art_676",
        "child_article_id": "private_lending_2020:art_25",
        "relation_type": "细化利息裁量上限",
        "notes": "逾期利息不得突破合同成立时一年期 LPR 四倍的法定司法保护上限红线。"
    },
    {
        "parent_article_id": "civil_code_2021:art_676",
        "child_article_id": "private_lending_2020:art_28",
        "relation_type": "利息与违约金综合穿透封顶",
        "notes": "逾期利息、违约金、资金占用费并存时，总计综合费率突破 LPR 四倍部分法院绝对不予支持。"
    },
    {
        "parent_article_id": "civil_code_2021:art_686",
        "child_article_id": "guarantee_interp_2021:art_25",
        "relation_type": "程序衔接与裁判主文执行顺序",
        "notes": "落实一般保证推定后，债权人仅起诉保证人的法院必须释明追加主债务人；裁判主文必须明确先执行主债务人财产。"
    },
    {
        "parent_article_id": "civil_code_2021:art_686",
        "child_article_id": "guarantee_interp_2021:art_32",
        "relation_type": "除斥期间与时效起算",
        "notes": "约定不明时保证期间推定为主债务届满后六个月，六个月内不起诉主债务人保证人彻底免责。"
    },
    {
        "parent_article_id": "company_law_2024:art_10",
        "child_article_id": "nine_minutes_2019:art_53",
        "relation_type": "审判实践认定规则",
        "notes": "最高院确立“看人不看章”原则：法定代表人或代理人享有代表权时，私刻假章依然有效；无权代理时真实印章亦不能绑架公司。"
    },
    {
        "parent_article_id": "criminal_law_2024:art_224",
        "child_article_id": "prosecution_standards_2022:art_69",
        "relation_type": "立案追诉门槛与刑民界限",
        "notes": "确立合同诈骗罪涉案数额在两万元以上应予刑事立案追诉，明确以非法占有为目的区别于民事合同违约。"
    },
    {
        "parent_article_id": "criminal_law_2024:art_175_1",
        "child_article_id": "prosecution_standards_2022:art_19",
        "relation_type": "立案追诉门槛",
        "notes": "骗取贷款罪给金融机构造成直接经济损失达五十万元以上应立案，防止将民事贷款展期纠纷简单推向刑事化。"
    }
]

SEED_ABROGATED_LAWS = [
    {
        "name": "合同法",
        "full_name": "中华人民共和国合同法",
        "abrogated_date": "2021-01-01",
        "replaced_by": "《中华人民共和国民法典》第三编合同（第四百六十三条至第七百一十三条）",
        "risk_tip": "严禁在2021年1月1日后法律事实中作为现行有效法条援引。若法律事实发生于2021年前，依《民法典时间效力若干规定》第一条第二款适用当时法律但需注明溯及力依据。"
    },
    {
        "name": "物权法",
        "full_name": "中华人民共和国物权法",
        "abrogated_date": "2021-01-01",
        "replaced_by": "《中华人民共和国民法典》第二编物权（第二百零五条至第四百六十二条）",
        "risk_tip": "已于2021年1月1日废止。居住权、抵押权不移转占有、动产浮动抵押规则全面升级为民法典物权编。"
    },
    {
        "name": "担保法",
        "full_name": "中华人民共和国担保法",
        "abrogated_date": "2021-01-01",
        "replaced_by": "《民法典》物权编担保物权及《最高法适用民法典有关担保制度的解释》（法释〔2020〕28号）",
        "risk_tip": "全面废止！注意保证方式推定规则重大逆转：未约定保证方式的，《民法典》第686条推定为一般保证（原担保法第19条推定为连带保证）！"
    },
    {
        "name": "民法通则",
        "full_name": "中华人民共和国民法通则",
        "abrogated_date": "2021-01-01",
        "replaced_by": "《中华人民共和国民法典》第一编总则",
        "risk_tip": "已废止。民事权利能力、民事行为能力、诉讼时效规则已被《民法典》总则编吸收重构。"
    },
    {
        "name": "侵权责任法",
        "full_name": "中华人民共和国侵权责任法",
        "abrogated_date": "2021-01-01",
        "replaced_by": "《中华人民共和国民法典》第七编侵权责任",
        "risk_tip": "已废止。自甘风险原则、自力救济及高空抛物责任已在民法典侵权编全新确立。"
    },
    {
        "name": "婚姻法",
        "full_name": "中华人民共和国婚姻法",
        "abrogated_date": "2021-01-01",
        "replaced_by": "《中华人民共和国民法典》第五编婚姻家庭",
        "risk_tip": "已废止。离婚冷静期、夫妻共同债务共债共签原则全面适用民法典新规。"
    },
    {
        "name": "继承法",
        "full_name": "中华人民共和国继承法",
        "abrogated_date": "2021-01-01",
        "replaced_by": "《中华人民共和国民法典》第六编继承",
        "risk_tip": "已废止。公证遗嘱不再具有法定最高效力，多份遗嘱冲突以最后的遗嘱为准。"
    }
]


def _seed_statutes_corpus(conn: sqlite3.Connection):
    """将高质量核心法典、司法解释与关系图谱批量写入 SQLite 与 FTS5"""
    cursor = conn.cursor()

    # 1. 插入法规
    for law in SEED_LAWS:
        cursor.execute("""
        INSERT OR REPLACE INTO laws (id, full_name, short_name, hierarchy, promulgated_by, promulgated_doc_no, effective_date, status, domain, summary)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            law["id"], law["full_name"], law["short_name"], law["hierarchy"],
            law["promulgated_by"], law["promulgated_doc_no"], law["effective_date"],
            law["status"], law["domain"], law["summary"]
        ))

    # 2. 插入法条
    for art in SEED_ARTICLES:
        cursor.execute("""
        INSERT OR REPLACE INTO articles (id, law_id, part_name, chapter_name, section_name, article_no_cn, article_no_int, content, has_proviso, key_terms, claim_basis_type)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            art["id"], art["law_id"], art["part_name"], art["chapter_name"], art["section_name"],
            art["article_no_cn"], art["article_no_int"], art["content"], art["has_proviso"],
            json.dumps(art["key_terms"], ensure_ascii=False), art["claim_basis_type"]
        ))

    # 3. 填充 FTS5 虚拟表
    cursor.execute("DELETE FROM articles_fts;")
    cursor.execute("""
    SELECT a.id, l.full_name, (a.part_name || ' ' || a.chapter_name) AS part_chap, a.article_no_cn, a.content, a.key_terms
    FROM articles a
    JOIN laws l ON a.law_id = l.id;
    """)
    rows = cursor.fetchall()
    for row in rows:
        cursor.execute("""
        INSERT INTO articles_fts (article_id, law_name, part_chapter, article_no_cn, content, key_terms)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (row[0], row[1], row[2], row[3], row[4], row[5]))

    # 4. 插入子母法关联图谱
    for link in SEED_PARENT_CHILD_LINKS:
        cursor.execute("""
        INSERT OR IGNORE INTO parent_child_links (parent_article_id, child_article_id, relation_type, notes)
        VALUES (?, ?, ?, ?)
        """, (link["parent_article_id"], link["child_article_id"], link["relation_type"], link["notes"]))

    # 5. 插入废止旧法库
    for ab in SEED_ABROGATED_LAWS:
        cursor.execute("""
        INSERT OR REPLACE INTO abrogated_laws (name, full_name, abrogated_date, replaced_by, risk_tip)
        VALUES (?, ?, ?, ?, ?)
        """, (ab["name"], ab["full_name"], ab["abrogated_date"], ab["replaced_by"], ab["risk_tip"]))

    # 更新每部法律的法条计数
    cursor.execute("""
    UPDATE laws SET article_count = (
        SELECT COUNT(*) FROM articles WHERE articles.law_id = laws.id
    );
    """)


# ==============================================================================
# 三路混合检索与图谱穿透函数 (Three-Way Hybrid Search + Parent-Child Graph)
# ==============================================================================
def search_statutes_hybrid(
    query: str,
    domain: Optional[str] = None,
    hierarchy: Optional[int] = None,
    status: str = "VALID",
    include_linked: bool = True,
    limit: int = 15
) -> List[Dict[str, Any]]:
    """
    三路混合检索：
    1. 精确条号直达（如输入 '民法典 585' 或 '585' 或 '刑法 224' 或 '公司法 23'）
    2. 智能复合词与法言法语短语检索（支持'套取贷款'、'刺破公司面纱'、'违约金调减'、'表见代理'等）
    3. FTS5 全文索引匹配 (Unicode61 BM25 ranking)
    返回结果自动携带【子法司法解释】与【母法关联】的双向穿透图谱！
    """
    query_str = query.strip()
    if not query_str:
        return []

    init_statute_database()
    results = []
    matched_ids = set()

    with get_db_connection() as conn:
        cursor = conn.cursor()
        return _search_statutes_hybrid_inner(
            cursor, query_str, domain, hierarchy, include_linked, limit, results, matched_ids
        )


def _search_statutes_hybrid_inner(
    cursor,
    query_str: str,
    domain: Optional[str],
    hierarchy: Optional[int],
    include_linked: bool,
    limit: int,
    results: List[Dict[str, Any]],
    matched_ids: set,
) -> List[Dict[str, Any]]:

    # --- 1. 第一路：精确条号解析与直达匹配 ---
    num_match = re.search(r"(\d+)", query_str)
    article_int = int(num_match.group(1)) if num_match else None
    law_keyword = re.sub(r"[\d\s条号第]+", "", query_str).strip()

    if article_int:
        exact_sql = """
        SELECT a.id, a.law_id, l.full_name, l.short_name, l.hierarchy, l.domain, l.status,
               a.part_name, a.chapter_name, a.article_no_cn, a.article_no_int,
               a.content, a.has_proviso, a.key_terms, a.claim_basis_type,
               100.0 AS rank_score, 'EXACT_ARTICLE_MATCH' AS match_mode
        FROM articles a
        JOIN laws l ON a.law_id = l.id
        WHERE a.article_no_int = ?
        """
        params: List[Any] = [article_int]
        if law_keyword:
            exact_sql += " AND (l.full_name LIKE ? OR l.short_name LIKE ?)"
            params.extend([f"%{law_keyword}%", f"%{law_keyword}%"])
        if domain and domain != "全部":
            exact_sql += " AND l.domain = ?"
            params.append(domain)
        if hierarchy:
            exact_sql += " AND l.hierarchy = ?"
            params.append(hierarchy)

        cursor.execute(exact_sql, params)
        for row in cursor.fetchall():
            matched_ids.add(row["id"])
            results.append(dict(row))

    # --- 2. 第二路：多词与复合短语全文穿透匹配 (Phrase & Bi-gram Multi-term Matching) ---
    clean_q = re.sub(r'[^\w\u4e00-\u9fa5]', ' ', query_str).strip()
    if clean_q:
        # 分词生成候选词集
        raw_words = clean_q.split()
        search_terms = []
        for w in raw_words:
            if len(w) >= 2:
                search_terms.append(w)
                if len(w) == 4:
                    search_terms.extend([w[:2], w[2:]])
                elif len(w) > 4:
                    # 抽取双字词
                    search_terms.extend([w[i:i+2] for i in range(0, len(w)-1, 2)])
            else:
                search_terms.append(w)

        # 优先全短语匹配或4字跨词通配 (如 '套取贷款' -> '%套取%贷款%')
        phrase_params = [f"%{clean_q}%", f"%{clean_q}%", f"%{clean_q}%"]
        wildcard_clause = ""
        if len(clean_q) >= 4 and " " not in clean_q:
            half = len(clean_q) // 2
            w_pat = f"%{clean_q[:half]}%{clean_q[half:]}%"
            wildcard_clause = " OR a.content LIKE ? OR a.key_terms LIKE ?"
            phrase_params.extend([w_pat, w_pat])

        phrase_sql = f"""
        SELECT a.id, a.law_id, l.full_name, l.short_name, l.hierarchy, l.domain, l.status,
               a.part_name, a.chapter_name, a.article_no_cn, a.article_no_int,
               a.content, a.has_proviso, a.key_terms, a.claim_basis_type,
               50.0 AS rank_score, 'PHRASE_EXACT_MATCH' AS match_mode
        FROM articles a
        JOIN laws l ON a.law_id = l.id
        WHERE (a.content LIKE ? OR a.key_terms LIKE ? OR l.full_name LIKE ?{wildcard_clause})
        """
        if domain and domain != "全部":
            phrase_sql += " AND l.domain = ?"
            phrase_params.append(domain)
        if hierarchy:
            phrase_sql += " AND l.hierarchy = ?"
            phrase_params.append(hierarchy)
        phrase_sql += " LIMIT ?"
        phrase_params.append(limit)

        cursor.execute(phrase_sql, phrase_params)
        for row in cursor.fetchall():
            if row["id"] not in matched_ids:
                matched_ids.add(row["id"])
                results.append(dict(row))

        # 若还有空格分隔的多词，执行多词联立检索（如 '借贷' AND '利息'）
        if len(raw_words) >= 2 and len(results) < limit:
            sub_terms = raw_words[:4]
            multi_sql = """
            SELECT a.id, a.law_id, l.full_name, l.short_name, l.hierarchy, l.domain, l.status,
               a.part_name, a.chapter_name, a.article_no_cn, a.article_no_int,
               a.content, a.has_proviso, a.key_terms, a.claim_basis_type,
               30.0 AS rank_score, 'MULTI_TERM_MATCH' AS match_mode
            FROM articles a
            JOIN laws l ON a.law_id = l.id
            WHERE """ + " AND ".join(["(a.content LIKE ? OR a.key_terms LIKE ?)" for _ in sub_terms])
            m_params: List[Any] = []
            for st in sub_terms:
                m_params.extend([f"%{st}%", f"%{st}%"])
            if domain and domain != "全部":
                multi_sql += " AND l.domain = ?"
                m_params.append(domain)
            if hierarchy:
                multi_sql += " AND l.hierarchy = ?"
                m_params.append(hierarchy)
            multi_sql += " LIMIT ?"
            m_params.append(limit - len(results))

            cursor.execute(multi_sql, m_params)
            for row in cursor.fetchall():
                if row["id"] not in matched_ids:
                    matched_ids.add(row["id"])
                    results.append(dict(row))

    # --- 3. 第三路：FTS5 全文索引检索 ---
    if len(results) < limit and clean_q:
        fts_tokens = [f'"{tok}"' for tok in clean_q.split() if tok]
        if fts_tokens:
            fts_query_expr = " OR ".join(fts_tokens)
            try:
                fts_sql = """
                SELECT a.id, a.law_id, l.full_name, l.short_name, l.hierarchy, l.domain, l.status,
                       a.part_name, a.chapter_name, a.article_no_cn, a.article_no_int,
                       a.content, a.has_proviso, a.key_terms, a.claim_basis_type,
                       bm25(articles_fts) * -10.0 AS rank_score, 'FTS5_TEXT_MATCH' AS match_mode
                FROM articles_fts f
                JOIN articles a ON f.article_id = a.id
                JOIN laws l ON a.law_id = l.id
                WHERE articles_fts MATCH ?
                """
                fts_params: List[Any] = [fts_query_expr]
                if domain and domain != "全部":
                    fts_sql += " AND l.domain = ?"
                    fts_params.append(domain)
                if hierarchy:
                    fts_sql += " AND l.hierarchy = ?"
                    fts_params.append(hierarchy)
                fts_sql += " ORDER BY rank_score DESC LIMIT ?"
                fts_params.append(limit - len(results))

                cursor.execute(fts_sql, fts_params)
                for row in cursor.fetchall():
                    if row["id"] not in matched_ids:
                        matched_ids.add(row["id"])
                        results.append(dict(row))
            except Exception as e:
                logger.warning(f"FTS5 检索异常: {e}")

    # --- 4. 子母法双向图谱穿透 (Parent-Child Relational Linking) ---
    if include_linked:
        for item in results:
            item_id = item["id"]
            # 查询子法（如该条是母法，查询解释该母法的司法解释）
            cursor.execute("""
            SELECT l.parent_article_id, l.child_article_id, l.relation_type, l.notes,
                   a.article_no_cn, a.content, law.short_name AS law_name, law.hierarchy
            FROM parent_child_links l
            JOIN articles a ON l.child_article_id = a.id
            JOIN laws law ON a.law_id = law.id
            WHERE l.parent_article_id = ?
            """, (item_id,))
            item["child_interpretations"] = [dict(r) for r in cursor.fetchall()]

            # 查询母法（如该条是司法解释，查询其依托的上位母法）
            cursor.execute("""
            SELECT l.parent_article_id, l.child_article_id, l.relation_type, l.notes,
                   a.article_no_cn, a.content, law.short_name AS law_name, law.hierarchy
            FROM parent_child_links l
            JOIN articles a ON l.parent_article_id = a.id
            JOIN laws law ON a.law_id = law.id
            WHERE l.child_article_id = ?
            """, (item_id,))
            item["parent_statutes"] = [dict(r) for r in cursor.fetchall()]

            # 解析 key_terms
            if isinstance(item.get("key_terms"), str):
                try:
                    item["key_terms"] = json.loads(item["key_terms"])
                except Exception:
                    item["key_terms"] = []

    return results[:limit]


def get_article_details_with_graph(article_id: str) -> Optional[Dict[str, Any]]:
    """获取单条法条详情及其完整的子母法关联网"""
    init_statute_database()
    with get_db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
        SELECT a.*, l.full_name AS law_full_name, l.short_name AS law_short_name,
               l.hierarchy, l.domain, l.status, l.promulgated_by, l.effective_date
        FROM articles a
        JOIN laws l ON a.law_id = l.id
        WHERE a.id = ?
        """, (article_id,))
        row = cursor.fetchone()
        if not row:
            return None

        art = dict(row)
        if isinstance(art.get("key_terms"), str):
            try:
                art["key_terms"] = json.loads(art["key_terms"])
            except Exception:
                art["key_terms"] = []

        cursor.execute("""
        SELECT l.relation_type, l.notes,
               a.id AS child_id, a.article_no_cn, a.content, law.short_name AS law_name, law.full_name AS law_full_name
        FROM parent_child_links l
        JOIN articles a ON l.child_article_id = a.id
        JOIN laws law ON a.law_id = law.id
        WHERE l.parent_article_id = ?
        """, (article_id,))
        art["children"] = [dict(r) for r in cursor.fetchall()]

        cursor.execute("""
        SELECT l.relation_type, l.notes,
               a.id AS parent_id, a.article_no_cn, a.content, law.short_name AS law_name, law.full_name AS law_full_name
        FROM parent_child_links l
        JOIN articles a ON l.parent_article_id = a.id
        JOIN laws law ON a.law_id = law.id
        WHERE l.child_article_id = ?
        """, (article_id,))
        art["parents"] = [dict(r) for r in cursor.fetchall()]

        return art


def import_custom_statute(
    law_id: str,
    full_name: str,
    short_name: str,
    hierarchy: int,
    promulgated_by: str,
    effective_date: str,
    domain: str,
    raw_text: str,
    summary: str = ""
) -> Dict[str, Any]:
    """
    通过专用正则原子切片器（编-章-节-条），批量将用户上传或粘贴的法律法规切分入库并自动索引
    """
    init_statute_database()
    from gateway.routers.phase3_rag_sign import chinese_law_chunker

    # 执行切片
    chunks = chinese_law_chunker(raw_text, law_name=full_name)
    if not chunks:
        raise ValueError("未能识别出任何有效的法条结构（需包含'第X条'格式）。")

    with get_db_connection() as conn:
        cursor = conn.cursor()

        # 1. 写入 laws 表
        cursor.execute("""
        INSERT OR REPLACE INTO laws (id, full_name, short_name, hierarchy, promulgated_by, effective_date, status, domain, article_count, summary)
        VALUES (?, ?, ?, ?, ?, ?, 'VALID', ?, ?, ?)
        """, (law_id, full_name, short_name, hierarchy, promulgated_by, effective_date, domain, len(chunks), summary))

        # 2. 写入 articles 与 FTS5
        num_pattern = re.compile(r"第([一二三四五六七八九十百千\d]+)条")
        inserted_count = 0

        cn_num_map = {
            '零': 0, '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
            '六': 6, '七': 7, '八': 8, '九': 9, '十': 10,
            '百': 100, '千': 1000
        }

        def parse_chinese_num(s: str) -> Optional[int]:
            if s.isdigit():
                return int(s)
            try:
                import cn2an
                return cn2an.cn2an(s, "normal")
            except Exception:
                return None

        for idx, chunk in enumerate(chunks):
            art_no_cn = chunk["article_no"]
            m_num = num_pattern.search(art_no_cn)
            art_no_int = None
            if m_num:
                art_no_int = parse_chinese_num(m_num.group(1))

            art_id = f"{law_id}:art_{art_no_int if art_no_int else idx + 1}"
            content = chunk["content"]
            has_proviso = 1 if any(kw in content for kw in ["但是", "除外", "另有约定的", "前款规定不适用"]) else 0

            cursor.execute("""
            INSERT OR REPLACE INTO articles (id, law_id, part_name, chapter_name, section_name, article_no_cn, article_no_int, content, has_proviso, key_terms, claim_basis_type)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                art_id, law_id, chunk["part"], chunk["chapter"], chunk["section"],
                art_no_cn, art_no_int, content, has_proviso, json.dumps([]), "自导入规范"
            ))

            # 写入 FTS5
            cursor.execute("""
            INSERT INTO articles_fts (article_id, law_name, part_chapter, article_no_cn, content, key_terms)
            VALUES (?, ?, ?, ?, ?, ?)
            """, (art_id, full_name, f"{chunk['part']} {chunk['chapter']}", art_no_cn, content, "[]"))

            inserted_count += 1

        conn.commit()

    return {
        "status": "success",
        "law_id": law_id,
        "law_name": full_name,
        "articles_imported": inserted_count
    }


def get_statute_database_stats() -> Dict[str, Any]:
    """获取数据库全局运行指标与统计数据"""
    init_statute_database()
    with get_db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM laws;")
        total_laws = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM articles;")
        total_articles = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM parent_child_links;")
        total_links = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM abrogated_laws;")
        total_abrogated = cursor.fetchone()[0]

        cursor.execute("SELECT domain, COUNT(*) as cnt FROM laws GROUP BY domain;")
        domain_breakdown = {r["domain"]: r["cnt"] for r in cursor.fetchall()}

        cursor.execute("SELECT hierarchy, COUNT(*) as cnt FROM laws GROUP BY hierarchy;")
        hierarchy_breakdown = {r["hierarchy"]: r["cnt"] for r in cursor.fetchall()}


    return {
        "status": "online",
        "engine": "SQLite FTS5 Full-Text Engine",
        "database_file": str(get_laws_db_path()),
        "total_laws": total_laws,
        "total_articles": total_articles,
        "total_parent_child_links": total_links,
        "total_abrogated_laws": total_abrogated,
        "domain_breakdown": domain_breakdown,
        "hierarchy_breakdown": hierarchy_breakdown
    }
