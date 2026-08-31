from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
DATA = ROOT / "data"
SEASON_ID = "8102cd81-43a0-d0d7-bd59-47b8fe9bed1b"
ACCOUNTS = [
    ("elsewhere", "elsewhere#999t", "elsewhere"),
    ("dead-eyes", "dead eyes#999t", "dead eyes"),
    ("taylorswiftfan13", "taylorswiftfan13#lari", "taylorswiftfan13"),
]
VLR_PLAYERS = [
    ("thommy", "51239", "thommy"),
    ("fracarissa", "45269", "fracarissa"),
]


def pending(riot_id: str) -> dict:
    return {
        "status": "pending",
        "metadata": {
            "jogador": riot_id,
            "season_id": SEASON_ID,
            "gerado_em": None,
            "quantidade_agentes": 0,
            "quantidade_mapas": 0,
        },
        "agentes": {"top_5": [], "ranking_completo": [], "criterio_top_5": {"minimo_partidas": 5}},
        "mapas": {"ranking": []},
        "resumo": {"melhor_agente_geral": None, "melhor_mapa": None, "pior_mapa": None},
    }


def pending_vlr(slug: str, player_id: str, label: str) -> dict:
    return {
        "status": "pending_stats",
        "maps": [], "agents": [], "top5": [], "data": [],
        "profile": {
            "player_id": player_id, "slug": slug, "name": label, "real_name": "",
            "aliases": [], "country": "", "avatar": "",
            "profile_url": f"https://www.vlr.gg/player/{player_id}/{slug}/?timespan=all",
            "socials": [], "total_winnings": "$0",
            "current_teams": [], "past_teams": [], "event_placements": [],
        },
        "career": {"totalWinnings": "$0", "currentTeams": [], "pastTeams": [], "placements": [], "eventsPlayed": []},
        "meta": {"updatedAt": None, "player": label, "playerId": player_id, "slug": slug,
                 "profileUrl": f"https://www.vlr.gg/player/{player_id}/{slug}/?timespan=all"},
    }


def main() -> None:
    (SITE / "data" / "tracker").mkdir(parents=True, exist_ok=True)
    (SITE / "data" / "vlr").mkdir(parents=True, exist_ok=True)

    # VLR: copia as bases persistentes individuais e cria um manifest público.
    source_manifest_path = DATA / "vlr_players.json"
    source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8")) if source_manifest_path.exists() else {}
    source_by_slug = {p.get("slug"): p for p in source_manifest.get("players", [])}
    vlr_manifest = {"updated_at": datetime.now().astimezone().isoformat(timespec="seconds"), "players": []}
    for slug, player_id, label in VLR_PLAYERS:
        src = DATA / "vlr" / f"{slug}.json"
        dst = SITE / "data" / "vlr" / f"{slug}.json"
        if src.exists():
            shutil.copy2(src, dst)
        elif not dst.exists():
            dst.write_text(json.dumps(pending_vlr(slug, player_id, label), ensure_ascii=False, indent=2), encoding="utf-8")
        manifest_row = source_by_slug.get(slug, {})
        vlr_manifest["players"].append({
            "slug": slug,
            "player_id": player_id,
            "player_slug": slug,
            "label": label,
            "data_file": f"vlr/{slug}.json",
            "profile_url": f"https://www.vlr.gg/player/{player_id}/{slug}/?timespan=all",
            "status": manifest_row.get("status", json.loads(dst.read_text(encoding="utf-8")).get("status", "ready")),
        })
    (SITE / "data" / "vlr_players.json").write_text(json.dumps(vlr_manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    # Legacy para links antigos que ainda esperam data/vlr.json.
    thommy_src = DATA / "vlr" / "thommy.json"
    if thommy_src.exists():
        shutil.copy2(thommy_src, SITE / "data" / "vlr.json")

    tracker_manifest = {
        "season_id": SEASON_ID,
        "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "accounts": [],
    }
    for slug, riot_id, label in ACCOUNTS:
        dst = SITE / "data" / "tracker" / f"{slug}.json"
        src = DATA / "tracker" / slug / "tracker_insights.json"
        if src.exists():
            shutil.copy2(src, dst)
        if not dst.exists():
            dst.write_text(json.dumps(pending(riot_id), ensure_ascii=False, indent=2), encoding="utf-8")
        tracker_manifest["accounts"].append({
            "slug": slug,
            "riot_id": riot_id,
            "label": label,
            "data_file": f"tracker/{slug}.json",
            "profile_url": "",
            "status": json.loads(dst.read_text(encoding="utf-8")).get("status", "ready"),
        })
    (SITE / "data" / "tracker_accounts.json").write_text(
        json.dumps(tracker_manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
