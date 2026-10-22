/**
 * LawFlow Module: settings.js
 */
import { api, ApiError, API_BASE, withDownloadToken } from '../api.js';
import { showToast } from '../ui/toast.js';



    // =========================================================================
    // 6. 模型引擎配置与分发热切换逻辑
    // =========================================================================
    let currentEngineSettings = null;
    let selectedMode = 'cloud';
    let providerPresets = {};

    async function fetchEngineHealth() {
      try {
        const resp = await api.request(`${API_BASE}/api/v1/settings/llm`);
        if (!resp.ok) return;
        const d = await resp.json();
        currentEngineSettings = d.settings;
        providerPresets = d.presets || {};
        updateEngineStatusUI(d.health, d.settings);
      } catch (e) {
        console.warn("探测引擎健康状态失败:", e);
      }
    }

    function updateEngineStatusUI(health, settings) {
      const statusText = document.getElementById('sidebar-status-text');
      const pulseDot = document.getElementById('sidebar-pulse-dot');
      const popoverAi = document.getElementById('popover-ai-status');
      const headerTag = document.getElementById('header-engine-mode-tag');
      const piiTag = document.getElementById('header-pii-tag');

      if (piiTag && settings) {
        if (settings.pii_shield_enabled !== false) {
          piiTag.style.display = 'inline-flex';
        } else {
          piiTag.style.display = 'none';
        }
      }

      if (!health) return;

      const llmMode = health.llm_mode || health.mode;
      if ((llmMode === 'cloud' || health.mode === 'cloud') && health.status === 'healthy' && health.model_ready !== false) {
        statusText.innerText = `云端引擎在线 (${settings.model || 'DeepSeek'})`;
        popoverAi.innerText = `${settings.model} (延迟 ${health.latency_ms || 0}ms)`;
        pulseDot.style.backgroundColor = '#22c55e';
        pulseDot.style.boxShadow = '0 0 6px rgba(34, 197, 94, 0.8)';
        if (headerTag) headerTag.innerText = `云端: ${settings.model || 'DeepSeek'}`;
      } else if ((llmMode === 'ollama' || health.mode === 'ollama') && health.status === 'healthy') {
        statusText.innerText = `本地引擎在线 (${health.target_model || 'Gemma4'})`;
        popoverAi.innerText = `${health.target_model} 就绪`;
        pulseDot.style.backgroundColor = '#22c55e';
        pulseDot.style.boxShadow = '0 0 6px rgba(34, 197, 94, 0.8)';
        if (headerTag) headerTag.innerText = `本地: ${health.target_model || 'Gemma4'}`;
      } else {
        statusText.innerText = `规则模式（未连接模型）`;
        popoverAi.innerText = `规范实务模板引擎 (全算法兜底)`;
        pulseDot.style.backgroundColor = '#C58532';
        pulseDot.style.boxShadow = '0 0 6px rgba(197, 133, 50, 0.8)';
        if (headerTag) headerTag.innerText = `规则模式（未连接模型）`;
      }
    }

    async function openEngineSettingsModal() {
      const modal = document.getElementById('modal-engine-settings');
      modal.classList.add('active');
      hideTestFeedback();

      try {
        const resp = await api.request(`${API_BASE}/api/v1/settings/llm`);
        const d = await resp.json();
        currentEngineSettings = d.settings;
        providerPresets = d.presets || {};

        let mode = d.settings.provider || 'cloud';
        if (mode === 'auto') {
          mode = d.settings.has_api_key ? 'cloud' : 'ollama';
        }
        selectEngineMode(mode);

        const presetSelect = document.getElementById('cfg-cloud-preset');
        presetSelect.value = d.settings.cloud_preset || 'deepseek';

        document.getElementById('cfg-base-url').value = d.settings.base_url || 'https://api.deepseek.com/v1';
        document.getElementById('cfg-model').value = d.settings.model || 'deepseek-chat';
        document.getElementById('cfg-ollama-url').value = d.settings.ollama_base_url || 'http://127.0.0.1:11434';
        
        const piiShieldCheck = document.getElementById('cfg-pii-shield');
        if (piiShieldCheck) {
          piiShieldCheck.checked = d.settings.pii_shield_enabled !== false;
        }

        const apiKeyInput = document.getElementById('cfg-api-key');
        apiKeyInput.value = '';
        const keyStatus = document.getElementById('cfg-key-status');
        if (d.settings.has_api_key) {
          keyStatus.innerText = `已预置: ${d.settings.api_key_masked}`;
        } else {
          keyStatus.innerText = '未配置';
        }
      } catch (e) {
        showToast("读取设置失败: " + e);
      }
    }

    function closeEngineSettingsModal() {
      const modal = document.getElementById('modal-engine-settings');
      modal.classList.remove('active');
    }

    function handleModalBackdropClick(e) {
      if (e.target.id === 'modal-engine-settings') {
        closeEngineSettingsModal();
      }
    }

    function selectEngineMode(mode) {
      selectedMode = mode;
      document.querySelectorAll('#modal-engine-settings .segmented-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.cfg-pane').forEach(p => p.classList.remove('active'));

      if (mode === 'cloud') {
        document.getElementById('btn-mode-cloud').classList.add('active');
        document.getElementById('pane-cloud').classList.add('active');
      } else if (mode === 'ollama') {
        document.getElementById('btn-mode-ollama').classList.add('active');
        document.getElementById('pane-ollama').classList.add('active');
      } else if (mode === 'pii') {
        document.getElementById('btn-mode-pii').classList.add('active');
        document.getElementById('pane-pii').classList.add('active');
      } else {
        document.getElementById('btn-mode-rule').classList.add('active');
        document.getElementById('pane-rule').classList.add('active');
      }
      hideTestFeedback();
    }

    function onCloudPresetChange() {
      const val = document.getElementById('cfg-cloud-preset').value;
      if (val in providerPresets) {
        document.getElementById('cfg-base-url').value = providerPresets[val].base_url;
        document.getElementById('cfg-model').value = providerPresets[val].default_model;
      }
    }

    function toggleApiKeyVisibility() {
      const input = document.getElementById('cfg-api-key');
      input.type = input.type === 'password' ? 'text' : 'password';
    }

    function showTestFeedback(isSuccess, text) {
      const fb = document.getElementById('cfg-test-feedback');
      const textEl = document.getElementById('cfg-test-text');
      fb.className = 'cfg-test-feedback ' + (isSuccess ? 'success' : 'error');
      textEl.innerText = text;
      fb.style.display = 'flex';
    }

    function hideTestFeedback() {
      const fb = document.getElementById('cfg-test-feedback');
      fb.style.display = 'none';
    }

    async function testEngineConnection() {
      const btn = document.getElementById('btn-test-connection');
      const origHtml = btn.innerHTML;
      btn.innerHTML = `<span class="spinner-dark"></span> 正在测速...`;
      btn.disabled = true;
      hideTestFeedback();

      const payload = {
        provider: selectedMode,
        cloud_preset: document.getElementById('cfg-cloud-preset').value,
        api_key: document.getElementById('cfg-api-key').value,
        base_url: document.getElementById('cfg-base-url').value,
        model: document.getElementById('cfg-model').value,
        ollama_base_url: document.getElementById('cfg-ollama-url').value
      };

      try {
        const resp = await api.request(`${API_BASE}/api/v1/settings/test-llm`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        const res = await resp.json();
        btn.innerHTML = origHtml;
        btn.disabled = false;

        if (res.success) {
          showTestFeedback(true, res.message || `测试成功！延迟 ${res.latency_ms}ms`);
        } else {
          showTestFeedback(false, res.error || "连接测试失败，请检查密钥或接口地址");
        }
      } catch (e) {
        btn.innerHTML = origHtml;
        btn.disabled = false;
        showTestFeedback(false, "请求测试接口异常: " + e);
      }
    }

    async function saveEngineSettings() {
      const btn = document.getElementById('btn-save-engine');
      const origText = btn.innerText;
      btn.innerText = "保存中...";
      btn.disabled = true;

      let cloudConsent = !!(currentEngineSettings && currentEngineSettings.cloud_consent);
      if (selectedMode === 'cloud' && !cloudConsent) {
        const preset = document.getElementById('cfg-cloud-preset').value || 'cloud';
        const presetName = (providerPresets[preset] && providerPresets[preset].name) || preset;
        const ok = window.confirm(
          `案情文本将在脱敏后发送至第三方服务：${presetName}\n\n请确认已知悉并同意后再继续。`
        );
        if (!ok) {
          btn.innerText = origText;
          btn.disabled = false;
          return;
        }
        cloudConsent = true;
      }

      const payload = {
        provider: selectedMode,
        cloud_preset: document.getElementById('cfg-cloud-preset').value,
        api_key: document.getElementById('cfg-api-key').value,
        base_url: document.getElementById('cfg-base-url').value,
        model: document.getElementById('cfg-model').value,
        ollama_base_url: document.getElementById('cfg-ollama-url').value,
        pii_shield_enabled: document.getElementById('cfg-pii-shield') ? document.getElementById('cfg-pii-shield').checked : true,
        cloud_consent: cloudConsent
      };

      try {
        const resp = await api.request(`${API_BASE}/api/v1/settings/llm`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        const res = await resp.json();
        btn.innerText = origText;
        btn.disabled = false;

        if (res.status === 'success') {
          showToast("模型引擎配置已更新并即时生效");
          currentEngineSettings = res.settings;
          updateEngineStatusUI(res.health, res.settings);
          closeEngineSettingsModal();
        } else {
          showToast("保存失败: " + (res.message || "未知错误"));
        }
      } catch (e) {
        btn.innerText = origText;
        btn.disabled = false;
        showToast("保存设置异常: " + e);
      }
    }


    // =========================================================================
    // 阶段六：律所级利益冲突穿透排查与本地库比对引注熔断 (Phase 6 Compliance & Guard)
    // =========================================================================
    let _currentConflictResult = null;
    let _lastCitationAudit = null;

    function openConflictCheckModal() {
      const modal = document.getElementById('modal-conflict-check');
      if (modal) {
        modal.classList.add('active');
        syncConflictFormFromGlobalCase();
        loadConflictRegistry();
      }
    }

    function closeConflictCheckModal() {
      const modal = document.getElementById('modal-conflict-check');
      if (modal) modal.classList.remove('active');
    }

    function handleConflictModalBackdropClick(e) {
      if (e.target.id === 'modal-conflict-check') closeConflictCheckModal();
    }

    function switchConflictModalTab(tab) {
      const isCheck = tab === 'check';
      document.getElementById('tab-btn-conflict-check').classList.toggle('active', isCheck);
      document.getElementById('tab-btn-conflict-registry').classList.toggle('active', !isCheck);
      document.getElementById('view-conflict-check').style.display = isCheck ? 'block' : 'none';
      document.getElementById('view-conflict-registry').style.display = isCheck ? 'none' : 'block';
      if (!isCheck) loadConflictRegistry();
    }

    function syncConflictFormFromGlobalCase() {
      const ctx = window._globalCaseContext || {};
      if (ctx.plaintiff) {
        document.getElementById('chk-client-name').value = ctx.plaintiff.name || '';
        document.getElementById('chk-client-id').value = ctx.plaintiff.id_card_or_uscc || '';
      }
      if (ctx.defendant) {
        document.getElementById('chk-opposing-name').value = ctx.defendant.name || '';
        document.getElementById('chk-opposing-id').value = ctx.defendant.id_card_or_uscc || '';
      }
      if (ctx.cause_of_action) {
        document.getElementById('chk-case-subject').value = ctx.cause_of_action;
      }
    }

    function quickCheckTabLitigationConflict() {
      openConflictCheckModal();
      document.getElementById('chk-client-name').value = document.getElementById('pkg-p-name').value || '';
      document.getElementById('chk-client-id').value = document.getElementById('pkg-p-id').value || '';
      document.getElementById('chk-opposing-name').value = document.getElementById('pkg-d-name').value || '';
      document.getElementById('chk-opposing-id').value = document.getElementById('pkg-d-id').value || '';
      document.getElementById('chk-case-subject').value = document.getElementById('pkg-cause').value || '';
      runConflictCheckSubmit();
    }

    async function runConflictCheckSubmit() {
      const clientName = document.getElementById('chk-client-name').value.trim();
      const opposingName = document.getElementById('chk-opposing-name').value.trim();
      if (!clientName || !opposingName) {
        showToast("请输入委托人名称与相对方名称！");
        return;
      }

      const btn = document.getElementById('btn-run-conflict-check');
      const origText = btn.innerHTML;
      btn.innerHTML = `<span class="spinner"></span> 穿透排查中...`;
      btn.disabled = true;

      const rawEntities = document.getElementById('chk-related-entities').value.trim();
      const related = rawEntities ? rawEntities.split(/[,，、]/).map(s => s.trim()).filter(Boolean) : [];

      const payload = {
        client_name: clientName,
        opposing_party: opposingName,
        client_id_or_code: document.getElementById('chk-client-id').value.trim(),
        opposing_id_or_code: document.getElementById('chk-opposing-id').value.trim(),
        related_entities: related,
        case_subject: document.getElementById('chk-case-subject').value.trim()
      };

      try {
        const resp = await api.request(`${API_BASE}/api/v1/conflict/check`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        const res = await resp.json();
        _currentConflictResult = res;
        renderConflictResult(res);

        // 更新全局状态徽章
        const globalBadge = document.getElementById('gcase-conflict-btn-text');
        if (globalBadge) {
          if (res.conflict_level === 'UNABLE_TO_CHECK' || res.verdict === 'UNABLE_TO_CHECK') {
            globalBadge.innerText = '未完成排查';
            globalBadge.style.color = '#D32F2F';
          } else if (res.conflict_level === 'PROHIBITED' || res.conflict_level === 'CRITICAL_BLOCKED') {
            globalBadge.innerText = '🚫 不得代理';
          } else if (res.conflict_level === 'WAIVABLE_WITH_CONSENT' || res.conflict_level === 'HIGH_WARNING') {
            globalBadge.innerText = '⚠️ 须告知并经同意';
          } else if (res.conflict_level === 'CAUTION' || res.conflict_level === 'CAUTION_REQUIRED') {
            globalBadge.innerText = '🔍 需人工判断';
          } else {
            globalBadge.innerText = '🛡️ 未发现冲突';
          }
        }
      } catch (err) {
        showToast("排查接口调用失败: " + err);
      } finally {
        btn.innerHTML = origText;
        btn.disabled = false;
      }
    }

    function renderConflictResult(res) {
      const box = document.getElementById('conflict-result-box');
      box.style.display = 'block';

      let statusColor = '#2E7D32';
      let statusBg = '#F1F8E9';
      let statusBorder = '#C8E6C9';
      let icon = '✅';
      let unableLabel = '';

      const conflictLvl = res.conflict_level || res.verdict;
      if (conflictLvl === 'UNABLE_TO_CHECK') {
        statusColor = '#D32F2F';
        statusBg = '#FFEBEE';
        statusBorder = '#FFCDD2';
        icon = '⛔';
        unableLabel = '未完成排查';
        res.status_label = res.status_label || res.message || '未完成排查';
      } else if (conflictLvl === 'PROHIBITED' || conflictLvl === 'CRITICAL_BLOCKED') {
        statusColor = '#D32F2F';
        statusBg = '#FFEBEE';
        statusBorder = '#FFCDD2';
        icon = '🚫';
      } else if (conflictLvl === 'WAIVABLE_WITH_CONSENT' || conflictLvl === 'HIGH_WARNING') {
        statusColor = '#E65100';
        statusBg = '#FFF3E0';
        statusBorder = '#FFE0B2';
        icon = '⚠️';
      } else if (conflictLvl === 'CAUTION' || conflictLvl === 'CAUTION_REQUIRED') {
        statusColor = '#F57F17';
        statusBg = '#FFFDE7';
        statusBorder = '#FFF9C4';
        icon = '🔔';
      }

      let rulesHtml = (res.triggered_rules || []).map(r => `<span class="badge" style="background:#fff; color:${statusColor}; border:1px solid ${statusBorder}; font-size:11px;">${r}</span>`).join(' ');

      let conflictsHtml = '';
      if (res.conflicts && res.conflicts.length > 0) {
        conflictsHtml = `
          <div style="margin-top: 12px;">
            <div style="font-weight: 700; font-size: 12px; color: ${statusColor}; margin-bottom: 6px;">穿透命中风险底档案件 (${res.conflicts.length} 起)：</div>
            <div style="display: flex; flex-direction: column; gap: 8px;">
              ${res.conflicts.map(c => `
                <div style="background: #fff; border: 1px solid ${statusBorder}; border-radius: 4px; padding: 10px; font-size: 11.5px;">
                  <div style="display: flex; justify-content: space-between; margin-bottom: 4px;">
                    <strong>[${c.type}] ${c.case_name}</strong>
                    <span style="color: var(--text-muted); font-family: var(--font-mono);">${c.case_no}</span>
                  </div>
                  <div style="color: var(--text-secondary); margin-bottom: 4px;">
                    底档委托人: <strong>${c.registered_client}</strong> · 底档相对方: <strong>${c.registered_opposing}</strong> · 主办律师: ${c.handling_lawyer || '律所律师'}
                  </div>
                  <div style="color: ${statusColor}; font-weight: 500;">
                    ${c.description}
                  </div>
                </div>
              `).join('')}
            </div>
          </div>
        `;
      }

      let certHtml = '';
      if (res.clearance_certificate) {
        const cert = res.clearance_certificate;
        certHtml = `
          <div style="margin-top: 14px; background: #FAF9F6; border: 1px solid #C8E6C9; border-radius: 4px; padding: 12px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
              <span style="font-weight: 700; color: #2E7D32; font-size: 12px; display: flex; align-items: center; gap: 6px;">
                <span>🛡️</span> 律所利益冲突排查验讫数字证书 (Clearance Certificate)
              </span>
              <span style="font-size: 10.5px; color: var(--text-muted); font-family: var(--font-mono);">${cert.certificate_no}</span>
            </div>
            <div style="font-size: 11px; color: var(--text-secondary); line-height: 1.6;">
              验讫结论: <strong>${cert.verification_status}</strong><br/>
              SHA-256 数字指纹: <code style="font-family: var(--font-mono); color: #14233C; font-size: 10.5px; background: #EFEFEF; padding: 2px 4px; border-radius: 2px;">${cert.sha256_fingerprint}</code><br/>
              排查时间: ${cert.timestamp} · 核验人员: ${cert.handling_lawyer} · 防伪效力: 诉讼归档留底有效
            </div>
          </div>
        `;
      }

      box.innerHTML = ` // safe-html: pre-escaped or nested HTML fragment
        <div style="background: ${escapeHtml(statusBg)}; border: 1px solid ${escapeHtml(statusBorder)}; border-radius: var(--radius-sm); padding: 14px;">
          <div style="display: flex; align-items: flex-start; justify-content: space-between;">
            <div>
              <div style="font-size: 14px; font-weight: 700; color: ${escapeHtml(statusColor)}; display: flex; align-items: center; gap: 8px;">
                <span>${escapeHtml(icon)}</span>
                <span>${escapeHtml(unableLabel || res.summary || res.message || '')}</span>
              </div>
              <div style="font-size: 12px; color: var(--text-secondary); margin-top: 4px;">
                ${escapeHtml(res.recommendation)}
              </div>
            </div>
            <div style="display: flex; gap: 4px;">
              ${rulesHtml} // safe-html: static or pre-escaped HTML fragment
            </div>
          </div>
          ${conflictsHtml} // safe-html: static or pre-escaped HTML fragment
          ${certHtml} // safe-html: static or pre-escaped HTML fragment
        </div>
      `;
    }

    async function loadConflictRegistry() {
      try {
        const resp = await api.request(`${API_BASE}/api/v1/conflict/registry`);
        const d = await resp.json();
        const tbody = document.getElementById('conflict-registry-tbody');
        const badge = document.getElementById('conflict-registry-count-badge');
        if (badge) badge.innerText = d.count || 0;
        if (!tbody) return;

        if (!d.registry || d.registry.length === 0) {
          tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: var(--text-muted); padding: 15px;">暂无底档案件</td></tr>`;
          return;
        }

        tbody.innerHTML = d.registry.map(item => `
          <tr style="border-bottom: 1px solid var(--border-hairline);">
            <td style="padding: 6px 10px;">
              <span class="badge" style="background:${escapeHtml(item.status === 'ACTIVE' ? '#E8F5E9; color:#2E7D32;' : (item.status === 'RETAINER' ? '#FFF3E0; color:#E65100;' : '#ECEFF1; color:#546E7A;'))} font-size: 10px;">
                ${escapeHtml(item.status === 'ACTIVE' ? '在办' : (item.status === 'RETAINER' ? '常年顾问' : '已结案'))}
              </span>
            </td>
            <td style="padding: 6px 10px; font-family: var(--font-mono); color: var(--text-secondary);">${escapeHtml(item.case_no)}</td>
            <td style="padding: 6px 10px; font-weight: 600; color: var(--primary-navy);">${escapeHtml(item.case_name)}</td>
            <td style="padding: 6px 10px;">${escapeHtml(item.client_name)}</td>
            <td style="padding: 6px 10px;">${escapeHtml(item.opposing_party || '-')}</td>
            <td style="padding: 6px 10px; color: var(--text-muted);">${escapeHtml(item.handling_lawyer || '主办律师')}</td>
          </tr>
        `).join('');
      } catch (e) {
        console.error("加载底档失败", e);
      }
    }

    function toggleRegisterCaseDrawer() {
      const drawer = document.getElementById('drawer-register-case');
      if (drawer) drawer.style.display = drawer.style.display === 'none' ? 'block' : 'none';
    }

    async function submitRegisterConflictCase() {
      const caseName = document.getElementById('reg-case-name').value.trim();
      const caseNo = document.getElementById('reg-case-no').value.trim();
      const clientName = document.getElementById('reg-client-name').value.trim();
      const opposingParty = document.getElementById('reg-opposing-party').value.trim();
      const status = document.getElementById('reg-case-status').value;
      const lawyer = document.getElementById('reg-lawyer').value.trim() || '主办律师';

      if (!caseName || !clientName) {
        showToast("请输入案件名称和委托人！");
        return;
      }

      try {
        const resp = await api.request(`${API_BASE}/api/v1/conflict/register-case`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            case_name: caseName,
            case_no: caseNo,
            client_name: clientName,
            opposing_party: opposingParty,
            status: status,
            handling_lawyer: lawyer
          })
        });
        const res = await resp.json();
        showToast("已成功录入底档库！");
        toggleRegisterCaseDrawer();
        loadConflictRegistry();
      } catch (e) {
        showToast("录入失败: " + e);
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
        if (st === 'LOCAL_MATCH') {
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

    async function runPiiScanUI() {
      const text = document.getElementById('pii-scan-input')?.value.trim();
      if (!text) {
        showToast("请输入待扫描脱敏的文本！");
        return;
      }
      showToast("正在执行本地 PII 敏感信息扫描...");
      try {
        const resp = await api.request(`${API_BASE}/api/v1/settings/pii/scan`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text: text })
        });
        if (!resp.ok) {
          const err = await resp.json().catch(() => null);
          throw new Error(err?.detail || ('HTTP ' + resp.status));
        }
        const data = await resp.json();
        renderPiiScanResult(data);
        showToast("PII 扫描脱敏完成");
      } catch (e) {
        showToast(err instanceof ApiError ? err.userMessage : (err && err.userMessage ? err.userMessage : `操作失败：${err.message || "请求异常"}（错误码 CLIENT_ERROR）`), "error");
      }
    }

    function renderPiiScanResult(data) {
      const box = document.getElementById('pii-scan-result');
      if (!box) return;
      box.style.display = 'block';
      const entities = data.detected_entities || [];
      const badgeList = entities.map(e => `
        <span class="badge" style="background:#FEF3C7; color:#B45309; font-size:11px; margin-right:4px; margin-bottom:4px; display:inline-block;">
          ${escapeHtml(e.entity_type || e.type || 'PII')}: ${escapeHtml(e.text || e.raw || '')}
        </span>
      `).join('');
      box.innerHTML = ` // safe-html: pii scan results, escaped
        <div style="font-weight: 700; font-size: 12px; color: var(--primary-navy); margin-bottom: 6px;">
          识别到的敏感实体 (共 ${escapeHtml(String(entities.length))} 处)：
        </div>
        <div style="margin-bottom: 10px;">${badgeList || '<span style="color:var(--text-muted); font-size:11px;">未检测到高风险个人隐私实体</span>'}</div>
        <div style="font-weight: 700; font-size: 12px; color: var(--primary-navy); margin-bottom: 4px;">
          脱敏后文本 (安全占位符已替换)：
        </div>
        <div style="background:#FFF; border:1px solid #E2DFD7; border-radius:4px; padding:8px 10px; font-size:11.5px; font-family:var(--font-mono); white-space:pre-wrap; max-height:140px; overflow-y:auto; line-height:1.5;">${escapeHtml(data.masked_text || '')}</div>
      `;
    }


