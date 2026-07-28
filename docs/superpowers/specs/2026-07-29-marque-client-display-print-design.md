# Marque client sur `/display` et `/print`

**Date :** 2026-07-29 · **Demande :** Nathan — « quand un client me commande un ComRoster,
pouvoir mettre le logo de mon client à la place de celui du ComRoster sur le `/display` »,
avec cette contrainte : « j'aimerais pas non plus que le client puisse changer à volonté de
son côté, donc pas juste un paramètre dans l'admin ».

**Arbitrages validés :** périmètre `/display` **+** `/print` · **co-branding** (le crédit
ComRoster reste, en discret) · pack de marque **posé à la fabrication**, aucune interface
d'administration · pas de signature cryptographique.

---

## 0. Le principe

La marque n'est pas une donnée d'application : c'est une **propriété du boîtier**, au même
titre que sa configuration réseau. Elle ne vit donc ni dans le brouillon, ni dans l'état
publié, ni dans `DATA_DIR` — elle vit dans un chemin système que l'application **lit** et
n'écrit jamais.

C'est ce qui répond à la contrainte de départ : le verrou n'est pas un mot de passe qu'on
pourrait contourner, c'est **l'absence de tout chemin d'écriture** depuis l'application vers
la marque. Le client peut disposer de la totalité de l'administration : il n'y a rien à
atteindre.

## 1. Le pack de marque

```
/etc/comroster/branding/          ← hors DATA_DIR, hors dépôt, root:root
├── brand.json
├── logo.svg
└── logo-print.svg                (optionnel)
```

```json
{
  "name": "Acme Live",
  "logo": "logo.svg",
  "logo_print": "logo-print.svg",
  "mono": false
}
```

| Champ | Requis | Rôle |
|---|---|---|
| `name` | oui | Attribut `alt` de l'image ; nom porté par la feuille imprimée. |
| `logo` | oui | Nom de fichier du logo écran. **Basename seul.** |
| `logo_print` | non | Variante encre noire. Absent → on réutilise `logo`. |
| `mono` | non (défaut `false`) | `true` : logo monochrome, l'inversion en thème jour est conservée. `false` : logo couleur, aucun filtre. |

**`logo` et `logo_print` sont validés comme basenames** : un nom contenant `/`, `\` ou `..`
invalide le pack. La source est de confiance — c'est l'exploitant, en root — mais on ne
concatène jamais un chemin non validé. Défense en profondeur, coût nul.

**Extensions acceptées : `.svg` et `.png` uniquement.** Le JPEG est refusé : sans canal
alpha, un logo rend mal sur le fond sombre du tableau. La conversion appartient à la
préparation du pack, pas au boîtier.

Une seule entrée de configuration, dans le style de
[config.py](../../../comroster/config.py) :

```python
self.BRAND_DIR = os.environ.get("COMROSTER_BRAND_DIR", "")
```

Vide ou absent → ComRoster. Le comportement par défaut est celui d'aujourd'hui, à l'octet
près.

## 2. Le service `comroster/services/branding.py`

Construit dans `create_app` aux côtés des autres services :

```python
app.extensions["branding"] = Branding(app.config.get("BRAND_DIR"))
```

**Chargement unique au démarrage.** La marque ne change pas pendant qu'un show tourne, et
poser un pack implique de toute façon un redémarrage du service (§6). Aucun accès disque sur
le chemin chaud.

**Politique fail-safe**, alignée sur celle de
[lifetime.py](../../../comroster/services/lifetime.py) : dossier absent, JSON illisible,
champ requis manquant, fichier introuvable, extension interdite, basename invalide → **repli
intégral sur ComRoster**, accompagné d'un `log.warning` explicite nommant la cause.

**Aucune exception au démarrage, quelle que soit la faute.** Un pack raté ne doit jamais
empêcher un boîtier de démarrer une heure avant un show. C'est la règle appliance déjà
appliquée au carnet de bord.

Surface exposée, en lecture seule après construction :

| Attribut | Valeur |
|---|---|
| `active` | `True` si un pack valide a été chargé |
| `name` | nom du client |
| `logo_path` | chemin absolu du logo écran |
| `print_logo_path` | chemin absolu du logo papier (retombe sur `logo_path`) |
| `mono` | booléen |
| `version` | plus grand `mtime` des fichiers du pack, pour l'invalidation de cache |

Une seule `version` pour les deux logos : le pack est posé d'un bloc, il n'y a pas de cas où
la variante papier changerait sans l'écran.

**Aucune méthode d'écriture.** C'est le point de conception central : le verrouillage tient
à l'absence de mutateur, pas à un contrôle d'accès.

## 3. Servir les fichiers

Deux routes publiques dans le blueprint `display`, aux côtés de `/display/qr.svg`
([display.py](../../../comroster/display.py)) :

| Route | Sert |
|---|---|
| `GET /branding/logo` | le logo écran |
| `GET /branding/logo-print` | la variante papier |

Sans pack actif, les deux répondent **404** — les templates ne les référencent pas dans ce
cas, mais la route reste honnête.

`send_file(..., conditional=True)` laisse Flask gérer ETag et `Last-Modified`, complété d'un
`Cache-Control` à durée longue. L'invalidation passe par `?v=<version>` sur l'URL générée
dans le template : c'est la transposition exacte du cache-buster `?v=<mtime>` que
[`__init__.py`](../../../comroster/__init__.py) applique déjà aux URLs `static`, lequel ne
couvre que l'endpoint `static` et ne peut donc pas servir ici.

## 4. Rendu

### 4.1 `/display`

[display.html:34](../../../templates/display.html) devient conditionnel. Marque active :

```html
<img class="brand-mark{% if not brand.mono %} brand-mark-color{% endif %}"
     src="{{ url_for('display.brand_logo', v=brand.version) }}"
     alt="{{ brand.name }}">
