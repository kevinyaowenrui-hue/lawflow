/**
 * LawFlow UI Toast Module (toast.js)
 * 提供成功、警告、失败、信息四种状态的轻量级 Toast 提示与专属图标
 */

export function showToast(msg, type = 'info') {
  let container = document.getElementById('toast-container');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toast-container';
    container.className = 'toast-container';
    document.body.appendChild(container);
  }

  const toast = document.createElement('div');
  const normalizedType = type === 'warning' ? 'warn' : (type || 'info');
  toast.className = `toast ${normalizedType}`;

  let iconSvg = '';
  if (normalizedType === 'success') {
    iconSvg = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#16A34A" stroke-width="2.5"><polyline points="20 6 9 17 4 12"></polyline></svg>';
  } else if (normalizedType === 'warn') {
    iconSvg = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#D97706" stroke-width="2.5"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>';
  } else if (normalizedType === 'error' || normalizedType === 'danger') {
    iconSvg = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#DC2626" stroke-width="2.5"><circle cx="12" cy="12" r="10"></circle><line x1="15" y1="9" x2="9" y2="15"></line><line x1="9" y1="9" x2="15" y2="15"></line></svg>';
  } else {
    iconSvg = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#C58532" stroke-width="2"><polyline points="20 6 9 17 4 12"></polyline></svg>';
  }

  const safeMsg = typeof window.escapeHtml === 'function' ? window.escapeHtml(String(msg || '')) : String(msg || '');
  toast.innerHTML = `${iconSvg}<span>${safeMsg}</span>`; // safe-html: toast static svg and escaped msg
  container.appendChild(toast);
  setTimeout(() => toast.classList.add('show'), 10);
  setTimeout(() => {
    toast.classList.remove('show');
    setTimeout(() => toast.remove(), 250);
  }, 2600);
}

// 挂载至全局
if (typeof window !== 'undefined') {
  window.showToast = showToast;
}
