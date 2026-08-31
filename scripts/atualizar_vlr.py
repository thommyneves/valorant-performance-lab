from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Iterable

import requests
from bs4 import BeautifulSoup, Tag

BASE = "https://www.vlr.gg"
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "vlr"
LEGACY_DB_FILE = ROOT / "data" / "vlr.json"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151 Safari/537.36"
    )
}

PLAYERS = [
    {
        "slug": "thommy",
        "player_id": "51239",
        "player_slug": "thommy",
        "label": "thommy",
        "profile_url": f"{BASE}/player/51239/thommy/?timespan=all",
    },
    {
        "slug": "fracarissa",
        "player_id": "45269",
        "player_slug": "fracarissa",
        "label": "fracarissa",
        "profile_url": f"{BASE}/player/45269/fracarissa/?timespan=all",
    },
]

SECTION_LABELS = {
    "current teams",
    "past teams",
    "event placements",
    "recent results",
    "agents",
    "news",
}


def clean(text: str | None) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def number(text: str):
    text = clean(text).replace("%", "").replace(",", ".")
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    return float(match.group()) if match else None


def absolute_url(value: str | None) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    if value.startswith("//"):
        return "https:" + value
    if value.startswith("/"):
        return BASE + value
    return value


def get(url: str) -> BeautifulSoup:
    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")


def player_profile_soup(player: dict) -> BeautifulSoup:
    return get(player["profile_url"])


def extract_match_links(soup: BeautifulSoup) -> list[str]:
    """Extrai links reais de partidas do VLR e remove query strings/duplicatas."""
    links: list[str] = []
    seen: set[str] = set()

    # Nas páginas /player/matches os cards de resultado usam wf-card/m-item.
    # O fallback em todos os anchors deixa o coletor resistente a pequenas mudanças no HTML.
    anchors = soup.select('a.wf-card.m-item[href], a[href^="/"]')
    for link in anchors:
        href = clean(link.get("href", ""))
        if not href:
            continue
        href = href.split("?", 1)[0].split("#", 1)[0].rstrip("/")
        # Partidas do VLR têm o formato /<id-numérico>/<slug-da-partida>.
        if not re.fullmatch(r"/\d{4,}/[^/]+", href):
            continue
        slug = href.rsplit("/", 1)[-1].casefold()
        if any(word in slug for word in ("player", "team", "event", "rankings", "stats", "matches", "search")):
            continue
        if href not in seen:
            seen.add(href)
            links.append(href)
    return links


def match_links_for_player(player: dict, profile_soup: BeautifulSoup | None = None) -> list[str]:
    """Busca TODO o histórico do jogador em /player/matches, incluindo paginação."""
    collected: list[str] = []
    seen: set[str] = set()
    page = 1

    while page <= 30:
        base = f"{BASE}/player/matches/{player['player_id']}/{player['player_slug']}"
        url = base if page == 1 else f"{base}/?page={page}"
        try:
            soup = get(url)
        except requests.RequestException as exc:
            print(f"Aviso ao abrir histórico VLR ({url}): {exc}")
            break

        page_links = extract_match_links(soup)
        new_links = [href for href in page_links if href not in seen]
        print(f"Página {page}: {len(page_links)} partidas encontradas ({len(new_links)} novas)")

        if not new_links:
            break

        for href in new_links:
            seen.add(href)
            collected.append(href)

        # VLR costuma indicar a próxima página por <link rel=next> ou botão de paginação.
        next_link = soup.find("link", rel=lambda value: value and "next" in value)
        next_button = soup.select_one(f'a[href*="page={page + 1}"]')
        if not next_link and not next_button:
            break
        page += 1

    # Fallback: se a página de histórico falhar, ainda tenta os Recent Results do perfil.
    if not collected and profile_soup is not None:
        collected = extract_match_links(profile_soup)
        if collected:
            print(f"Fallback pelo perfil: {len(collected)} partidas encontradas")

    return collected


