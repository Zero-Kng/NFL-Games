"""
Fontes de dados do app: arquivos públicos do nflverse (CC-BY-4.0).

Mantém em dados/brutos/ uma cópia validada e atualizada dos arquivos de que o
app precisa. Baixa só o que mudou: compara a data de atualização e o tamanho
de cada arquivo (informados pela API do GitHub) com o manifest.json.

Nunca perde a cópia boa: o download vai para um .tmp, as colunas são
conferidas e só então o arquivo substitui o anterior. Sem internet, o app
segue com o que já tem; sem internet e sem cópia nenhuma, levanta SemDados.

Uso:
    python etl/fontes.py              # sincroniza 2021 até a temporada atual
"""

from __future__ import annotations

import csv
import gzip
import io
import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
DADOS = ROOT / "dados"

# Os únicos endereços que o servidor acessa (requisito S.3).
API = "https://api.github.com/repos/nflverse/nflverse-data/releases/tags/"
DOWNLOAD = "https://github.com/nflverse/nflverse-data/releases/download/"

PRIMEIRA_TEMPORADA = 2021
TIMEOUT_S = 60


@dataclass(frozen=True)
class Fonte:
    nome: str
    release: str
    padrao: str                  # regex do nome do arquivo; o grupo "ano" marca a temporada
    colunas: frozenset[str]      # obrigatórias: sem elas o arquivo é rejeitado
    por_ano: bool = True
    anos_min: int = PRIMEIRA_TEMPORADA   # a fonte só existe a partir deste ano

    def casa(self, arquivo: str) -> int | None | bool:
        """Ano do arquivo (fonte por ano), True (fonte única) ou False (não é desta fonte)."""
        m = re.fullmatch(self.padrao, arquivo)
        if not m:
            return False
        return int(m.group("ano")) if self.por_ano else True


def _c(*nomes: str) -> frozenset[str]:
    return frozenset(nomes)


CATALOGO: list[Fonte] = [
    Fonte("jogos", "schedules", r"games\.csv\.gz",
          _c("game_id", "season", "game_type", "week", "gameday", "gametime", "away_team", "home_team",
             "away_score", "home_score", "overtime", "old_game_id", "espn"), por_ano=False),
    Fonte("jogadores", "players", r"players\.csv\.gz",
          _c("gsis_id", "display_name", "position", "position_group", "pfr_id", "headshot", "height",
             "weight", "college_name", "birth_date"), por_ano=False),
    Fonte("elencos", "rosters", r"roster_(?P<ano>\d{4})\.csv(\.gz)?",
          _c("season", "team", "position", "jersey_number", "gsis_id", "full_name", "depth_chart_position")),
    Fonte("jogadas", "pbp", r"play_by_play_(?P<ano>\d{4})\.csv\.gz",
          _c("game_id", "old_game_id", "play_id", "order_sequence", "season", "week", "qtr", "down", "ydstogo",
             "yardline_100",
             "posteam", "defteam", "play_type", "yards_gained", "desc", "epa", "total_home_score",
             "total_away_score", "time", "pass", "rush", "sack", "interception", "touchdown", "penalty")),
    Fonte("participacao", "pbp_participation", r"pbp_participation_(?P<ano>\d{4})\.csv(\.gz)?",
          _c("old_game_id", "play_id", "offense_formation", "offense_personnel", "defenders_in_box",
             "defense_personnel", "number_of_pass_rushers", "offense_players", "defense_players")),
    Fonte("ftn", "ftn_charting", r"ftn_charting_(?P<ano>\d{4})\.csv(\.gz)?",
          _c("nflverse_game_id", "nflverse_play_id", "qb_location", "n_offense_backfield", "n_defense_box",
             "n_pass_rushers", "starting_hash"), anos_min=2022),
    Fonte("estatisticas", "stats_player", r"stats_player_week_(?P<ano>\d{4})\.csv\.gz",
          _c("player_id", "season", "week", "season_type", "game_id", "team", "opponent_team", "position")),
    Fonte("avancadas_def", "pfr_advstats", r"advstats_week_def_(?P<ano>\d{4})\.csv(\.gz)?",
          _c("game_id", "pfr_player_id", "def_pressures", "def_missed_tackles", "def_targets")),
    Fonte("avancadas_pass", "pfr_advstats", r"advstats_week_pass_(?P<ano>\d{4})\.csv(\.gz)?",
          _c("game_id", "pfr_player_id", "passing_bad_throw_pct", "times_pressured")),
    Fonte("avancadas_rush", "pfr_advstats", r"advstats_week_rush_(?P<ano>\d{4})\.csv(\.gz)?",
          _c("game_id", "pfr_player_id", "rushing_yards_after_contact", "rushing_broken_tackles")),
    Fonte("avancadas_rec", "pfr_advstats", r"advstats_week_rec_(?P<ano>\d{4})\.csv(\.gz)?",
          _c("game_id", "pfr_player_id", "receiving_drop", "receiving_broken_tackles")),
    Fonte("snaps", "snap_counts", r"snap_counts_(?P<ano>\d{4})\.csv(\.gz)?",
          _c("game_id", "pfr_player_id", "position", "team", "offense_snaps", "defense_snaps")),
]


