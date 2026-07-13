#!/usr/bin/env python3
"""Sonde de calibrage de la réception beltpack.

Affiche en direct le `raw_signal` (signalLevel BRUT renvoyé par l'antenne Bolero)
de chaque beltpack connecté, à côté des barres actuellement calculées. Sert à
CALIBRER les seuils de `_signal_bars` dans comroster/services/antenna.py.

Prérequis : ComRoster tourne et l'antenne est connectée (via l'admin).
Lancer sur le Pi (ou toute machine qui joint le serveur) :

    python3 tools/signal-probe.py
    python3 tools/signal-probe.py http://192.168.1.50:8080   # serveur distant

Mode d'emploi : pose un beltpack tout près de l'antenne, note son `raw`.
Éloigne-le progressivement (autre pièce, derrière un mur…), note le `raw` à
chaque « niveau » de réception, jusqu'à la limite de décrochage. Communique
ces relevés → on ajuste les seuils. Ctrl+C pour arrêter.
"""
import json
import sys
import time
import urllib.request

BASE = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://127.0.0.1:8080"
if not BASE.startswith(("http://", "https://")):
    BASE = "http://" + BASE    # tolère « 192.168.1.50:8080 » sans le schéma
URL = BASE + "/api/live"       # endpoint public (pas d'authentification)


def fetch():
    with urllib.request.urlopen(URL, timeout=4) as r:
        return json.load(r)


def main():
    print(f"Sonde réception → {URL}   (Ctrl+C pour arrêter)\n")
    while True:
        try:
            data = fetch()
        except Exception as exc:  # noqa: BLE001 — outil de diagnostic, on tolère tout
            print(f"\r⚠️  serveur/antenne injoignable : {exc}", end="", flush=True)
            time.sleep(2)
            continue

        bps = data.get("beltpacks", {})
        online = {n: i for n, i in bps.items() if i.get("online")}
        print("\033[2J\033[H", end="")   # efface l'écran
        print(f"Sonde réception → {URL}\n")
        print(f"{'BP':>4} | {'raw_signal':>10} | {'barres':>6} | {'batterie':>8} | {'charge':>6}")
        print("-" * 52)
        if not online:
            print("(aucun beltpack en ligne — allume-en un et rapproche-le de l'antenne)")
        for num in sorted(online, key=lambda x: int(x) if x.isdigit() else 0):
            info = online[num]
            raw = info.get("raw_signal")
            bars = info.get("signal")
            batt = info.get("battery")
            chg = "⚡" if info.get("charging") else ""
            print(f"{num:>4} | {str(raw):>10} | {str(bars):>6} | "
                  f"{(str(batt) + '%') if batt is not None else '—':>8} | {chg:>6}")
        print("\nÉloigne un beltpack et note le 'raw_signal' à chaque niveau de réception.")
        time.sleep(1.5)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nArrêt.")
