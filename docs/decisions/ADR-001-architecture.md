## Principes structurants

- L'application fonctionne entièrement en local après installation.
- Le fonctionnement courant ne dépend d'aucun service distant.
- Les composants nécessaires sont exécutés sur la machine de l'utilisateur.
- Les échanges réseau sont limités aux communications locales nécessaires.
- Les mises à jour et téléchargements de modèles peuvent nécessiter Internet, mais restent facultatifs pendant l'utilisation courante.

## Conséquences

- Les services doivent disposer de healthchecks et de journaux locaux.
- Docker Compose doit permettre de démarrer et d'arrêter l'environnement.
- Les dépendances et les modèles nécessaires doivent pouvoir être préparés avant une utilisation hors ligne.
- L'application doit signaler clairement lorsqu'une fonctionnalité exige exceptionnellement Internet.