KNOWN_MAPS = [
    "Abyss", "Ascent", "Bind", "Breeze", "Corrode", "Fracture", "Haven",
    "Icebox", "Lotus", "Pearl", "Split", "Sunset", "Summit", "District",
    "Kasbah", "Piazza", "Drift", "Glitch",
]


def find_map_name(container: Tag) -> str:
    """Lê o nome do mapa usando a mesma estrutura que funcionou no scraper isolado."""
    selectors = [
        ".vm-stats-game-header",
        ".vm-stats-game-header-name",
        ".vm-stats-game-header-item",
        ".map",
        ".map-header",
    ]
    for selector in selectors:
        for element in container.select(selector):
            text = clean(element.get_text(" ", strip=True))
            for map_name in KNOWN_MAPS:
                if re.search(rf"\b{re.escape(map_name)}\b", text, re.I):
                    return map_name

    for element in container.find_all(["div", "span", "a"]):
        text = clean(element.get_text(" ", strip=True))
        if not text or len(text) > 100:
            continue
        for map_name in KNOWN_MAPS:
            if re.search(rf"\b{re.escape(map_name)}\b", text, re.I):
                return map_name
    return ""


def find_player_row(container: Tag, player: dict) -> Tag | None:
    """VLR usa linhas .ovw-row (divs), não uma tabela tr/td tradicional."""
    rows = container.select(".ovw-row")
    player_id = str(player["player_id"])
    player_name = str(player["player_slug"]).casefold()

    # Mais confiável: ID no link do jogador.
    for row in rows:
        for link in row.select('a[href*="/player/"]'):
            href = clean(link.get("href", ""))
            if re.match(rf"^/player/{re.escape(player_id)}(?:/|$)", href):
                return row

    # Fallback igual ao script que funcionou no teste do usuário.
    for row in rows:
        for element in row.select(".ovw-player-name"):
            name = clean(element.get_text(" ", strip=True)).casefold()
            if name == player_name:
                return row

    for row in rows:
        if player_name in clean(row.get_text(" ", strip=True)).casefold():
            return row
    return None


def agent_from_row(row: Tag) -> str:
    # Nas linhas ovw-row, as imagens da célula de agentes carregam title/alt com o nome.
    selectors = [".mod-agents img", ".mod-agent img", ".agent img", ".wf-module-item img"]
    for selector in selectors:
        for img in row.select(selector):
            value = clean(img.get("title") or img.get("alt") or "")
            if value:
                return value.title()

    for img in row.find_all("img"):
        value = clean(img.get("title") or img.get("alt") or "")
        if value:
            return value.title()
    return ""


def _first_int(text: str) -> int | None:
    match = re.search(r"-?\d+", clean(text))
    return int(match.group()) if match else None


def _first_float(text: str) -> float | None:
    match = re.search(r"-?\d+(?:\.\d+)?", clean(text))
    return float(match.group()) if match else None


def _first_percent(text: str) -> float | None:
    match = re.search(r"(\d+(?:\.\d+)?)%", clean(text))
    return float(match.group(1)) / 100 if match else None