class SemDados(RuntimeError):
    """Sem internet (ou fonte fora do ar) e sem nenhuma cópia local utilizável."""


class ArquivoInvalido(ValueError):
    """O arquivo baixado não tem o formato esperado."""


@dataclass
class Sincronizacao:
    baixados: list[str] = field(default_factory=list)
    falhas: list[str] = field(default_factory=list)
    anos_alterados: set[int] = field(default_factory=set)
    globais_alterados: set[str] = field(default_factory=set)   # fontes únicas (jogos, jogadores)
    sem_rede: bool = False
    segundos: float = 0.0

    @property
    def mudou(self) -> bool:
        return bool(self.baixados)


def temporada_atual(hoje: datetime | None = None) -> int:
    """A temporada da NFL começa em setembro: antes disso, ainda vale a do ano anterior."""
    hoje = hoje or datetime.now(timezone.utc)
    return hoje.year if hoje.month >= 9 else hoje.year - 1


# --------------------------------------------------------------------------- #
# rede (isolada para os testes trocarem o endereço)
# --------------------------------------------------------------------------- #
class Rede:
    def __init__(self, api: str = API, download: str = DOWNLOAD, timeout: float = TIMEOUT_S):
        self.api, self.download, self.timeout = api, download, timeout

    def _abrir(self, url: str):
        if not (url.startswith(self.api) or url.startswith(self.download)):
            raise PermissionError(f"endereço fora das fontes permitidas: {url}")
        req = urllib.request.Request(url, headers={"User-Agent": "nfl-games", "Accept": "*/*"})
        token = os.environ.get("GITHUB_TOKEN")
        if token and url.startswith(self.api):
            # No GitHub Actions (site-publico): sem token, a API limita a 60 chamadas/hora por
            # IP, e os runners dividem IPs. Só a API recebe o token, nunca os downloads.
            req.add_header("Authorization", f"Bearer {token}")
        return urllib.request.urlopen(req, timeout=self.timeout)

    def release(self, tag: str) -> list[dict]:
        """[{name, size, updated_at, url}] dos arquivos da release."""
        try:
            with self._abrir(self.api + tag) as r:
                dados = json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (403, 429) and e.headers.get("X-RateLimit-Remaining") == "0":
                raise ConnectionError("limite de chamadas da API do GitHub atingido") from e
            raise
        return [
            {"name": a["name"], "size": a["size"], "updated_at": a["updated_at"],
             "url": self.download + f"{tag}/{a['name']}"}
            for a in dados.get("assets", [])
        ]

    def baixar(self, url: str, destino: Path) -> None:
        with self._abrir(url) as r, open(destino, "wb") as f:
            while bloco := r.read(1 << 20):
                f.write(bloco)


class SemAcesso(Rede):
    """Modo offline (`serve.py --offline`): o mesmo caminho de "sem internet", sem tocar na rede."""

    def release(self, tag: str) -> list[dict]:
        raise ConnectionError("modo offline")

    def baixar(self, url: str, destino: Path) -> None:
        raise ConnectionError("modo offline")


# --------------------------------------------------------------------------- #
def _cabecalho(caminho: Path) -> list[str]:
    abrir = gzip.open if caminho.name.endswith(".gz") or _eh_gzip(caminho) else open
    with abrir(caminho, "rt", encoding="utf-8", newline="") as f:
        return next(csv.reader(io.StringIO(f.readline())), [])


def _eh_gzip(caminho: Path) -> bool:
    with open(caminho, "rb") as f:
        return f.read(2) == b"\x1f\x8b"


def validar(caminho: Path, fonte: Fonte) -> None:
    try:
        colunas = set(_cabecalho(caminho))
    except (OSError, UnicodeDecodeError, EOFError) as e:
        raise ArquivoInvalido(f"{caminho.name}: ilegível ({e})") from e
    faltam = fonte.colunas - colunas
    if faltam:
        raise ArquivoInvalido(f"{caminho.name}: faltam colunas {sorted(faltam)}")


def _escolher(fonte: Fonte, arquivos: list[dict], anos: range) -> dict[str, dict]:
    """Um arquivo por temporada (ou o único), preferindo a versão .gz."""
    escolhidos: dict[object, dict] = {}
    for a in arquivos:
        chave = fonte.casa(a["name"])
        if chave is False:
            continue
        if fonte.por_ano and (chave not in anos or chave < fonte.anos_min):
            continue
        atual = escolhidos.get(chave)
        if atual is None or (a["name"].endswith(".gz") and not atual["name"].endswith(".gz")):
            escolhidos[chave] = a
    return {a["name"]: a | {"ano": (k if fonte.por_ano else None)} for k, a in escolhidos.items()}


