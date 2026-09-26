"""
Esquema ilustrativo da formação de uma jogada (spec dados-externos, Requisito 4).

Sem tracking, a prancheta coloca os jogadores reais da jogada (participação do
nflverse) em posições-modelo da formação. Sai no mesmo formato do /tracking,
com 1 quadro e `ilustrativo: true`, para o Field atual desenhar sem mudança.

Coordenadas do dataset antigo: x de 0 a 120 no comprimento, y de 0 a 53,3;
o ataque joga para +x (`playDirection = "right"`), e a esquerda do ataque é o
y pequeno. Sem a lista de jogadores (2026, só FTN), sai um esquema genérico,
sem nomes nem números (`generico: true`). Sem formação nenhuma: None.
"""

from __future__ import annotations

import math

LARGURA = 53.3
HASH = {"L": 23.58, "M": LARGURA / 2, "R": LARGURA - 23.58}   # marcas a 70'9" das laterais

# "No box": até 7 jd da linha e dentro da largura da linha ofensiva estendida.
BOX_PROF, BOX_LARG = 7.0, 5.0

# Profundidade do QB (jd atrás da linha) pelo qb_location do FTN ou pela formação.
# Sob o center, 2 jd: a OL está a 1 jd, e o QB colado nela ficaria em cima do C.
PROF_QB = {"S": 5.0, "P": 4.0, "U": 2.0}
FORMACAO_QB = {"SHOTGUN": "S", "EMPTY": "S", "WILDCAT": "S", "PISTOL": "P",
               "UNDER CENTER": "U", "SINGLEBACK": "U", "I_FORM": "U", "JUMBO": "U"}
NOME_QB = {"S": "SHOTGUN", "P": "PISTOL", "U": "UNDER CENTER"}
# Onde ficam os backs: (jd atrás da linha, deslocamento lateral em relação à bola)
BACKS = {"S": [(5.0, 1.5), (5.0, -1.5), (3.0, 0.0)],
         "P": [(6.0, 0.0), (4.0, 1.5), (4.0, -1.5)],
         "U": [(6.0, 0.0), (3.5, 0.0), (3.5, 1.5), (3.5, -1.5)]}   # sob o center: RB a 6 e FB a 3,5 (I-form)

# Posição da fonte -> papel no desenho (as listas às vezes trazem posições "trocadas")
PAPEL_ATAQUE = {**dict.fromkeys(["C"], "C"), **dict.fromkeys(["G"], "G"), **dict.fromkeys(["T", "OL"], "T"),
                **dict.fromkeys(["DL", "DE", "DT", "NT", "LS"], "extra"),
                **dict.fromkeys(["TE", "LB", "ILB", "OLB", "MLB"], "TE"),
                "RB": "RB", "FB": "FB", "QB": "QB"}                      # o resto: WR
PAPEL_DEFESA = {**dict.fromkeys(["DL", "DE", "DT", "NT", "OL", "C", "G", "T", "LS"], "DL"),
                **dict.fromkeys(["LB", "ILB", "OLB", "MLB", "TE", "FB", "RB", "QB"], "LB"),
                **dict.fromkeys(["CB", "WR"], "CB"), **dict.fromkeys(["S", "FS", "SS", "K", "P"], "S"),
                "DB": "DB"}
ORDEM_OL = {"C": 0, "G": 1, "T": 2, "extra": 3}


def _vazio(v) -> bool:
    return v is None or (isinstance(v, float) and math.isnan(v)) or (isinstance(v, str) and not v.strip())


def _lista(v) -> list[str | None]:
    return [] if _vazio(v) else [(s.strip() or None) for s in str(v).split(";")]


def _int(v):
    try:
        return None if _vazio(v) else int(float(v))
    except ValueError:
        return None


def _y(y: float) -> float:
    return round(min(max(y, 1.0), LARGURA - 1.0), 2)


def _x(x: float) -> float:
    return round(min(max(x, 0.5), 119.5), 2)


def _jogadores(jogada: dict, lado: str) -> list[dict]:
    pre = "of" if lado == "offense" else "def"
    pos = _lista(jogada.get(f"{pre}_posicoes"))
    ids, nomes, nums = (_lista(jogada.get(f"{pre}_{c}")) for c in ("ids", "nomes", "numeros"))
    pega = lambda xs, i: xs[i] if i < len(xs) else None  # noqa: E731
    return [{"id": pega(ids, i), "name": pega(nomes, i), "jersey": _int(pega(nums, i)), "position": p or "?"}
            for i, p in enumerate(pos)]


