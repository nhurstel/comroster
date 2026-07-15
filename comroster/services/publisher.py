"""Publication du brouillon vers l'affichage — chemin partagé.

Utilisé par l'API (`POST /api/publish`, action explicite « Envoyer ») et par
l'auto-sync du roster (live_poller). Centralise la séquence enregistrer +
archiver + diffuser pour qu'il n'existe qu'une seule façon de publier.
"""


def broadcast_published(app, state):
    """Enregistre l'état publié, l'archive dans l'historique et le diffuse (SSE)."""
    app.extensions["storage"].save_published(state)
    app.extensions["history"].archive(state)
    app.extensions["broker"].publish("published", state)