def _ler_manifesto(destino: Path) -> dict:
    try:
        return json.loads((destino / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _gravar_manifesto(destino: Path, manifesto: dict) -> None:
    tmp = destino / "manifest.json.tmp"
    tmp.write_text(json.dumps(manifesto, indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, destino / "manifest.json")


def descartar(destino: Path, anos: set[int]) -> int:
    """
    Apaga os brutos das temporadas dadas (já montadas e encerradas) e marca no
    manifesto `descartado: true`. A sincronização não os baixa de novo, a menos
    que o nflverse os republique. Devolve quantos bytes foram liberados.
    """
    destino = Path(destino)
    manifesto = _ler_manifesto(destino)
    liberado = 0
    for chave, m in manifesto.get("arquivos", {}).items():
        if m.get("ano") in anos and not m.get("descartado"):
            local = destino / "brutos" / chave
            if local.exists():
                liberado += local.stat().st_size
                local.unlink()
            m["descartado"] = True
    _gravar_manifesto(destino, manifesto)
    return liberado


def sincronizar(destino: Path = DADOS, anos: range | None = None, rede: Rede | None = None,
                progresso: Callable[[str], None] = print, forcar: set[int] | None = None) -> Sincronizacao:
    """
    `forcar`: temporadas cujos brutos descartados devem ser baixados de novo
    (por exemplo, para remontar uma temporada cujas tabelas sumiram).
    """
    forcar = forcar or set()
    t0 = time.perf_counter()
    destino = Path(destino)
    anos = anos or range(PRIMEIRA_TEMPORADA, temporada_atual() + 1)
    rede = rede or Rede()
    brutos = destino / "brutos"
    brutos.mkdir(parents=True, exist_ok=True)
    manifesto = _ler_manifesto(destino)
    arquivos_m: dict = manifesto.setdefault("arquivos", {})
    res = Sincronizacao()

    catalogo_por_release: dict[str, list[Fonte]] = {}
    for f in CATALOGO:
        catalogo_por_release.setdefault(f.release, []).append(f)

    for tag, fontes in catalogo_por_release.items():
        if res.sem_rede:
            break
        try:
            remotos = rede.release(tag)
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as e:
            res.sem_rede = True
            res.falhas.append(f"{tag}: sem acesso à fonte ({e})")
            progresso(f"[aviso] sem acesso ao nflverse ({e}); seguindo com a cópia local")
            break
        for fonte in fontes:
            for nome, a in _escolher(fonte, remotos, anos).items():
                local = brutos / tag / nome
                antes = arquivos_m.get(f"{tag}/{nome}")
                igual = bool(antes) and antes.get("updated_at") == a["updated_at"] and antes.get("size") == a["size"]
                descartado_ok = bool(antes) and antes.get("descartado") and a["ano"] not in forcar
                if igual and (local.exists() or descartado_ok):
                    continue
                local.parent.mkdir(parents=True, exist_ok=True)
                tmp = local.with_name(local.name + ".tmp")
                progresso(f"  baixando {tag}/{nome} ({a['size'] / 2**20:.1f} MB)...")
                try:
                    rede.baixar(a["url"], tmp)
                    validar(tmp, fonte)
                except ArquivoInvalido as e:
                    tmp.unlink(missing_ok=True)
                    res.falhas.append(str(e))
                    progresso(f"[erro] {e}; mantendo a cópia anterior")
                    continue
                except (urllib.error.URLError, TimeoutError, OSError) as e:
                    tmp.unlink(missing_ok=True)
                    res.falhas.append(f"{tag}/{nome}: {e}")
                    progresso(f"[aviso] falha ao baixar {tag}/{nome} ({e}); mantendo a cópia anterior")
                    continue
                os.replace(tmp, local)
                arquivos_m[f"{tag}/{nome}"] = {
                    "fonte": fonte.nome, "ano": a["ano"], "updated_at": a["updated_at"], "size": a["size"],
                    "baixadoEm": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                }
                _gravar_manifesto(destino, manifesto)   # progresso salvo arquivo a arquivo
                res.baixados.append(f"{tag}/{nome}")
                if a["ano"] is None:
                    res.globais_alterados.add(fonte.nome)
                else:
                    res.anos_alterados.add(a["ano"])

    faltando = [f.nome for f in CATALOGO if not any(
        m.get("fonte") == f.nome and ((brutos / k).exists() or m.get("descartado"))
        for k, m in arquivos_m.items())]
    if faltando:
        raise SemDados(
            "não há cópia local de: " + ", ".join(faltando)
            + (". Sem acesso à internet para baixar." if res.sem_rede else ".")
        )
    if not res.sem_rede:
        manifesto["ultimaSincronizacao"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        _gravar_manifesto(destino, manifesto)
    res.segundos = time.perf_counter() - t0
    return res


if __name__ == "__main__":
    import sys
    try:
        r = sincronizar(progresso=lambda m: print(m, flush=True))
    except SemDados as e:
        print(f"[erro] {e}", file=sys.stderr)
        raise SystemExit(1)
    print(f"ok em {r.segundos:.0f}s: {len(r.baixados)} baixados, {len(r.falhas)} falhas, "
          f"temporadas alteradas: {sorted(r.anos_alterados)}, globais: {sorted(r.globais_alterados)}")
