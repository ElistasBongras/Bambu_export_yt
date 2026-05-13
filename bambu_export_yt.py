import argparse
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timedelta
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
    with path.open("r", encoding="utf-8-sig") as f:
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
        try:
            creds = flow.run_local_server(port=0)
        except Exception:
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
    progress_callback=None,
    playlist_id: Optional[str] = None,
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
        if status and progress_callback:
            progress_callback(int(status.progress() * 100))
        elif status:
            logging.info("Upload progress : %s%%", int(status.progress() * 100))
    video_id = response.get("id")
    
    # Add to playlist if specified
    if playlist_id and video_id:
        try:
            youtube.playlistItems().insert(
                part="snippet",
                body={
                    "snippet": {
                        "playlistId": playlist_id,
                        "resourceId": {
                            "kind": "youtube#video",
                            "videoId": video_id,
                        },
                    }
                },
            ).execute()
            logging.info("Vidéo ajoutée à la playlist %s", playlist_id)
        except Exception as e:
            logging.warning("Impossible d'ajouter à la playlist : %s", e)
    
    return response


def load_processed_state(state_file: Path) -> Dict[str, str]:
    if not state_file.exists():
        return {}
    return load_json(state_file)


def load_upload_history(history_file: Path) -> List[Dict[str, str]]:
    if not history_file.exists():
        return []
    try:
        history = load_json(history_file)
        return history if isinstance(history, list) else []
    except Exception as exc:
        logging.warning("Impossible de charger l'historique des uploads : %s", exc)
        return []


def save_upload_history(history_file: Path, history: List[Dict[str, str]]) -> None:
    save_json(history_file, history)


def prune_upload_history(history: List[Dict[str, str]], now: Optional[datetime] = None) -> List[Dict[str, str]]:
    if now is None:
        now = datetime.utcnow()
    return [
        entry
        for entry in history
        if (now - datetime.fromisoformat(entry["timestamp"])) < timedelta(days=1)
    ]


def get_upload_history_file(config: Dict) -> Path:
    return Path(config["youtube"].get("upload_history_file", "upload_history.json")).expanduser()


def get_next_upload_available_time(history: List[Dict[str, str]], max_uploads_per_day: int) -> Optional[datetime]:
    recent = prune_upload_history(history)
    if len(recent) < max_uploads_per_day:
        return None
    sorted_history = sorted(recent, key=lambda entry: entry["timestamp"])
    return datetime.fromisoformat(sorted_history[0]["timestamp"]) + timedelta(days=1)


def record_upload(history_file: Path, video_path: Path, video_id: Optional[str]) -> None:
    now = datetime.utcnow()
    history = load_upload_history(history_file)
    history = prune_upload_history(history, now)
    history.append({
        "timestamp": now.isoformat(),
        "source": str(video_path),
        "video_id": video_id or "",
    })
    save_upload_history(history_file, history)


def wait_for_upload_slot(history_file: Path, max_uploads_per_day: int, stop_event=None) -> bool:
    while True:
        history = load_upload_history(history_file)
        history = prune_upload_history(history)
        save_upload_history(history_file, history)
        if len(history) < max_uploads_per_day:
            return True

        next_time = get_next_upload_available_time(history, max_uploads_per_day)
        if next_time is None:
            return True

        delay = (next_time - datetime.utcnow()).total_seconds()
        if delay <= 0:
            return True

        logging.info(
            "Limite quotidienne d'uploads dépassée (%s vidéos sur les dernières 24h). Reprise dans %s.",
            max_uploads_per_day,
            str(timedelta(seconds=int(delay))),
        )
        if stop_event is not None and stop_event.is_set():
            return False
        time.sleep(min(delay, 60))


def merge_defaults(config: Dict, defaults: Dict) -> Dict:
    merged = defaults.copy()
    merged.update(config)
    return merged


def process_videos(config: Dict, dry_run: bool = False, progress_callback=None, playlist_id: Optional[str] = None, stop_event=None) -> None:
    start_time = time.time()
    source_dir = Path(config["source_dir"]).expanduser()
    dest_dir = Path(config.get("dest_dir", config["source_dir"])).expanduser()
    state_file = Path(config.get("processed_state_file", "processed_videos.json")).expanduser()

    state = load_processed_state(state_file)
    upload_history_file = get_upload_history_file(config)
    upload_history_file.parent.mkdir(parents=True, exist_ok=True)
    max_uploads_per_day = int(config["youtube"].get("max_uploads_per_day", 13) or 13)
    if max_uploads_per_day <= 0:
        max_uploads_per_day = 13

    history = load_upload_history(upload_history_file)
    history = prune_upload_history(history)
    save_upload_history(upload_history_file, history)

    videos = list_video_files(source_dir)
    if not videos:
        logging.info("Aucune vidéo trouvée dans %s", source_dir)
        return

    youtube = authorize_youtube(
        Path(config["youtube"]["client_secrets_file"]).expanduser(),
        Path(config["youtube"]["credentials_file"]).expanduser(),
    )

    processed_count = 0
    for video_path in videos:
        if str(video_path) in state:
            logging.debug("Déjà traité : %s", video_path)
            continue

        title = config["youtube"].get(
            "default_title", "Timelapse BambuLab X1C {date}"
        ).format(date=datetime.fromtimestamp(video_path.stat().st_mtime).strftime("%Y-%m-%d"))
        description = config["youtube"].get(
            "default_description", "Timelapse imprimante 3D BambuLab X1C"
        )
        tags = config["youtube"].get("tags", ["BambuLab", "X1C", "impression 3D", "timelapse"])
        privacy_status = config["youtube"].get("privacy_status", "private")
        category_id = config["youtube"].get("category_id", "28")

        if dry_run:
            logging.info("[DRY RUN] Prêt à uploader : %s", video_path)
            logging.info("Titre : %s", title)
            logging.info("Description : %s", description)
        else:
            if not wait_for_upload_slot(upload_history_file, max_uploads_per_day, stop_event):
                logging.info("Arrêt demandé avant reprise des uploads.")
                break
            logging.info("Upload de %s vers YouTube", video_path)
            response = upload_video(
                youtube,
                video_path,
                title,
                description,
                tags,
                privacy_status,
                category_id,
                progress_callback,
                playlist_id,
            )
            logging.info("Upload terminé : %s", video_path)
            record_upload(upload_history_file, video_path, response.get("id") if response else None)
            target_path = rename_and_move_file(video_path, dest_dir, config.get("rename_pattern", "BambuLab_X1C_{date}_{time}"))
            state[str(video_path)] = str(target_path)
            save_json(state_file, state)
        processed_count += 1

    end_time = time.time()
    total_time = end_time - start_time
    if progress_callback:
        progress_callback(100)  # Ensure progress reaches 100%
    logging.info("Métriques : %d vidéos traitées en %.2f secondes (%.2f s/vidéo)", processed_count, total_time, total_time / max(processed_count, 1))


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
