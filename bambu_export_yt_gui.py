import json
import logging
import os
import queue
import subprocess
import threading
import time
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

CONFIG_PATH = Path(__file__).parent / "config.json"
DEFAULT_CONFIG = {
    "source_dir": "",
    "dest_dir": "",
    "rename_pattern": "BambuLab_X1C_{date}_{time}",
    "processed_state_file": "processed_videos.json",
    "youtube": {
        "client_secrets_file": "client_secrets.json",
        "credentials_file": "youtube_credentials.json",
        "default_title": "Timelapse imprimante 3D BambuLab X1C - {date}",
        "default_description": "Timelapse automatique BambuLab X1C uploadé sur YouTube.",
        "privacy_status": "private",
        "tags": ["BambuLab", "X1C", "impression 3D", "timelapse"],
        "category_id": "28",
        "playlist_id": "",
        "max_uploads_per_day": 13,
        "upload_history_file": "upload_history.json",
    },
}

try:
    import bambu_export_yt as backend
except Exception as exc:
    backend = None
    BACKEND_ERROR = exc
else:
    BACKEND_ERROR = None


class GuiApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("BambuLab X1C Timelapse YouTube")
        self.geometry("960x900")
        self.minsize(920, 740)
        self.resizable(True, True)
        self.config_values = {}
        self.log_queue = queue.Queue()
        self.worker_thread = None
        self.stop_event = threading.Event()
        self.progress_var = tk.DoubleVar()
        self.dark_mode = False
        self.config_collapsed = False
        self.style = ttk.Style()
        self.default_theme = self.style.theme_use()

        self.create_widgets()
        self.load_config()
        self.after(100, self.process_log_queue)

    def create_widgets(self):
        main_frame = ttk.Frame(self, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(0, weight=0)
        main_frame.rowconfigure(1, weight=0)
        main_frame.rowconfigure(2, weight=1)

        config_frame = ttk.LabelFrame(main_frame, text="Configuration")
        config_frame.grid(row=0, column=0, sticky="nsew", padx=2, pady=2)
        config_frame.columnconfigure(1, weight=1)
        config_frame.rowconfigure(12, weight=1)

        run_frame = ttk.LabelFrame(main_frame, text="Actions")
        run_frame.grid(row=1, column=0, sticky="ew", padx=2, pady=2)
        run_frame.columnconfigure(0, weight=1)
        run_frame.columnconfigure(1, weight=1)
        run_frame.columnconfigure(2, weight=1)
        run_frame.columnconfigure(3, weight=1)

        log_frame = ttk.LabelFrame(main_frame, text="Journal")
        log_frame.grid(row=2, column=0, sticky="nsew", padx=2, pady=2)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        self.config_frame = config_frame
        self.create_config_form(config_frame)
        self.create_run_buttons(run_frame)
        self.create_log_area(log_frame)

    def create_config_form(self, parent):
        self.entry_vars = {
            "source_dir": tk.StringVar(),
            "dest_dir": tk.StringVar(),
            "client_secrets_file": tk.StringVar(),
            "credentials_file": tk.StringVar(),
            "rename_pattern": tk.StringVar(value=DEFAULT_CONFIG["rename_pattern"]),
            "processed_state_file": tk.StringVar(value=DEFAULT_CONFIG["processed_state_file"]),
            "default_title": tk.StringVar(value=DEFAULT_CONFIG["youtube"]["default_title"]),
            "default_description": tk.StringVar(value=DEFAULT_CONFIG["youtube"]["default_description"]),
            "tags": tk.StringVar(value=", ".join(DEFAULT_CONFIG["youtube"]["tags"])),
            "privacy_status": tk.StringVar(value=DEFAULT_CONFIG["youtube"]["privacy_status"]),
            "category_id": tk.StringVar(value=DEFAULT_CONFIG["youtube"]["category_id"]),
            "playlist_id": tk.StringVar(value=DEFAULT_CONFIG["youtube"]["playlist_id"]),
            "max_uploads_per_day": tk.StringVar(value=str(DEFAULT_CONFIG["youtube"]["max_uploads_per_day"])),
            "upload_history_file": tk.StringVar(value=DEFAULT_CONFIG["youtube"]["upload_history_file"]),
            "watch_interval": tk.StringVar(value="0"),
        }

        rows = [
            ("Dossier source", "source_dir", True),
            ("Dossier destination", "dest_dir", True),
            ("Fichier client OAuth", "client_secrets_file", True),
            ("Fichier token YouTube", "credentials_file", True),
            ("Modèle de nom", "rename_pattern", False),
            ("Fichier état traité", "processed_state_file", False),
            ("Titre par défaut", "default_title", False),
            ("Tags (séparés par virgule)", "tags", False),
            ("Statut confidentialité", "privacy_status", False),
            ("ID catégorie YouTube", "category_id", False),
            ("ID playlist YouTube", "playlist_id", False),
            ("Téléversements max / 24h", "max_uploads_per_day", False),
            ("Fichier historique uploads", "upload_history_file", False),
            ("Intervalle de surveillance (s)", "watch_interval", False),
        ]

        for index, (label_text, key, has_browse) in enumerate(rows):
            label = ttk.Label(parent, text=label_text)
            label.grid(row=index, column=0, sticky="w", pady=4, padx=2)
            entry = ttk.Entry(parent, textvariable=self.entry_vars[key], width=75)
            entry.grid(row=index, column=1, sticky="w", pady=4, padx=2)
            if has_browse:
                btn = ttk.Button(parent, text="Parcourir", command=lambda k=key: self.browse_value(k))
                btn.grid(row=index, column=2, sticky="w", padx=2)

        description_label = ttk.Label(parent, text="Description par défaut")
        description_label.grid(row=len(rows), column=0, sticky="nw", pady=4, padx=2)
        self.description_text = scrolledtext.ScrolledText(parent, width=72, height=5, wrap=tk.WORD)
        self.description_text.grid(row=len(rows), column=1, columnspan=2, sticky="nsew", pady=4, padx=2)
        self.description_text.insert("1.0", DEFAULT_CONFIG["youtube"]["default_description"])

        button_frame = ttk.Frame(parent)
        button_frame.grid(row=len(rows) + 1, column=0, columnspan=3, sticky="ew", pady=8)
        save_btn = ttk.Button(button_frame, text="Enregistrer la configuration", command=self.save_config)
        save_btn.pack(side=tk.LEFT, padx=2)
        load_btn = ttk.Button(button_frame, text="Charger la configuration", command=self.load_config)
        load_btn.pack(side=tk.LEFT, padx=2)

        self.toggle_config_button = ttk.Button(parent, text="Réduire configuration", command=self.toggle_config)
        self.toggle_config_button.grid(row=len(rows) + 2, column=0, columnspan=3, sticky="ew", pady=4, padx=2)

    def create_run_buttons(self, parent):
        self.run_button = ttk.Button(parent, text="Exécuter une passe", command=self.run_once)
        self.run_button.grid(row=0, column=0, padx=4, pady=4)

        self.dry_run_button = ttk.Button(parent, text="Simulation (dry-run)", command=self.run_dry)
        self.dry_run_button.grid(row=0, column=1, padx=4, pady=4)

        self.start_watch_button = ttk.Button(parent, text="Démarrer la surveillance", command=self.start_watch)
        self.start_watch_button.grid(row=0, column=2, padx=4, pady=4)

        self.stop_button = ttk.Button(parent, text="Arrêter", command=self.stop_worker, state=tk.DISABLED)
        self.stop_button.grid(row=0, column=3, padx=4, pady=4)

        self.open_source_button = ttk.Button(parent, text="Ouvrir dossier source", command=self.open_source_dir)
        self.open_source_button.grid(row=1, column=0, padx=4, pady=4)

        self.open_dest_button = ttk.Button(parent, text="Ouvrir dossier destination", command=self.open_dest_dir)
        self.open_dest_button.grid(row=1, column=1, padx=4, pady=4)

        self.show_processed_button = ttk.Button(parent, text="Voir vidéos traitées", command=self.show_processed_videos)
        self.show_processed_button.grid(row=1, column=2, padx=4, pady=4)

        # Progress bar
        self.progress_bar = ttk.Progressbar(parent, variable=self.progress_var, maximum=100)
        self.progress_bar.grid(row=2, column=0, columnspan=4, sticky="ew", padx=4, pady=4)

        # Theme button only
        self.theme_button = ttk.Button(parent, text="Thème sombre", command=self.toggle_theme)
        self.theme_button.grid(row=3, column=0, columnspan=4, sticky="ew", padx=4, pady=4)

    def create_log_area(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)
        self.log_text = scrolledtext.ScrolledText(parent, wrap=tk.WORD, state=tk.DISABLED)
        self.log_text.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)

    def browse_value(self, key):
        if key in {"source_dir", "dest_dir"}:
            directory = filedialog.askdirectory(title="Choisir un dossier")
            if directory:
                self.entry_vars[key].set(directory)
        else:
            file_path = filedialog.askopenfilename(title="Choisir un fichier")
            if file_path:
                self.entry_vars[key].set(file_path)

    def load_config(self):
        if CONFIG_PATH.exists():
            try:
                with CONFIG_PATH.open("r", encoding="utf-8-sig") as f:
                    config = json.load(f)
                self.apply_config(config)
                self.log_info(f"Configuration chargée depuis {CONFIG_PATH}")
            except Exception as exc:
                messagebox.showerror("Erreur", f"Impossible de charger config.json : {exc}")
        else:
            self.apply_config(DEFAULT_CONFIG)
            self.log_info("Aucun config.json trouvé, valeurs par défaut chargées.")

    def apply_config(self, config):
        self.entry_vars["source_dir"].set(config.get("source_dir", ""))
        self.entry_vars["dest_dir"].set(config.get("dest_dir", ""))
        self.entry_vars["client_secrets_file"].set(config.get("youtube", {}).get("client_secrets_file", "client_secrets.json"))
        self.entry_vars["credentials_file"].set(config.get("youtube", {}).get("credentials_file", "youtube_credentials.json"))
        self.entry_vars["rename_pattern"].set(config.get("rename_pattern", DEFAULT_CONFIG["rename_pattern"]))
        self.entry_vars["processed_state_file"].set(config.get("processed_state_file", DEFAULT_CONFIG["processed_state_file"]))
        self.entry_vars["default_title"].set(config.get("youtube", {}).get("default_title", DEFAULT_CONFIG["youtube"]["default_title"]))
        self.description_text.delete("1.0", tk.END)
        self.description_text.insert("1.0", config.get("youtube", {}).get("default_description", DEFAULT_CONFIG["youtube"]["default_description"]))
        self.entry_vars["tags"].set(", ".join(config.get("youtube", {}).get("tags", DEFAULT_CONFIG["youtube"]["tags"])))
        self.entry_vars["privacy_status"].set(config.get("youtube", {}).get("privacy_status", DEFAULT_CONFIG["youtube"]["privacy_status"]))
        self.entry_vars["category_id"].set(config.get("youtube", {}).get("category_id", DEFAULT_CONFIG["youtube"]["category_id"]))
        self.entry_vars["playlist_id"].set(config.get("youtube", {}).get("playlist_id", DEFAULT_CONFIG["youtube"]["playlist_id"]))
        self.entry_vars["max_uploads_per_day"].set(str(config.get("youtube", {}).get("max_uploads_per_day", DEFAULT_CONFIG["youtube"]["max_uploads_per_day"])))
        self.entry_vars["upload_history_file"].set(config.get("youtube", {}).get("upload_history_file", DEFAULT_CONFIG["youtube"]["upload_history_file"]))
        self.entry_vars["watch_interval"].set(str(config.get("watch_interval", "0")))

    def get_config(self):
        return {
            "source_dir": self.entry_vars["source_dir"].get().strip(),
            "dest_dir": self.entry_vars["dest_dir"].get().strip(),
            "rename_pattern": self.entry_vars["rename_pattern"].get().strip(),
            "processed_state_file": self.entry_vars["processed_state_file"].get().strip(),
            "youtube": {
                "client_secrets_file": self.entry_vars["client_secrets_file"].get().strip(),
                "credentials_file": self.entry_vars["credentials_file"].get().strip(),
                "default_title": self.entry_vars["default_title"].get().strip(),
                "default_description": self.description_text.get("1.0", tk.END).strip(),
                "tags": [tag.strip() for tag in self.entry_vars["tags"].get().split(",") if tag.strip()],
                "privacy_status": self.entry_vars["privacy_status"].get().strip(),
                "category_id": self.entry_vars["category_id"].get().strip(),
                "playlist_id": self.entry_vars["playlist_id"].get().strip(),
                "max_uploads_per_day": int(self.entry_vars["max_uploads_per_day"].get().strip() or DEFAULT_CONFIG["youtube"]["max_uploads_per_day"]),
                "upload_history_file": self.entry_vars["upload_history_file"].get().strip(),
            },
            "watch_interval": int(self.entry_vars["watch_interval"].get().strip() or 0),
        }

    def save_config(self):
        config = self.get_config()
        try:
            with CONFIG_PATH.open("w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            self.log_info(f"Configuration enregistrée dans {CONFIG_PATH}")
        except Exception as exc:
            messagebox.showerror("Erreur", f"Impossible d'enregistrer config.json : {exc}")

    def validate_config(self, config):
        if not config["source_dir"]:
            raise ValueError("Le dossier source est requis.")
        if not config["dest_dir"]:
            raise ValueError("Le dossier de destination est requis.")
        if not Path(config["source_dir"]).exists():
            raise ValueError("Le dossier source n'existe pas.")
        client_secrets_file = config.get("youtube", {}).get("client_secrets_file", "")
        if not client_secrets_file:
            raise ValueError("Le fichier client OAuth est requis.")
        # Résoudre le chemin relatif par rapport au répertoire du projet
        client_secrets_path = Path(client_secrets_file)
        if not client_secrets_path.is_absolute():
            client_secrets_path = CONFIG_PATH.parent / client_secrets_file
        if not client_secrets_path.exists():
            raise ValueError(f"Le fichier client OAuth est introuvable : {client_secrets_file}")
        max_uploads_per_day = config.get("youtube", {}).get("max_uploads_per_day", 13)
        if not isinstance(max_uploads_per_day, int) or max_uploads_per_day <= 0:
            raise ValueError("Le nombre maximum de vidéos par jour doit être un entier positif.")
        return True

    def append_log(self, message):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    def log_info(self, message):
        self.log_queue.put(message)

    def process_log_queue(self):
        try:
            while True:
                message = self.log_queue.get_nowait()
                self.append_log(message)
        except queue.Empty:
            pass
        self.after(100, self.process_log_queue)

    def run_once(self):
        self.start_task(dry_run=False, watch=0)

    def run_dry(self):
        self.start_task(dry_run=True, watch=0)

    def start_watch(self):
        watch = self.entry_vars["watch_interval"].get().strip()
        if not watch.isdigit():
            messagebox.showerror("Erreur", "Intervalle de surveillance invalide.")
            return
        self.start_task(dry_run=False, watch=int(watch))

    def start_task(self, dry_run: bool, watch: int):
        if self.worker_thread and self.worker_thread.is_alive():
            messagebox.showwarning("En cours", "Une tâche est déjà en cours.")
            return
        config = self.get_config()
        try:
            self.validate_config(config)
        except Exception as exc:
            messagebox.showerror("Erreur de configuration", str(exc))
            return
        if backend is None:
            messagebox.showerror("Erreur", f"Impossible de démarrer : {BACKEND_ERROR}")
            return
        # Normaliser les chemins relatifs pour qu'ils soient absolus
        config = self._normalize_config_paths(config)
        self.save_config()
        self.stop_event.clear()
        self.progress_var.set(0)
        self.worker_thread = threading.Thread(target=self.worker, args=(config, dry_run, watch), daemon=True)
        self.worker_thread.start()
        self.run_button.config(state=tk.DISABLED)
        self.dry_run_button.config(state=tk.DISABLED)
        self.start_watch_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)

    def _normalize_config_paths(self, config: dict) -> dict:
        """Convertir les chemins relatifs en chemins absolus."""
        config_dir = CONFIG_PATH.parent
        
        # Normaliser les chemins principaux
        if config.get("source_dir") and not Path(config["source_dir"]).is_absolute():
            config["source_dir"] = str(config_dir / config["source_dir"])
        if config.get("dest_dir") and not Path(config["dest_dir"]).is_absolute():
            config["dest_dir"] = str(config_dir / config["dest_dir"])
        if config.get("processed_state_file") and not Path(config["processed_state_file"]).is_absolute():
            config["processed_state_file"] = str(config_dir / config["processed_state_file"])
        
        # Normaliser les chemins YouTube
        if "youtube" in config:
            youtube_config = config["youtube"]
            if youtube_config.get("client_secrets_file") and not Path(youtube_config["client_secrets_file"]).is_absolute():
                youtube_config["client_secrets_file"] = str(config_dir / youtube_config["client_secrets_file"])
            if youtube_config.get("credentials_file") and not Path(youtube_config["credentials_file"]).is_absolute():
                youtube_config["credentials_file"] = str(config_dir / youtube_config["credentials_file"])
            if youtube_config.get("upload_history_file") and not Path(youtube_config["upload_history_file"]).is_absolute():
                youtube_config["upload_history_file"] = str(config_dir / youtube_config["upload_history_file"])
        
        return config

    def worker(self, config, dry_run, watch):
        self.log_info("Tâche démarrée...")
        logger = logging.getLogger("bambu_export_yt_gui")
        logger.setLevel(logging.INFO)
        logger.handlers.clear()
        queue_handler = QueueLoggingHandler(self.log_queue)
        logger.addHandler(queue_handler)

        try:
            root_logger = logging.getLogger()
            root_logger.setLevel(logging.INFO)
            root_logger.handlers.clear()
            root_logger.addHandler(queue_handler)
            formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
            queue_handler.setFormatter(formatter)
            if watch <= 0:
                backend.process_videos(
                    config,
                    dry_run=dry_run,
                    progress_callback=self.update_progress,
                    playlist_id=config["youtube"].get("playlist_id"),
                    stop_event=self.stop_event,
                )
            else:
                while not self.stop_event.is_set():
                    backend.process_videos(
                        config,
                        dry_run=dry_run,
                        progress_callback=self.update_progress,
                        playlist_id=config["youtube"].get("playlist_id"),
                        stop_event=self.stop_event,
                    )
                    self.log_info(f"Attente de {watch} secondes avant nouveau scan...")
                    for _ in range(watch):
                        if self.stop_event.is_set():
                            break
                        time.sleep(1)
        except Exception as exc:
            self.log_info(f"Erreur : {exc}")
        finally:
            self.log_info("Tâche terminée.")
            self.progress_var.set(0)
            self.run_button.config(state=tk.NORMAL)
            self.dry_run_button.config(state=tk.NORMAL)
            self.start_watch_button.config(state=tk.NORMAL)
            self.stop_button.config(state=tk.DISABLED)

    def stop_worker(self):
        if self.worker_thread and self.worker_thread.is_alive():
            self.stop_event.set()
            self.log_info("Arrêt demandé...")

    def toggle_theme(self):
        self.dark_mode = not self.dark_mode
        if self.dark_mode:
            self.configure(bg="#2b2b2b")
            self.theme_button.config(text="Thème clair")
            self.style.theme_use('clam')
            self.style.configure("TFrame", background="#2b2b2b")
            self.style.configure("TLabelframe", background="#2b2b2b")
            self.style.configure("TLabelframe.Label", background="#2b2b2b", foreground="#ffffff")
            self.style.configure("TLabel", background="#2b2b2b", foreground="#ffffff")
            self.style.configure("TButton", background="#4b4b4b", foreground="#ffffff")
            self.style.map("TButton",
                background=[('active', '#5a5a5a'), ('pressed', '#3a3a3a')],
                foreground=[('active', '#ffffff'), ('pressed', '#ffffff')]
            )
            self.style.configure("TEntry", fieldbackground="#4b4b4b", foreground="#ffffff", background="#4b4b4b")
            self.style.configure("Treeview", background="#2b2b2b", fieldbackground="#2b2b2b", foreground="#ffffff")
            self.style.configure("Vertical.TScrollbar", background="#4b4b4b", troughcolor="#333333", arrowcolor="#ffffff")
            self.style.configure("Dark.Horizontal.TProgressbar", troughcolor="#333333", background="#4b4b4b")
            self.progress_bar.config(style="Dark.Horizontal.TProgressbar")
            self.description_text.config(bg="#1e1e1e", fg="#ffffff", insertbackground="#ffffff")
            self.log_text.config(bg="#1e1e1e", fg="#ffffff", insertbackground="#ffffff")
        else:
            self.configure(bg="SystemButtonFace")
            self.theme_button.config(text="Thème sombre")
            self.style.theme_use(self.default_theme)
            self.progress_bar.config(style="Horizontal.TProgressbar")
            self.description_text.config(bg="white", fg="black", insertbackground="black")
            self.log_text.config(bg="white", fg="black", insertbackground="black")

    def update_progress(self, value):
        self.progress_var.set(value)
        self.update_idletasks()

    def toggle_config(self):
        if self.config_collapsed:
            self.config_frame.grid()
            self.toggle_config_button.config(text="Réduire configuration")
        else:
            self.config_frame.grid_remove()
            self.toggle_config_button.config(text="Afficher configuration")
        self.config_collapsed = not self.config_collapsed

    def open_source_dir(self):
        source_dir = self.entry_vars["source_dir"].get().strip()
        if not source_dir:
            messagebox.showwarning("Avertissement", "Aucun dossier source défini.")
            return
        try:
            if os.name == 'nt':  # Windows
                subprocess.run(['explorer', source_dir])
            else:
                subprocess.run(['xdg-open', source_dir])
            self.log_info(f"Dossier source ouvert : {source_dir}")
        except Exception as exc:
            messagebox.showerror("Erreur", f"Impossible d'ouvrir le dossier : {exc}")

    def open_dest_dir(self):
        dest_dir = self.entry_vars["dest_dir"].get().strip()
        if not dest_dir:
            messagebox.showwarning("Avertissement", "Aucun dossier destination défini.")
            return
        try:
            if os.name == 'nt':  # Windows
                subprocess.run(['explorer', dest_dir])
            else:
                subprocess.run(['xdg-open', dest_dir])
            self.log_info(f"Dossier destination ouvert : {dest_dir}")
        except Exception as exc:
            messagebox.showerror("Erreur", f"Impossible d'ouvrir le dossier : {exc}")

    def show_processed_videos(self):
        state_file = Path(self.entry_vars["processed_state_file"].get().strip() or "processed_videos.json")
        if not state_file.exists():
            messagebox.showinfo("Info", f"Aucun fichier d'état trouvé : {state_file}")
            return

        try:
            state = backend.load_json(state_file)
            if not state:
                messagebox.showinfo("Info", "Aucune vidéo traitée trouvée.")
                return

            # Créer une nouvelle fenêtre pour afficher la liste
            processed_window = tk.Toplevel(self)
            processed_window.title("Vidéos traitées")
            processed_window.geometry("800x600")

            frame = ttk.Frame(processed_window, padding=10)
            frame.pack(fill=tk.BOTH, expand=True)

            label = ttk.Label(frame, text=f"Vidéos traitées ({len(state)} vidéos)")
            label.pack(pady=5)

            tree = ttk.Treeview(frame, columns=("source", "destination"), show="headings")
            tree.heading("source", text="Source")
            tree.heading("destination", text="Destination")
            tree.pack(fill=tk.BOTH, expand=True, pady=5)

            scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=tree.yview)
            tree.configure(yscrollcommand=scrollbar.set)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

            for source, dest in state.items():
                tree.insert("", tk.END, values=(source, dest))

            # Bouton pour ouvrir le fichier d'état
            def open_state_file():
                try:
                    if os.name == 'nt':
                        subprocess.run(['notepad', str(state_file)])
                    else:
                        subprocess.run(['xdg-open', str(state_file)])
                except Exception as exc:
                    messagebox.showerror("Erreur", f"Impossible d'ouvrir le fichier : {exc}")

            open_button = ttk.Button(frame, text="Ouvrir fichier d'état", command=open_state_file)
            open_button.pack(pady=5)

        except Exception as exc:
            messagebox.showerror("Erreur", f"Impossible de lire le fichier d'état : {exc}")


class QueueLoggingHandler(logging.Handler):
    def __init__(self, queue_obj):
        super().__init__()
        self.queue = queue_obj

    def emit(self, record):
        self.queue.put(self.format(record))


def main():
    # Changer le répertoire de travail vers le répertoire parent de l'exécutable
    # pour que les chemins relatifs aux configs fonctionnent depuis dist/
    os.chdir(Path(__file__).parent.parent)
    
    if backend is None:
        message = (
            "Le module bambu_export_yt n'a pas pu être chargé.\n"
            "Installez les dépendances avec `pip install -r requirements.txt`.\n"
            f"Erreur technique : {BACKEND_ERROR}"
        )
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Erreur de dépendances", message)
        return
    app = GuiApp()
    app.mainloop()


if __name__ == "__main__":
    main()