def extract_statistics(row: Tag) -> dict | None:
    """Extrai a coluna All das stats R/ACS/KDA/KAST/ADR/HS/FK/FD.

    O HTML do VLR junta All/Attack/Defend dentro de cada div, por exemplo:
    `10 6 4/16 8 8/4 2 2` significa K=10, D=16, A=4 no total.
    """
    texts = []
    for div in row.find_all("div", recursive=False):
        text = clean(div.get_text(" ", strip=True))
        if text:
            texts.append(text)

    kda_index = None
    for i, text in enumerate(texts):
        groups = text.split("/")
        if len(groups) != 3:
            continue
        if all(re.search(r"\d", group) for group in groups):
            kda_index = i
            break
    if kda_index is None:
        return None

    rating_index = None
    for i in range(max(0, kda_index - 5), kda_index):
        first = texts[i].split()[0] if texts[i].split() else ""
        if re.fullmatch(r"\d+\.\d+", first):
            rating_index = i
            break
    if rating_index is None:
        return None

    acs_index = None
    for i in range(rating_index + 1, kda_index):
        first = texts[i].split()[0] if texts[i].split() else ""
        if re.fullmatch(r"\d+", first):
            acs_index = i
            break
    if acs_index is None:
        return None

    kast_index = None
    for i in range(kda_index + 1, len(texts)):
        if re.search(r"\d+(?:\.\d+)?%", texts[i]):
            kast_index = i
            break
    if kast_index is None:
        return None

    adr_index = None
    for i in range(kast_index + 1, len(texts)):
        if re.match(r"^\s*\d+(?:\.\d+)?(?:\s|$)", texts[i]):
            adr_index = i
            break
    if adr_index is None:
        return None

    hs_index = None
    for i in range(adr_index + 1, len(texts)):
        if re.search(r"\d+(?:\.\d+)?%", texts[i]):
            hs_index = i
            break
    if hs_index is None:
        return None

    numeric_after_hs = []
    for i in range(hs_index + 1, len(texts)):
        if re.match(r"^\s*[+-]?\d+(?:\s|$)", texts[i]):
            numeric_after_hs.append(i)
        if len(numeric_after_hs) >= 2:
            break
    if len(numeric_after_hs) < 2:
        return None
    fk_index, fd_index = numeric_after_hs[:2]

    groups = texts[kda_index].split("/")
    kills = _first_int(groups[0])
    deaths = _first_int(groups[1])
    assists = _first_int(groups[2])
    rating = _first_float(texts[rating_index])
    acs = _first_int(texts[acs_index])
    kast = _first_percent(texts[kast_index])
    adr = _first_float(texts[adr_index])
    hs = _first_percent(texts[hs_index])
    fk = _first_int(texts[fk_index])
    fd = _first_int(texts[fd_index])

    required = (rating, acs, kills, deaths, assists, kast, adr, hs, fk, fd)
    if any(value is None for value in required):
        return None

    return {
        "rating": float(rating),
        "acs": int(acs),
        "k": int(kills),
        "d": int(deaths),
        "a": int(assists),
        "kast": float(kast),
        "adr": float(adr),
        "hs": float(hs),
        "fk": int(fk),
        "fd": int(fd),
    }


def parse_match(href: str, player: dict) -> list[dict]:
    """Extrai cada mapa usando a estrutura .vm-stats-game + .ovw-row do VLR."""
    soup = get(BASE + href)
    records: list[dict] = []
    games = soup.select(".vm-stats-game") or soup.select("[data-game-id]")

    for game in games:
        game_id = clean(game.get("data-game-id", ""))
        if game_id.casefold() in {"all", "0"}:
            continue

        map_name = find_map_name(game)
        if not map_name:
            continue

        row = find_player_row(game, player)
        if row is None:
            continue

        stats = extract_statistics(row)
        agent = agent_from_row(row)
        if not stats or not agent:
            continue

        records.append({
            "map": map_name,
            "agent": agent,
            **stats,
            "url": BASE + href,
        })

    return records

def section_links(soup: BeautifulSoup, label: str, href_prefix: str) -> list[Tag]:
    """Collect anchors after a visible VLR section label until the next major label."""
    wanted = label.casefold()
    label_node = soup.find(
        string=lambda value: isinstance(value, str) and clean(value).casefold() == wanted
    )
    if not label_node:
        return []

    heading = label_node.parent
    items: list[Tag] = []
    seen: set[int] = set()
    for node in heading.find_all_next():
        if node is heading:
            continue
        text = clean(node.get_text(" ", strip=True)).casefold()
        classes = " ".join(node.get("class", [])) if isinstance(node, Tag) else ""
        if (
            text in SECTION_LABELS
            and text != wanted
            and ("wf-label" in classes or node.name in {"h1", "h2", "h3", "h4"})
        ):
            break
        if node.name == "a" and str(node.get("href", "")).startswith(href_prefix):
            marker = id(node)
            if marker not in seen:
                seen.add(marker)
                items.append(node)
    return items


