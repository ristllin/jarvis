import os
import json
from datetime import datetime, timezone
from jarvis.memory.models import BlobRecord
from jarvis.observability.logger import get_logger

log = get_logger("blob")


class BlobStorage:
    """Append-only JSON-lines blob storage under /data/blob/"""

    def __init__(self, data_dir: str = "/data"):
        self.blob_dir = os.path.join(data_dir, "blob")
        os.makedirs(self.blob_dir, exist_ok=True)

    def store(self, event_type: str, content: str, metadata: dict = None) -> str:
        now = datetime.now(timezone.utc)
        record = BlobRecord(
            timestamp=now.isoformat(),
            event_type=event_type,
            content=content,
            metadata=metadata or {},
        )
        filename = now.strftime("%Y-%m-%d.jsonl")
        filepath = os.path.join(self.blob_dir, filename)
        with open(filepath, "a") as f:
            f.write(record.model_dump_json() + "\n")
        return filepath

    def read_recent(self, limit: int = 50) -> list[dict]:
        """Read most recent blob entries across all files."""
        entries = []
        files = sorted(
            [f for f in os.listdir(self.blob_dir) if f.endswith(".jsonl")],
            reverse=True,
        )
        for fname in files:
            if len(entries) >= limit:
                break
            filepath = os.path.join(self.blob_dir, fname)
            with open(filepath, "r") as f:
                lines = f.readlines()
            for line in reversed(lines):
                if len(entries) >= limit:
                    break
                try:
                    entries.append(json.loads(line.strip()))
                except json.JSONDecodeError:
                    continue
        return entries

    def get_stats(self) -> dict:
        total_files = 0
        total_size = 0
        for fname in os.listdir(self.blob_dir):
            if fname.endswith(".jsonl"):
                total_files += 1
                total_size += os.path.getsize(os.path.join(self.blob_dir, fname))
        return {
            "total_files": total_files,
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
        }
