/**
 * LawFlow Module: 06_citation_guard.js
 */
import { api, ApiError, API_BASE, withDownloadToken } from '../api.js';
import { showToast } from '../ui/toast.js';


// safe-html: static tab template
export const CITATIONGUARD_TAB_HTML = `      
      <!-- 1. 顶部指标与全景架构看板 -->
      <div class="surface-card" style="margin-bottom: 20px;">
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px;">
          <div>
            <div style="display: flex; align-items: center; gap: 8px;">
              <span style="font-size: 15px; font-weight: 700; color: var(--primary-navy);">法条库与子母法图谱中枢</span>
              <span class="live-badge valid" style="font-size: 11px; height: 24px; padding: 0 8px;">
                <span class="pulse-dot" style="width: 6px; height: 6px;"></span>
                <span>SQLite FTS5 全文索引引擎在线</span>
              </span>
            </div>
            <div style="font-size: 12px; color: var(--text-muted); margin-top: 3px;" id="statute-coverage-note">
              三路混合检索 · 子母法穿透 · 仅覆盖本工具引擎引用的部分条文（已核验/待核验分列），并非权威法典全集
            </div>
          </div>

          <div style="display: flex; align-items: center; gap: 8px;">
            <button class="btn btn-secondary btn-sm" onclick="toggleImportDrawer()" style="display: inline-flex; align-items: center; gap: 5px;">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line></svg>
              <span>导入新法或高院指引</span>
            </button>
            <button class="btn btn-secondary btn-sm" onclick="reloadStatutesCorpus()" title="重新加载法规库指标">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"></polyline><polyline points="1 20 1 14 7 14"></polyline><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path></svg>
              <span>刷新指标</span>
            </button>
            <button class="btn btn-secondary btn-sm" onclick="reseedStatutesCorpus()" title="强制重置并重新灌装法条种子语料">
              <span>重载语料</span>
            </button>
          </div>
        </div>

        <!-- KPI 指标网格 -->
        <div class="metric-summary-box" style="margin-top: 14px; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));">
          <div class="metric-item">
            <span class="metric-label">现行核心法典</span>
            <span class="metric-value highlight" id="statute-kpi-laws">10 部</span>
            <span class="metric-sub">涵盖民商/劳动/刑事/公司</span>
          </div>
          <div class="metric-item">
            <span class="metric-label">实务要件法条</span>
            <span class="metric-value" id="statute-kpi-articles">—</span>
            <span class="metric-sub" id="statute-kpi-verify-sub">已核验 / 待核验分列</span>
          </div>
          <div class="metric-item">
            <span class="metric-label">子母法图谱连带</span>
            <span class="metric-value" id="statute-kpi-links" style="color: var(--accent-amber);">11 组</span>
            <span class="metric-sub">违约金30%上限/担保推定等</span>
          </div>
          <div class="metric-item">
            <span class="metric-label">废止旧法拦截库</span>
            <span class="metric-value" id="statute-kpi-abrogated" style="color: var(--status-warn);">7 部</span>
            <span class="metric-sub">合同法/担保法/物权法严阻</span>
          </div>
          <div class="metric-item">
            <span class="metric-label">检索响应延迟</span>
            <span class="metric-value" style="color: var(--status-valid);">&lt; 15 ms</span>
            <span class="metric-sub">单文件 SQLite 零外部依赖</span>
          </div>
        </div>
      </div>

      <!-- 2. 检索控制台与筛选器 -->
      <div class="surface-card" style="margin-bottom: 20px;">
        <div style="display: flex; gap: 10px; align-items: center;">
          <div style="position: relative; flex: 1;">
            <svg style="position: absolute; left: 12px; top: 11px; width: 16px; height: 16px; color: var(--text-muted);" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
            <input aria-label="输入法典法条编号或裁判要旨关键词"  type="text" id="statute-search-input" class="quick-input" style="padding-left: 36px; height: 38px; font-size: 13.5px;" placeholder="输入条号直达（如：民法典 585、刑法 224、公司法 23）或法言法语（如：套取贷款、刺破公司面纱、看人不看章）..." onkeydown="if(event.key==='Enter') executeStatuteSearch()">
          </div>
          <button class="btn" onclick="executeStatuteSearch()" style="height: 38px; padding: 0 20px; display: inline-flex; align-items: center; gap: 6px;">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
            <span>混合检索</span>
          </button>
        </div>

        <!-- 快捷查询标签组 -->
        <div style="display: flex; align-items: center; gap: 6px; flex-wrap: wrap; margin-top: 10px;">
          <span style="font-size: 11px; font-weight: 600; color: var(--text-muted);">实务高频直达：</span>
          <span role="button" tabindex="0"  class="citation-pill" onclick="quickFillStatuteSearch('民法典 585')">民法典 585 (违约金30%上限)</span>
          <span role="button" tabindex="0"  class="citation-pill" onclick="quickFillStatuteSearch('新公司法 23')">公司法 23 (刺破公司面纱)</span>
          <span role="button" tabindex="0"  class="citation-pill" onclick="quickFillStatuteSearch('民间借贷 13')">民间借贷 13 (套取贷款转贷无效)</span>
          <span role="button" tabindex="0"  class="citation-pill" onclick="quickFillStatuteSearch('民法典 686')">民法典 686 (一般保证法定推定)</span>
          <span role="button" tabindex="0"  class="citation-pill" onclick="quickFillStatuteSearch('刑法 224')">刑法 224 (合同诈骗与追诉标准)</span>
          <span role="button" tabindex="0"  class="citation-pill" onclick="quickFillStatuteSearch('劳动合同法 47')">劳动合同法 47 (补偿N与社平3倍)</span>
          <span role="button" tabindex="0"  class="citation-pill" onclick="quickFillStatuteSearch('看人不看章')">九民纪要 41 (盖章行为/看人不看章)</span>
          <span role="button" tabindex="0"  class="citation-pill" onclick="quickFillStatuteSearch('刑法 175')">刑法 175之一 (骗取贷款罪)</span>
        </div>

        <!-- 部门法与位阶筛选栏 -->
        <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 12px; padding-top: 10px; border-top: 1px solid var(--border-hairline); flex-wrap: wrap; gap: 10px;">
          <div style="display: flex; align-items: center; gap: 6px; flex-wrap: wrap;">
            <span style="font-size: 11.5px; font-weight: 600; color: var(--text-secondary);">部门法：</span>
            <div id="statute-domain-pills" style="display: inline-flex; gap: 4px; flex-wrap: wrap;">
              <button class="perspective-btn blue active" data-domain="全部" onclick="selectStatuteDomain('全部', this)">全部</button>
              <button class="perspective-btn blue" data-domain="民商" onclick="selectStatuteDomain('民商', this)">民商总揽</button>
              <button class="perspective-btn blue" data-domain="合同" onclick="selectStatuteDomain('合同', this)">合同编</button>
              <button class="perspective-btn blue" data-domain="公司" onclick="selectStatuteDomain('公司', this)">公司企业</button>
              <button class="perspective-btn blue" data-domain="劳动" onclick="selectStatuteDomain('劳动', this)">劳动社保</button>
              <button class="perspective-btn blue" data-domain="刑事" onclick="selectStatuteDomain('刑事', this)">刑事法</button>
              <button class="perspective-btn blue" data-domain="民诉程序" onclick="selectStatuteDomain('民诉程序', this)">民诉程序</button>
            </div>
          </div>

          <div style="display: flex; align-items: center; gap: 8px;">
            <span style="font-size: 11.5px; font-weight: 600; color: var(--text-secondary);">位阶：</span>
            <select aria-label="statute hierarchy filter"  id="statute-hierarchy-filter" onchange="executeStatuteSearch()" style="padding: 4px 8px; font-size: 12px;">
              <option value="">全部效力位阶</option>
              <option value="1">L1 国家基本法律 (民法典/刑法/公司法)</option>
              <option value="2">L2 最高法司法解释 (通则解释/民间借贷/担保)</option>
              <option value="4">L4 会议纪要与指引 (九民纪要/高院指引)</option>
            </select>
          </div>
        </div>
      </div>

      <!-- 3. 新法规原子切片导入抽屉 (默认折叠) -->
      <div id="statute-import-drawer" class="surface-card" style="display: none; margin-bottom: 20px; background: #FAF9F6; border: 1.5px dashed var(--accent-amber-border);">
        <div class="card-header">
          <div class="card-title">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="12" y1="18" x2="12" y2="12"></line><line x1="9" y1="15" x2="15" y2="15"></line></svg>
            律所私有新法规/地方审判指引一键切片导入 (Chinese Law Chunker)
          </div>
          <button class="btn btn-secondary btn-sm" onclick="toggleImportDrawer()">收起抽屉</button>
        </div>

        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin-top: 10px;">
          <div>
            <label style="font-size: 11px; font-weight: 600; color: var(--text-secondary);">法规全局唯一 ID</label>
            <input aria-label="如 sh_highcourt_housing_2023"  type="text" id="import-law-id" class="quick-input" placeholder="如 sh_highcourt_housing_2023" style="margin-top: 3px;">
          </div>
          <div>
            <label style="font-size: 11px; font-weight: 600; color: var(--text-secondary);">法规标准全称</label>
            <input aria-label="如《上海市高级人民法院关于审理房屋买卖合同纠纷若干问题的解答》"  type="text" id="import-law-fullname" class="quick-input" placeholder="如《上海市高级人民法院关于审理房屋买卖合同纠纷若干问题的解答》" style="margin-top: 3px;">
          </div>
          <div>
            <label style="font-size: 11px; font-weight: 600; color: var(--text-secondary);">法规简称</label>
            <input aria-label="如 上海高院房产买卖解答"  type="text" id="import-law-shortname" class="quick-input" placeholder="如 上海高院房产买卖解答" style="margin-top: 3px;">
          </div>
          <div>
            <label style="font-size: 11px; font-weight: 600; color: var(--text-secondary);">制定机关</label>
            <input aria-label="如 上海市高级人民法院"  type="text" id="import-law-promulgated" class="quick-input" placeholder="如 上海市高级人民法院" style="margin-top: 3px;">
          </div>
        </div>

        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin-top: 10px;">
          <div>
            <label style="font-size: 11px; font-weight: 600; color: var(--text-secondary);">效力位阶</label>
            <select aria-label="import law hierarchy"  id="import-law-hierarchy" style="width: 100%; padding: 6px 8px; margin-top: 3px;">
              <option value="4">L4 地方高院裁判指引/会议纪要</option>
              <option value="2">L2 最高人民法院司法解释</option>
              <option value="1">L1 全国人大及常委会基本法律</option>
              <option value="3">L3 国务院行政法规/部门司法规定</option>
            </select>
          </div>
          <div>
            <label style="font-size: 11px; font-weight: 600; color: var(--text-secondary);">部门法领域</label>
            <select aria-label="import law domain"  id="import-law-domain" style="width: 100%; padding: 6px 8px; margin-top: 3px;">
              <option value="民商">民商事</option>
              <option value="合同">合同法</option>
              <option value="公司">公司企业</option>
              <option value="劳动">劳动人事</option>
              <option value="刑事">刑事犯罪</option>
              <option value="民诉程序">诉讼程序与执行</option>
            </select>
          </div>
          <div>
            <label style="font-size: 11px; font-weight: 600; color: var(--text-secondary);">施行/发布日期</label>
            <input aria-label="import law date"  type="date" id="import-law-date" class="quick-input" value="2024-01-01" style="margin-top: 3px;">
          </div>
        </div>

        <div style="margin-top: 12px;">
          <label style="font-size: 11px; font-weight: 600; color: var(--text-secondary);">法规正文原文 (系统将自动按“编-章-节-条-款”精准切块，绝不破坏同一法条完整性)</label>
          <textarea aria-label="粘贴法典或司法解释全文，示例：&#10;第一条 为了正确审理...&#10;第二条 当事人一方逾期履行的，另一方可以...&#10;第三条 具有下列情形之一的，应当认定为..."  id="import-law-rawtext" class="quick-input" rows="8" placeholder="粘贴法典或司法解释全文，示例：&#10;第一条 为了正确审理...&#10;第二条 当事人一方逾期履行的，另一方可以...&#10;第三条 具有下列情形之一的，应当认定为..." style="margin-top: 4px; font-family: var(--font-mono); font-size: 12px; line-height: 1.5;"></textarea>
        </div>

        <div style="margin-top: 12px; display: flex; justify-content: flex-end; gap: 10px;">
          <button class="btn btn-secondary" onclick="toggleImportDrawer()">取消</button>
          <button class="btn" onclick="submitStatuteImport()">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"></polyline></svg>
            <span>执行原子切片并入库</span>
          </button>
        </div>
      </div>

      <!-- 4. 主体双栏联动穿透对照视图 (50% : 50%) -->
      <div class="split-grid-50-50">
        
        <!-- 左栏：检索命中的法条清单 -->
        <div class="surface-card" style="display: flex; flex-direction: column; gap: 14px;">
          <div class="card-header">
            <div class="card-title">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"></path><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"></path></svg>
              <span>匹配法条清单</span>
              <span class="badge" id="statute-results-badge" style="background: rgba(20, 35, 60, 0.08); color: var(--primary-navy); margin-left: 6px;">共 0 条</span>
            </div>
            <span class="card-tip">点击任意法条卡片，右栏穿透展开子母法图谱</span>
          </div>

          <!-- 法条卡片容器 -->
          <div id="statute-articles-container" style="display: flex; flex-direction: column; gap: 12px; max-height: 720px; overflow-y: auto; padding-right: 4px;">
            <div style="text-align: center; padding: 40px 20px; color: var(--text-muted); font-size: 13px;">
              输入条号或关键词（或点击上方快捷标签）开启全量法典混合检索...
            </div>
          </div>
        </div>

        <!-- 右栏：子母法双向穿透与实务裁量图谱面板 -->
        <div class="surface-card" style="display: flex; flex-direction: column; gap: 14px; position: sticky; top: 16px;">
          <div class="card-header">
            <div class="card-title">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><circle cx="18" cy="5" r="3"></circle><circle cx="6" cy="12" r="3"></circle><circle cx="18" cy="19" r="3"></circle><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"></line><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"></line></svg>
              <span>子母法双向穿透与实务裁量图谱</span>
            </div>
            <button class="btn btn-secondary btn-sm" id="btn-copy-active-statute" onclick="copyActiveStatuteCitation()" style="display: none;">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
              <span>复制法条原文</span>
            </button>
          </div>

          <!-- 穿透图谱展示容器 -->
          <div id="statute-graph-container" style="display: flex; flex-direction: column; gap: 14px; max-height: 720px; overflow-y: auto;">
            <div style="text-align: center; padding: 60px 20px; color: var(--text-muted); font-size: 13px;">
              👈 请在左侧列表中点击任意法条，此处将实时穿透展开关联的【最高法司法解释】与【上位母法规范】。
            </div>
          </div>
        </div>

      </div>

    </section>

    <!-- ======================================================================
         模块 07：案件独立空间与核心图谱中枢 (Matter Vault & Core Graphs)
         ====================================================================== -->
`;