def parse_team_item(item: Tag) -> dict:
    logo_node = item.select_one("img")
    logo = absolute_url(logo_node.get("src", "") if logo_node else "")
    light_parts = [clean(node.get_text(" ", strip=True)) for node in item.select(".ge-text-light")]
    light_parts = [part for part in light_parts if part]
    status_node = item.select_one(".wf-tag.mod-light")
    status = clean(status_node.get_text(" ", strip=True) if status_node else "")
    full_text = clean(item.get_text(" ", strip=True))
    name = full_text
    for remove in [status, *light_parts]:
        if remove:
            name = name.replace(remove, " ", 1)
    name = clean(name)
    href = absolute_url(item.get("href", ""))
    return {
        "name": name,
        "status": status,
        "dates": " · ".join(light_parts),
        "logo": logo,
        "url": href,
    }


def parse_teams(soup: BeautifulSoup) -> tuple[list[dict], list[dict]]:
    current = [parse_team_item(item) for item in section_links(soup, "Current Teams", "/team/")]
    past = [parse_team_item(item) for item in section_links(soup, "Past Teams", "/team/")]

    # Fallback for layout variations: at least preserve team links from the summary area.
    if not current and not past:
        container = soup.select_one(".player-summary-container-1")
        if container:
            raw = [parse_team_item(item) for item in container.select('a[href^="/team/"]')]
            if raw:
                current = raw[:1]
                past = raw[1:]
    return current, past


def ordinal_match(text: str):
    return re.search(r"\b\d+(?:st|nd|rd|th)(?:\s*[–—-]\s*\d+(?:st|nd|rd|th))?\b", text, re.I)


def parse_event_placements(soup: BeautifulSoup) -> list[dict]:
    placements: list[dict] = []
    for item in soup.select(".wf-module-item.player-event-item"):
        event_node = item.select_one(".text-of")
        event = clean(event_node.get_text(" ", strip=True) if event_node else "")
        item_text = clean(item.get_text(" ", strip=True))
        year_match = re.findall(r"\b20\d{2}\b", item_text)
        year = year_match[-1] if year_match else ""
        href = absolute_url(item.get("href", ""))

        detail_nodes = []
        for node in item.select(".ge-text-light"):
            detail = clean(node.get_text(" ", strip=True))
            if detail and ordinal_match(detail):
                detail_nodes.append(node)

        if not detail_nodes:
            # Keep the event card even if VLR changes the placement class.
            match = ordinal_match(item_text)
            if match:
                placements.append({
                    "event": event,
                    "series": "",
                    "placement": clean(match.group(0)),
                    "prize": clean(re.search(r"\$[\d,]+", item_text).group(0)) if re.search(r"\$[\d,]+", item_text) else "",
                    "team": "",
                    "year": year,
                    "url": href,
                })
            continue

        for detail_node in detail_nodes:
            detail_text = clean(detail_node.get_text(" ", strip=True))
            placement_match = ordinal_match(detail_text)
            if not placement_match:
                continue
            placement = clean(placement_match.group(0))
            series = clean(detail_text[:placement_match.start()].rstrip("–—- "))

            # Usually each placement line is wrapped in its own row. Walk up a few levels
            # and use the smallest parent containing the detail plus useful team/prize text.
            candidates: list[str] = []
            parent = detail_node.parent
            for _ in range(4):
                if not isinstance(parent, Tag) or parent is item:
                    break
                candidate = clean(parent.get_text(" ", strip=True))
                if candidate:
                    candidates.append(candidate)
                parent = parent.parent
            line_text = next((c for c in candidates if c != detail_text and len(c) <= 180), item_text)
            prize_match = re.search(r"\$[\d,]+", line_text)
            prize = prize_match.group(0) if prize_match else ""

            team = line_text
            for remove in [event, detail_text, series, placement, prize, year]:
                if remove:
                    team = team.replace(remove, " ", 1)
            team = clean(re.sub(r"^[–—-]+|[–—-]+$", "", team))
            # If the selected parent was too broad, avoid showing the whole card as a team.
            if len(team) > 80 or ordinal_match(team):
                team = ""

            placements.append({
                "event": event,
                "series": series,
                "placement": placement,
                "prize": prize,
                "team": team,
                "year": year,
                "url": href,
            })
    return placements


