import assert from "node:assert/strict";
import fs from "node:fs";
import {
  CALC_SYNC_EMPTY_MESSAGE,
  EMPTY_CASE_FILL_HINT,
  buildCaseContextFromMatter,
  describeCaseOverwrites,
  planCalcSync,
} from "../frontend/js/modules/case_sync_rules.js";

const emptySync = planCalcSync({ principal: "", start: "", end: "", interestText: "—", mode: "lpr" });
assert.equal(emptySync.ok, false);
assert.equal(emptySync.message, CALC_SYNC_EMPTY_MESSAGE);
assert.equal(emptySync.patch, null);
assert.equal(JSON.stringify(emptySync).includes("500000"), false);
assert.equal(JSON.stringify(emptySync).includes("2023-01-01"), false);

const partial = planCalcSync({
  principal: "80000",
  start: "",
  end: "2024-05-01",
  interestText: "—",
  mode: "lpr",
  statement: "填写本金、期间和计息规则后，点击核算。",
  feeSnapshot: { actual_fee: 1800, preservation_fee: 0 },
});
assert.equal(partial.ok, true);
assert.equal(partial.patch.principal, 80000);
assert.equal(partial.patch.amount, 80000);
assert.equal(partial.patch.start_date, undefined);
assert.equal(partial.patch.end_date, "2024-05-01");
assert.equal(partial.patch.interest_total, undefined);
assert.equal(partial.patch.formal_statement, undefined);
assert.equal(partial.patch.court_fee, 1800);

const otherPage = planCalcSync({
  principal: "1000",
  start: "2024-02-02",
  end: "2024-03-03",
  interestText: "2026-11-19",
  mode: "court",
  statement: "这不是利息说明",
});
assert.equal(otherPage.ok, true);
assert.equal(otherPage.patch.interest_total, undefined);
assert.equal(otherPage.patch.formal_statement, undefined);
assert.equal(otherPage.patch.principal, 1000);

const interest = planCalcSync({
  principal: "1000",
  start: "2024-02-02",
  end: "2024-03-03",
  interestText: "¥ 1,234.50",
  mode: "lpr",
  statement: "按本案填写的本金分段计息。",
});
assert.equal(interest.patch.interest_total, 1234.5);
assert.equal(interest.patch.formal_statement, "按本案填写的本金分段计息。");

const lines = describeCaseOverwrites([
  { label: "原告", before: "甲公司", after: "乙公司" },
  { label: "被告", before: "丙", after: "丙" },
  { label: "标的", before: "", after: 200000, kind: "amount" },
  { label: "标的", before: "100", after: 0, kind: "amount" },
]);
assert.deepEqual(lines, ["原告由 甲公司 改为 乙公司", "标的由 100 改为 （空）"]);

const switched = buildCaseContextFromMatter(
  {
    matter_id: "M2",
    title: "乙案",
    cause_of_action: "买卖合同纠纷",
    court_name: "某区人民法院",
    principal_amount: null,
    plaintiff_name: "乙公司",
    defendant_info: { name: "丁公司", phone: "13800000000" },
    summary: "乙公司交货后未收到货款。",
  },
  {
    matter_id: "M1",
    amount: 500000,
    plaintiff: { name: "甲公司" },
    interest_calc: { principal: 500000, start_date: "2023-01-01", interest_total: 1 },
    statutes: [{ id: "old" }],
  },
);
assert.equal(switched.matter_id, "M2");
assert.equal(switched.plaintiff.name, "乙公司");
assert.equal(switched.defendant.name, "丁公司");
assert.equal(switched.defendant.phone, "13800000000");
assert.equal(switched.amount, 0);
assert.equal(switched.court, "某区人民法院");
assert.equal(switched.facts, "乙公司交货后未收到货款。");
assert.equal(switched.interest_calc.interest_total, 0);
assert.equal(switched.interest_calc.start_date, "");
assert.deepEqual(switched.statutes, []);
assert.equal(EMPTY_CASE_FILL_HINT, "请按本案填写");

const matters = fs.readFileSync(new URL("../frontend/js/modules/07_matters.js", import.meta.url), "utf8");
const renderStart = matters.indexOf("function renderWorkflowStepUI");
const renderEnd = matters.indexOf("async function advanceWorkflowStep2UI");
const renderBlock = matters.slice(renderStart, renderEnd);
for (const name of ["wf-claim-item", "wf-statute-item", "wf-counter-item"]) {
  const inputAt = renderBlock.indexOf(`name="${name}"`);
  assert.notEqual(inputAt, -1, name);
  const inputTag = renderBlock.slice(inputAt, renderBlock.indexOf(">", inputAt));
  assert.equal(inputTag.includes("checked"), false, name);
}
assert.equal(renderBlock.includes("EMPTY_CASE_FILL_HINT"), true);
const syncStart = matters.indexOf("function syncCurrentCalcToCaseContext");
const syncEnd = matters.indexOf("function readFieldValue");
const syncBlock = matters.slice(syncStart, syncEnd);
assert.equal(syncBlock.includes("500000"), false);
assert.equal(syncBlock.includes("2023-01-01"), false);
assert.equal(syncBlock.includes("const interestTotal"), false);

const vault = fs.readFileSync(new URL("../gateway/routers/matter_vault.py", import.meta.url), "utf8");
for (const marker of ["3,500,000", "3500000", "14.5%", "共同创业", "EMS催告"]) {
  assert.equal(vault.includes(marker), false, marker);
}

console.log("case sync rules ok");