```

Sans marque : la ligne actuelle, mot pour mot.

Deux corrections dans [display.css:112-116](../../../static/css/display.css), toutes deux
nécessaires :

1. **Ratio libre.** `.brand-mark` est aujourd'hui carré et figé (`1.85rem × 1.85rem`), ce qui
   convient au glyphe ComRoster mais pas à un logo client, presque toujours un wordmark
   horizontal. Il passe à hauteur fixe et largeur libre bornée :
   `height: 1.85rem; width: auto; max-width: 9rem; object-fit: contain`. Un glyphe carré rend
   alors exactement comme avant, à la même hauteur.

2. **Neutralisation du filtre.** La règle existante
   `body.display-page[data-theme="day"] .brand-mark { filter: invert(1); }` inverse le glyphe
   monochrome en thème jour. Appliquée à un logo couleur, elle le rendrait en négatif. La
   classe `.brand-mark-color`, posée quand `mono` est faux, remet `filter: none` sur les deux
   thèmes.

Aucun skin ne redéfinit `.brand-mark` (vérifié dans
[skins.css](../../../static/css/skins.css)) : le changement reste confiné à `display.css`.
Le CSS ajouté n'utilise aucune variable nouvelle, pour rester compatible avec le contrôle de
[test_css_tokens.py](../../../tests/test_css_tokens.py).

### 4.2 `/print`

Le logo entre dans `.sheet-head` de [print.html](../../../templates/print.html), à gauche de
`.sheet-title` — la place naturelle d'un logo sur un document. Il utilise
`/branding/logo-print`. Rien n'est ajouté sans marque active.

`print.css` est autonome (elle ne charge pas `main.css`) : les règles du logo imprimé y sont
écrites avec ses propres jetons.

### 4.3 Accès depuis les templates

Un `@app.context_processor` injecte `brand` dans tous les templates. Préféré à l'ajout d'un
argument aux quatre appels `render_template` concernés — et à tous ceux à venir.

## 5. Le co-branding

| | Sans pack | Avec pack |
|---|---|---|
| Pied `/display` | `COMROSTER par Nathan Hurstel` *(inchangé)* | `Propulsé par ComRoster` |
| Pied `/print` | `ComRoster · <titre> · …` *(inchangé)* | `<nom client> · <titre> · … · Propulsé par ComRoster` |

Les skins `lineaire` et `grille` redéfinissent la couleur de `.created-by`
([skins.css](../../../static/css/skins.css)) : un simple changement de texte leur est
transparent.

## 6. Fabrication — `deploy/set-branding.sh`

```
sudo deploy/set-branding.sh ~/packs/acme-live/     # pose la marque
sudo deploy/set-branding.sh --reset                # revient à ComRoster
```

Le script, dans l'ordre :

1. **Valide le pack avant de toucher au système.** `brand.json` parsable, `name` et `logo`
   présents, basenames valides, fichiers existants, extensions autorisées. Un pack invalide
   est refusé ici, bruyamment, plutôt qu'ignoré en silence au démarrage suivant.

2. **Garde-fou overlay.** [readonly-fs.sh](../../../deploy/readonly-fs.sh) active un
   overlayfs sur la **racine** : les écritures système partent en RAM et disparaissent au
   redémarrage. Poser un pack dans `/etc` avec l'overlay actif serait donc sans effet
   durable. Le script détecte cet état et **refuse**, en expliquant l'ordre correct — poser
   la marque, *puis* activer l'overlay. Le message suit le style du garde-fou déjà présent
   dans `readonly-fs.sh`.

   Corollaire heureux : sur un boîtier livré overlay actif, **même un accès root ne permet
   pas de modifier durablement la marque** — le redémarrage la restaure.

3. Copie dans `/etc/comroster/branding/` en `root:root`, fichiers `0644`, dossier `0755`.

4. Ajoute `Environment=COMROSTER_BRAND_DIR=/etc/comroster/branding` à
   [comroster.service](../../../deploy/comroster.service) si absent, puis `daemon-reload` et
   `restart comroster`.

`--reset` supprime le dossier et retire la ligne `Environment=`, puis redémarre.

Une section « Marque client » est ajoutée à
[raspberry-pi.md](../../../deploy/raspberry-pi.md) : composition d'un pack, pose, ordre
vis-à-vis de l'overlay.

## 7. Tests — `tests/test_branding.py`

La fixture `app` de [conftest.py](../../../tests/conftest.py) accepte des surcharges de
configuration : `create_app({"BRAND_DIR": str(tmp_path / "branding")})` suffit, sans toucher
à l'environnement.

| Cas | Attendu |
|---|---|
| Sans `BRAND_DIR` | `/display` sert `comroster-glyph.svg`, pieds inchangés — **non-régression** |
| Pack valide, `/display` | l'image pointe `/branding/logo`, `alt` = nom du client, pied = « Propulsé par ComRoster » |
| Pack valide, `/admin/print` | le logo et le nom du client sont présents |
| `brand.json` corrompu | repli ComRoster **et l'application démarre** |
| Logo déclaré mais absent | repli ComRoster **et l'application démarre** |
| Extension interdite (`.jpg`) | repli ComRoster **et l'application démarre** |
| `logo` contenant `../` | repli ComRoster **et l'application démarre** |
| `GET /branding/logo` sans pack | 404 |
| `mono: false` | la classe neutralisant le filtre est présente |
| `mono: true` | elle est absente |

Les quatre cas de repli sont le cœur du lot : ils vérifient la promesse appliance — une
marque mal posée dégrade l'apparence, jamais la disponibilité.

## 8. Hors périmètre, délibérément

- Aucun téléversement, aucune page d'administration, aucun second mot de passe.
- Aucune signature cryptographique du pack (arbitrage explicite : le boîtier est verrouillé
  physiquement, le coût d'une gestion de clés n'est pas justifié).
- Favicon, `<title>`, écran de démarrage et page de connexion restent ComRoster.
- Ni couleur d'accent, ni police client : logo et nom, rien d'autre.
- Pas de rechargement à chaud : poser un pack implique un redémarrage du service.

## 9. Deux valeurs à caler sur le terrain

- **`max-width: 9rem`** pour le logo écran : chiffre posé à vue, sur un en-tête déjà dense
  (titre, statistiques, horloge, badge « En direct »). À confirmer avec un vrai logo client.
- **Extensions SVG/PNG** : à rouvrir au JPEG si les clients en fournissent couramment et que
  la conversion à la fabrication devient une gêne.