def parse_total_winnings(soup: BeautifulSoup, placements: Iterable[dict]) -> str:
    # VLR's total is the largest dollar amount visible in the placement card for these profiles.
    # Prefer text near the label when available, then fall back to the whole page.
    label_node = soup.find(string=lambda value: isinstance(value, str) and clean(value).casefold() == "total winnings")
    scopes: list[Tag | BeautifulSoup] = []
    if label_node:
        parent = label_node.parent
        for _ in range(4):
            if isinstance(parent, Tag):
                scopes.append(parent)
                parent = parent.parent
    scopes.append(soup)

    for scope in scopes:
        text = clean(scope.get_text(" ", strip=True))
        amounts = [int(x.replace(",", "")) for x in re.findall(r"\$([\d,]+)", text)]
        if amounts:
            # If we're in a compact earnings scope, the first/largest value is the total.
            return f"${max(amounts):,}"

    amounts = []
    for row in placements:
        prize = row.get("prize", "")
        m = re.search(r"\$([\d,]+)", prize)
        if m:
            amounts.append(int(m.group(1).replace(",", "")))
    return f"${sum(amounts):,}" if amounts else "$0"


def parse_profile(soup: BeautifulSoup, player: dict) -> dict:
    name_node = soup.select_one("h1.wf-title") or soup.select_one(".wf-title")
    real_name_node = soup.select_one(".player-real-name")
    avatar_node = soup.select_one(".wf-avatar.mod-player img")
    header = soup.select_one(".player-header")

    name = clean(name_node.get_text(" ", strip=True) if name_node else player["label"])
    real_name = clean(real_name_node.get_text(" ", strip=True) if real_name_node else "")
    avatar = absolute_url(avatar_node.get("src", "") if avatar_node else "")

    aliases: list[str] = []
    # Keep alias parsing scoped to the DOM node that actually contains the label.
    # This avoids accidentally appending the country or social text on profiles
    # whose header layout differs slightly.
    alias_text_node = soup.find(
        string=lambda value: isinstance(value, str) and "aliases:" in value.casefold()
    )
    if alias_text_node:
        alias_parent_text = clean(alias_text_node.parent.get_text(" ", strip=True))
        alias_parts = re.split(r"aliases?:", alias_parent_text, flags=re.I, maxsplit=1)
        if len(alias_parts) == 2:
            alias_text = clean(alias_parts[1].lstrip("–—- "))
            aliases = [clean(x) for x in alias_text.split(",") if clean(x)]

    country = ""
    flag = header.select_one(".flag") if header else None
    if flag:
        country = clean(flag.get("title") or flag.get("alt") or flag.get_text(" ", strip=True))
        if not country:
            classes = flag.get("class", [])
            mod = next((x[4:] for x in classes if x.startswith("mod-")), "")
            country = mod.upper()

    socials = []
    for link in soup.select("a.social"):
        href = absolute_url(link.get("href", ""))
        if href:
            socials.append({"label": clean(link.get_text(" ", strip=True)), "url": href})

    current_teams, past_teams = parse_teams(soup)
    placements = parse_event_placements(soup)
    total_winnings = parse_total_winnings(soup, placements)

    return {
        "player_id": player["player_id"],
        "slug": player["slug"],
        "name": name or player["label"],
        "real_name": real_name,
        "aliases": aliases,
        "country": country,
        "avatar": avatar,
        "profile_url": player["profile_url"],
        "socials": socials,
        "total_winnings": total_winnings,
        "current_teams": current_teams,
        "past_teams": past_teams,
        "event_placements": placements,
    }


def avg(rows, key):
    return mean(float(row[key]) for row in rows)


