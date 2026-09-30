# Catering API – Raspberry Pi pour le workflow MT - CATERING

API Python qui prépare le panier et le paiement sur Marjane, appelée par le workflow n8n **VIRTUOCODE - STAGIAIRE VIRTUOCODE - MT - CATERING**.
Le Raspberry Pi remplace Render : n8n reste sur le cloud et appelle le Pi en HTTPS via un tunnel Tailscale. Aucun port n'est ouvert sur le routeur du bureau.

```
n8n cloud (lundi 9 h) ──HTTPS──> Tailscale Funnel ──> Raspberry Pi (API :8000) ──> site Marjane
        │
        └── Slack : validation du panier (Approuver / Refuser)
```

## Contenu du dépôt

```
catering-api/
├── main.py                  API FastAPI (endpoints /session/panier et /session/pay)
├── requirements.txt         Dépendances Python
├── Dockerfile               Ancien déploiement Render (non utilisé sur le Pi)
├── .env.example             Modèle du fichier de configuration
├── .gitignore               Exclut .env, storage_state.json et les captures de debug
├── scripts/
│   ├── generer_cookies.py   Connexion manuelle à Marjane → storage_state.json (sur PC)
│   └── open_session.py      Rouvre la session Marjane enregistrée, pour vérifier (sur PC)
├── deploy/
│   ├── install_pi.sh        Installe l'API sur le Pi (étape 3)
│   └── catering-api.service Service systemd (démarrage automatique)
├── n8n/
│   └── MT_CATERING_workflow.json   Export du workflow n8n (sauvegarde)
└── docs/
    └── Guide_Raspberry_Pi_MT_CATERING.docx   Version Word du guide (installation manuelle)
```


## À prévoir

- Raspberry Pi 4 ou 5, 4 Go de RAM minimum
- Carte microSD 32 Go + son alimentation officielle
- Câble Ethernet branché au réseau du bureau
- Accès à ce dépôt GitHub et clé d'API, transmise séparément
- Un compte Tailscale (gratuit)

## Étape 1 – Installer le système sur le Pi

1. Sur un PC, ouvrir **Raspberry Pi Imager** et choisir *Raspberry Pi OS Lite (64-bit)*.
2. Dans les réglages : nom d'hôte `catering-pi`, utilisateur `pi`, un mot de passe, **SSH activé**.
3. Flasher la carte, l'insérer dans le Pi, brancher Ethernet puis l'alimentation.
4. Depuis le PC, se connecter :

```bash
ssh pi@catering-pi.local
```

5. Copier-coller sur le Pi :

```bash
sudo apt update && sudo apt full-upgrade -y
sudo apt install -y git python3-venv python3-pip chromium
sudo timedatectl set-timezone Africa/Casablanca
```

## Étape 2 – Générer les cookies Marjane (sur un PC avec écran)

À faire sur un PC, pas sur le Pi :

```bash
git clone https://github.com/sarabencheqroune/catering-api.git
cd catering-api
pip install -r requirements.txt
playwright install chromium
python scripts/generer_cookies.py
```

Le script ouvre Marjane dans un navigateur : se connecter au compte, puis appuyer sur `Entrée` dans le terminal. La session est enregistrée dans `storage_state.json`. Copier ce fichier sur le Pi (après l'étape 3) :

```bash
scp storage_state.json pi@catering-pi.local:~/catering-api/
```

## Étape 3 – Installer l'API sur le Pi

1. Copier-coller sur le Pi :

```bash
cd ~
git clone https://github.com/sarabencheqroune/catering-api.git
cd catering-api
cp .env.example .env
nano .env
```

2. Dans `nano`, compléter la ligne `API_KEY=` avec la clé transmise séparément (ne pas toucher à `COOKIES_DIR`), puis enregistrer (`Ctrl+O`, `Entrée`, `Ctrl+X`).
3. Copier `storage_state.json` depuis le PC (commande `scp` de l'étape 2).
4. Lancer l'installation :

```bash
bash deploy/install_pi.sh
```

Le script installe les dépendances, crée le service `catering-api` et vérifie que l'API répond. Il doit afficher `OK : l'API répond`. L'API redémarre seule après une coupure.

## Étape 4 – Rendre l'API accessible à n8n

1. Copier-coller sur le Pi :

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

2. Ouvrir le lien affiché et se connecter au compte Tailscale.
3. Dans la console Tailscale (*Access controls*), autoriser **Funnel** si c'est demandé.
4. Copier-coller sur le Pi :

```bash
sudo tailscale funnel --bg 8000
```

5. **Noter l'URL affichée** (de la forme `https://catering-pi.xxxx.ts.net`) : c'est `<URL_TUNNEL>` pour l'étape 5. Elle ne change pas après redémarrage.

## Étape 5 – Modifier le workflow n8n

Dans n8n, ouvrir le workflow « *VIRTUOCODE - STAGIAIRE VIRTUOCODE - MT - CATERING* » et effectuer les actions suivantes :

1. **Supprimer** les nœuds *Marjane_Connexion_test* et *Wait* (ils ne servaient qu'à réveiller Render).
2. **Relier** *Liste produits* → *Marjane_Connexion*.
3. **Changer l'URL** de deux nœuds :

| Nœud | Nouvelle URL |
| --- | --- |
| Marjane_Connexion | `<URL_TUNNEL>/session/panier` |
| Finaliser paiement | `<URL_TUNNEL>/session/pay` |

4. **Vérifier l'identifiant** *Header Auth account 13* : sa valeur doit être identique à la clé `API_KEY` du fichier `.env` du Pi.
5. **Changer le destinataire Slack** (actuellement sara.bencheqroune) dans les 3 nœuds : *Demande Validation Panier*, *Commande validée*, *Panier non validé*.
6. **Enregistrer.**

> **Important :** dans le nœud *Finaliser paiement* (onglet *Settings*), désactiver **Retry On Fail**. Sinon, une erreur de l'API peut relancer le paiement jusqu'à 5 fois.

## Étape 6 – Tester et activer

1. Dans n8n, cliquer sur **Execute workflow**.
2. Dans Slack, cliquer sur **Refuser** : le message « Panier non validé » doit ensuite s'afficher (aucun paiement n'est fait).
3. Si tout fonctionne, basculer le workflow sur **Active**. Il tournera chaque lundi à 9 h.

## En cas de problème

| Symptôme | À faire sur le Pi |
| --- | --- |
| n8n : timeout ou erreur 502 | `sudo systemctl restart catering-api` puis `tailscale funnel status` |
| n8n : erreur 401 ou 403 | Aligner la clé du `.env` et l'identifiant n8n, puis `sudo systemctl restart catering-api` |
| Erreur côté Marjane | Lire les logs : `journalctl -u catering-api -n 100`. Si la session a expiré, régénérer `storage_state.json` (étape 2) |
| Mettre à jour l'API | `cd ~/catering-api && git pull && sudo systemctl restart catering-api` |

## Point à corriger avant la mise en production

Dans `main.py`, l'endpoint `/session/pay` attend encore deux sélecteurs provisoires : `SELECTEUR_CONFIRMATION_COMMANDE` et `SELECTEUR_NUMERO_COMMANDE`. Tant qu'ils ne sont pas remplacés par les vrais sélecteurs de la page de confirmation Marjane. (Ces deux sélecteurs se trouvent sur la page de paiement)


Merci Pour tout 🙏
