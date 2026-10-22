"""
LawFlow 智律工作台 - 法典与子母法关系图谱数据库引擎 (SQLite FTS5 架构)
功能：
1. 法律法规结构化存储（母法、司法解释、行政法规、会议纪要四级分层）
2. SQLite FTS5 全文检索 + 三路混合检索（精确条号 + 短语 + FTS5）
3. 母法 ⇄ 司法解释子母法关系图谱
4. 种子数据来自 data/legal/*.json；用户导入一律 USER_IMPORTED_UNVERIFIED
5. articles_fts 为 articles 的外部内容表，触发器同步
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional

from gateway.core.db import connect
from gateway.core.paths import get_laws_db_path

logger = logging.getLogger("lawflow.statute_db")

ARTICLE_SELECT_COLS = """
        a.id, a.law_id, l.full_name, l.short_name, l.hierarchy, l.domain, l.status,
        a.part_name, a.chapter_name, a.article_no_cn, a.article_no_int,
        a.content, a.has_proviso, a.key_terms, a.claim_basis_type,
        a.verification_status, a.source_url, a.verified_at, a.verified_by, a.review_note,
        l.version_note AS law_version_note, l.verification_status AS law_verification_status
"""


def _verification_label(status: Optional[str]) -> str:
    s = (status or "").upper()
    if s == "VERIFIED":
        return "已核验"
    if s == "USER_IMPORTED_UNVERIFIED":
        return "用户导入·未核验"
    if s == "PENDING_HUMAN":
        return "待律师核验"
    if s:
        return f"待核验({s})"
    return "待律师核验"


def _annotate_result(item: Dict[str, Any]) -> Dict[str, Any]:
    vstatus = item.get("verification_status") or "PENDING_HUMAN"
    item["verification_status"] = vstatus
    item["verification_label"] = _verification_label(vstatus)
    if int(item.get("hierarchy") or 0) == 4:
        tip = "不得作为裁判依据直接援引，只能在说理部分参考"
        note = item.get("law_version_note") or ""
        item["citation_caveat"] = tip
    if isinstance(item.get("key_terms"), str):
        try:
            item["key_terms"] = json.loads(item["key_terms"])
        except Exception:
            item["key_terms"] = []
    return item


@contextmanager
def get_db_connection() -> Iterator[sqlite3.Connection]:
    with connect(get_laws_db_path(), row_factory=sqlite3.Row) as conn:
        yield conn


def _add_column_if_missing(cursor: sqlite3.Cursor, table: str, column: str, decl: str) -> None:
    cursor.execute(f"PRAGMA table_info({table})")
    cols = {r[1] for r in cursor.fetchall()}
    if column not in cols:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")


def _ensure_fts_external(cursor: sqlite3.Cursor) -> None:
    """确保 articles_fts 为 content='articles' 外部内容表，并用触发器同步。"""
    need_rebuild = False
    cursor.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='articles_fts'"
    )
    row = cursor.fetchone()
    sql = (row[0] if row else "") or ""
    if "content='articles'" not in sql and 'content="articles"' not in sql:
        cursor.execute("DROP TABLE IF EXISTS articles_fts")
        need_rebuild = True

    cursor.execute("""
    CREATE VIRTUAL TABLE IF NOT EXISTS articles_fts USING fts5(
        content,
        article_no_cn,
        key_terms,
        content='articles',
        content_rowid='rowid',
        tokenize = 'unicode61'
    );
    """)

    # 触发器（先删后建，保证幂等）
    for trg in ("articles_ai", "articles_ad", "articles_au"):
        cursor.execute(f"DROP TRIGGER IF EXISTS {trg}")

    cursor.execute("""
    CREATE TRIGGER articles_ai AFTER INSERT ON articles BEGIN
      INSERT INTO articles_fts(rowid, content, article_no_cn, key_terms)
      VALUES (new.rowid, new.content, new.article_no_cn, new.key_terms);
    END;
    """)
    cursor.execute("""
    CREATE TRIGGER articles_ad AFTER DELETE ON articles BEGIN
      INSERT INTO articles_fts(articles_fts, rowid, content, article_no_cn, key_terms)
      VALUES('delete', old.rowid, old.content, old.article_no_cn, old.key_terms);
    END;
    """)
    cursor.execute("""
    CREATE TRIGGER articles_au AFTER UPDATE ON articles BEGIN
      INSERT INTO articles_fts(articles_fts, rowid, content, article_no_cn, key_terms)
      VALUES('delete', old.rowid, old.content, old.article_no_cn, old.key_terms);
      INSERT INTO articles_fts(rowid, content, article_no_cn, key_terms)
      VALUES (new.rowid, new.content, new.article_no_cn, new.key_terms);
    END;
    """)

    if need_rebuild:
        try:
            cursor.execute("INSERT INTO articles_fts(articles_fts) VALUES('rebuild')")
        except sqlite3.Error as e:
            logger.warning("FTS rebuild 失败（可能尚无数据）: %s", e)


def _rebuild_fts(cursor: sqlite3.Cursor) -> None:
    try:
        cursor.execute("INSERT INTO articles_fts(articles_fts) VALUES('rebuild')")
    except sqlite3.Error as e:
        logger.warning("FTS rebuild 异常: %s", e)


def init_statute_database(force_reseed: bool = False):
    """初始化数据库表结构与预置法规数据"""
    with get_db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS laws (
            id TEXT PRIMARY KEY,
            full_name TEXT NOT NULL,
            short_name TEXT NOT NULL,
            hierarchy INTEGER NOT NULL,
            promulgated_by TEXT NOT NULL,
            promulgated_doc_no TEXT,
            effective_date TEXT NOT NULL,
            abrogated_date TEXT,
            status TEXT NOT NULL DEFAULT 'VALID',
            domain TEXT NOT NULL,
            article_count INTEGER DEFAULT 0,
            summary TEXT,
            version_note TEXT,
            verification_status TEXT
        );
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS articles (
            id TEXT PRIMARY KEY,
            law_id TEXT NOT NULL,
            part_name TEXT,
            chapter_name TEXT,
            section_name TEXT,
            article_no_cn TEXT NOT NULL,
            article_no_int INTEGER,
            content TEXT NOT NULL,
            has_proviso INTEGER DEFAULT 0,
            key_terms TEXT,
            claim_basis_type TEXT,
            verification_status TEXT DEFAULT 'PENDING_HUMAN',
            source_url TEXT,
            verified_at TEXT,
            verified_by TEXT,
            review_note TEXT,
            FOREIGN KEY (law_id) REFERENCES laws(id) ON DELETE CASCADE
        );
        """)

        for col, decl in (
            ("version_note", "TEXT"),
            ("verification_status", "TEXT"),
        ):
            _add_column_if_missing(cursor, "laws", col, decl)

        for col, decl in (
            ("verification_status", "TEXT DEFAULT 'PENDING_HUMAN'"),
            ("source_url", "TEXT"),
            ("verified_at", "TEXT"),
            ("verified_by", "TEXT"),
            ("review_note", "TEXT"),
        ):
            _add_column_if_missing(cursor, "articles", col, decl)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS parent_child_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            parent_article_id TEXT NOT NULL,
            child_article_id TEXT NOT NULL,
            relation_type TEXT NOT NULL,
            notes TEXT,
            FOREIGN KEY (parent_article_id) REFERENCES articles(id) ON DELETE CASCADE,
            FOREIGN KEY (child_article_id) REFERENCES articles(id) ON DELETE CASCADE,
            UNIQUE(parent_article_id, child_article_id)
        );
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS abrogated_laws (
            name TEXT PRIMARY KEY,
            full_name TEXT NOT NULL,
            abrogated_date TEXT NOT NULL,
            replaced_by TEXT NOT NULL,
            risk_tip TEXT NOT NULL
        );
        """)

        _ensure_fts_external(cursor)
        conn.commit()

        cursor.execute("SELECT COUNT(*) FROM laws;")
        law_count = cursor.fetchone()[0]
        if law_count == 0 or force_reseed:
            logger.info("法规库为空或触发重新灌装，开始注入种子法典数据...")
            if force_reseed and law_count > 0:
                cursor.execute("DELETE FROM parent_child_links")
                cursor.execute("DELETE FROM articles")
                cursor.execute("DELETE FROM laws")
                # 外部内容 FTS 随 DELETE 触发器清理；再 rebuild 兜底
            _seed_statutes_corpus(conn)
            conn.commit()
            logger.info("法典与子母法图谱种子注入完成")
        else:
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
    """将种子法典、司法解释与关系图谱写入 SQLite；结束时 rebuild FTS。"""
    cursor = conn.cursor()
    _ensure_fts_external(cursor)

    for law in _seed_laws():
        cursor.execute(
            """
            INSERT OR REPLACE INTO laws (
                id, full_name, short_name, hierarchy, promulgated_by, promulgated_doc_no,
                effective_date, status, domain, summary, version_note, verification_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                law["id"],
                law["full_name"],
                law["short_name"],
                law["hierarchy"],
                law["promulgated_by"],
                law.get("promulgated_doc_no"),
                law["effective_date"],
                law.get("status") or "VALID",
                law["domain"],
                law.get("summary") or "",
                law.get("version_note") or "",
                law.get("verification_status"),
            ),
        )

    for art in _seed_articles():
        vstatus = art.get("verification_status") or "PENDING_HUMAN"
        cursor.execute(
            """
            INSERT OR REPLACE INTO articles (
                id, law_id, part_name, chapter_name, section_name, article_no_cn, article_no_int,
                content, has_proviso, key_terms, claim_basis_type,
                verification_status, source_url, verified_at, verified_by, review_note
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                art["id"],
                art["law_id"],
                art.get("part_name") or "",
                art.get("chapter_name") or "",
                art.get("section_name") or "",
                art["article_no_cn"],
                art.get("article_no_int"),
                art["content"],
                art.get("has_proviso") or 0,
                json.dumps(art.get("key_terms") or [], ensure_ascii=False),
                art.get("claim_basis_type") or "",
                vstatus,
                art.get("source_url") or "",
                art.get("verified_at"),
                art.get("verified_by"),
                art.get("review_note") or "",
            ),
        )

    cursor.execute("DELETE FROM parent_child_links")
    for link in _seed_links():
        cursor.execute(
            """
            INSERT OR IGNORE INTO parent_child_links (parent_article_id, child_article_id, relation_type, notes)
            VALUES (?, ?, ?, ?)
            """,
            (
                link["parent_article_id"],
                link["child_article_id"],
                link["relation_type"],
                link.get("notes") or "",
            ),
        )

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

    cursor.execute(
        """
        UPDATE laws SET article_count = (
            SELECT COUNT(*) FROM articles WHERE articles.law_id = laws.id
        );
        """
    )
    _rebuild_fts(cursor)


def search_statutes_hybrid(
    query: str,
    domain: Optional[str] = None,
    hierarchy: Optional[int] = None,
    status: str = "VALID",
    include_linked: bool = True,
    limit: int = 15,
) -> List[Dict[str, Any]]:
    query_str = query.strip()
    if not query_str:
        return []

    init_statute_database()
    results: List[Dict[str, Any]] = []
    matched_ids: set = set()

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

    num_match = re.search(r"(\d+)", query_str)
    article_int = int(num_match.group(1)) if num_match else None
    law_keyword = re.sub(r"[\d\s条号第]+", "", query_str).strip()

    if article_int:
        exact_sql = f"""
        SELECT {ARTICLE_SELECT_COLS},
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
            results.append(_annotate_result(dict(row)))

    clean_q = re.sub(r"[^\w\u4e00-\u9fa5]", " ", query_str).strip()
    if clean_q:
        raw_words = clean_q.split()
        phrase_params = [f"%{clean_q}%", f"%{clean_q}%", f"%{clean_q}%"]
        wildcard_clause = ""
        if len(clean_q) >= 4 and " " not in clean_q:
            half = len(clean_q) // 2
            w_pat = f"%{clean_q[:half]}%{clean_q[half:]}%"
            wildcard_clause = " OR a.content LIKE ? OR a.key_terms LIKE ?"
            phrase_params.extend([w_pat, w_pat])

        phrase_sql = f"""
        SELECT {ARTICLE_SELECT_COLS},
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
                results.append(_annotate_result(dict(row)))

        if len(raw_words) >= 2 and len(results) < limit:
            sub_terms = raw_words[:4]
            multi_sql = f"""
            SELECT {ARTICLE_SELECT_COLS},
               30.0 AS rank_score, 'MULTI_TERM_MATCH' AS match_mode
            FROM articles a
            JOIN laws l ON a.law_id = l.id
            WHERE """ + " AND ".join(
                ["(a.content LIKE ? OR a.key_terms LIKE ?)" for _ in sub_terms]
            )
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
                    results.append(_annotate_result(dict(row)))

    if len(results) < limit and clean_q:
        fts_tokens = [f'"{tok}"' for tok in clean_q.split() if tok]
        if fts_tokens:
            fts_query_expr = " OR ".join(fts_tokens)
            try:
                fts_sql = f"""
                SELECT {ARTICLE_SELECT_COLS},
                       bm25(articles_fts) * -10.0 AS rank_score, 'FTS5_TEXT_MATCH' AS match_mode
                FROM articles_fts f
                JOIN articles a ON a.rowid = f.rowid
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
                        results.append(_annotate_result(dict(row)))
            except Exception as e:
                logger.warning("FTS5 检索异常: %s", e)

    if include_linked:
        for item in results:
            item_id = item["id"]
            cursor.execute(
                """
                SELECT l.parent_article_id, l.child_article_id, l.relation_type, l.notes,
                       a.article_no_cn, a.content, a.verification_status,
                       law.short_name AS law_name, law.hierarchy
                FROM parent_child_links l
                JOIN articles a ON l.child_article_id = a.id
                JOIN laws law ON a.law_id = law.id
                WHERE l.parent_article_id = ?
                """,
                (item_id,),
            )
            children = []
            for r in cursor.fetchall():
                d = dict(r)
                d["verification_label"] = _verification_label(d.get("verification_status"))
                children.append(d)
            item["child_interpretations"] = children

            cursor.execute(
                """
                SELECT l.parent_article_id, l.child_article_id, l.relation_type, l.notes,
                       a.article_no_cn, a.content, a.verification_status,
                       law.short_name AS law_name, law.hierarchy
                FROM parent_child_links l
                JOIN articles a ON l.parent_article_id = a.id
                JOIN laws law ON a.law_id = law.id
                WHERE l.child_article_id = ?
                """,
                (item_id,),
            )
            parents = []
            for r in cursor.fetchall():
                d = dict(r)
                d["verification_label"] = _verification_label(d.get("verification_status"))
                parents.append(d)
            item["parent_statutes"] = parents

    return results[:limit]


def get_article_details_with_graph(article_id: str) -> Optional[Dict[str, Any]]:
    init_statute_database()
    with get_db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute(
            f"""
            SELECT {ARTICLE_SELECT_COLS}
            FROM articles a
            JOIN laws l ON a.law_id = l.id
            WHERE a.id = ?
            """,
            (article_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None

        art = _annotate_result(dict(row))
        art["law_full_name"] = art.get("full_name")
        art["law_short_name"] = art.get("short_name")

        cursor.execute(
            """
            SELECT l.relation_type, l.notes,
                   a.id AS child_id, a.article_no_cn, a.content, a.verification_status,
                   law.short_name AS law_name, law.full_name AS law_full_name
            FROM parent_child_links l
            JOIN articles a ON l.child_article_id = a.id
            JOIN laws law ON a.law_id = law.id
            WHERE l.parent_article_id = ?
            """,
            (article_id,),
        )
        art["children"] = [dict(r) for r in cursor.fetchall()]

        cursor.execute(
            """
            SELECT l.relation_type, l.notes,
                   a.id AS parent_id, a.article_no_cn, a.content, a.verification_status,
                   law.short_name AS law_name, law.full_name AS law_full_name
            FROM parent_child_links l
            JOIN articles a ON l.parent_article_id = a.id
            JOIN laws law ON a.law_id = law.id
            WHERE l.child_article_id = ?
            """,
            (article_id,),
        )
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
    summary: str = "",
) -> Dict[str, Any]:
    """用户导入：status=USER_IMPORTED，verification_status=USER_IMPORTED_UNVERIFIED。"""
    init_statute_database()
    from gateway.routers.phase3_rag_sign import chinese_law_chunker

    chunks = chinese_law_chunker(raw_text, law_name=full_name)
    if not chunks:
        raise ValueError("未能识别出任何有效的法条结构（需包含'第X条'格式）。")

    with get_db_connection() as conn:
        cursor = conn.cursor()
        _ensure_fts_external(cursor)

        cursor.execute(
            """
            INSERT OR REPLACE INTO laws (
                id, full_name, short_name, hierarchy, promulgated_by, effective_date,
                status, domain, article_count, summary, version_note, verification_status
            ) VALUES (?, ?, ?, ?, ?, ?, 'USER_IMPORTED', ?, ?, ?, ?, 'USER_IMPORTED_UNVERIFIED')
            """,
            (
                law_id,
                full_name,
                short_name,
                hierarchy,
                promulgated_by,
                effective_date,
                domain,
                len(chunks),
                summary,
                "用户导入·未核验",
            ),
        )

        num_pattern = re.compile(r"第([一二三四五六七八九十百千\d]+)条")

        def parse_chinese_num(s: str) -> Optional[int]:
            if s.isdigit():
                return int(s)
            try:
                import cn2an

                return cn2an.cn2an(s, "normal")
            except Exception:
                return None

        inserted_count = 0
        for idx, chunk in enumerate(chunks):
            art_no_cn = chunk["article_no"]
            m_num = num_pattern.search(art_no_cn)
            art_no_int = parse_chinese_num(m_num.group(1)) if m_num else None
            art_id = f"{law_id}:art_{art_no_int if art_no_int else idx + 1}"
            content = chunk["content"]
            has_proviso = (
                1
                if any(kw in content for kw in ["但是", "除外", "另有约定的", "前款规定不适用"])
                else 0
            )

            cursor.execute(
                """
                INSERT OR REPLACE INTO articles (
                    id, law_id, part_name, chapter_name, section_name, article_no_cn, article_no_int,
                    content, has_proviso, key_terms, claim_basis_type,
                    verification_status, source_url, verified_at, verified_by, review_note
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'USER_IMPORTED_UNVERIFIED', '', NULL, NULL, ?)
                """,
                (
                    art_id,
                    law_id,
                    chunk["part"],
                    chunk["chapter"],
                    chunk["section"],
                    art_no_cn,
                    art_no_int,
                    content,
                    has_proviso,
                    json.dumps([]),
                    "自导入规范",
                    "用户导入·未核验",
                ),
            )
            inserted_count += 1

        conn.commit()
        _rebuild_fts(cursor)
        conn.commit()

    return {
        "status": "success",
        "law_id": law_id,
        "law_name": full_name,
        "articles_imported": inserted_count,
        "verification_status": "USER_IMPORTED_UNVERIFIED",
    }


def get_statute_database_stats() -> Dict[str, Any]:
    """获取数据库全局运行指标；不含服务器文件系统完整路径。"""
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

        cursor.execute(
            """
            SELECT COALESCE(verification_status, 'PENDING_HUMAN') AS vs, COUNT(*) AS cnt
            FROM articles GROUP BY COALESCE(verification_status, 'PENDING_HUMAN')
            """
        )
        verification_counts = {r["vs"]: r["cnt"] for r in cursor.fetchall()}

        verified_n = verification_counts.get("VERIFIED", 0)
        pending_n = verification_counts.get("PENDING_HUMAN", 0) + verification_counts.get(
            "USER_IMPORTED_UNVERIFIED", 0
        )

    return {
        "status": "online",
        "engine": "SQLite FTS5 Full-Text Engine",
        "database_file": "cn_laws_kb.db",
        "total_laws": total_laws,
        "total_articles": total_articles,
        "total_parent_child_links": total_links,
        "total_abrogated_laws": total_abrogated,
        "domain_breakdown": domain_breakdown,
        "hierarchy_breakdown": hierarchy_breakdown,
        "verification_counts": verification_counts,
        "coverage_note": (
            f"已核验 {verified_n} 条、待核验 {pending_n} 条，仅覆盖本工具引擎引用的部分条文，"
            "并非权威法典全集。"
        ),
    }