def build_db(data: list[dict], player: dict, profile: dict) -> dict:
    data.sort(key=lambda row: (row.get("url", ""), row["map"]), reverse=True)
    for index, row in enumerate(data, 1):
        row["id"] = index

    agents = []
    for agent_name in sorted({row["agent"] for row in data}):
        rows = [row for row in data if row["agent"] == agent_name]
        kd = sum(row["k"] for row in rows) / max(1, sum(row["d"] for row in rows))
        fkfd = sum(row["fk"] for row in rows) / max(1, sum(row["fd"] for row in rows))
        map_ratings = {}
        for map_name in {row["map"] for row in rows}:
            map_rows = [row for row in rows if row["map"] == map_name]
            map_ratings[map_name] = avg(map_rows, "rating")
        best_map = max(map_ratings, key=map_ratings.get)
        agents.append({
            "agent": agent_name,
            "games": len(rows),
            "rating": avg(rows, "rating"),
            "acs": avg(rows, "acs"),
            "k": avg(rows, "k"),
            "d": avg(rows, "d"),
            "a": avg(rows, "a"),
            "kd": kd,
            "hs": avg(rows, "hs"),
            "fk": avg(rows, "fk"),
            "fd": avg(rows, "fd"),
            "fkfd": fkfd,
            "bestMap": best_map,
            "bestMapRating": map_ratings[best_map],
        })
    agents.sort(key=lambda row: row["rating"], reverse=True)

    maps = []
    for map_name in sorted({row["map"] for row in data}):
        candidates = []
        for agent_name in {row["agent"] for row in data if row["map"] == map_name}:
            rows = [row for row in data if row["map"] == map_name and row["agent"] == agent_name]
            candidates.append((avg(rows, "rating"), agent_name, rows))
        rating, agent_name, rows = max(candidates)
        maps.append({
            "map": map_name,
            "agent": agent_name,
            "games": len(rows),
            "rating": rating,
            "acs": avg(rows, "acs"),
            "k": avg(rows, "k"),
            "d": avg(rows, "d"),
            "a": avg(rows, "a"),
            "hs": avg(rows, "hs"),
            "fk": avg(rows, "fk"),
            "fd": avg(rows, "fd"),
        })
    maps.sort(key=lambda row: row["rating"], reverse=True)

    eligible = [row for row in agents if row["games"] >= 5]

    def norm(value, values):
        lo, hi = min(values), max(values)
        return 50 if hi == lo else (value - lo) / (hi - lo) * 100

    top5 = []
    if eligible:
        metrics = {key: [row[key] for row in eligible] for key in ("rating", "acs", "kd", "fkfd", "games")}
        ranked = []
        for row in eligible:
            score = (
                .35 * norm(row["rating"], metrics["rating"])
                + .20 * norm(row["kd"], metrics["kd"])
                + .20 * norm(row["acs"], metrics["acs"])
                + .15 * norm(row["fkfd"], metrics["fkfd"])
                + .10 * norm(row["games"], metrics["games"])
            )
            ranked.append((score, row))
        for rank, (score, row) in enumerate(sorted(ranked, reverse=True, key=lambda item: item[0])[:5], 1):
            top5.append({
                **row,
                "rank": rank,
                "score": score,
                "bestRating": row["bestMapRating"],
                "why": (
                    f"Combina rating {row['rating']:.3f}, K:D {row['kd']:.2f}, "
                    f"ACS {row['acs']:.1f} e experiência em {row['games']} mapas."
                ),
                "attention": "Use o histórico por mapa para conferir consistência e tamanho da amostra.",
            })

    unique_events = []
    seen_events = set()
    for placement in profile.get("event_placements", []):
        event = placement.get("event", "")
        if event and event not in seen_events:
            seen_events.add(event)
            unique_events.append(event)

    return {
        "maps": maps,
        "agents": agents,
        "top5": top5,
        "data": data,
        "career": {
            "totalWinnings": profile.get("total_winnings", "$0"),
            "currentTeams": profile.get("current_teams", []),
            "pastTeams": profile.get("past_teams", []),
            "placements": profile.get("event_placements", []),
            "eventsPlayed": unique_events,
        },
        "profile": profile,
        "meta": {
            "updatedAt": datetime.now().astimezone().isoformat(),
            "player": profile.get("name") or player["label"],
            "playerId": player["player_id"],
            "slug": player["slug"],
            "profileUrl": player["profile_url"],
        },
    }


