import os
from datetime import UTC, datetime

import chromadb

from jarvis.memory.models import MemoryEntry
from jarvis.observability.logger import get_logger

log = get_logger("vector_memory")

DUPLICATE_THRESHOLD = 0.05  # cosine distance; < this = near-duplicate


class VectorMemory:
    """ChromaDB-backed long-term vector memory with importance decay and deduplication."""

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

    def add(self, entry: MemoryEntry, deduplicate: bool = True) -> bool:
        """Add a memory entry. Returns False if skipped as duplicate."""
        if deduplicate and self.collection.count() > 0:
            existing = self.collection.query(
                query_texts=[entry.content],
                n_results=1,
            )
            if existing and existing["distances"] and existing["distances"][0]:
                distance = existing["distances"][0][0]
                if distance < DUPLICATE_THRESHOLD:
                    existing_id = existing["ids"][0][0]
                    existing_meta = existing["metadatas"][0][0] if existing["metadatas"] else {}
                    old_score = float(existing_meta.get("importance_score", 0.5))
                    new_score = max(old_score, entry.importance_score)
                    if new_score > old_score:
                        self.collection.update(
                            ids=[existing_id],
                            metadatas=[{**existing_meta, "importance_score": new_score}],
                        )
                    log.info("memory_deduplicated", existing_id=existing_id, distance=distance)
                    return False

        self.collection.add(
            ids=[entry.id],
            documents=[entry.content],
            metadatas=[
                {
                    "importance_score": entry.importance_score,
                    "ttl_hours": entry.ttl_hours or -1,
                    "created_at": entry.created_at,
                    "source": entry.source,
                    "creator_flag": entry.creator_flag,
                    "permanent_flag": entry.permanent_flag,
                    **{k: str(v) for k, v in entry.metadata.items()},
                }
            ],
        )
        return True

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
                entries.append(
                    {
                        "id": results["ids"][0][i],
                        "content": doc,
                        "metadata": meta,
                        "distance": results["distances"][0][i] if results["distances"] else None,
                    }
                )
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
        now = datetime.now(UTC)
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

    def get_all(self, limit: int = 100, offset: int = 0) -> list[dict]:
        """Get all vector memory entries for browsing."""
        if not self.collection or self.collection.count() == 0:
            return []
        all_data = self.collection.get(
            include=["documents", "metadatas"],
            limit=limit,
            offset=offset,
        )
        entries = []
        for i, mid in enumerate(all_data["ids"]):
            doc = all_data["documents"][i] if all_data["documents"] else ""
            meta = all_data["metadatas"][i] if all_data["metadatas"] else {}
            entries.append(
                {
                    "id": mid,
                    "content": doc,
                    "importance_score": float(meta.get("importance_score", 0)),
                    "source": meta.get("source", ""),
                    "permanent": meta.get("permanent_flag") in (True, "True", "true"),
                    "created_at": meta.get("created_at", ""),
                    "ttl_hours": int(meta.get("ttl_hours", -1)),
                    "metadata": {
                        k: v
                        for k, v in meta.items()
                        if k
                        not in (
                            "importance_score",
                            "source",
                            "permanent_flag",
                            "created_at",
                            "ttl_hours",
                            "creator_flag",
                        )
                    },
                }
            )
        # Sort by importance descending
        entries.sort(key=lambda e: e["importance_score"], reverse=True)
        return entries

    def delete_memory(self, memory_id: str):
        """Delete a specific memory entry."""
        if self.collection:
            self.collection.delete(ids=[memory_id])

    def flush_all(self) -> int:
        """Delete ALL entries from vector memory. Returns count deleted."""
        if not self.collection:
            return 0
        count = self.collection.count()
        if count == 0:
            return 0
        all_ids = self.collection.get()["ids"]
        if all_ids:
            self.collection.delete(ids=all_ids)
        log.info("vector_memory_flushed_all", count=count)
        return count

    def flush_non_permanent(self) -> int:
        """Delete all non-permanent entries. Returns count deleted."""
        if not self.collection:
            return 0
        all_data = self.collection.get(include=["metadatas"])
        to_delete = []
        for i, mid in enumerate(all_data["ids"]):
            meta = all_data["metadatas"][i]
            if meta.get("permanent_flag") not in (True, "True", "true"):
                to_delete.append(mid)
        if to_delete:
            self.collection.delete(ids=to_delete)
        log.info("vector_memory_flushed_non_permanent", count=len(to_delete))
        return len(to_delete)

    def deduplicate(self) -> int:
        """Scan all entries and remove near-duplicates, keeping the highest-importance version."""
        if not self.collection or self.collection.count() < 2:
            return 0
        all_data = self.collection.get(include=["documents", "metadatas"])
        ids = all_data["ids"]
        docs = all_data["documents"]
        metas = all_data["metadatas"]
        to_delete = set()

        for i in range(len(ids)):
            if ids[i] in to_delete:
                continue
            results = self.collection.query(query_texts=[docs[i]], n_results=5)
            if not results or not results["ids"]:
                continue
            for j, match_id in enumerate(results["ids"][0]):
                if match_id == ids[i] or match_id in to_delete:
                    continue
                distance = results["distances"][0][j] if results["distances"] else 1.0
                if distance < DUPLICATE_THRESHOLD:
                    match_meta = results["metadatas"][0][j] if results["metadatas"] else {}
                    my_score = float(metas[i].get("importance_score", 0))
                    match_score = float(match_meta.get("importance_score", 0))
                    victim = match_id if my_score >= match_score else ids[i]
                    to_delete.add(victim)

        if to_delete:
            self.collection.delete(ids=list(to_delete))
            log.info("vector_memory_deduplicated", removed=len(to_delete))
        return len(to_delete)

    def get_stats(self) -> dict:
        count = self.collection.count() if self.collection else 0
        return {"total_entries": count}
