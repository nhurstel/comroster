// Harnais de test JS — DÉVELOPPEMENT UNIQUEMENT.
//
// `static/js/*.js` reste du JavaScript nu chargé par de simples <script> : rien de ce que
// npm installe n'atteint jamais le boîtier. Ce fichier ne sert qu'à exécuter, sous Node,
// les modules de logique pure (board.js, netmask.js, ink.js) que l'admin et l'écran
// partagent — jusqu'ici la seule façon de les vérifier était d'ouvrir un navigateur.
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    include: ["tests/js/**/*.test.js"],
    // Pas de jsdom : ce qui est testé ici est PUR par construction. Le jour où un test
    // réclamerait un DOM, c'est le signe que la logique visée doit d'abord en sortir.
    environment: "node",
  },
});
