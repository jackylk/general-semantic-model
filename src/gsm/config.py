from dataclasses import dataclass, field
from pathlib import Path
import os
from dotenv import dotenv_values

@dataclass
class Settings:
    passwords: dict[str, str] = field(repr=False)
    host: str = '127.0.0.1'
    port: int = 55438
    source_root: Path | None = None
    file_root: Path = field(default_factory=lambda: Path.home()/'.local/share/general-semantic-model/files')

    @classmethod
    def load(cls):
        cfg = {**dotenv_values('.env'), **os.environ}
        return cls(passwords={
            'owner': cfg.get('GSM_DB_PASSWORD', ''),
            'developer': cfg.get('GSM_DEVELOPER_DB_PASSWORD', ''),
            'consumer': cfg.get('GSM_CONSUMER_DB_PASSWORD', ''),
        }, host=cfg.get('GSM_DB_HOST', '127.0.0.1'), port=int(cfg.get('GSM_DB_PORT', 55438)),
            source_root=Path(cfg['GSM_SOURCE_ROOT']).expanduser().resolve() if cfg.get('GSM_SOURCE_ROOT') else None,
            file_root=Path(cfg.get('GSM_FILE_ROOT', str(Path.home()/'.local/share/general-semantic-model/files'))).expanduser().resolve())
