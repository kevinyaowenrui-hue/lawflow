/**
 * LawFlow Module: converter.js
 */
import { api, ApiError, API_BASE, withDownloadToken } from '../api.js';
import { showToast } from '../ui/toast.js';



    // =========================================================================
    let converterSelectedFiles = [];
    let lastConvertedResult = null;

    async function openFileConverterModal() {
      const modal = document.getElementById('modal-file-converter');
      if (!modal) return;
      modal.classList.add('active');
      await fetchConverterStatus();
    }

    function closeFileConverterModal() {
      const modal = document.getElementById('modal-file-converter');
      if (modal) modal.classList.remove('active');
    }

    function handleConverterModalBackdropClick(e) {
      if (e.target && e.target.id === 'modal-file-converter') {
        closeFileConverterModal();
      }
    }

    async function fetchConverterStatus() {
      try {
        const resp = await api.request('/api/v1/converter/status');
        if (!resp.ok) return;
        const data = await resp.json();
        const badge = document.getElementById('modal-converter-engine-badge');
        const desc = document.getElementById('modal-converter-engine-desc');
        const hint = document.getElementById('modal-converter-filee-hint');
        const headerTag = document.getElementById('header-converter-tag');

        if (data.filee_installed) {
          if (badge) {
            badge.style.background = 'rgba(37, 99, 235, 0.15)';
            badge.style.color = '#1D4ED8';
            badge.textContent = '🚀 Filee 离线全格式引擎就绪 (244+ 格式)';
          }
          if (desc) desc.textContent = 'Filee CLI 增强模式（支持 CAD、HWP、特殊音视频与 244 种全格式本地极速转码）';
          if (hint) hint.innerHTML = `已挂载引擎路径: <code>${escapeHtml(data.filee_path || 'tools/filee')}</code>`;
          if (headerTag) headerTag.textContent = '⚖️ Filee转码箱';
        } else {
          if (badge) {
            badge.style.background = 'rgba(34, 197, 94, 0.15)';
            badge.style.color = '#15803D';
            badge.textContent = '⚡ 内置司法引擎就绪';
          }
          if (desc) desc.textContent = 'LawFlow 司法内置快速转码引擎（原生支持 HEIC/TIFF/PDF/Word/CSV/音频）';
          if (hint) hint.innerHTML = '💡 可将 Filee.exe 绿色便携版放入 <code>tools/filee</code> 解锁 244 种工业格式';
        }
      } catch (e) {
        console.warn('获取转码引擎状态失败:', e);
      }
    }

    function applyConverterPreset(presetId, targetFormat, batesPrefix, stampBates) {
      const targetSelect = document.getElementById('converter-target-format');
      const batesInput = document.getElementById('converter-bates-prefix');
      const stampBox = document.getElementById('converter-stamp-checkbox');

      if (targetSelect) targetSelect.value = targetFormat;
      if (batesInput && batesPrefix) batesInput.value = batesPrefix;
      if (stampBox) stampBox.checked = stampBates;

      onTargetFormatChange(targetFormat);
      showToast(`已应用预设: ${targetFormat.toUpperCase()}`);
    }

    function onTargetFormatChange(val) {
      const batesGroup = document.getElementById('converter-bates-group');
      const stampGroup = document.getElementById('converter-stamp-group');
      if (val === 'pdf') {
        if (batesGroup) batesGroup.style.display = 'block';
        if (stampGroup) stampGroup.style.display = 'flex';
      } else {
        if (batesGroup) batesGroup.style.display = 'none';
        if (stampGroup) stampGroup.style.display = 'none';
      }
    }

    function onConverterFilesSelected(files) {
      if (!files || files.length === 0) return;
      converterSelectedFiles = Array.from(files);
      renderConverterFilesSummary();
    }

    function clearConverterFiles() {
      converterSelectedFiles = [];
      const fileInput = document.getElementById('converter-file-input');
      if (fileInput) fileInput.value = '';
      const list = document.getElementById('converter-selected-list');
      if (list) list.style.display = 'none';
    }

    function renderConverterFilesSummary() {
      const list = document.getElementById('converter-selected-list');
      const countSpan = document.getElementById('converter-files-count');
      const summaryDiv = document.getElementById('converter-files-summary');
      if (!list || !countSpan || !summaryDiv) return;

      if (converterSelectedFiles.length === 0) {
        list.style.display = 'none';
        return;
      }

      list.style.display = 'block';
      countSpan.textContent = converterSelectedFiles.length;
      summaryDiv.innerHTML = converterSelectedFiles.map((f, i) => {
        const sizeMb = (f.size / (1024 * 1024)).toFixed(2);
        return `<div style="display:flex; justify-content:space-between; padding:2px 0; border-bottom:1px dashed #F1F5F9;">
          <span>📄 <strong>${escapeHtml(i+1)}.</strong> ${escapeHtml(f.name)}</span>
          <span style="color:#64748B; font-family:var(--font-mono); font-size:11px;">${escapeHtml(sizeMb)} MB</span>
        </div>`;
      }).join('');
    }

    async function executeOfflineConversion() {
      if (converterSelectedFiles.length === 0) {
        alert('请先选择或拖拽待转换的文件！');
        return;
      }

      const targetFormat = document.getElementById('converter-target-format').value;
      const batesPrefix = document.getElementById('converter-bates-prefix').value.trim() || '证据';
      const stampBates = document.getElementById('converter-stamp-checkbox').checked;

      const btn = document.getElementById('btn-run-converter');
      const progressText = document.getElementById('converter-progress-text');
      const resultBox = document.getElementById('converter-result-box');

      if (btn) btn.disabled = true;
      if (progressText) {
        progressText.style.display = 'inline';
        progressText.textContent = `正在执行本地离线转换中 (${converterSelectedFiles.length} 个文件)...`;
      }
      if (resultBox) resultBox.style.display = 'none';

      try {
        let endpoint = '/api/v1/converter/convert';
        const formData = new FormData();

        const isMultiImagesToPdf = converterSelectedFiles.length > 1 && targetFormat === 'pdf';
        if (isMultiImagesToPdf) {
          endpoint = '/api/v1/converter/batch-merge-bates';
          converterSelectedFiles.forEach(f => formData.append('files', f));
          formData.append('evidence_label', batesPrefix);
          formData.append('stamp_bates', stampBates ? 'true' : 'false');
        } else {
          formData.append('file', converterSelectedFiles[0]);
          formData.append('target_format', targetFormat);
          formData.append('bates_prefix', batesPrefix);
          formData.append('stamp_bates', stampBates ? 'true' : 'false');
        }

        const resp = await api.request(endpoint, {
          method: 'POST',
          body: formData
        });

        if (!resp.ok) {
          const err = await resp.json().catch(() => ({}));
          throw new Error(err.detail || '转换失败');
        }

        const res = await resp.json();
        lastConvertedResult = res;

        if (resultBox) {
          resultBox.style.display = 'block';
          const title = document.getElementById('converter-result-title');
          const desc = document.getElementById('converter-result-desc');
          const timeSpan = document.getElementById('converter-result-time');
          const dlBtn = document.getElementById('converter-download-btn');
          const engineBadge = document.getElementById('converter-result-engine');

          if (title) title.textContent = '转码成功并已归档';
          if (timeSpan) timeSpan.textContent = `耗时: ${res.elapsed_ms || 100}ms`;
          if (engineBadge) {
            engineBadge.textContent = res.engine === 'filee' ? 'Filee 离线全格式引擎' : 'LawFlow 司法内置快速引擎';
          }
          const sizeKb = ((res.file_size || 0) / 1024).toFixed(1);
          const pageInfo = res.total_pages ? ` (共 ${res.total_pages} 页)` : '';
          if (desc) {
            desc.innerHTML = `已生成成品文件：<strong>${escapeHtml(res.output_filename)}</strong>${escapeHtml(pageInfo)} · 大小: ${escapeHtml(sizeKb)} KB。可立即下载或直接联动诉讼流水线！`;
          }
          if (dlBtn && res.download_url) {
            dlBtn.href = withDownloadToken(res.download_url);
            dlBtn.download = res.output_filename;
          }
        }
        showToast('离线转码已成功完成！');
      } catch (e) {
        alert('转换失败: ' + e.message);
      } finally {
        if (btn) btn.disabled = false;
        if (progressText) progressText.style.display = 'none';
      }
    }

    function pushConvertedToEvidenceList() {
      if (!lastConvertedResult || !lastConvertedResult.output_filename) {
        showToast('暂无已转换的成品文件');
        return;
      }
      const navBtn = document.getElementById('nav-evidence');
      if (typeof switchNavTab === 'function') {
        switchNavTab('tab-evidence', '03 证据清洗与庭审', navBtn);
      }
      closeFileConverterModal();
      const redactInput = document.getElementById('redact-pdf-name');
      if (redactInput) redactInput.value = lastConvertedResult.output_filename;
      showToast(`已将 ${lastConvertedResult.output_filename} 载入 03 证据清洗区！`);
    }

    function pushConvertedToVoiceCopilot() {
      if (!lastConvertedResult || !lastConvertedResult.output_filename) {
        showToast('暂无已转换的成品文件');
        return;
      }
      closeFileConverterModal();
      if (typeof toggleGlobalVoiceDrawer === 'function') {
        const drawer = document.getElementById('global-voice-drawer');
        if (drawer && !drawer.classList.contains('active')) {
          toggleGlobalVoiceDrawer();
        }
      }
      const textInput = document.getElementById('drawer-text-input');
      if (textInput) {
        textInput.value = `请对已转码的涉案证据文件《${lastConvertedResult.output_filename}》进行要素梳理与三性审查`;
        if (typeof sendDrawerTextMessage === 'function') {
          sendDrawerTextMessage();
        }
      }
    }

    function initConverterDropZone() {
      const dropZone = document.getElementById('converter-drop-zone');
      if (!dropZone) return;
      dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.style.borderColor = 'var(--accent-amber)';
        dropZone.style.background = '#FFFDF8';
      });
      dropZone.addEventListener('dragleave', (e) => {
        e.preventDefault();
        dropZone.style.borderColor = '#CBD5E1';
        dropZone.style.background = '#FCFBF9';
      });
      dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.style.borderColor = '#CBD5E1';
        dropZone.style.background = '#FCFBF9';
        if (e.dataTransfer && e.dataTransfer.files) {
          onConverterFilesSelected(e.dataTransfer.files);
        }
      });
    }

    // =========================================================================
    // 批次 15 新增：案件状态流转、软删除、期限日历、PII扫描、证据三性质证与红队攻击

export {
  openFileConverterModal,
  closeFileConverterModal,
  handleConverterModalBackdropClick,
  fetchConverterStatus,
  applyConverterPreset,
  onTargetFormatChange,
  onConverterFilesSelected,
  clearConverterFiles,
  renderConverterFilesSummary,
  executeOfflineConversion,
  pushConvertedToEvidenceList,
  pushConvertedToVoiceCopilot,
  initConverterDropZone,
};