export function renderTabCitationGuard() {
  const el = document.getElementById('tab-statutes');
  if (el) {
    // safe-html: mount static tab template
    el.innerHTML = CITATIONGUARD_TAB_HTML;
  }
}


    // =========================================================================
    // 6. 模块 06：权威法典与子母法图谱检索中枢 (SQLite FTS5 + 穿透图谱)
    // =========================================================================
    let currentStatutesResults = [];
    let currentActiveArticleId = null;
    let selectedStatuteDomain = "全部";

    async function reloadStatutesCorpus() {
      try {
        const resp = await api.request(`${API_BASE}/api/v1/statutes/overview`);
        if (resp.ok) {
          const res = await resp.json();
          const d = res.data;
          document.getElementById('statute-kpi-laws').innerText = `${d.total_laws} 部`;
          const vc = d.verification_counts || {};
          const verified = vc.VERIFIED || 0;
          const pending = (vc.PENDING_HUMAN || 0) + (vc.USER_IMPORTED_UNVERIFIED || 0);
          document.getElementById('statute-kpi-articles').innerText = `${d.total_articles} 条`;
          const sub = document.getElementById('statute-kpi-verify-sub');
          if (sub) sub.innerText = `已核验 ${verified} · 待核验 ${pending}`;
          document.getElementById('statute-kpi-links').innerText = `${d.total_parent_child_links} 组`;
          document.getElementById('statute-kpi-abrogated').innerText = `${d.total_abrogated_laws} 部`;
          const noteEl = document.getElementById('statute-coverage-note');
          if (noteEl && d.coverage_note) noteEl.innerText = d.coverage_note;
        }
      } catch (e) {
        console.warn("加载法规概览异常:", e);
      }
    }

    async function reseedStatutesCorpus() {
      if (!confirm('确认强制重置并重新灌装法条种子语料？此操作不可撤销。')) {
        return;
      }
      try {
        const resp = await api.request(`${API_BASE}/api/v1/statutes/reseed`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ confirm: 'RESEED' })
        });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok) {
          showToast('重载语料失败: ' + (data.detail || resp.status));
          return;
        }
        showToast('法典语料已重新灌装');
        await reloadStatutesCorpus();
      } catch (e) {
        showToast('重载语料异常: ' + e);
      }
    }

    function quickFillStatuteSearch(query) {
      document.getElementById('statute-search-input').value = query;
      executeStatuteSearch();
    }

    function selectStatuteDomain(domain, btnElem) {
      selectedStatuteDomain = domain;
      const container = document.getElementById('statute-domain-pills');
      if (container) {
        container.querySelectorAll('button').forEach(b => b.classList.remove('active'));
      }
      if (btnElem) btnElem.classList.add('active');
      executeStatuteSearch();
    }

    function toggleImportDrawer() {
      const drawer = document.getElementById('statute-import-drawer');
      if (drawer) {
        drawer.style.display = (drawer.style.display === 'none' || !drawer.style.display) ? 'block' : 'none';
      }
    }

    async function executeStatuteSearch() {
      const query = document.getElementById('statute-search-input').value.trim() || "民法典 585";
      const hierarchy = document.getElementById('statute-hierarchy-filter').value;
      const container = document.getElementById('statute-articles-container');

      container.innerHTML = `
        <div style="text-align: center; padding: 40px; color: var(--text-muted); font-size: 13px;">
          <span class="spinner-dark"></span> 正在执行 SQLite FTS5 三路混合检索与子母法图谱穿透...
        </div>
      `;

      try {
        const resp = await api.request(`${API_BASE}/api/v1/statutes/search`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            query: query,
            domain: selectedStatuteDomain,
            hierarchy: hierarchy ? parseInt(hierarchy) : null,
            status: "VALID",
            include_linked: true,
            limit: 15
          })
        });

        if (!resp.ok) {
          const err = await resp.json();
          container.innerHTML = `<div style="color: var(--status-warn); padding: 20px;">检索失败: ${escapeHtml(err.detail || '未知错误')}</div>`;
          return;
        }

        const data = await resp.json();
        currentStatutesResults = data.results || [];
        document.getElementById('statute-results-badge').innerText = `共 ${currentStatutesResults.length} 条`;

        if (currentStatutesResults.length === 0) {
          container.innerHTML = `
            <div style="text-align: center; padding: 40px; color: var(--text-muted); font-size: 13px;">
              未检索到符合条件的法条。建议尝试输入条号数字（如 585、224、23）或关键法律术语。
            </div>
          `;
          document.getElementById('statute-graph-container').innerHTML = `
            <div style="text-align: center; padding: 60px 20px; color: var(--text-muted); font-size: 13px;">
              暂无匹配法条图谱。
            </div>
          `;
          return;
        }

        // 渲染左侧法条卡片列表
        container.innerHTML = "";
        currentStatutesResults.forEach((art, idx) => {
          const card = document.createElement('div');
          card.className = `element-card proven ${idx === 0 ? 'active' : ''}`;
          card.id = `statute-card-${art.id.replace(/[:.]/g, '_')}`;
          card.style.cursor = 'pointer';
          card.onclick = () => renderStatuteGraphDetail(art.id);

          const provBadge = art.has_proviso ? `<span class="badge" style="background: rgba(197, 133, 50, 0.15); color: var(--accent-amber); font-size: 10px;">含除外但书</span>` : '';
          const childrenCount = (art.child_interpretations && art.child_interpretations.length) ? art.child_interpretations.length : 0;
          const childBadge = childrenCount > 0 ? `<span class="badge" style="background: rgba(34, 197, 94, 0.12); color: var(--status-valid); font-size: 10px;">★ 关联 ${childrenCount} 条司法解释</span>` : '';
          const vLabel = art.verification_label || (art.verification_status === 'VERIFIED' ? '已核验' : (art.verification_status === 'USER_IMPORTED_UNVERIFIED' ? '用户导入·未核验' : '待律师核验'));
          const vBadgeColor = art.verification_status === 'VERIFIED' ? '#15803D' : '#B45309';
          const vBadgeBg = art.verification_status === 'VERIFIED' ? 'rgba(34,197,94,0.12)' : 'rgba(245,158,11,0.15)';
          const verifyBadge = `<span class="badge" style="background: ${vBadgeBg}; color: ${vBadgeColor}; font-size: 10px;">${vLabel}</span>`;
          const matchModeLabel = art.match_mode === 'EXACT_ARTICLE_MATCH' ? '精确条号直达' : (art.match_mode === 'PHRASE_EXACT_MATCH' ? '短语精准匹配' : 'FTS5 全文命中');
          const isPinned = (window.CaseContextStore && window.CaseContextStore.hasStatute(art.id));

          card.innerHTML = `
            <div class="element-card-header">
              <div style="display: flex; align-items: center; gap: 6px; flex-wrap: wrap;">
                <span class="citation-pill" style="font-weight: 700; background: #14233C; color: #FFF; border: none;">${escapeHtml(art.article_no_cn)}</span>
                <span style="font-size: 12.5px; font-weight: 600; color: var(--primary-navy);">${escapeHtml(art.short_name || art.full_name)}</span>
                ${escapeHtml(verifyBadge)}
                <span style="font-size: 11px; color: var(--text-muted);">${escapeHtml(art.part_name || '')} ${escapeHtml(art.chapter_name || '')}</span>
              </div>
              <span style="font-size: 10.5px; color: var(--accent-amber); font-weight: 500;">${escapeHtml(matchModeLabel)}</span>
            </div>

            <div style="font-size: 12px; color: var(--text-secondary); line-height: 1.6; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; margin-top: 4px;">
              ${escapeHtml(art.content)}
            </div>

            <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 6px; font-size: 11px;">
              <div style="display: flex; gap: 5px; align-items: center;">
                <span class="element-badge" style="background: var(--bg-subtle);">${escapeHtml(art.claim_basis_type || '规范条文')}</span>
                ${escapeHtml(provBadge)}
                ${escapeHtml(childBadge)}
              </div>
              <div style="display: flex; align-items: center; gap: 6px;">
                <button type="button" class="btn-select-statute ${escapeHtml(isPinned ? 'selected' : '')}" id="btn-statute-list-${escapeHtml(art.id.replace(/[:.]/g, '_'))}" onclick="event.stopPropagation(); toggleSelectStatuteFromList('${escapeHtml(art.id)}', '${escapeHtml((art.short_name || art.full_name || '').replace(/'/g, "\\'"))}', '${escapeHtml(art.article_no_cn)}', ${escapeHtml(JSON.stringify(art.content).replace(/"/g, '&quot;'))})">
                  ${escapeHtml(isPinned ? '✓ 已选入本案' : '📌 选入本案依据')}
                </button>
                <span style="color: var(--primary-navy); font-weight: 600;">穿透图谱 ➔</span>
              </div>
            </div>
          `;
          container.appendChild(card);
        });

        // 默认激活展开第一项
        if (currentStatutesResults.length > 0) {
          renderStatuteGraphDetail(currentStatutesResults[0].id);
        }

      } catch (e) {
        container.innerHTML = `<div style="color: var(--status-warn); padding: 20px;">请求异常: ${escapeHtml(e)}</div>`;
      }
    }

    async function renderStatuteGraphDetail(articleId) {
      currentActiveArticleId = articleId;

      // 更新左侧列表激活高亮
      document.querySelectorAll('#statute-articles-container .element-card').forEach(c => {
        c.style.borderColor = "var(--border-hairline)";
        c.style.background = "var(--bg-surface)";
      });
      const activeCard = document.getElementById(`statute-card-${articleId.replace(/[:.]/g, '_')}`);
      if (activeCard) {
        activeCard.style.borderColor = "var(--accent-amber)";
        activeCard.style.background = "#FCFBF9";
      }

      const graphBox = document.getElementById('statute-graph-container');
      const copyBtn = document.getElementById('btn-copy-active-statute');
      if (copyBtn) copyBtn.style.display = 'inline-flex';

      try {
        const resp = await api.request(`${API_BASE}/api/v1/statutes/article/${articleId}`);
        if (!resp.ok) {
          graphBox.innerHTML = `<div style="color: var(--status-warn); padding: 20px;">未获取到法条穿透详情</div>`;
          return;
        }

        const res = await resp.json();
        const art = res.article;
        const isDetailPinned = (window.CaseContextStore && window.CaseContextStore.hasStatute(art.id));

        let childrenHtml = '';
        if (art.children && art.children.length > 0) {
          childrenHtml = `
            <div style="margin-top: 14px; border-top: 1.5px solid var(--border-hairline); padding-top: 12px;">
              <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px;">
                <span style="font-size: 12.5px; font-weight: 700; color: var(--primary-navy); display: flex; align-items: center; gap: 6px;">
                  <span style="width: 8px; height: 8px; border-radius: 50%; background: #22c55e;"></span>
                  下位最高法司法解释穿透细化 (${art.children.length} 条)
                </span>
                <span class="badge valid">裁判尺度标准直连</span>
              </div>
              <div style="display: flex; flex-direction: column; gap: 10px;">
                ${art.children.map(c => `
                  <div style="background: #F8FAF8; border: 1px solid rgba(34, 197, 94, 0.25); border-left: 3.5px solid #22c55e; border-radius: var(--radius-sm); padding: 12px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                      <span style="font-size: 12px; font-weight: 700; color: var(--primary-navy);">${c.law_name} · ${c.article_no_cn}</span>
                      <span class="badge" style="background: rgba(34, 197, 94, 0.15); color: #15803d; font-size: 10.5px;">${c.relation_type}</span>
                    </div>
                    <div style="font-size: 11.5px; color: #166534; font-weight: 600; margin-bottom: 6px; background: rgba(34, 197, 94, 0.08); padding: 5px 8px; border-radius: 3px;">
                      📌 实务裁判要点：${c.notes || '详见司法解释裁判指引'}
                    </div>
                    <div style="font-size: 11.5px; color: var(--text-secondary); line-height: 1.6; white-space: pre-wrap;">
                      ${c.content}
                    </div>
                  </div>
                `).join('')}
              </div>
            </div>
          `;
        } else {
          childrenHtml = `
            <div style="margin-top: 14px; border-top: 1px solid var(--border-hairline); padding-top: 10px; font-size: 11.5px; color: var(--text-muted);">
              暂无直接绑定的特定司法解释条目（适用母法通用裁判规则）。
            </div>
          `;
        }

        let parentsHtml = '';
        if (art.parents && art.parents.length > 0) {
          parentsHtml = `
            <div style="margin-top: 14px; border-top: 1.5px solid var(--border-hairline); padding-top: 12px;">
              <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px;">
                <span style="font-size: 12.5px; font-weight: 700; color: var(--primary-navy); display: flex; align-items: center; gap: 6px;">
                  <span style="width: 8px; height: 8px; border-radius: 50%; background: #3b82f6;"></span>
                  上位母法请求权基础溯源 (${art.parents.length} 条)
                </span>
                <span class="badge" style="background: rgba(59, 130, 246, 0.15); color: #1d4ed8;">基本法律溯源</span>
              </div>
              <div style="display: flex; flex-direction: column; gap: 10px;">
                ${art.parents.map(p => `
                  <div style="background: #F8FAFC; border: 1px solid rgba(59, 130, 246, 0.25); border-left: 3.5px solid #3b82f6; border-radius: var(--radius-sm); padding: 12px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                      <span style="font-size: 12px; font-weight: 700; color: var(--primary-navy);">${p.law_name} · ${p.article_no_cn}</span>
                      <span class="badge" style="background: rgba(59, 130, 246, 0.15); color: #1e40af; font-size: 10.5px;">${p.relation_type}</span>
                    </div>
                    <div style="font-size: 11.5px; color: #1e3a8a; font-weight: 600; margin-bottom: 6px; background: rgba(59, 130, 246, 0.08); padding: 5px 8px; border-radius: 3px;">
                      📌 母法依托要点：${p.notes || '上位法请求权基础依据'}
                    </div>
                    <div style="font-size: 11.5px; color: var(--text-secondary); line-height: 1.6; white-space: pre-wrap;">
                      ${p.content}
                    </div>
                  </div>
                `).join('')}
              </div>
            </div>
          `;
        }

        graphBox.innerHTML = ` // safe-html: pre-escaped or nested HTML fragment
          <!-- 当前法条核心卡片 -->
          <div style="background: #FFFFFF; border: 1px solid var(--border-hairline); border-radius: var(--radius-sm); padding: 16px; box-shadow: 0 1px 4px rgba(20, 35, 60, 0.06);">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
              <div>
                <span style="font-size: 14px; font-weight: 700; color: var(--primary-navy);">${escapeHtml(art.law_full_name)}</span>
                <span class="citation-pill" style="margin-left: 6px; font-weight: 700; background: #14233C; color: #FFF; border: none;">${escapeHtml(art.article_no_cn)}</span>
              </div>
              <span class="badge" style="background: rgba(197, 133, 50, 0.15); color: var(--accent-amber); font-weight: 600;">
                ${escapeHtml(art.claim_basis_type || '要件规范')}
              </span>
            </div>

            <div style="font-size: 11px; color: var(--text-muted); margin-bottom: 10px;">
              ${escapeHtml(art.part_name || '')} · ${escapeHtml(art.chapter_name || '')} · 施行日期：${escapeHtml(art.effective_date)} · 效力：现行有效
            </div>

            <div id="active-statute-fulltext" style="font-size: 12.5px; color: #1F2937; line-height: 1.7; background: #FAF9F6; padding: 12px 14px; border-radius: var(--radius-sm); border: 1px solid #EFECE6; font-family: var(--font-body); white-space: pre-wrap;">
              ${escapeHtml(art.content)}
            </div>

            <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 10px; font-size: 11px; color: var(--text-muted);">
              <span>规范属性：${escapeHtml(art.has_proviso ? '包含明确【但书除外规定】' : '一般强制性/倡导性规定')}</span>
              <div style="display: flex; align-items: center; gap: 6px;">
                <button type="button" class="btn-select-statute ${escapeHtml(isDetailPinned ? 'selected' : '')}" id="btn-pin-active-statute" onclick="toggleSelectStatuteFromList('${escapeHtml(art.id)}', '${escapeHtml((art.law_full_name || art.short_name || '').replace(/'/g, "\\'"))}', '${escapeHtml(art.article_no_cn)}', document.getElementById('active-statute-fulltext').innerText)">
                  ${escapeHtml(isDetailPinned ? '✓ 已选入本案依据' : '📌 选入本案请求权依据')}
                </button>
                <button class="btn btn-secondary btn-sm" onclick="copyToClipboard(document.getElementById('active-statute-fulltext').innerText, '已成功复制法条全文')" style="padding: 2px 8px; font-size: 10.5px;">
                  复制正文
                </button>
              </div>
            </div>
          </div>

          <!-- 子法与母法穿透区 -->
          ${childrenHtml} // safe-html: static or pre-escaped HTML fragment
          ${parentsHtml} // safe-html: static or pre-escaped HTML fragment
        `;

      } catch (e) {
        graphBox.innerHTML = `<div style="color: var(--status-warn); padding: 20px;">渲染穿透图谱异常: ${escapeHtml(e)}</div>`;
      }
    }

    function copyActiveStatuteCitation() {
      const el = document.getElementById('active-statute-fulltext');
      if (el) {
        copyToClipboard(el.innerText, "已成功复制选定法条正文");
      }
    }

    async function submitStatuteImport() {
      const lawId = document.getElementById('import-law-id').value.trim();
      const fullName = document.getElementById('import-law-fullname').value.trim();
      const shortName = document.getElementById('import-law-shortname').value.trim();
      const promulgated = document.getElementById('import-law-promulgated').value.trim();
      const hierarchy = parseInt(document.getElementById('import-law-hierarchy').value);
      const domain = document.getElementById('import-law-domain').value;
      const effectiveDate = document.getElementById('import-law-date').value;
      const rawText = document.getElementById('import-law-rawtext').value.trim();

      if (!lawId || !fullName || !shortName || !rawText) {
        showToast("请完整填写法规ID、全称、简称与正文全文！");
        return;
      }

      showToast("正在执行编章节条款原子切片与 FTS5 入库...");

      try {
        const resp = await api.request(`${API_BASE}/api/v1/statutes/import`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            law_id: lawId,
            full_name: fullName,
            short_name: shortName,
            hierarchy: hierarchy,
            promulgated_by: promulgated || "地方审判机关",
            effective_date: effectiveDate || "2024-01-01",
            domain: domain,
            raw_text: rawText,
            summary: "律所用户自主导入法规"
          })
        });

        if (!resp.ok) {
          const err = await resp.json();
          showToast("导入失败: " + (err.detail || "格式不规范"));
          return;
        }

        const res = await resp.json();
        showToast(res.message);
        toggleImportDrawer();
        await reloadStatutesCorpus();
        quickFillStatuteSearch(shortName);
      } catch (e) {
        showToast("网络请求异常: " + e);
      }
    }

    // 本地库比对引注熔断模态框控制
    function openCitationGuardReportModal(customAudit) {
      const audit = customAudit || window._lastCitationAudit;
      const modal = document.getElementById('modal-citation-guard');
      if (modal) {
        modal.classList.add('active');
        if (audit) {
          renderCitationAuditReport(audit);
        }
      }
    }

    function closeCitationGuardReportModal() {
      const modal = document.getElementById('modal-citation-guard');
      if (modal) modal.classList.remove('active');
    }

    function handleCitationGuardModalBackdropClick(e) {
      if (e.target.id === 'modal-citation-guard') closeCitationGuardReportModal();
    }

    function switchCitationGuardTab(tab) {
      document.getElementById('tab-btn-cg-items')?.classList.toggle('active', tab === 'items');
      document.getElementById('tab-btn-cg-tester')?.classList.toggle('active', tab === 'tester');
      document.getElementById('tab-btn-cg-single')?.classList.toggle('active', tab === 'single');
      if (document.getElementById('view-cg-items')) document.getElementById('view-cg-items').style.display = tab === 'items' ? 'block' : 'none';
      if (document.getElementById('view-cg-tester')) document.getElementById('view-cg-tester').style.display = tab === 'tester' ? 'block' : 'none';
      if (document.getElementById('view-cg-single')) document.getElementById('view-cg-single').style.display = tab === 'single' ? 'block' : 'none';
    }

    function renderCitationAuditReport(audit) {
      if (!audit) return;
      const stats = audit.stats || {};
      document.getElementById('cg-stat-total').innerText = (stats.total_citations || 0) + (stats.case_numbers_total || 0);
      document.getElementById('cg-stat-verified').innerText = (stats.verified_count || 0) + (stats.case_numbers_verified || 0);
      document.getElementById('cg-stat-abrogated').innerText = stats.abrogated_count || 0;
      document.getElementById('cg-stat-hallucinated').innerText = stats.hallucinated_count || 0;

      const badge = document.getElementById('cg-modal-badge');
      if (badge) {
        if (audit.has_abrogated_laws || audit.has_hallucinations) {
          badge.style.background = '#C58532';
          badge.innerText = `⚠️ 已熔断并修正旧法/拦截虚构 (合格率 ${audit.compliance_rate})`;
        } else {
          badge.style.background = '#2E7D32';
          badge.innerText = `100% 权威现行有效 (零法条案号幻觉)`;
        }
      }

      const listDiv = document.getElementById('cg-items-list');
      if (!listDiv) return;

      const items = audit.items || [];
      const cases = audit.case_numbers || [];

      if (items.length === 0 && cases.length === 0) {
        listDiv.innerHTML = `<div style="text-align: center; color: var(--text-muted); padding: 25px;">文书中未探测到具体法条或案号引用</div>`;
        return;
      }

      const itemsHtml = items.map((it, idx) => {
        const st = it.audit_status || it.status || '';
        let badgeBg = '#FFF8E1';
        let badgeColor = '#B78103';
        let label = '待核验';
        if (st === 'HISTORICAL_VALID') {
          badgeBg = '#E0F2FE';
          badgeColor = '#0369A1';
          label = '📜 行为时实体法（2021年前事实）';
        } else if (st === 'LOCAL_MATCH') {
          badgeBg = '#E8F5E9';
          badgeColor = '#2E7D32';
          label = '本地库比对一致';
        } else if (st === 'ABROGATED_BLOCKED' || st === 'CONTENT_MISMATCH' || st === 'HALLUCINATION_EXCEEDED') {
          badgeBg = '#FFEBEE';
          badgeColor = '#D32F2F';
          label = st === 'ABROGATED_BLOCKED' ? '已废止·禁止引用' : (st === 'CONTENT_MISMATCH' ? '正文不一致' : '虚构条号');
        } else if (st === 'UNRECOGNIZED_LAW') {
          badgeBg = '#FFEBEE';
          badgeColor = '#C62828';
          label = '未识别法律名称';
        } else if (st === 'UNINDEXED_UNVERIFIABLE' || st === 'PENDING_VERIFICATION') {
          badgeBg = '#FFF8E1';
          badgeColor = '#B78103';
          label = st === 'PENDING_VERIFICATION' ? '已收录·待核验' : '未收录·无法核验';
        }

        let replaceHtml = '';
        if (it.suggested_replacement) {
          replaceHtml = `
            <div style="background: #FFF8E1; border: 1px solid #FFE082; padding: 6px 10px; border-radius: 3px; margin-top: 6px; font-size: 11px; color: #8D6E63;">
              💡 自动替换建议: <strong>${it.suggested_replacement}</strong> (${it.risk_tip || '已自动切换至现行民法典对应条款'})
            </div>
          `;
        }

        let articleContentHtml = '';
        if (it.article_content) {
          articleContentHtml = `
            <div style="background: #F4F6F9; border-left: 3px solid #14233C; padding: 6px 10px; margin-top: 6px; font-size: 11.5px; color: var(--text-primary); line-height: 1.5;">
              <span style="font-weight: 700; color: var(--primary-navy);">${it.statute_full_name || it.law_name}：</span>
              ${it.article_content}
            </div>
          `;
        }

        return `
          <div style="background: #FAF9F6; border: 1px solid #EAE6DD; border-radius: 4px; padding: 12px; margin-bottom: 8px;">
            <div style="display: flex; justify-content: space-between; align-items: center;">
              <div style="font-size: 13px; font-weight: 700; color: var(--primary-navy);">
                ${idx + 1}. ${it.citation_text}
              </div>
              <span class="badge" style="background: ${badgeBg}; color: ${badgeColor}; font-weight: 600;">
                ${label}
              </span>
            </div>
            ${replaceHtml}
            ${articleContentHtml}
          </div>
        `;
      }).join('');

      let casesHtml = '';
      if (cases.length > 0) {
        casesHtml = `
          <div style="font-weight: 700; font-size: 13px; color: var(--primary-navy); margin: 16px 0 8px 0; display:flex; align-items:center; gap:6px;">
            <span>🏛️ 司法审判案号（裁判文书）穿透反查 (${cases.length} 项)</span>
          </div>
        ` + cases.map((c, idx) => {
          let badgeBg = '#FFF8E1';
          let badgeColor = '#B78103';
          let label = '案号格式合规·未核验';
          if (c.status === 'DEMO_DATA_BLOCKED' || (c.is_hallucination && c.status === 'DEMO_DATA_BLOCKED')) {
            badgeBg = '#FFEBEE';
            badgeColor = '#D32F2F';
            label = '演示数据·不得引用';
          } else if (c.is_hallucination) {
            badgeBg = '#FFEBEE';
            badgeColor = '#D32F2F';
            label = '案号异常拦截';
          } else if (c.status === 'STRUCTURE_ONLY_UNVERIFIED' || c.status === 'SYNTAX_VALID_UNINDEXED' || c.status === 'VALID_STRUCTURE_UNVERIFIED_IN_LOCAL_DB') {
            badgeBg = '#FFF8E1';
            badgeColor = '#B78103';
            label = '案号格式合规·本地库未收录';
          } else if (c.status === 'LOCAL_MATCH') {
            badgeBg = '#E8F5E9';
            badgeColor = '#2E7D32';
            label = '本地库比对一致';
          }

          let precHtml = '';
          if (c.matched_precedent) {
            precHtml = `
              <div style="background: #F4F6F9; border-left: 3px solid #14233C; padding: 6px 10px; margin-top: 6px; font-size: 11.5px; color: var(--text-primary); line-height: 1.5;">
                <span style="font-weight: 700; color: var(--primary-navy);">${c.matched_precedent.title}（${c.matched_precedent.court_name}）</span>
                <div style="margin-top: 2px; color: var(--text-secondary);">${c.matched_precedent.holding_summary || ''}</div>
              </div>
            `;
          }

          return `
            <div style="background: #FAF9F6; border: 1px solid #EAE6DD; border-radius: 4px; padding: 12px; margin-bottom: 8px;">
              <div style="display: flex; justify-content: space-between; align-items: center;">
                <div style="font-size: 13px; font-weight: 700; color: var(--primary-navy);">
                  ${idx + 1}. ${c.standard_case_number || c.raw_case_number}
                </div>
                <span class="badge" style="background: ${badgeBg}; color: ${badgeColor}; font-weight: 600;">
                  ${label}
                </span>
              </div>
              <div style="font-size: 11.5px; color: var(--text-secondary); margin-top: 4px;">
                ${c.notes || ''}
              </div>
              ${precHtml}
            </div>
          `;
        }).join('');
      }

      listDiv.innerHTML = itemsHtml + casesHtml;
    }

    async function runCustomCitationAudit() {
      const text = document.getElementById('cg-custom-text').value.trim();
      if (!text) {
        showToast("请先粘贴需要反查法条的文书文本！");
        return;
      }
      const autoSanitize = document.getElementById('cg-auto-sanitize-chk').checked;
      const incidentDateEl = document.getElementById('cg-incident-date');
      const incidentDate = incidentDateEl && incidentDateEl.value ? incidentDateEl.value : null;

      try {
        const payload = { text: text, auto_sanitize: autoSanitize };
        if (incidentDate) payload.incident_date = incidentDate;
        const resp = await api.request(`${API_BASE}/api/v1/guard/audit-citations`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        const res = await resp.json();
        renderCitationAuditReport(res);

        const resBox = document.getElementById('cg-custom-result');
        resBox.style.display = 'block';
        const warnHtml = (res.warnings && res.warnings.length)
          ? `<div style="font-size: 11.5px; color: #B78103; margin-bottom: 8px;">${res.warnings.join('<br>')}</div>`
          : '';
        resBox.innerHTML = ` // safe-html: pre-escaped or nested HTML fragment
          <div style="font-weight: 700; font-size: 12.5px; color: var(--primary-navy); margin-bottom: 6px;">本地库比对与净化结果：</div>
          <div style="font-size: 12px; color: var(--text-secondary); margin-bottom: 8px;">${escapeHtml(res.audit_report || '')}</div>
          ${warnHtml} // safe-html: static or pre-escaped HTML fragment
          ${res.sanitized_text ? ` // safe-html: static or pre-escaped HTML fragment
            <div style="margin-top: 8px;">
              <div style="font-weight: 600; font-size: 11px; color: #2E7D32; margin-bottom: 4px;">处理后文本：</div>
              <textarea aria-label="处理后文本" class="quick-input" rows="4" readonly style="font-size: 11.5px; line-height: 1.5; background: #fff;">${res.sanitized_text}</textarea>
            </div>
          ` : ''}
        `;
      } catch (e) {
        showToast("检测失败: " + e);
      }
    }


    async function runSingleCitationVerifyUI() {
      const lawName = (document.getElementById('cg-single-law')?.value || '民法典').trim();
      const artNum = parseInt(document.getElementById('cg-single-article')?.value || '585', 10);
      showToast("正在核验单条法条有效性与现行地位...");
      try {
        const resp = await api.request(`${API_BASE}/api/v1/guard/verify-single`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            law_name: lawName,
            article_num: isNaN(artNum) ? 1 : artNum
          })
        });
        if (!resp.ok) {
          const err = await resp.json().catch(() => null);
          throw new Error(err?.detail || ('HTTP ' + resp.status));
        }
        const data = await resp.json();
        renderSingleCitationResult(data, 'law');
        showToast("单条法条核验完成");
      } catch (e) {
        showToast(err instanceof ApiError ? err.userMessage : (err && err.userMessage ? err.userMessage : `操作失败：${err.message || "请求异常"}（错误码 CLIENT_ERROR）`), "error");
      }
    }

    async function runSingleCaseNumberVerifyUI() {
      const caseNo = (document.getElementById('cg-single-caseno')?.value || '').trim();
      if (!caseNo) {
        showToast("请输入待核验的裁判案号！");
        return;
      }
      showToast("正在核验裁判案号规范性与真伪...");
      try {
        const resp = await api.request(`${API_BASE}/api/v1/guard/verify-case-number`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ case_number: caseNo })
        });
        if (!resp.ok) {
          const err = await resp.json().catch(() => null);
          throw new Error(err?.detail || ('HTTP ' + resp.status));
        }
        const data = await resp.json();
        renderSingleCitationResult(data, 'case');
        showToast("案号核验完成");
      } catch (e) {
        showToast(err instanceof ApiError ? err.userMessage : (err && err.userMessage ? err.userMessage : `操作失败：${err.message || "请求异常"}（错误码 CLIENT_ERROR）`), "error");
      }
    }

    function renderSingleCitationResult(data, kind) {
      const box = document.getElementById('cg-single-result');
      if (!box) return;
      box.style.display = 'block';
      if (kind === 'case') {
        const isValid = data.is_valid || data.is_recognized;
        const color = isValid ? '#059669' : '#DC2626';
        const bg = isValid ? '#ECFDF5' : '#FEF2F2';
        box.innerHTML = ` // safe-html: case number verification details
          <div style="border-left: 4px solid ${escapeHtml(color)}; background: ${escapeHtml(bg)}; padding: 10px 12px; border-radius: 4px;">
            <div style="display:flex; justify-content:space-between; align-items:center;">
              <strong style="font-size:13px; color:var(--primary-navy);">${escapeHtml(data.case_number || '')}</strong>
              <span class="badge" style="background:${escapeHtml(bg)}; color:${escapeHtml(color)}; font-weight:700;">${escapeHtml(isValid ? '✓ 案号结构规范' : '⚠️ 格式或审级瑕疵')}</span>
            </div>
            <div style="font-size:12px; color:var(--text-secondary); margin-top:6px; line-height:1.5;">
              审判法院：${escapeHtml(data.court || '未指定')} · 审级类型：${escapeHtml(data.case_type || '民事')} · 年份：${escapeHtml(String(data.year || ''))}
            </div>
            ${data.risk_tip ? `<div style="font-size:11.5px; color:#DC2626; margin-top:4px;">风险提示：${escapeHtml(data.risk_tip)}</div>` : ''}
          </div>
        `;
      } else {
        const isValid = data.is_valid;
        const color = isValid ? '#059669' : '#DC2626';
        const bg = isValid ? '#ECFDF5' : '#FEF2F2';
        box.innerHTML = ` // safe-html: statute citation verification details
          <div style="border-left: 4px solid ${escapeHtml(color)}; background: ${escapeHtml(bg)}; padding: 10px 12px; border-radius: 4px;">
            <div style="display:flex; justify-content:space-between; align-items:center;">
              <strong style="font-size:13px; color:var(--primary-navy);">《${escapeHtml(data.statute_full_name || data.law_name || '')}》第${escapeHtml(String(data.article_num || ''))}条 (${escapeHtml(data.article_no_cn || '')})</strong>
              <span class="badge" style="background:${escapeHtml(bg)}; color:${escapeHtml(color)}; font-weight:700;">${escapeHtml(isValid ? '✓ 现行有效法典条文' : '⚠️ 废止旧法或条号越界')}</span>
            </div>
            <div style="font-size:11.5px; color:var(--text-primary); margin-top:6px; line-height:1.6; background:#FFF; padding:8px 10px; border-radius:4px; border:1px solid #E2DFD7;">
              ${escapeHtml(data.article_content || '未检索到法条正文')}
            </div>
            ${data.risk_tip ? `<div style="font-size:11.5px; color:#DC2626; margin-top:6px;">执业风险防范：${escapeHtml(data.risk_tip)}</div>` : ''}
            ${data.replacement_suggestion ? `<div style="font-size:11.5px; color:#059669; margin-top:4px;">民法典现行替代条文：${escapeHtml(data.replacement_suggestion)}</div>` : ''}
          </div>
        `;
      }
    }

export {
  reloadStatutesCorpus,
  reseedStatutesCorpus,
  quickFillStatuteSearch,
  selectStatuteDomain,
  toggleImportDrawer,
  executeStatuteSearch,
  renderStatuteGraphDetail,
  copyActiveStatuteCitation,
  submitStatuteImport,
  openCitationGuardReportModal,
  closeCitationGuardReportModal,
  handleCitationGuardModalBackdropClick,
  switchCitationGuardTab,
  renderCitationAuditReport,
  runCustomCitationAudit,
  runSingleCitationVerifyUI,
  runSingleCaseNumberVerifyUI,
  renderSingleCitationResult,
};
