import os
import chromadb
from datetime import datetime, timezone
from jarvis.memory.models import MemoryEntry
from jarvis.observability.logger import get_logger

log = get_logger("vector_memory")


class VectorMemory:
    """ChromaDB-backed long-term vector memory with importance decay.
    Uses persistent local client (no separate server needed)."""

    def __init__(self, data_dir: str = "/data"):
        self.data_dir = data_dir
        self.client = None
        self.collection = None

    def connect(self):
        chroma_dir = os.path.join(self.data_dir, "chroma")
        os.makedirs(chroma_dir, exist_ok=True)
        self.client = chromadb.PersistentClient(path=chroma_dir)
        self.collection = self.client.get_or_create_collection(
            name="jarvis_memory",
            metadata={"hnsw:space": "cosine"},
        )
        log.info("vector_memory_connected", path=chroma_dir)

    def add(self, entry: MemoryEntry):
        self.collection.add(
            ids=[entry.id],
            documents=[entry.content],
            metadatas=[{
                "importance_score": entry.importance_score,
                "ttl_hours": entry.ttl_hours or -1,
                "created_at": entry.created_at,
                "source": entry.source,
                "creator_flag": entry.creator_flag,
                "permanent_flag": entry.permanent_flag,
                **{k: str(v) for k, v in entry.metadata.items()},
            }],
        )

    def search(self, query: str, n_results: int = 5) -> list[dict]:
        if self.collection.count() == 0:
            return []
        results = self.collection.query(
            query_texts=[query],
            n_results=min(n_results, self.collection.count()),
        )
        entries = []
        if results and results["documents"]:
            for i, doc in enumerate(results["documents"][0]):
                meta = results["metadatas"][0][i] if results["metadatas"] else {}
                entries.append({
                    "id": results["ids"][0][i],
                    "content": doc,
                    "metadata": meta,
                    "distance": results["distances"][0][i] if results["distances"] else None,
                })
        return entries

    def mark_permanent(self, memory_id: str):
        self.collection.update(
            ids=[memory_id],
            metadatas=[{"permanent_flag": True, "ttl_hours": -1}],
        )

    def decay_importance(self, decay_factor: float = 0.95):
        """Reduce importance of non-permanent memories."""
        all_data = self.collection.get(include=["metadatas"])
        if not all_data["ids"]:
            return
        ids_to_update = []
        new_metadatas = []
        for i, mid in enumerate(all_data["ids"]):
            meta = all_data["metadatas"][i]
            if meta.get("permanent_flag") in (True, "True", "true"):
                continue
            current = float(meta.get("importance_score", 0.5))
            new_score = max(0.01, current * decay_factor)
            meta["importance_score"] = new_score
            ids_to_update.append(mid)
            new_metadatas.append(meta)

        if ids_to_update:
            self.collection.update(ids=ids_to_update, metadatas=new_metadatas)

    def prune_expired(self):
        """Remove memories past their TTL (unless permanent)."""
        all_data = self.collection.get(include=["metadatas"])
        if not all_data["ids"]:
            return 0
        now = datetime.now(timezone.utc)
        to_delete = []
        for i, mid in enumerate(all_data["ids"]):
            meta = all_data["metadatas"][i]
            if meta.get("permanent_flag") in (True, "True", "true"):
                continue
            ttl = int(meta.get("ttl_hours", -1))
            if ttl <= 0:
                continue
            created = meta.get("created_at", "")
            try:
                created_dt = datetime.fromisoformat(created)
                hours_old = (now - created_dt).total_seconds() / 3600
                if hours_old > ttl:
                    to_delete.append(mid)
            except (ValueError, TypeError):
                continue
        if to_delete:
            self.collection.delete(ids=to_delete)
            log.info("memories_pruned", count=len(to_delete))
        return len(to_delete)

    def get_stats(self) -> dict:
        count = self.collection.count() if self.collection else 0
        return {"total_entries": count}
