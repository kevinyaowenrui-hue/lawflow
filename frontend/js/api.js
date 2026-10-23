/**
 * LawFlow 智律工作台 - 统一 API 客户端 (api.js)
 * 封装基址、Token 注入、超时控制、JSON 解析、resp.ok 校验与友好错误转换
 */

export const API_BASE = "";

export class ApiError extends Error {
  constructor(message, status, errorCode, detail, requestId) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.errorCode = errorCode || (status ? `HTTP_${status}` : "NETWORK_ERROR");
    this.detail = detail;
    this.requestId = requestId;
    this.userMessage = `操作失败：${message}（错误码 ${this.errorCode}）`;
  }
}

export function getApiToken() {
  if (typeof window === "undefined") return "";
  if (window.LAWFLOW_API_TOKEN) return window.LAWFLOW_API_TOKEN;
  const meta = document.querySelector('meta[name="lawflow-token"]');
  if (meta && meta.content) return meta.content;
  try {
    return localStorage.getItem("LAWFLOW_API_TOKEN") || sessionStorage.getItem("LAWFLOW_API_TOKEN") || "";
  } catch (e) {
    return "";
  }
}


export function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

export function withDownloadToken(url) {
  if (!url || typeof url !== "string") return url || "#";
  const token = getApiToken();
  if (!token) return url;
  const sep = url.includes("?") ? "&" : "?";
  if (url.includes("token=")) return url;
  return `${url}${sep}token=${encodeURIComponent(token)}`;
}

const ERROR_MESSAGE_MAP = {
  "AUTH_REQUIRED": "身份凭证缺失或未授权，请检查访问权限",
  "FORBIDDEN": "当前操作无权限执行",
  "NOT_FOUND": "请求的案件、材料或记录不存在",
  "INTERNAL_ERROR": "服务器内部处理异常，请稍后重试",
  "TIMEOUT": "网络请求超时，请检查后端服务状态",
  "NETWORK_ERROR": "网络连接异常，无法连接至本地智律网关",
  "VALIDATION_ERROR": "请求参数校验失败，请检查输入项",
  "BAD_REQUEST": "请求格式不合规或参数不完整",
};

export function mapFriendlyError(status, code, serverMsg) {
  if (code && ERROR_MESSAGE_MAP[code]) {
    return ERROR_MESSAGE_MAP[code];
  }
  if (status === 401) return ERROR_MESSAGE_MAP["AUTH_REQUIRED"];
  if (status === 403) return ERROR_MESSAGE_MAP["FORBIDDEN"];
  if (status === 404) return ERROR_MESSAGE_MAP["NOT_FOUND"];
  if (status === 422) return "提交参数不符合规范，请核对输入数据";
  if (status >= 500) return ERROR_MESSAGE_MAP["INTERNAL_ERROR"];
  if (serverMsg && typeof serverMsg === "string" && serverMsg.length < 80 && !serverMsg.includes("Traceback") && !serverMsg.includes("line ") && !serverMsg.includes(".py") && !serverMsg.includes("OperationalError") && !serverMsg.includes("sqlite3")) {
    return serverMsg;
  }
  return "系统处理遇到异常，请稍后重试";
}

export async function request(endpoint, options = {}) {
  const url = endpoint.startsWith("http://") || endpoint.startsWith("https://")
    ? endpoint
    : `${API_BASE}${endpoint.startsWith("/") ? "" : "/"}${endpoint}`;

  const headers = new Headers(options.headers || {});
  const token = getApiToken();
  if (token && !headers.has("X-LawFlow-Token")) {
    headers.set("X-LawFlow-Token", token);
  }

  const isFormData = typeof FormData !== "undefined" && options.body instanceof FormData;
  if (!isFormData && !headers.has("Content-Type") && options.body && typeof options.body === "string") {
    headers.set("Content-Type", "application/json");
  }

  const timeoutMs = options.timeout || 60000;
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  let resp;
  try {
    resp = await fetch(url, {
      ...options,
      headers,
      signal: controller.signal,
    });
  } catch (err) {
    clearTimeout(timeoutId);
    const isTimeout = err.name === "AbortError";
    const code = isTimeout ? "TIMEOUT" : "NETWORK_ERROR";
    const msg = isTimeout ? "请求超时" : "网络连接中断";
    const friendly = mapFriendlyError(0, code, msg);
    console.error(`[Api Network Error] ${options.method || "GET"} ${url}`, err);
    throw new ApiError(friendly, 0, code, err.message);
  } finally {
    clearTimeout(timeoutId);
  }

  if (!resp.ok) {
    let errData = null;
    let detailText = "";
    try {
      errData = await resp.json();
    } catch (_) {
      try {
        detailText = await resp.text();
      } catch (__) {}
    }

    const errorCode = (errData && (errData.error_code || (errData.detail && errData.detail.error_code))) || `HTTP_${resp.status}`;
    const serverDetail = (errData && (errData.message || (typeof errData.detail === "string" ? errData.detail : (errData.detail && errData.detail.message)))) || detailText;
    const reqId = (errData && (errData.request_id || (errData.detail && errData.detail.request_id))) || "";
    const friendlyMsg = mapFriendlyError(resp.status, errorCode, serverDetail);

    console.error(`[Api Error ${resp.status}] ${options.method || "GET"} ${url}`, {
      status: resp.status,
      errorCode,
      serverDetail,
      requestId: reqId,
    });
    throw new ApiError(friendlyMsg, resp.status, errorCode, serverDetail, reqId);
  }

  let data = null;
  if (resp.status !== 204) {
    const contentType = resp.headers.get("content-type") || "";
    if (contentType.includes("application/json")) {
      try {
        data = await resp.json();
      } catch (_) {
        data = {};
      }
    } else {
      try {
        data = await resp.text();
      } catch (_) {
        data = "";
      }
    }
  }

  return {
    ok: true,
    status: resp.status,
    statusText: resp.statusText,
    headers: resp.headers,
    data: data,
    json: async () => data,
    text: async () => (typeof data === "string" ? data : JSON.stringify(data)),
  };
}

export const api = {
  get: async (endpoint, options = {}) => {
    const res = await request(endpoint, { ...options, method: "GET" });
    return res.data;
  },
  post: async (endpoint, body, options = {}) => {
    const isFormData = typeof FormData !== "undefined" && body instanceof FormData;
    const isString = typeof body === "string";
    const payload = isFormData || isString || body === undefined ? body : JSON.stringify(body);
    const res = await request(endpoint, { ...options, method: "POST", body: payload });
    return res.data;
  },
  put: async (endpoint, body, options = {}) => {
    const isFormData = typeof FormData !== "undefined" && body instanceof FormData;
    const isString = typeof body === "string";
    const payload = isFormData || isString || body === undefined ? body : JSON.stringify(body);
    const res = await request(endpoint, { ...options, method: "PUT", body: payload });
    return res.data;
  },
  delete: async (endpoint, options = {}) => {
    const res = await request(endpoint, { ...options, method: "DELETE" });
    return res.data;
  },
  request,
  withDownloadToken,
};

// 挂载至全局
if (typeof window !== "undefined") {
  window.api = api;
  window.ApiError = ApiError;
  window.API_BASE = API_BASE;
  window.withDownloadToken = withDownloadToken;
  window.escapeHtml = escapeHtml;
  window.activeMatterId = null;
  window.activeMatterData = null;
  window.allVaultMatters = [];
  window.lastCalcDeadline = null;
  window.lastAppealDeadline = null;
  window.currentDeepData = null;
  window._lastCitationAudit = null;
}
