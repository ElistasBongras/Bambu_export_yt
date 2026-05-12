import argparse
import json
import logging
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
except ImportError:
    print(
        "Erreur : les dépendances Google ne sont pas installées."
        " Installez-les avec `pip install -r requirements.txt`."
    )
    sys.exit(1)

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
VIDEO_EXTENSIONS = [".mp4", ".mov", ".mkv", ".avi"]


def load_json(path: Path) -> Dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def normalize_filename(value: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9._ \-]+", "_", value)
    sanitized = re.sub(r"[ \-]{2,}", "_", sanitized)
    return sanitized.strip("_.-")


def build_output_filename(path: Path, pattern: str) -> str:
    timestamp = datetime.fromtimestamp(path.stat().st_mtime)
    data = {
        "date": timestamp.strftime("%Y-%m-%d"),
        "time": timestamp.strftime("%H-%M-%S"),
        "original": path.stem,
        "extension": path.suffix.lower().lstrip("."),
    }
    base_name = pattern.format(**data)
    safe_name = normalize_filename(base_name)
    return f"{safe_name}{path.suffix.lower()}"


def list_video_files(source_dir: Path) -> List[Path]:
    if not source_dir.exists():
        logging.warning("Le dossier source n'existe pas : %s", source_dir)
        return []
    return sorted(
        [p for p in source_dir.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS],
        key=lambda p: p.stat().st_mtime,
    )


def get_unique_destination(dest: Path) -> Path:
    if not dest.exists():
        return dest
    stem, suffix = dest.stem, dest.suffix
    index = 1
    while True:
        candidate = dest.with_name(f"{stem}_{index}{suffix}")
        if not candidate.exists():
            return candidate
        index += 1


def rename_and_move_file(source: Path, dest_dir: Path, pattern: str) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    output_name = build_output_filename(source, pattern)
    destination = get_unique_destination(dest_dir / output_name)
    logging.info("Renommage : %s -> %s", source, destination)
    source.replace(destination)
    return destination


def authorize_youtube(client_secrets_file: Path, token_file: Path) -> build:
    creds = None
    if token_file.exists():
        creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)
    if creds and creds.valid:
        return build("youtube", "v3", credentials=creds)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        flow = InstalledAppFlow.from_client_secrets_file(str(client_secrets_file), SCOPES)
        creds = flow.run_console()
    with token_file.open("w", encoding="utf-8") as token:
        token.write(creds.to_json())
    return build("youtube", "v3", credentials=creds)


def upload_video(
    youtube,
    file_path: Path,
    title: str,
    description: str,
    tags: List[str],
    privacy_status: str,
    category_id: str,
) -> Dict:
    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": privacy_status,
        },
    }
    media = MediaFileUpload(str(file_path), chunksize=-1, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            logging.info("Upload progress : %s%%", int(status.progress() * 100))
    return response


def load_processed_state(state_file: Path) -> Dict[str, str]:
    if not state_file.exists():
        return {}
    return load_json(state_file)


def merge_defaults(config: Dict, defaults: Dict) -> Dict:
    merged = defaults.copy()
    merged.update(config)
    return merged


def process_videos(config: Dict, dry_run: bool = False) -> None:
    source_dir = Path(config["source_dir"]).expanduser()
    dest_dir = Path(config.get("dest_dir", config["source_dir"])).expanduser()
    state_file = Path(config.get("processed_state_file", "processed_videos.json")).expanduser()

    state = load_processed_state(state_file)
    videos = list_video_files(source_dir)
    if not videos:
        logging.info("Aucune vidéo trouvée dans %s", source_dir)
        return

    youtube = authorize_youtube(
        Path(config["youtube"]["client_secrets_file"]).expanduser(),
        Path(config["youtube"]["credentials_file"]).expanduser(),
    )

    for video_path in videos:
        if str(video_path) in state:
            logging.debug("Déjà traité : %s", video_path)
            continue

        target_path = rename_and_move_file(video_path, dest_dir, config.get("rename_pattern", "BambuLab_X1C_{date}_{time}"))
        title = config["youtube"].get(
            "default_title", "Timelapse BambuLab X1C {date}"
        ).format(date=datetime.fromtimestamp(target_path.stat().st_mtime).strftime("%Y-%m-%d"))
        description = config["youtube"].get(
            "default_description", "Timelapse imprimante 3D BambuLab X1C"
        )
        tags = config["youtube"].get("tags", ["BambuLab", "X1C", "impression 3D", "timelapse"])
        privacy_status = config["youtube"].get("privacy_status", "private")
        category_id = config["youtube"].get("category_id", "28")

        if dry_run:
            logging.info("[DRY RUN] Prêt à uploader : %s", target_path)
            logging.info("Titre : %s", title)
            logging.info("Description : %s", description)
        else:
            logging.info("Upload de %s vers YouTube", target_path)
            upload_video(
                youtube,
                target_path,
                title,
                description,
                tags,
                privacy_status,
                category_id,
            )
            logging.info("Upload terminé : %s", target_path)

        state[str(video_path)] = str(target_path)
        save_json(state_file, state)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Automatisation : récupération, renommage et upload de timelapses YouTube."
    )
    parser.add_argument("--config", type=str, default="config.json", help="Chemin du fichier de configuration JSON.")
    parser.add_argument("--dry-run", action="store_true", help="Simule le traitement sans uploader.")
    parser.add_argument("--watch", type=int, default=0, help="Scanner en boucle toutes les X secondes.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    config_path = Path(args.config).expanduser()
    if not config_path.exists():
        logging.error("Fichier de configuration introuvable : %s", config_path)
        return 1

    config = load_json(config_path)

    while True:
        process_videos(config, dry_run=args.dry_run)
        if args.watch <= 0:
            break
        logging.info("Attente de %s secondes avant le prochain scan...", args.watch)
        time.sleep(args.watch)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