def load_old_db(player: dict) -> dict:
    db_file = DATA_DIR / f"{player['slug']}.json"
    if db_file.exists():
        return json.loads(db_file.read_text(encoding="utf-8"))
    if player["slug"] == "thommy" and LEGACY_DB_FILE.exists():
        return json.loads(LEGACY_DB_FILE.read_text(encoding="utf-8"))
    return {"data": []}


def update_player(player: dict, max_matches: int | None = None) -> dict:
    print(f"\n=== VLR {player['label']} ({player['player_id']}) ===")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    old = load_old_db(player)
    soup = player_profile_soup(player)
    profile = parse_profile(soup, player)
    links = match_links_for_player(player, soup)
    if max_matches is not None:
        links = links[:max_matches]

    known_urls = {row.get("url", "") for row in old.get("data", []) if row.get("url")}
    fresh: list[dict] = []
    print(f"Total de partidas no histórico: {len(links)}")
    for index, href in enumerate(links, 1):
        match_url = BASE + href
        if match_url in known_urls:
            continue
        print(f"[{index}/{len(links)}] {href}")
        try:
            parsed = parse_match(href, player)
            if parsed:
                fresh.extend(parsed)
                print(f"  -> {len(parsed)} mapa(s) lido(s)")
            else:
                print("  -> aviso: nenhuma stat de mapa encontrada para este jogador")
        except requests.RequestException as exc:
            print(f"Aviso: {exc}")

    merged = {(row.get("url", ""), row.get("map", "")): row for row in old.get("data", [])}
    for row in fresh:
        merged[(row["url"], row["map"])] = row

    db = build_db(list(merged.values()), player, profile)
    db_file = DATA_DIR / f"{player['slug']}.json"
    db_file.write_text(json.dumps(db, ensure_ascii=False, indent=2), encoding="utf-8")
    if player["slug"] == "thommy":
        LEGACY_DB_FILE.write_text(json.dumps(db, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        f"Concluído: {len(fresh)} mapas novos; {len(db['data'])} registros; "
        f"{len(db['career']['placements'])} colocações."
    )
    return db


def write_manifest(statuses: dict[str, str] | None = None) -> None:
    statuses = statuses or {}
    manifest = {
        "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "players": [
            {
                **player,
                "data_file": f"vlr/{player['slug']}.json",
                "status": statuses.get(player["slug"], "ready"),
            }
            for player in PLAYERS
        ],
    }
    (ROOT / "data" / "vlr_players.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def main():
    parser = argparse.ArgumentParser(description="Atualiza dados VLR dos jogadores configurados.")
    parser.add_argument(
        "--player",
        choices=[player["slug"] for player in PLAYERS],
        help="Atualiza somente um jogador (ex.: --player fracarissa).",
    )
    parser.add_argument(
        "--max-matches",
        type=int,
        default=None,
        help="Limita o número de partidas para teste. Sem este argumento, processa todo o histórico.",
    )
    args = parser.parse_args()

    selected = [p for p in PLAYERS if not args.player or p["slug"] == args.player]
    statuses: dict[str, str] = {}
    errors = []

    for player in selected:
        try:
            update_player(player, max_matches=args.max_matches)
            statuses[player["slug"]] = "ready"
        except Exception as exc:
            statuses[player["slug"]] = "error"
            errors.append((player["label"], exc))
            print(f"ERRO em {player['label']}: {exc}", file=sys.stderr)

    # Preserve o status dos jogadores que não foram selecionados no manifest.
    for player in PLAYERS:
        statuses.setdefault(player["slug"], "ready")
    write_manifest(statuses)

    if errors and len(errors) == len(selected):
        raise RuntimeError("Nenhum perfil VLR selecionado pôde ser atualizado.")


if __name__ == "__main__":
    main()
