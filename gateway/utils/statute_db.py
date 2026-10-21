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
        else:
            # 法规已存在时仍刷新废止表（单一数据源 upsert，补齐民法总则/收养法等）
            for ab in _seed_abrogated():
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO abrogated_laws (name, full_name, abrogated_date, replaced_by, risk_tip)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        ab["name"],
                        ab.get("full_name") or ab["name"],
                        ab.get("abrogated_date") or "2021-01-01",
                        ab.get("replaced_by") or "TODO(律师核实)",
                        ab.get("risk_tip") or "",
                    ),
                )
            conn.commit()


# ==============================================================================
# 权威预置法典与子母法图谱：从 data/legal/*.json 统一加载（不再内嵌重复字典）
# ==============================================================================
def _seed_laws():
    from gateway.utils.legal_data import load_seed_articles_bundle
    return list(load_seed_articles_bundle().get("laws") or [])


def _seed_articles():
    from gateway.utils.legal_data import load_seed_articles_bundle
    return list(load_seed_articles_bundle().get("articles") or [])


def _seed_links():
    from gateway.utils.legal_data import load_seed_links
    return list(load_seed_links())


def _seed_abrogated():
    from gateway.utils.legal_data import load_abrogated_laws
    return list(load_abrogated_laws())


def _seed_statutes_corpus(conn: sqlite3.Connection):
    """将高质量核心法典、司法解释与关系图谱批量写入 SQLite 与 FTS5"""
    cursor = conn.cursor()

    # 1. 插入法规
    for law in _seed_laws():
        cursor.execute("""
        INSERT OR REPLACE INTO laws (id, full_name, short_name, hierarchy, promulgated_by, promulgated_doc_no, effective_date, status, domain, summary)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            law["id"], law["full_name"], law["short_name"], law["hierarchy"],
            law["promulgated_by"], law["promulgated_doc_no"], law["effective_date"],
            law["status"], law["domain"], law["summary"]
        ))

    # 2. 插入法条
    for art in _seed_articles():
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
    for link in _seed_links():
        cursor.execute("""
        INSERT OR IGNORE INTO parent_child_links (parent_article_id, child_article_id, relation_type, notes)
        VALUES (?, ?, ?, ?)
        """, (link["parent_article_id"], link["child_article_id"], link["relation_type"], link["notes"]))

    # 5. 插入废止旧法库
    for ab in _seed_abrogated():
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
