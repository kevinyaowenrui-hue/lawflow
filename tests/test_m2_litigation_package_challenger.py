# -*- coding: utf-8 -*-
"""
Challenger 2 Empirical Verification Suite for Milestone M2:
Mobile Court Standard Filing Package (移动微法院标准立案包).

Verifies:
1. POST /api/v1/phase1/generate-litigation-package (spc_mobile & flat)
2. GET /api/v1/phase1/package/{package_id}/download (spc_mobile & flat)
3. GET /api/documents/download/{filename} with .zip extension
4. media_type="application/zip" and valid extractable ZIP archive
5. Edge cases:
   - invalid package_id (must return 404)
   - invalid archive_format (must return 422)
   - empty sub_documents / auto_generate_sub_docs=False
"""
from __future__ import annotations

import io
import os
import zipfile
import pytest


@pytest.fixture
def no_ollama(monkeypatch):
    """Force rule fallback without requiring local Ollama."""
    from gateway.core.ollama_client import ollama_client

    async def _offline(*args, **kwargs):
        return False

    monkeypatch.setattr(ollama_client, "_is_ollama_online", _offline)
    monkeypatch.setattr(ollama_client, "settings", {**ollama_client.settings, "provider": "ollama", "api_key": ""})
    return ollama_client


def _base_payload(archive_format="spc_mobile"):
    return {
        "cause_of_action": "民间借贷纠纷",
        "plaintiff": {
            "name": "挑战者原告甲",
            "id_card_or_uscc": "110101199003072340",
            "address": "北京市朝阳区测试路1号",
            "phone": "13800000001",
        },
        "defendant": {
            "name": "挑战者被告乙有限公司",
            "id_card_or_uscc": "91350100M000100Y43",
            "address": "福州市鼓楼区测试路2号",
            "phone": "13800000002",
            "party_type": "legal",
            "legal_rep": "王某某",
            "rep_position": "执行董事",
        },
        "claims": ["判令被告偿还借款本金 200,000 元"],
        "claim_amount": 200000.0,
        "raw_case_notes": "2023年1月1日被告向原告借款20万元，约定年利率10%，至今未还本付息。",
        "court_name": "北京市朝阳区人民法院",
        "archive_format": archive_format,
        "auto_generate_sub_docs": True,
    }


def test_spc_mobile_package_generation_and_zip_structure(client, no_ollama):
    """验证 POST generate-litigation-package 默认 spc_mobile 结构及 4 个标准目录。"""
    payload = _base_payload(archive_format="spc_mobile")
    resp = client.post("/api/v1/phase1/generate-litigation-package", json=payload)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data.get("package_id"), "Missing package_id"
    assert data.get("package_zip_name"), "Missing package_zip_name"
    assert data.get("package_zip_url"), "Missing package_zip_url"
    assert data.get("package_flat_zip_name"), "Missing package_flat_zip_name"
    assert data.get("package_flat_zip_url"), "Missing package_flat_zip_url"
    assert data.get("package_download_url"), "Missing package_download_url"
    assert "archive_categories" in data, "Missing archive_categories"

    # 验证分类目录字典结构
    categories = data["archive_categories"]
    assert "01_起诉状及身份证明" in categories
    assert "02_委托代理材料" in categories
    assert "03_送达地址确认书" in categories
    assert "04_证据清单与证据材料" in categories

    # 验证通过 documents/download 下载 zip 归档
    zip_resp = client.get(data["package_zip_url"])
    assert zip_resp.status_code == 200, zip_resp.text
    assert zip_resp.headers.get("content-type") == "application/zip"

    # 验证 ZIP 内容结构真实有效
    zf = zipfile.ZipFile(io.BytesIO(zip_resp.content), "r")
    namelist = zf.namelist()
    assert any(n.startswith("01_起诉状及身份证明/") for n in namelist), "Missing category 01"
    assert any(n.startswith("02_委托代理材料/") for n in namelist), "Missing category 02"
    assert any(n.startswith("03_送达地址确认书/") for n in namelist), "Missing category 03"
    assert any(n.startswith("04_证据清单与证据材料/") for n in namelist), "Missing category 04"


