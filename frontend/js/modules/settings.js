/**

 * LawFlow Module: settings.js

 */

import { api, ApiError, API_BASE, withDownloadToken, escapeHtml } from '../api.js';

import { showToast } from '../ui/toast.js';







    // =========================================================================

    // 6. 模型引擎配置与分发热切换逻辑

    // =========================================================================

    let currentEngineSettings = null;

    let selectedMode = 'cloud';

    let providerPresets = {};



    async function fetchEngineHealth() {
      installOutboundGuards();
      installMatterFeeGuard();

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

        const piiLabel = document.getElementById('header-pii-label');

        if (piiTag) {

          const shieldOn = !settings || settings.pii_shield_enabled !== false;
          piiTag.style.display = 'inline-flex';
          piiTag.title = shieldOn
            ? '案情、证据摘录、代理意见会发给所填服务商。已识别的身份证等号码会在发送前替换，不能写成已经脱敏。能识别的未成年人信息和病历默认不外发；识别不了的不会当成已经拦住。'
            : '案情、证据摘录、代理意见会发给所填服务商。脱敏开关已关闭，身份证等号码也会发送。能识别的未成年人信息和病历默认不外发；识别不了的不会当成已经拦住。';

          piiTag.style.background = '#FEF3C7';

          piiTag.style.color = '#B45309';

          piiTag.style.borderColor = '#FCD34D';

        }

        if (piiLabel) piiLabel.innerText = '云端已开启，案情会外发';

      } else if ((llmMode === 'ollama' || health.mode === 'ollama') && health.status === 'healthy') {

        statusText.innerText = `本地引擎在线 (${health.target_model || 'Gemma4'})`;

        popoverAi.innerText = `${health.target_model} 就绪`;

        pulseDot.style.backgroundColor = '#22c55e';

        pulseDot.style.boxShadow = '0 0 6px rgba(34, 197, 94, 0.8)';

        if (headerTag) headerTag.innerText = `本地: ${health.target_model || 'Gemma4'}`;

        const piiLabel = document.getElementById('header-pii-label');

        if (piiTag) {

          piiTag.title = '当前走本地模型，案情不出本机。';

          piiTag.style.background = '#ECFDF5';

          piiTag.style.color = '#059669';

          piiTag.style.borderColor = '#A7F3D0';

        }

        if (piiLabel) piiLabel.innerText = '本地模型，案情不出本机';

      } else {

        statusText.innerText = `规则模式（未连接模型）`;

        popoverAi.innerText = `规范实务模板引擎 (全算法兜底)`;

        pulseDot.style.backgroundColor = '#C58532';

        pulseDot.style.boxShadow = '0 0 6px rgba(197, 133, 50, 0.8)';

        if (headerTag) headerTag.innerText = `规则模式（未连接模型）`;

        const piiLabel = document.getElementById('header-pii-label');

        if (piiLabel) piiLabel.innerText = '规则模式，不调用模型';

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

        await loadYuandianSettingsStatus();

        await loadLetterPrefixIntoSettings();

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



    async function loadYuandianSettingsStatus() {

      const status = document.getElementById('cfg-yuandian-status');

      const input = document.getElementById('cfg-yuandian-key');

      if (!status) return;

      try {

        const resp = await api.request(`${API_BASE}/api/v1/settings/yuandian`);

        const data = await resp.json();

        const settings = data.settings || {};

        if (input) input.value = '';

        status.innerText = settings.configured ? `已保存: ${settings.key_masked}` : '未配置';

      } catch (e) {

        status.innerText = '读取失败';

      }

    }



    async function testYuandianConnection() {

      const input = document.getElementById('cfg-yuandian-key');

      const key = input ? input.value.trim() : '';

      showTestFeedback(true, '正在连接元典…');

      try {

        const resp = await api.request(`${API_BASE}/api/v1/settings/yuandian/test`, {

          method: 'POST',

          headers: { 'Content-Type': 'application/json' },

          body: JSON.stringify({ api_key: key })

        });

        const data = await resp.json().catch(() => ({}));

        if (!resp.ok) {

          const detail = data.detail || '元典连接失败';

          showTestFeedback(false, typeof detail === 'string' ? detail : '元典连接失败');

          return;

        }

        showTestFeedback(true, data.message || '元典已连通');

        await loadYuandianSettingsStatus();

      } catch (e) {

        showTestFeedback(false, e.message || '元典连接失败');

      }

    }



    async function saveYuandianKeyIfPresent() {

      const input = document.getElementById('cfg-yuandian-key');

      const key = input ? input.value.trim() : '';

      if (!key || key.startsWith('****')) return;

      const resp = await api.request(`${API_BASE}/api/v1/settings/yuandian`, {

        method: 'POST',

        headers: { 'Content-Type': 'application/json' },

        body: JSON.stringify({ api_key: key })

      });

      if (!resp.ok) {

        const data = await resp.json().catch(() => ({}));

        throw new Error(data.detail || '元典密钥保存失败');

      }

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

        const baseUrl = (document.getElementById('cfg-base-url').value || '').trim();
        const modelName = (document.getElementById('cfg-model').value || '').trim();
        const providerLine = [presetName, modelName, baseUrl].filter(Boolean).join('，');
        const shieldOn = document.getElementById('cfg-pii-shield') ? document.getElementById('cfg-pii-shield').checked : true;
        const numberLine = shieldOn
          ? '脱敏开关目前开启：发送前会替换已识别的身份证号、手机号、银行卡号等号码。这是发送前的处理，不能写成已经脱敏。案情正文仍会发送。'
          : '脱敏开关目前关闭：身份证号、手机号、银行卡号等号码也会发送。';
        const ok = window.confirm(
          `案情、证据摘录、代理意见会发给所填服务商：${providerLine}。\n\n${numberLine}\n\n能从身份证出生日期或写明的出生日期识别的未成年人信息，以及写明病历、出院记录等的内容，默认不发往该服务商。识别不了的，不会当作已经拦住。\n\n向元典发送核对文本不在这次确认里，发送前会单独提示。\n\n请确认已知悉并同意后再继续。`
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

        const letterPrefixInput = document.getElementById('cfg-letter-prefix');

        if (letterPrefixInput) {

          const prefixSaved = await saveSettingsLetterPrefix(letterPrefixInput.value);

          if (!prefixSaved) {

            btn.innerText = origText;

            btn.disabled = false;

            return;

          }

        }

        await saveYuandianKeyIfPresent();

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

      const isRoster = tab === 'roster';

      document.getElementById('tab-btn-conflict-check').classList.toggle('active', isCheck);

      document.getElementById('tab-btn-conflict-registry').classList.toggle('active', tab === 'registry');

      const rosterBtn = document.getElementById('tab-btn-conflict-roster');

      if (rosterBtn) rosterBtn.classList.toggle('active', isRoster);

      document.getElementById('view-conflict-check').style.display = isCheck ? 'block' : 'none';

      document.getElementById('view-conflict-registry').style.display = tab === 'registry' ? 'block' : 'none';

      const rosterView = document.getElementById('view-firm-roster');

      if (rosterView) rosterView.style.display = isRoster ? 'block' : 'none';

      if (tab === 'registry') loadConflictRegistry();

      if (isRoster && window.loadFirmRoster) window.loadFirmRoster();

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



      const sameMatterEl = document.getElementById('chk-is-same-matter');

      const isSameMatter = sameMatterEl ? sameMatterEl.value.trim() : '';



      const payload = {

        client_name: clientName,

        opposing_party: opposingName,

        client_id_or_code: document.getElementById('chk-client-id').value.trim(),

        opposing_id_or_code: document.getElementById('chk-opposing-id').value.trim(),

        related_entities: related,

        case_subject: document.getElementById('chk-case-subject').value.trim(),

        is_same_matter: isSameMatter || null

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

      const cert = res.clearance_certificate || {};
      const certNo = String(cert.certificate_no || '').trim();
      if (certNo && cert.is_cleared) {
        certHtml = `
          <div style="margin-top: 14px; background: #FAF9F6; border: 1px solid #C8E6C9; border-radius: 4px; padding: 12px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
              <span style="font-weight: 700; color: #2E7D32; font-size: 12px; display: flex; align-items: center; gap: 6px;">
                <span>🛡️</span> 律所利益冲突排查验讫数字证书 (Clearance Certificate)
              </span>
              <span style="font-size: 10.5px; color: var(--text-muted); font-family: var(--font-mono);">${escapeHtml(certNo)}</span>
            </div>
            <div style="font-size: 11px; color: var(--text-secondary); line-height: 1.6;">
              验讫结论: <strong>${escapeHtml(cert.verification_status || '')}</strong><br/>
              SHA-256 数字指纹: <code style="font-family: var(--font-mono); color: #14233C; font-size: 10.5px; background: #EFEFEF; padding: 2px 4px; border-radius: 2px;">${escapeHtml(cert.sha256_fingerprint || '')}</code><br/>
              排查时间: ${escapeHtml(cert.timestamp || '')} · 核验人员: ${escapeHtml(cert.handling_lawyer || '')}
            </div>
          </div>
        `;
      } else {
        const conclusion = [
          res.conclusion,
          cert.conclusion,
          cert.verification_status,
          res.summary,
          res.status_label,
          res.message
        ].map(item => (item == null ? '' : String(item).trim())).find(Boolean) || '';
        if (conclusion) {
          certHtml = `
            <div style="margin-top: 14px; background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 4px; padding: 12px; font-size: 12px; color: var(--text-primary); line-height: 1.6;">
              ${escapeHtml(conclusion)}
            </div>
          `;
        }
      }



      // safe-html: pre-escaped or nested HTML fragment

      const generalNoticeHtml = `

        <div style="margin-top: 10px; background: #FFFBEB; border: 1px solid #FDE68A; border-radius: 4px; padding: 8px 10px; font-size: 11px; color: #92400E; line-height: 1.5;">

          <strong>【合规审查提示】</strong>${escapeHtml(res.general_prompt || '本结果仅基于本所系统内已登记的数据自动比对，可能因数据不全、名称不一致而遗漏冲突。最终是否接受委托，以律师事务所利益冲突审查的决定为准（《律师执业管理办法》第二十六条）。本结果不构成法律意见。')}

          <div style="margin-top: 4px; color: var(--text-muted); font-size: 10.5px;">${escapeHtml(res.personnel_and_relatives_check || '本所人员未录入，此项未检查。本所人员及近亲属利益冲突：本项未检查。')}</div>

        </div>

      `;



      // safe-html: conflict check rendered cards and badges
      box.innerHTML = `

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

              ${rulesHtml}

            </div>

          </div>

          ${conflictsHtml}

          ${certHtml}

          ${generalNoticeHtml}

        </div>

      `;

    }



    async function loadConflictRegistry() {

      try {

        const resp = await api.request(`${API_BASE}/api/v1/conflict/registry`);

        const d = await resp.json();

        const tbody = document.getElementById('conflict-registry-tbody');

        const badge = document.getElementById('conflict-registry-count-badge');

        if (badge) {
          const reported = Number(d.count);
          const actual = Number.isFinite(reported)
            ? reported
            : (Array.isArray(d.registry) ? d.registry.length : 0);
          badge.innerText = String(actual);
        }

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

        showToast(e instanceof ApiError ? e.userMessage : (e && e.userMessage ? e.userMessage : `操作失败：${e.message || "请求异常"}（错误码 CLIENT_ERROR）`), "error");

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

      // safe-html: pii scan results, escaped
      box.innerHTML = `

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



    // =========================================================================

    // 7. 系统运行环境与依赖体检逻辑 (System Environment Health Probing)

    // =========================================================================

    let currentSystemHealth = null;



    async function fetchSystemHealth(force = false) {

      try {

        const url = `${API_BASE}/api/system/health${force ? '?force=true' : ''}`;

        const resp = await api.request(url);

        if (!resp.ok) return null;

        const data = await resp.json();

        currentSystemHealth = data;

        updateSystemHealthUI(data);

        return data;

      } catch (e) {

        console.warn("探测系统环境健康失败:", e);

        return null;

      }

    }



    function updateSystemHealthUI(data) {

      if (!data) return;

      const dot = document.getElementById('header-health-dot');

      const tag = document.getElementById('header-health-tag');

      const btn = document.getElementById('header-system-health-btn');



      const overall = data.overall_status || 'OK';

      if (dot) {

        if (overall === 'OK') {

          dot.style.background = '#22c55e';

          dot.style.boxShadow = '0 0 6px rgba(34, 197, 94, 0.8)';

        } else if (overall === 'DEGRADED') {

          dot.style.background = '#f59e0b';

          dot.style.boxShadow = '0 0 6px rgba(245, 158, 11, 0.8)';

        } else {

          dot.style.background = '#ef4444';

          dot.style.boxShadow = '0 0 6px rgba(239, 68, 68, 0.8)';

        }

      }



      if (tag) {

        if (overall === 'OK') {

          tag.innerText = '🩺 环境就绪';

        } else if (overall === 'DEGRADED') {

          tag.innerText = '🩺 规则兜底';

        } else {

          tag.innerText = '🩺 核心缺失';

        }

      }



      if (btn) {

        btn.title = `系统运行环境体检: ${overall === 'OK' ? '全部就绪' : overall === 'DEGRADED' ? '部分降级·兜底可用' : '核心依赖缺失'} - 点击查看报告`;

      }



      const modal = document.getElementById('modal-system-health');

      if (modal && modal.classList.contains('active')) {

        renderSystemHealthModal(data);

      }

    }



    function renderSystemHealthModal(data) {

      if (!data) return;

      const overall = data.overall_status || 'OK';

      const badge = document.getElementById('health-overall-badge');

      const summaryTitle = document.getElementById('health-summary-title');

      const summaryIcon = document.getElementById('health-summary-icon');

      const summaryText = document.getElementById('health-summary-text');

      const lastChecked = document.getElementById('health-last-checked');



      if (badge) {

        if (overall === 'OK') {

          badge.textContent = '✅ 全部就绪 (OK)';

          badge.style.background = 'rgba(34, 197, 94, 0.2)';

          badge.style.color = '#4ADE80';

          badge.style.borderColor = 'rgba(74, 222, 128, 0.4)';

        } else if (overall === 'DEGRADED') {

          badge.textContent = '⚠️ 部分降级·兜底在线 (DEGRADED)';

          badge.style.background = 'rgba(245, 158, 11, 0.2)';

          badge.style.color = '#FBBF24';

          badge.style.borderColor = 'rgba(251, 191, 36, 0.4)';

        } else {

          badge.textContent = '❌ 核心缺失 (MISSING)';

          badge.style.background = 'rgba(239, 68, 68, 0.2)';

          badge.style.color = '#F87171';

          badge.style.borderColor = 'rgba(248, 113, 113, 0.4)';

        }

      }



      if (summaryTitle) {

        summaryTitle.textContent = overall === 'OK' ? '系统环境完备就绪' : overall === 'DEGRADED' ? '系统运行中（已启用内置降级兜底）' : '核心运行依赖缺失';

      }

      if (summaryIcon) {

        summaryIcon.textContent = overall === 'OK' ? '🟢' : overall === 'DEGRADED' ? '🟡' : '🔴';

      }

      if (summaryText) {

        summaryText.textContent = data.summary || '';

      }

      if (lastChecked) {

        lastChecked.textContent = `体检时间: ${new Date().toLocaleTimeString('zh-CN', { hour12: false })}`;

      }



      const diags = data.diagnostics || {};



      function updateCard(key, status, infoText, remText) {

        const badgeEl = document.getElementById(`health-badge-${key}`);

        const infoEl = document.getElementById(`health-info-${key}`);

        const remEl = document.getElementById(`health-remediation-${key}`);



        if (badgeEl) {

          if (status === 'OK') {

            badgeEl.textContent = '正常 (OK)';

            badgeEl.style.background = '#DCFCE7';

            badgeEl.style.color = '#15803D';

            badgeEl.style.border = '1px solid #86EFAC';

          } else if (status === 'DEGRADED') {

            badgeEl.textContent = '降级 (DEGRADED)';

            badgeEl.style.background = '#FEF3C7';

            badgeEl.style.color = '#B45309';

            badgeEl.style.border = '1px solid #FDE68A';

          } else {

            badgeEl.textContent = '缺失 (MISSING)';

            badgeEl.style.background = '#FEE2E2';

            badgeEl.style.color = '#B91C1C';

            badgeEl.style.border = '1px solid #FCA5A5';

          }

        }

        if (infoEl) infoEl.textContent = infoText;

        if (remEl) remEl.textContent = remText;

      }



      // 1. LibreOffice

      const lo = diags.libreoffice || {};

      updateCard(

        'libreoffice',

        lo.status || 'MISSING',

        `执行文件: ${lo.path || '未检测到 (系统 PATH 中未找到 soffice/libreoffice)'}`,

        lo.remediation || '未检测到 LibreOffice'

      );



      // 2. Ollama

      const ol = diags.ollama || {};

      const modelInfo = (ol.installed_models && ol.installed_models.length)

        ? `已装模型: ${ol.installed_models.join(', ')}`

        : '未安装模型';

      updateCard(

        'ollama',

        ol.status || 'MISSING',

        `服务端口: ${ol.endpoint || 'http://127.0.0.1:11434'} | ${modelInfo}`,

        ol.remediation || 'Ollama 服务未启动'

      );



      // 3. cn_laws_kb

      const laws = diags.cn_laws_kb || {};

      updateCard(

        'cn-laws',

        laws.status || 'MISSING',

        `底库路径: ${laws.path || '未找到'} | 法规收录: ${laws.laws_count ?? 0} 部 | 全文检索法条: ${laws.articles_count ?? 0} 条`,

        laws.remediation || '权威法典库状态异常'

      );



      // 4. matter_vault

      const vault = diags.matter_vault || {};

      updateCard(

        'matter-vault',

        vault.status || 'MISSING',

        `底库路径: ${vault.path || '未找到'} | 在册案件独立空间: ${vault.matters_count ?? 0} 件`,

        vault.remediation || '案件空间数据库状态异常'

      );



      // 5. pdf_engine

      const pdf = diags.pdf_engine || {};

      const avEngines = (pdf.available_engines || []).join(', ') || 'none';

      updateCard(

        'pdf-engine',

        pdf.status || 'DEGRADED',

        `活动渲染引擎: ${pdf.active_engine || 'local_pymupdf'} | 可用备选引擎: ${avEngines}`,

        pdf.remediation || 'PDF 渲染引擎矩阵正常'

      );

    }



    async function openSystemHealthModal() {

      const modal = document.getElementById('modal-system-health');

      if (!modal) return;

      modal.classList.add('active');



      if (currentSystemHealth) {

        renderSystemHealthModal(currentSystemHealth);

      }

      await refreshSystemHealth(false);

    }



    function closeSystemHealthModal() {

      const modal = document.getElementById('modal-system-health');

      if (modal) {

        modal.classList.remove('active');

      }

    }



    function handleSystemHealthModalBackdropClick(event) {

      if (event.target && event.target.id === 'modal-system-health') {

        closeSystemHealthModal();

      }

    }



    async function refreshSystemHealth(force = true) {

      const refreshBtn = document.getElementById('btn-refresh-system-health');

      if (refreshBtn) {

        refreshBtn.disabled = true;

        refreshBtn.innerHTML = '🔄 探测中...';

      }

      try {

        const data = await fetchSystemHealth(force);

        if (data) {

          renderSystemHealthModal(data);

          if (force && typeof showToast === 'function') {

            showToast('系统环境体检报告已更新', 'info');

          }

        }

      } catch (err) {

        console.error("刷新体检报告异常:", err);

      } finally {

        if (refreshBtn) {

          refreshBtn.disabled = false;

          refreshBtn.innerHTML = '🔄 重新体检';

        }

      }

    }



async function loadLetterPrefixIntoSettings() {

  ensureLetterPrefixField();

  try {

    const resp = await api.request(`${API_BASE}/api/v1/phase1/letter-prefix`);

    if (!resp || !resp.ok) return;

    const data = await resp.json();

    const prefix = (data && data.prefix) || '';

    const input = document.getElementById('cfg-letter-prefix');

    if (input) input.value = prefix;

    const pkg = document.getElementById('pkg-letter-prefix');

    if (pkg && !pkg.value && prefix) pkg.value = prefix;

  } catch (e) {

    console.warn('读取公函函号前缀失败', e);

  }

}



function ensureLetterPrefixField() {

  if (document.getElementById('cfg-letter-prefix')) return;

  const host = document.querySelector('#modal-engine-settings .modal-body');

  const tpl = document.getElementById('letter-prefix-field-template');

  if (!host || !tpl || !tpl.content) return;

  const fragment = tpl.content.cloneNode(true);

  const feedback = document.getElementById('cfg-test-feedback');

  if (feedback && feedback.parentElement === host) {

    host.insertBefore(fragment, feedback);

  } else {

    host.appendChild(fragment);

  }

  const input = document.getElementById('cfg-letter-prefix');

  if (input) {

    input.addEventListener('change', () => {

      saveSettingsLetterPrefix(input.value);

    });

  }

}



async function saveSettingsLetterPrefix(raw) {

  const text = String(raw == null ? '' : raw).trim();

  if (text.includes('京律函字')) {

    showToast('不能使用示例函号。请填本所自己的前缀，没有就留空。');

    const input = document.getElementById('cfg-letter-prefix');

    if (input) input.value = '';

    return false;

  }

  try {

    const resp = await api.request(`${API_BASE}/api/v1/phase1/letter-prefix`, {

      method: 'POST',

      headers: { 'Content-Type': 'application/json' },

      body: JSON.stringify({ prefix: text }),

    });

    if (!resp || !resp.ok) {

      showToast('函号前缀保存失败');

      return false;

    }

    const pkg = document.getElementById('pkg-letter-prefix');

    if (pkg && pkg.value.trim() !== text) pkg.value = text;

    return true;

  } catch (e) {

    showToast(e instanceof ApiError ? e.userMessage : ('函号前缀保存失败: ' + e));

    return false;

  }

}



let pendingRiskFeeRatio = null;

const RISK_FEE_PROHIBITED = [
  ['婚姻', /婚姻|离婚|同居/],
  ['继承', /继承|遗赠|遗产/],
  ['社会保险', /社会保险|社保待遇/],
  ['最低生活保障', /最低生活保障|低保/],
  ['赡养费', /赡养/],
  ['抚养费', /抚养/],
  ['扶养费', /扶养/],
  ['抚恤金', /抚恤/],
  ['救济金', /救济金/],
  ['工伤赔偿', /工伤/],
  ['劳动报酬', /劳动报酬/],
  ['刑事', /刑事/],
  ['行政', /行政/],
  ['国家赔偿', /国家赔偿/],
  ['群体性诉讼', /群体/],
];

function readNewMatterCause() {
  const causePick = (document.getElementById('new-matter-cause')?.value || '').trim();
  if (causePick === '__custom__') {
    return (document.getElementById('new-matter-cause-custom')?.value || '').trim();
  }
  return causePick;
}

function prohibitedRiskFeeLabel(cause) {
  const hit = RISK_FEE_PROHIBITED.find(([, pattern]) => pattern.test(cause || ''));
  return hit ? hit[0] : '';
}

function installOutboundGuards() {
  if (!api.request || api.request.__lfOutboundGuard) return;
  const original = api.request.bind(api);
  const guarded = async function(endpoint, options) {
    const path = String(endpoint || '');
    const opts = options || {};
    if (path.indexOf('/yuandian/check') !== -1) {
      const agreed = window.confirm(
        '即将向元典（open.chineselaw.com）发送核对文本原文，最多两万字。这次不经过云端脱敏开关，不能写成已经脱敏。\n\n' +
        '核对文本里的身份证等号码，不会因为云端脱敏开关而先被替换。开关关闭时，这些号码会按原文发送。\n\n' +
        '能从身份证出生日期或写明的出生日期识别的未成年人信息，以及写明病历、出院记录等的内容，默认不发送。识别不了的，不会当作已经拦住。\n\n' +
        '是否继续发送？'
      );
      if (!agreed) {
        throw new Error('已取消向元典发送核对文本');
      }
    }
    let next = opts;
    if (
      pendingRiskFeeRatio != null &&
      path.indexOf('/vault/matters') !== -1 &&
      String(opts.method || '').toUpperCase() === 'POST' &&
      typeof opts.body === 'string'
    ) {
      try {
        const body = JSON.parse(opts.body);
        body.practice = Object.assign({}, body.practice || {}, { risk_fee_ratio: pendingRiskFeeRatio });
        next = Object.assign({}, opts, { body: JSON.stringify(body) });
      } catch (err) {
        next = opts;
      }
    }
    return original(endpoint, next);
  };
  guarded.__lfOutboundGuard = true;
  api.request = guarded;
}

function installMatterFeeGuard() {
  const current = window.submitCreateNewMatter;
  if (typeof current !== 'function' || current.__lfFeeGuard) return;
  async function guardedSubmit() {
    const feeType = document.getElementById('new-matter-fee-type')?.value || 'unset';
    pendingRiskFeeRatio = null;
    if (feeType === 'risk') {
      const banned = prohibitedRiskFeeLabel(readNewMatterCause());
      if (banned) {
        showToast('《律师服务收费管理办法》第十一条、第十二条禁止对' + banned + '案件实行风险代理。本案案由属于禁止类型，不能保存。勾选「已说明」不能代替书面风险代理合同。');
        return;
      }
      const ratioRaw = (document.getElementById('new-matter-risk-ratio')?.value || '').trim();
      const ratio = Number(ratioRaw);
      if (!ratioRaw || !Number.isFinite(ratio) || ratio <= 0 || ratio > 100) {
        showToast('其他财产案件实行风险代理，必须填写约定比例。勾选「已说明」不能代替书面风险代理合同。');
        return;
      }
      if (ratio > 30) {
        const proceed = window.confirm(
          '约定比例为标的额的 ' + ratio + '%，已超过 30%。《律师服务收费管理办法》规定风险代理最高收费不得高于约定标的额的 30%，当地收费办法可能更严。仍要保存吗？'
        );
        if (!proceed) return;
      }
      pendingRiskFeeRatio = ratio;
    }
    try {
      return await current();
    } finally {
      pendingRiskFeeRatio = null;
    }
  }
  guardedSubmit.__lfFeeGuard = true;
  window.submitCreateNewMatter = guardedSubmit;
}

installOutboundGuards();
if (typeof document !== 'undefined') {
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', installMatterFeeGuard);
  } else {
    installMatterFeeGuard();
  }
}

export {

  fetchEngineHealth,

  updateEngineStatusUI,

  openEngineSettingsModal,

  closeEngineSettingsModal,

  handleModalBackdropClick,

  selectEngineMode,

  onCloudPresetChange,

  toggleApiKeyVisibility,

  showTestFeedback,

  hideTestFeedback,

  testEngineConnection,

  saveEngineSettings,

  testYuandianConnection,

  loadYuandianSettingsStatus,

  openConflictCheckModal,

  closeConflictCheckModal,

  handleConflictModalBackdropClick,

  switchConflictModalTab,

  syncConflictFormFromGlobalCase,

  quickCheckTabLitigationConflict,

  runConflictCheckSubmit,

  renderConflictResult,

  loadConflictRegistry,

  toggleRegisterCaseDrawer,

  submitRegisterConflictCase,

  runPiiScanUI,

  renderPiiScanResult,

  fetchSystemHealth,

  updateSystemHealthUI,

  renderSystemHealthModal,

  openSystemHealthModal,

  closeSystemHealthModal,

  handleSystemHealthModalBackdropClick,

  refreshSystemHealth,

};

