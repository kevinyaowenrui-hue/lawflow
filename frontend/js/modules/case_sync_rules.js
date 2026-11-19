/**
 * 当前案件与精算同步的纯规则。
 * 不读页面，也不写入 50 万、默认日期或别的案子的诉请。
 */

export const EMPTY_CASE_FILL_HINT = "请按本案填写";
export const CALC_SYNC_EMPTY_MESSAGE = "还没有可同步的计算结果";

function normalizeText(value) {
  if (value == null) return "";
  return String(value).trim();
}

export function normalizeAmount(value) {
  const text = normalizeText(value).replace(/,/g, "").replace(/^[¥￥]/, "");
  if (!text) return "";
  const num = Number(text);
  if (!Number.isFinite(num)) return text;
  return String(num);
}

function showComparedValue(value) {
  const text = normalizeText(value);
  if (!text) return "（空）";
  return text.length > 36 ? text.slice(0, 36) + "…" : text;
}

/**
 * 只列出已经填写、且会变成另一个值的字段。空表单不构成冲突。
 * fields: [{ label, before, after, kind }]
 */
export function describeCaseOverwrites(fields) {
  const lines = [];
  (fields || []).forEach((field) => {
    const kind = field.kind === "amount" ? "amount" : "text";
    const before = kind === "amount" ? normalizeAmount(field.before) : normalizeText(field.before);
    const after = kind === "amount" ? normalizeAmount(field.after) : normalizeText(field.after);
    if (!before || before === after) return;
    const afterShown = kind === "amount" && after === "0" ? "" : after;
    lines.push(`${field.label}由 ${showComparedValue(before)} 改为 ${showComparedValue(afterShown)}`);
  });
  return lines;
}

export function partyFromMatter(info, fallbackName) {
  const src = info && typeof info === "object" ? info : {};
  return {
    name: normalizeText(fallbackName || src.name),
    id: normalizeText(src.id || src.id_card_or_uscc || src.uscc || src.id_no),
    phone: normalizeText(src.phone),
    address: normalizeText(src.address),
  };
}

function blankInterestCalc() {
  return {
    principal: 0,
    start_date: "",
    end_date: "",
    interest_total: 0,
    formal_statement: "",
    court_fee: 0,
    preservation_fee: 0,
  };
}

/**
 * 用案件空间覆盖工作卡。换到另一件案子时不带走上一件的利息和法条。
 * 本金没录入时金额为 0，不补示例本金。
 */
export function buildCaseContextFromMatter(matter, previous) {
  const source = matter || {};
  const prev = previous || {};
  const same = !!(prev.matter_id && source.matter_id && prev.matter_id === source.matter_id);
  const amount = Number(source.principal_amount);
  return {
    matter_id: source.matter_id || "",
    title: source.title || "",
    cause: source.cause_of_action || "",
    court: source.court_name || "",
    amount: Number.isFinite(amount) ? amount : 0,
    plaintiff: partyFromMatter(source.plaintiff_info, source.plaintiff_name),
    defendant: partyFromMatter(source.defendant_info, source.defendant_name),
    interest_calc: same && prev.interest_calc ? prev.interest_calc : blankInterestCalc(),
    statutes: same && Array.isArray(prev.statutes) ? prev.statutes : [],
    facts: source.summary || source.case_summary || "",
    evidence_notes: same ? (prev.evidence_notes || "") : "",
  };
}

export function parseSyncedInterest(text) {
  const raw = normalizeText(text);
  if (!raw || raw === "—" || raw === "-" || raw === "–" || raw.includes("尚未")) return null;
  const num = Number(raw.replace(/[¥￥,\s元]/g, ""));
  if (!Number.isFinite(num)) return null;
  return num;
}

function usableStatement(statement) {
  const text = normalizeText(statement);
  if (!text) return "";
  if (text.includes("填写本金、期间和计息规则后")) return "";
  if (text.includes("不会预先放一套示例数字")) return "";
  return text;
}

/**
 * 本金、起息日、截止日都空：不生成补丁，调用方不得写入案件。
 * 只带回律师填过的本金和日期，以及本次真正算出的利息、诉讼费。
 */
export function planCalcSync(input) {
  const source = input || {};
  const principalRaw = normalizeText(source.principal);
  const startRaw = normalizeText(source.start);
  const endRaw = normalizeText(source.end);
  const mode = source.mode || "lpr";
  if (!principalRaw && !startRaw && !endRaw) {
    return { ok: false, message: CALC_SYNC_EMPTY_MESSAGE, patch: null };
  }

  const patch = {};
  if (principalRaw) {
    const principal = Number(principalRaw.replace(/,/g, ""));
    if (Number.isFinite(principal)) {
      patch.principal = principal;
      patch.amount = principal;
    }
  }
  if (startRaw) patch.start_date = startRaw;
  if (endRaw) patch.end_date = endRaw;

  if (mode === "lpr") {
    const interest = parseSyncedInterest(source.interestText);
    if (interest != null) patch.interest_total = interest;
    const statement = usableStatement(source.statement);
    if (statement) patch.formal_statement = statement;
  }

  const fee = source.feeSnapshot;
  if (fee && typeof fee === "object") {
    if (fee.actual_fee != null && fee.actual_fee !== "" && Number.isFinite(Number(fee.actual_fee))) {
      patch.court_fee = Number(fee.actual_fee);
    }
    if (fee.preservation_fee != null && fee.preservation_fee !== "" && Number.isFinite(Number(fee.preservation_fee))) {
      patch.preservation_fee = Number(fee.preservation_fee);
    }
  }

  if (!Object.keys(patch).length) {
    return { ok: false, message: CALC_SYNC_EMPTY_MESSAGE, patch: null };
  }
  return { ok: true, message: "", patch };
}