def test_flat_package_generation_and_zip_structure(client, no_ollama):
    """验证 flat 格式压缩包包含单层文件且不含目录前缀。"""
    payload = _base_payload(archive_format="flat")
    resp = client.post("/api/v1/phase1/generate-litigation-package", json=payload)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    flat_url = data["package_flat_zip_url"]
    zip_resp = client.get(flat_url)
    assert zip_resp.status_code == 200
    assert zip_resp.headers.get("content-type") == "application/zip"

    zf = zipfile.ZipFile(io.BytesIO(zip_resp.content), "r")
    namelist = zf.namelist()
    assert len(namelist) > 0
    # flat 模式下不应存在目录分级前缀
    for name in namelist:
        assert not name.startswith("01_")
        assert not name.startswith("02_")
        assert not name.startswith("03_")
        assert not name.startswith("04_")


def test_package_download_by_id_spc_and_flat(client, no_ollama):
    """验证 GET /api/v1/phase1/package/{package_id}/download 双格式下载。"""
    payload = _base_payload()
    resp = client.post("/api/v1/phase1/generate-litigation-package", json=payload)
    assert resp.status_code == 200
    pkg_id = resp.json()["package_id"]

    # 1. format=spc_mobile
    r_spc = client.get(f"/api/v1/phase1/package/{pkg_id}/download?format=spc_mobile")
    assert r_spc.status_code == 200
    assert r_spc.headers.get("content-type") == "application/zip"
    zf_spc = zipfile.ZipFile(io.BytesIO(r_spc.content), "r")
    assert any(n.startswith("01_起诉状及身份证明/") for n in zf_spc.namelist())

    # 2. format=flat
    r_flat = client.get(f"/api/v1/phase1/package/{pkg_id}/download?format=flat")
    assert r_flat.status_code == 200
    assert r_flat.headers.get("content-type") == "application/zip"
    zf_flat = zipfile.ZipFile(io.BytesIO(r_flat.content), "r")
    assert not any(n.startswith("01_起诉状及身份证明/") for n in zf_flat.namelist())


def test_edge_case_invalid_format_query_422(client, no_ollama):
    """边缘测试：无效的 format 参数应返回 422。"""
    payload = _base_payload()
    resp = client.post("/api/v1/phase1/generate-litigation-package", json=payload)
    assert resp.status_code == 200
    pkg_id = resp.json()["package_id"]

    r_inv = client.get(f"/api/v1/phase1/package/{pkg_id}/download?format=invalid_format")
    assert r_inv.status_code == 422


def test_edge_case_invalid_archive_format_in_post_422(client, no_ollama):
    """边缘测试：POST 请求体中传递非法 archive_format 应返回 422。"""
    payload = _base_payload(archive_format="tar_gz")
    resp = client.post("/api/v1/phase1/generate-litigation-package", json=payload)
    assert resp.status_code == 422


def test_edge_case_empty_sub_documents(client, no_ollama):
    """边缘测试：空附属文书列表时，归档生成仍应正常完成且 ZIP 可解压。"""
    payload = _base_payload()
    payload["auto_generate_sub_docs"] = False
    payload["sub_documents"] = []
    resp = client.post("/api/v1/phase1/generate-litigation-package", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["generated_documents"]) == 1  # 仅主起诉状

    r_zip = client.get(data["package_zip_url"])
    assert r_zip.status_code == 200
    zf = zipfile.ZipFile(io.BytesIO(r_zip.content), "r")
    assert len(zf.namelist()) >= 4  # 4个目录节点存在


def test_defect_invalid_package_id_must_404(client, no_ollama):
    """
    【关键缺陷检验用例】
    请求不存在的 package_id 时，必须返回 404 Not Found。
    若系统因 fallback 机制返回了其他已存在的 zip 文件，则测试失败！
    """
    # 步骤 1：先正常生成一个合法的包，确保 storage/generated/ 存在 zip 文件
    payload = _base_payload()
    resp = client.post("/api/v1/phase1/generate-litigation-package", json=payload)
    assert resp.status_code == 200

    # 步骤 2：请求一个完全不存在的 package_id
    fake_pkg_id = "pkg-nonexistent-9999999"
    r_fake = client.get(f"/api/v1/phase1/package/{fake_pkg_id}/download?format=spc_mobile")

    # 严格断言：必须返回 404，严禁返回 200
    assert r_fake.status_code == 404, (
        f"安全与接口缺陷：传入不存在的 package_id ({fake_pkg_id}) 时，"
        f"接口未返回 404，而是返回了 {r_fake.status_code}！"
        f"原因：download_litigation_package_zip 盲目回退并返回了磁盘上其他案件的最新 ZIP 包！"
    )
