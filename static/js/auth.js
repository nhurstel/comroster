/* Face avant des pages d'authentification : le voyant du bandeau et l'horloge
 * du pied.
 *
 * Pourquoi ce fichier existe : un disque qui respire dans un bandeau est un
 * ORNEMENT, et un ornement qui ressemble à une mesure est interdit ici (leçon
 * 2026-07-28 — c'est ce qui a fait retirer le filet du Journal et les faux
 * « [ OK ] » de l'ancien écran de démarrage). Le voyant ne se justifie que s'il
 * mesure quelque chose, donc il sonde.
 *
 * Ce qu'il dit, exactement : « le ComRoster répond MAINTENANT ». Au chargement
 * c'est trivialement vrai — la page vient d'en sortir. Son intérêt est la suite :
 * un poste de régie laissé sur cet écran voit le voyant tomber quand le boîtier
 * s'arrête, au lieu d'afficher un formulaire mort d'apparence normale.
 *
 * Sondage borné à la visibilité du document (leçon 2026-07-30 : une boucle qui
 * avait le droit de tourner dans une page dédiée ne l'a plus quand personne ne
 * regarde) — sur un Raspberry Pi, une requête toutes les 10 s pour un onglet en
 * arrière-plan est une dépense sans contrepartie.
 */
(function () {
    "use strict";

    var led = document.getElementById("auth-led");
    var etat = document.getElementById("auth-state");
    var horloge = document.getElementById("auth-clock");

    var PERIODE_MS = 10000;
    var enVol = false;

    function poser(nom, texte) {
        if (led) { led.dataset.state = nom; }
        if (etat) { etat.textContent = texte; }
    }

    function sonder() {
        // `enVol` évite d'empiler les requêtes quand le réseau traîne : sans lui,
        // un boîtier lent accumulerait une sonde par battement.
        if (document.hidden || enVol) { return; }
        enVol = true;
        fetch("/healthz", { cache: "no-store" })
            .then(function (r) {
                if (!r.ok) { throw new Error(String(r.status)); }
                poser("on", "ComRoster en ligne");
            })
            .catch(function () {
                poser("off", "ComRoster injoignable");
            })
            .finally(function () { enVol = false; });
    }

    function tic() {
        if (!horloge) { return; }
        // toLocaleTimeString et non un assemblage maison : l'heure d'une interface
        // francophone se rend dans sa locale (leçon 2026-07-28).
        horloge.textContent = new Date().toLocaleTimeString("fr-FR");
    }

    tic();
    setInterval(tic, 1000);

    sonder();
    setInterval(sonder, PERIODE_MS);
    // Revenir sur l'onglet doit rafraîchir tout de suite : attendre le prochain
    // battement afficherait jusqu'à 10 s d'état périmé au moment précis où
    // quelqu'un regarde.
    document.addEventListener("visibilitychange", function () {
        if (!document.hidden) { sonder(); }
    });
})();
