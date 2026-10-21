# -*- coding: utf-8 -*-
"""I-19：同一秒内连续建案 ID 不冲突。"""
from __future__ import annotations


def test_two_matters_same_second_unique_ids(client):
    payload = {
        "title": "并发测试案",
        "cause_of_action": "民间借贷纠纷",
    }
    r1 = client.post("/api/v1/vault/matters", json=payload)
    r2 = client.post("/api/v1/vault/matters", json=payload)
    assert r1.status_code == 200, r1.text
    assert r2.status_code == 200, r2.text

    def _id(resp):
        body = resp.json()
        m = body.get("matter") or body.get("data") or body
        return m.get("matter_id")

    id1, id2 = _id(r1), _id(r2)
    assert id1 and id2
    assert id1 != id2
