from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
DATA_ROOT = ROOT / "data" / "tracker"
SITE_ROOT = ROOT / "site" / "data" / "tracker"
SEASON_ID = "8102cd81-43a0-d0d7-bd59-47b8fe9bed1b"

ACCOUNTS = [
    {"slug": "elsewhere", "riot_id": "elsewhere#999t", "label": "elsewhere"},
    {"slug": "dead-eyes", "riot_id": "dead eyes#999t", "label": "dead eyes"},
    {"slug": "taylorswiftfan13", "riot_id": "taylorswiftfan13#lari", "label": "taylorswiftfan13"},
]


def tracker_url(riot_id: str) -> str:
    profile = quote(riot_id, safe="")
    return (
        f"https://tracker.gg/valorant/profile/riot/{profile}/overview"
        f"?platform=pc&playlist=competitive&season={SEASON_ID}"
    )


def run(cmd: list[str]) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=ROOT, check=True)


def pending_payload(account: dict, error: str | None = None) -> dict:
    return {
        "status": "pending" if not error else "error",
        "error": error,
        "metadata": {
            "jogador": account["riot_id"],
            "season_id": SEASON_ID,
            "gerado_em": datetime.now().astimezone().isoformat(timespec="seconds"),
            "quantidade_agentes": 0,
            "quantidade_mapas": 0,
        },
        "agentes": {"top_5": [], "ranking_completo": [], "criterio_top_5": {"minimo_partidas": 5}},
        "mapas": {"ranking": []},
        "resumo": {"melhor_agente_geral": None, "melhor_mapa": None, "pior_mapa": None},
    }


def ensure_manifest(results: dict[str, dict]) -> None:
    manifest = {
        "season_id": SEASON_ID,
        "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "accounts": [],
    }
    for account in ACCOUNTS:
        payload = results.get(account["slug"], {})
        manifest["accounts"].append(
            {
                **account,
                "profile_url": tracker_url(account["riot_id"]),
                "data_file": f"tracker/{account['slug']}.json",
                "status": payload.get("status", "ready"),
            }
        )
    SITE_ROOT.parent.mkdir(parents=True, exist_ok=True)
    (SITE_ROOT.parent / "tracker_accounts.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def main() -> int:
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    SITE_ROOT.mkdir(parents=True, exist_ok=True)
    results: dict[str, dict] = {}
    failures = 0

    for account in ACCOUNTS:
        slug = account["slug"]
        raw_dir = DATA_ROOT / slug
        raw_json = raw_dir / "tracker_dados.json"
        insights_json = raw_dir / "tracker_insights.json"
        public_json = SITE_ROOT / f"{slug}.json"
        print("\n" + "=" * 72)
        print(f"Atualizando Tracker: {account['riot_id']}")

        try:
            run([
                sys.executable,
                str(SCRIPTS / "puxar_tracker.py"),
                "--riot-id", account["riot_id"],
                "--season-id", SEASON_ID,
                "--saida", str(raw_dir),
            ])
            run([
                sys.executable,
                str(SCRIPTS / "analisar_tracker.py"),
                str(raw_json),
                "-o", str(insights_json),
                "--dashboard", str(public_json),
            ])
            payload = json.loads(public_json.read_text(encoding="utf-8"))
            payload["status"] = "ready"
            payload["profile_url"] = tracker_url(account["riot_id"])
            public_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            results[slug] = payload
        except Exception as exc:
            failures += 1
            print(f"AVISO: falha ao atualizar {account['riot_id']}: {exc}", file=sys.stderr)
            if public_json.exists():
                try:
                    payload = json.loads(public_json.read_text(encoding="utf-8"))
                    payload.setdefault("status", "stale")
                    payload["profile_url"] = tracker_url(account["riot_id"])
                    results[slug] = payload
                    continue
                except Exception:
                    pass
            payload = pending_payload(account, str(exc))
            payload["profile_url"] = tracker_url(account["riot_id"])
            public_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            results[slug] = payload

    ensure_manifest(results)
    print(f"\nTracker concluído: {len(ACCOUNTS) - failures} sucesso(s), {failures} falha(s).")
    # Não falha o deploy inteiro se o Tracker bloquear uma conta; o site preserva dados anteriores.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
