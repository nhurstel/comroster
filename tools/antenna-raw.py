#!/usr/bin/env python3
"""Dump du JSON BRUT de l'antenne Bolero — pour identifier les vrais noms de champs.

Interroge directement l'antenne (pas ComRoster) et affiche la structure complète
de /rest/nodeStatus (état live des beltpacks connectés) et /rest/bp (config).
Sert à trouver où se cache l'info de réception radio sur TON firmware.

    python3 tools/antenna-raw.py <ip-antenne> [mot-de-passe]

Exemple : python3 tools/antenna-raw.py 192.168.31.11 monMotDePasse

Copie-colle la sortie (au moins un beltpack connecté dans nodeStatus) pour qu'on
identifie le champ de signal/qualité radio.
"""
import base64
import json
import sys
import urllib.request

if len(sys.argv) < 2:
    print(__doc__)
    sys.exit(1)

IP = sys.argv[1]
PW = sys.argv[2] if len(sys.argv) > 2 else ""


def get(path):
    req = urllib.request.Request(f"http://{IP}{path}")
    if PW:
        creds = base64.b64encode(f"admin:{PW}".encode()).decode()
        req.add_header("Authorization", f"Basic {creds}")
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read().decode())


for path in ("/rest/nodeStatus", "/rest/bp"):
    print(f"\n{'=' * 60}\n{path}\n{'=' * 60}")
    try:
        print(json.dumps(get(path), indent=2, ensure_ascii=False))
    except Exception as exc:  # noqa: BLE001 — outil de diagnostic
        print(f"⚠️  échec : {exc}")
