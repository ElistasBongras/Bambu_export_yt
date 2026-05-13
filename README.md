# Bambu_export_yt

Outil Python pour automatiser les timelapses BambuLab X1C :
- récupérer les vidéos
- renommer les fichiers
- uploader sur YouTube

## Guide pas à pas

### Étape 1 : Installer Python

1. Si Python n'est pas installé, téléchargez-le depuis https://www.python.org/downloads/.
2. Choisissez la version 3.10 ou supérieure.
3. Lors de l'installation, cochez l'option "Add Python to PATH" si possible.

### Étape 2 : Ouvrir PowerShell dans le dossier du projet

1. Ouvrez l'explorateur Windows.
2. Rendez-vous dans `C:\Users\cleme\GitHub\Bambu_export_yt`.
3. Cliquez sur la barre d'adresse et tapez `powershell`, puis appuyez sur Entrée.

### Étape 3 : Lancer la configuration automatique

Dans PowerShell, tapez :

```powershell
.\setup.ps1
```

Le script va :
- détecter Python
- installer les dépendances nécessaires
- créer le fichier `config.json`

### Étape 4 : Créer les identifiants YouTube

1. Ouvrez la page Google Cloud Console : https://console.cloud.google.com/
2. Créez un nouveau projet ou choisissez un projet existant.
3. Activez l'API YouTube Data v3 :
   - `API & Services` > `Bibliothèque`
   - Cherchez "YouTube Data API v3"
   - Cliquez sur `Activer`
4. Créez des identifiants OAuth 2.0 :
   - `API & Services` > `Identifiants`
   - Cliquez sur `Créer des identifiants` > `ID client OAuth`
   - Type d'application : `Bureau`
   - Téléchargez le fichier JSON
5. Renommez ce fichier en `client_secrets.json` et placez-le dans le dossier du projet.

### Étape 5 : Vérifier `config.json`

Après `setup.ps1`, vous devez avoir un fichier `config.json` dans le dossier du projet.

Vérifiez que les chemins suivants sont corrects :
- `source_dir` : dossier où la BambuLab enregistre les vidéos
- `dest_dir` : dossier où les vidéos renommées seront placées
- `youtube.client_secrets_file` : `client_secrets.json`
- `youtube.credentials_file` : `youtube_credentials.json`

Note : vous n'avez généralement pas besoin de créer manuellement `youtube_credentials.json`.
Il est généré automatiquement lors du premier lancement du script, au moment où vous autorisez l'accès YouTube.

### Étape 6 : Lancer le traitement

Dans PowerShell, tapez :

```powershell
.\run.ps1
```

Le script vous demandera :
- si vous voulez faire une simulation sans upload
- si vous voulez exécuter une seule passe ou surveiller le dossier en continu

### Étape 7 : Autoriser l'accès YouTube

Lors du premier upload, un lien ou une fenêtre s'ouvre.

1. Connectez-vous avec votre compte Google YouTube.
2. Autorisez l'application à accéder à votre compte.
3. Le script enregistre un token dans `youtube_credentials.json`.

## Interface graphique

Pour utiliser l'interface graphique Python, lancez :

```powershell
python bambu_export_yt_gui.py
```

Ou utilisez le lanceur PowerShell :

```powershell
.\run_gui.ps1
```

L'interface permet de :
- choisir les dossiers source et destination
- configurer les identifiants YouTube
- sauvegarder la configuration dans `config.json`

## Exécutable autonome

Pour une utilisation plus simple sans terminal, un exécutable Windows a été créé.

 utilisez le fichier `Lancer_GUI.bat` pour un lancement facilité (il active l'environnement virtuel et lance le script Python directement).

**Note :** L'exécutable ajuste automatiquement son répertoire de travail pour accéder aux fichiers de configuration dans le dossier parent. Assurez-vous que `config.json`, `client_secrets.json`, etc. sont présents dans `C:\Users\cleme\GitHub\Bambu_export_yt`.

### Lancement direct avec Python

Si vous préférez lancer directement avec Python :

1. Ouvrez un terminal PowerShell dans le dossier du projet.
2. Tapez : `python bambu_export_yt_gui.py`

Ou utilisez le script PowerShell : `.\run_gui.ps1`
- démarrer une exécution, une simulation, ou une surveillance continue
- ouvrir les dossiers source et destination dans l'explorateur
- afficher la liste des vidéos déjà traitées

## Option manuelle

Si vous préférez exécuter directement le script Python :

```powershell
python bambu_export_yt.py --config config.json
```

Pour tester sans upload :

```powershell
python bambu_export_yt.py --config config.json --dry-run
```

Pour surveiller régulièrement le dossier et traiter les nouvelles vidéos :

```powershell
python bambu_export_yt.py --config config.json --watch 300
```

## Fonctionnement

- Le script liste les fichiers vidéo dans `source_dir`.
- Chaque fichier est renommé selon `rename_pattern`.
- La vidéo est uploadée sur YouTube avec les métadonnées du fichier de configuration.
- Les vidéos déjà traitées sont mémorisées dans `processed_videos.json`.

## Remarques

- `privacy_status` peut être `private`, `unlisted` ou `public`.
- `category_id` `28` correspond à "Science & Technology".