def _generico(jogada: dict, qb: str) -> tuple[list[dict], list[dict]]:
    backs = _int(jogada.get("backfield"))
    backs = 1 if backs is None else min(backs, 4)
    ataque = ["OL"] * 5 + ["QB"] + ["RB"] * backs + ["WR"] * max(0, 11 - 6 - backs)
    frente = _int(jogada.get("box"))
    frente = 7 if frente is None else min(frente, 11)
    atras = 11 - frente
    seg = 2 if atras >= 4 else 1 if atras == 3 else 0
    defesa = (["DL"] * min(4, frente) + ["LB"] * max(0, frente - 4) + ["CB"] * (atras - seg) + ["S"] * seg)
    vira = lambda ps: [{"id": None, "name": None, "jersey": None, "position": p} for p in ps]  # noqa: E731
    return vira(ataque), vira(defesa)


def _espalhar(n: int, passo: float, meia_largura: float) -> list[float]:
    """n deslocamentos simétricos em torno de 0, sem passar de ±meia_largura."""
    if n <= 1:
        return [0.0] * n
    passo = min(passo, 2 * meia_largura / (n - 1))
    return [(i - (n - 1) / 2) * passo for i in range(n)]


def _ataque(jog: list[dict], los: float, yb: float, qb: str) -> list[tuple[dict, float, float]]:
    papel = lambda p: PAPEL_ATAQUE.get(p["position"], "WR")  # noqa: E731
    out = []
    # linha ofensiva: C no meio, G, T e extras para fora
    ol = sorted((p for p in jog if papel(p) in ORDEM_OL), key=lambda p: ORDEM_OL[papel(p)])
    vagas_ol = [0.0] + [s * 1.2 * k for k in range(1, 6) for s in (-1, 1)]
    for p, dy in zip(ol, vagas_ol):
        out.append((p, los - 1, yb + dy))
    borda = max((abs(d) for d in vagas_ol[:len(ol)]), default=0.0) + 1.5
    # TE colado ao T (primeiro à direita), depois de wing
    for k, p in enumerate(p for p in jog if papel(p) == "TE"):
        lado = 1 if k % 2 == 0 else -1
        out.append((p, los - 1 - (k // 2), yb + lado * (borda + 1.5 * (k // 2))))
    # QB e backs; um segundo QB vai para fora como recebedor
    qbs = [p for p in jog if papel(p) == "QB"]
    if qbs:
        out.append((qbs[0], los - PROF_QB[qb], yb))
    vagas_b = BACKS[qb] + [(3.0 + k, 3.0 * (-1) ** k) for k in range(8)]
    backs = sorted((p for p in jog if papel(p) in ("RB", "FB")), key=lambda p: papel(p) == "FB")
    if qb == "U" and backs and papel(backs[0]) == "FB":      # só FB sob o center: ele fica a 3 jd
        vagas_b = vagas_b[1:]
    for p, (prof, dy) in zip(backs, vagas_b):
        out.append((p, los - prof, yb + dy))
    # recebedores abertos, alternando lados: fora a 5 jd da lateral, slot a 13 jd, depois 18
    wrs = qbs[1:] + [p for p in jog if papel(p) == "WR"]
    vagas_wr = [(1.0, y) for y in (5.0, LARGURA - 5.0)] + [(1.5, y) for y in (13.0, LARGURA - 13.0, 18.0,
                                                                               LARGURA - 18.0)]
    vagas_wr += [(2.5, y) for y in (9.0, LARGURA - 9.0)] * 4
    for p, (prof, y) in zip(wrs, vagas_wr):
        out.append((p, los - prof, y))
    return out


def _defesa(jog: list[dict], los: float, yb: float, wrs_y: list[float], box: int | None):
    papel = {id(p): PAPEL_DEFESA.get(p["position"], "LB") for p in jog}
    dbs = [p for p in jog if papel[id(p)] == "DB"]          # 2021-22: DB sem CB × S
    n_s = 2 if len(dbs) >= 4 else 1 if len(dbs) == 3 else 0
    for k, p in enumerate(dbs):
        papel[id(p)] = "S" if k >= len(dbs) - n_s else "CB"
    grupo = lambda g: [p for p in jog if papel[id(p)] == g]  # noqa: E731
    pos = {}                                                  # id(jogador) -> [x, y]
    dl, lb, cb, s = grupo("DL"), grupo("LB"), grupo("CB"), grupo("S")
    for p, dy in zip(dl, _espalhar(len(dl), 2.0, BOX_LARG - 0.2)):
        pos[id(p)] = [los + 1, yb + dy]
    for p, dy in zip(lb, _espalhar(len(lb), 3.0, BOX_LARG - 0.5)):
        pos[id(p)] = [los + 4.5, yb + dy]
    # CB espelhando os recebedores (os mais abertos primeiro), depois nas laterais livres
    abertos = sorted(wrs_y, key=lambda y: -abs(y - yb))
    livres = [y for y in (5.0, LARGURA - 5.0) if all(abs(y - w) > 1 for w in abertos)]
    extras = [yb + lado * (BOX_LARG + 3 + k) for k in range(6) for lado in (1, -1)]
    for p, y in zip(cb, abertos + livres + extras):
        pos[id(p)] = [los + 6, y]
    for p, dy in zip(s, _espalhar(len(s), 16.0 if len(s) == 2 else 10.0, 10.0)):
        pos[id(p)] = [los + 12, yb + dy]

    if box is not None:                      # o desenho respeita o número de defensores no box
        alvo = min(box, len(jog))
        dentro = dl + lb                     # DL e LB começam todos no box
        # faltam: os DBs mais perto da bola descem para o box
        laterais = (4.5, -4.5, 3.0, -3.0, 1.5, -1.5, 0.0)
        candidatos = sorted(s + cb, key=lambda p: abs(pos[id(p)][1] - yb) + (0 if papel[id(p)] == "S" else 50))
        for k, p in enumerate(candidatos[:max(0, alvo - len(dentro))]):
            pos[id(p)] = [los + 6 + 0.5 * (k // len(laterais)), yb + laterais[k % len(laterais)]]
        # sobram: primeiro os LBs, depois a DL, dos mais abertos para o meio, saem para fora do box
        sobra = len(dentro) - alvo
        fora = {1: 0, -1: 0}                 # quantos já saíram por lado, para não empilhar
        for grupo_, prof in ((lb, 5.0), (dl, 1.0)):
            for p in sorted(grupo_, key=lambda p: -abs(pos[id(p)][1] - yb)):
                if sobra <= 0:
                    break
                lado = 1 if pos[id(p)][1] >= yb else -1
                pos[id(p)] = [los + prof, yb + lado * (BOX_LARG + 2.5 + 1.5 * fora[lado])]
                fora[lado] += 1
                sobra -= 1
    return [(p, x, y) for p in jog for x, y in [pos[id(p)]]]


def esquema(jogada: dict) -> dict | None:
    """Mesmo formato de /tracking com 1 quadro: players[{nflId, name, jersey,
    position, side, team, t:[[x, y, 0, 0, 0]]}], ball, lineOfScrimmage,
    yardsToGo, frameCount=1, ilustrativo=True. None se não houver formação."""
    formacao = None if _vazio(jogada.get("formacao")) else str(jogada["formacao"]).strip().upper()
    qb_ftn = None if _vazio(jogada.get("qb_local")) else str(jogada["qb_local"]).strip().upper()
    qb = qb_ftn if qb_ftn in PROF_QB else FORMACAO_QB.get(formacao) if formacao else None
    if formacao is None and qb is None:
        return None
    qb = qb or "S"
    jarda = jogada.get("yardline_100")
    if _vazio(jarda):
        return None
    los = 110.0 - float(jarda)
    hash_ = None if _vazio(jogada.get("hash")) else str(jogada["hash"]).strip().upper()
    yb = HASH.get(hash_, HASH["M"])

    ataque, defesa = _jogadores(jogada, "offense"), _jogadores(jogada, "defense")
    generico = not ataque or not defesa
    if generico:
        ataque, defesa = _generico(jogada, qb)

    pos_at = _ataque(ataque, los, yb, qb)
    wrs_y = [y for p, _, y in pos_at if PAPEL_ATAQUE.get(p["position"], "WR") == "WR"]
    pos_df = _defesa(defesa, los, yb, wrs_y, _int(jogada.get("box")))

    players, usados = [], set()
    for lado, time_, lista in (("offense", jogada.get("posteam"), pos_at), ("defense", jogada.get("defteam"), pos_df)):
        for k, (p, x, y) in enumerate(lista, 1):
            nfl_id = p["id"] if p["id"] and p["id"] not in usados else f"{lado}-{k}"
            usados.add(nfl_id)
            players.append({"nflId": nfl_id, "name": p["name"], "jersey": p["jersey"], "position": p["position"],
                            "side": lado, "team": None if _vazio(time_) else str(time_), "role": None,
                            "linedUp": None, "rating": None, "t": [[_x(x), _y(y), 0, 0, 0]]})
    return {
        "gameId": _int(jogada.get("gameId")), "playId": _int(jogada.get("play_id")),
        "fps": 10, "frameCount": 1, "playDirection": "right", "snapIndex": 0, "releaseIndex": None,
        "lineOfScrimmage": los, "yardsToGo": _int(jogada.get("ydstogo")),
        "players": players, "ball": [[los, round(yb, 2)]], "events": [],
        "ilustrativo": True, "generico": generico,
        "formacao": {"nome": formacao or NOME_QB[qb],
                     "pessoalAtaque": None if _vazio(jogada.get("pessoal_of")) else jogada["pessoal_of"],
                     "pessoalDefesa": None if _vazio(jogada.get("pessoal_def")) else jogada["pessoal_def"],
                     "box": _int(jogada.get("box")), "rushers": _int(jogada.get("rushers"))},
    }
