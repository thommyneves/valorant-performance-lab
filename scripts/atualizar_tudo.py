from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"


def run(script: str) -> None:
    subprocess.run([sys.executable, str(SCRIPTS / script)], cwd=ROOT, check=True)


if __name__ == "__main__":
    run("atualizar_vlr.py")
    run("atualizar_tracker.py")
    run("preparar_site.py")
    print("Dados do VLR e Tracker atualizados e site preparado.")
