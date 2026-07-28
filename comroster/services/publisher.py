"""Publication du brouillon vers l'affichage — chemin partagé.

Utilisé par l'API (`POST /api/publish`, action explicite « Envoyer ») et par
l'auto-sync du roster (live_poller). Centralise la séquence enregistrer +
archiver + diffuser pour qu'il n'existe qu'une seule façon de publier.
"""


def broadcast_published(app, state, label="", pinned=False):
    """Enregistre l'état publié, l'archive dans l'historique et le diffuse (SSE).

    `label` / `pinned` : point de repère facultatif (« Filage », « Générale »). Jamais
    posés par l'auto-sync, qui publie en continu — un repère est une intention
    d'opérateur, pas un effet de bord du réseau intercom.
    """
    app.extensions["storage"].save_published(state)
    app.extensions["history"].archive(state, label=label, pinned=pinned)
    app.extensions["broker"].publish("published", state)
