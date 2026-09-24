"""Metadados das 32 franquias (nome, apelido e cores oficiais aproximadas)."""

TEAMS: dict[str, dict[str, str]] = {
    "ARI": {"name": "Arizona Cardinals", "nick": "Cardinals", "primary": "#97233F", "secondary": "#FFB612"},
    "ATL": {"name": "Atlanta Falcons", "nick": "Falcons", "primary": "#A71930", "secondary": "#000000"},
    "BAL": {"name": "Baltimore Ravens", "nick": "Ravens", "primary": "#241773", "secondary": "#9E7C0C"},
    "BUF": {"name": "Buffalo Bills", "nick": "Bills", "primary": "#00338D", "secondary": "#C60C30"},
    "CAR": {"name": "Carolina Panthers", "nick": "Panthers", "primary": "#0085CA", "secondary": "#101820"},
    "CHI": {"name": "Chicago Bears", "nick": "Bears", "primary": "#0B162A", "secondary": "#C83803"},
    "CIN": {"name": "Cincinnati Bengals", "nick": "Bengals", "primary": "#FB4F14", "secondary": "#000000"},
    "CLE": {"name": "Cleveland Browns", "nick": "Browns", "primary": "#311D00", "secondary": "#FF3C00"},
    "DAL": {"name": "Dallas Cowboys", "nick": "Cowboys", "primary": "#041E42", "secondary": "#869397"},
    "DEN": {"name": "Denver Broncos", "nick": "Broncos", "primary": "#0C2340", "secondary": "#FC4C02"},
    "DET": {"name": "Detroit Lions", "nick": "Lions", "primary": "#0076B6", "secondary": "#B0B7BC"},
    "GB": {"name": "Green Bay Packers", "nick": "Packers", "primary": "#203731", "secondary": "#FFB612"},
    "HOU": {"name": "Houston Texans", "nick": "Texans", "primary": "#03202F", "secondary": "#A71930"},
    "IND": {"name": "Indianapolis Colts", "nick": "Colts", "primary": "#002C5F", "secondary": "#A2AAAD"},
    "JAX": {"name": "Jacksonville Jaguars", "nick": "Jaguars", "primary": "#006778", "secondary": "#D7A22A"},
    "KC": {"name": "Kansas City Chiefs", "nick": "Chiefs", "primary": "#E31837", "secondary": "#FFB81C"},
    "LA": {"name": "Los Angeles Rams", "nick": "Rams", "primary": "#003594", "secondary": "#FFA300"},
    "LAC": {"name": "Los Angeles Chargers", "nick": "Chargers", "primary": "#0080C6", "secondary": "#FFC20E"},
    "LV": {"name": "Las Vegas Raiders", "nick": "Raiders", "primary": "#101820", "secondary": "#A5ACAF"},
    "MIA": {"name": "Miami Dolphins", "nick": "Dolphins", "primary": "#008E97", "secondary": "#FC4C02"},
    "MIN": {"name": "Minnesota Vikings", "nick": "Vikings", "primary": "#4F2683", "secondary": "#FFC62F"},
    "NE": {"name": "New England Patriots", "nick": "Patriots", "primary": "#002244", "secondary": "#C60C30"},
    "NO": {"name": "New Orleans Saints", "nick": "Saints", "primary": "#101820", "secondary": "#D3BC8D"},
    "NYG": {"name": "New York Giants", "nick": "Giants", "primary": "#0B2265", "secondary": "#A71930"},
    "NYJ": {"name": "New York Jets", "nick": "Jets", "primary": "#125740", "secondary": "#000000"},
    "PHI": {"name": "Philadelphia Eagles", "nick": "Eagles", "primary": "#004C54", "secondary": "#A5ACAF"},
    "PIT": {"name": "Pittsburgh Steelers", "nick": "Steelers", "primary": "#101820", "secondary": "#FFB612"},
    "SEA": {"name": "Seattle Seahawks", "nick": "Seahawks", "primary": "#002244", "secondary": "#69BE28"},
    "SF": {"name": "San Francisco 49ers", "nick": "49ers", "primary": "#AA0000", "secondary": "#B3995D"},
    "TB": {"name": "Tampa Bay Buccaneers", "nick": "Buccaneers", "primary": "#D50A0A", "secondary": "#34302B"},
    "TEN": {"name": "Tennessee Titans", "nick": "Titans", "primary": "#0C2340", "secondary": "#4B92DB"},
    "WAS": {"name": "Washington Football Team", "nick": "Washington", "primary": "#5A1414", "secondary": "#FFB612"},
}


def team_info(abbr: str) -> dict[str, str]:
    base = TEAMS.get(abbr, {"name": abbr, "nick": abbr, "primary": "#013369", "secondary": "#D50A0A"})
    return {"abbr": abbr, **base}
