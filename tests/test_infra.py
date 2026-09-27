"""Garante que a infraestrutura de teste (tarefa 1.1) funciona."""

from conftest import http_json


def test_fixture_servidor_responde_meta(servidor):
    status, meta = http_json(servidor.url + "/api/meta")
    assert status == 200
    assert meta["season"] >= 2026 and len(meta["seasons"]) >= 6


# ------------------------------------------------ site-publico, tarefa 6
def test_workflow_pages():
    """Publicação diária no GitHub Pages: gatilhos, permissões mínimas e passos (design, componente 6)."""
    import yaml
    from conftest import ROOT
    texto = (ROOT / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")
    wf = yaml.safe_load(texto)
    gatilhos = wf.get("on", wf.get(True))                  # o YAML 1.1 lê a chave "on" como True
    assert gatilhos["schedule"] == [{"cron": "0 10 * * *"}]
    assert gatilhos["push"]["branches"] == ["main"]
    assert set(gatilhos["push"]["paths"]) == {"app/**", "server/**", "etl/**", "tools/exportar.py",
                                              ".github/workflows/pages.yml"}
    assert "workflow_dispatch" in gatilhos
    assert wf["permissions"] == {"contents": "read", "pages": "write", "id-token": "write"}
    assert wf["concurrency"]["group"] == "pages"
    passos = [p for job in wf["jobs"].values() for p in job["steps"]]
    ordem = [next((i for i, p in enumerate(passos) if alvo in (p.get("run", "") + p.get("uses", ""))), None)
             for alvo in ("etl/montar.py", "tools/exportar.py", "actions/upload-pages-artifact", "actions/deploy-pages")]
    assert None not in ordem and ordem == sorted(ordem), ordem
    upload = next(p for p in passos if "upload-pages-artifact" in p.get("uses", ""))
    assert upload["with"]["path"] == "site"
    assert "git push" not in texto and "contents: write" not in texto
