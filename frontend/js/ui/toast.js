/**
 * LawFlow UI Toast Module (toast.js)
 * 提供成功、警告、失败、信息四种状态的轻量级 Toast 提示与专属图标
 */

export function isPinnedFormFailure(msg) {
  const text = String(msg || '');
  if (!text || text.includes('还没有可同步的计算结果')) return false;
  if (/生成失败/.test(text) || /生成[^。\n]{0,30}失败/.test(text)) return true;
  if (/期限/.test(text) && /失败|读不到|没有读到|无法读取|未读到|暂时没有/.test(text)) return true;
  if (/测算失败|核算失败/.test(text) && /期|期限|时效/.test(text)) return true;
  return false;
}

function pinAboveDeadlineBoard(msg) {
  return /期限清单|今日期限|暂时没有读到/.test(String(msg || ''));
}

function pinFormFailure(msg) {
  const text = String(msg || '');
  const aboveBoard = pinAboveDeadlineBoard(text);
  const board = typeof document !== 'undefined' ? document.getElementById('today-deadlines-board') : null;
  const active = typeof document !== 'undefined' ? document.querySelector('.workspace-tab.active') : null;
  const anchor = (aboveBoard && board) ? board : (active || document.body);
  const stackId = aboveBoard && board ? 'sticky-failures-deadlines' : 'sticky-failures-form';
  let stack = document.getElementById(stackId);
  if (!stack) {
    stack = document.createElement('div');
    stack.id = stackId;
    stack.dataset.stickyFailures = '1';
    stack.style.margin = '0 0 8px';
  }
  if (aboveBoard && board && board.parentElement) {
    if (stack.nextElementSibling !== board) board.parentElement.insertBefore(stack, board);
  } else if (anchor && anchor.firstChild !== stack) {
    anchor.insertBefore(stack, anchor.firstChild);
  }
  const already = Array.from(stack.children).some((item) => item.dataset.msg === text);
  if (already) return;
  const item = document.createElement('div');
  item.dataset.msg = text;
  item.setAttribute('role', 'alert');
  item.style.cssText = 'margin:0 0 8px;padding:8px 10px;background:#FEF2F2;color:#991B1B;border:1px solid #FECACA;border-radius:4px;font-size:12px;display:flex;justify-content:space-between;align-items:flex-start;gap:8px;';
  const span = document.createElement('span');
  span.textContent = text;
  span.style.whiteSpace = 'pre-wrap';
  const dismiss = document.createElement('button');
  dismiss.type = 'button';
  dismiss.textContent = '关闭';
  dismiss.style.cssText = 'flex:none;background:#fff;border:1px solid #FECACA;color:#991B1B;border-radius:4px;padding:2px 8px;cursor:pointer;';
  dismiss.addEventListener('click', () => {
    item.remove();
    if (!stack.childElementCount) stack.remove();
  });
  item.appendChild(span);
  item.appendChild(dismiss);
  stack.appendChild(item);
}

export function showToast(msg, type = 'info') {
  if (isPinnedFormFailure(msg)) {
    pinFormFailure(msg);
    return;
  }
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
