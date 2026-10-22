# -*- coding: utf-8 -*-
"""批次14 I-35：Stirling/Ollama 探测缓存，一键成套无模型时 <5 秒。"""
from __future__ import annotations

import time

import pytest


def _loan_payload():
    return {
        "cause_of_action": "民间借贷纠纷",
        "claim_amount": 100000.0,
        "raw_case_notes": "出借人向借款人出借人民币10万元，约定一年后还本付息。",
        "court_name": "北京市朝阳区人民法院",
        "claims": ["判令被告偿还借款本金及利息"],
        "auto_generate_sub_docs": True,
        "plaintiff": {
            "name": "测试原告甲",
            "id_card_or_uscc": "110101199003072340",
            "address": "北京市朝阳区测试路1号",
            "phone": "13800000001",
        },
        "defendant": {
            "name": "测试被告乙",
            "id_card_or_uscc": "110101199001011234",
            "address": "北京市海淀区示例街2号",
            "phone": "13900000002",
        },
    }


@pytest.fixture
def unreachable_services(monkeypatch):
    """将 Stirling 与 Ollama 指向未监听端口，禁用 LibreOffice，并重置探测缓存。"""
    import gateway.core.service_probe as probe
    import gateway.routers.phase1_litigation as p1
    from gateway.core.ollama_client import ollama_client

    monkeypatch.setenv("STIRLING_PDF_URL", "http://127.0.0.1:9")
    monkeypatch.setattr(p1, "STIRLING_PDF_URL", "http://127.0.0.1:9")
    monkeypatch.setattr(p1, "_convert_docx_via_soffice", lambda *a, **k: False)

    monkeypatch.setattr(
        ollama_client,
        "settings",
        {
            **ollama_client.settings,
            "provider": "ollama",
            "api_key": "",
            "cloud_consent": False,
            "ollama_base_url": "http://127.0.0.1:9",
        },
    )
    ollama_client._ollama_available = False
    ollama_client._last_ollama_probe = 1e18
    ollama_client.last_llm_mode = "rule_fallback"

    async def _offline(*a, **k):
        return False

    monkeypatch.setattr(ollama_client, "_is_ollama_online", _offline)

    probe.reset_probe_cache()
    return probe


def test_litigation_package_fast_with_unreachable_services(client, unreachable_services, monkeypatch):
    probe = unreachable_services
    calls = {"stirling": 0}

    real_probe = probe.probe_stirling_pdf

    def counting_probe(force: bool = False):
        # 仅在实际发起探测时计数（缓存命中不计入）
        cache = probe._cache
        now = time.time()
        ttl = probe._ttl_seconds()
        cached = (
            not force
            and cache.get("stirling") is not None
            and (now - float(cache.get("stirling_at", 0))) < ttl
        )
        if not cached:
            calls["stirling"] += 1
        return real_probe(force=force)

    monkeypatch.setattr(probe, "probe_stirling_pdf", counting_probe)
    # is_stirling_available 默认调用 probe_stirling_pdf
    monkeypatch.setattr(probe, "is_stirling_available", lambda force=False: counting_probe(force=force))
    probe.reset_probe_cache()

    t0 = time.perf_counter()
    r1 = client.post("/api/v1/phase1/generate-litigation-package", json=_loan_payload())
    elapsed = time.perf_counter() - t0
    assert r1.status_code == 200, r1.text
    data = r1.json()
    assert elapsed < 5.0, f"一键成套耗时 {elapsed:.2f}s，应 < 5s"
    es = data.get("engine_status") or {}
    assert es.get("pdf") == "local_pymupdf", es

    after_first = calls["stirling"]
    assert after_first == 1, f"首次应探测一次，实际 {after_first}"

    r2 = client.post("/api/v1/phase1/generate-litigation-package", json=_loan_payload())
    assert r2.status_code == 200, r2.text
    assert calls["stirling"] == 1, f"连续两次调用应只探测一次，实际 {calls['stirling']}"
