"""Garante que a infraestrutura de teste (tarefa 1.1) funciona."""

from conftest import http_json


def test_fixture_servidor_responde_meta(servidor):
    status, meta = http_json(servidor.url + "/api/meta")
    assert status == 200
    assert meta["counts"]["games"] == 122
