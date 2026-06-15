"""
KnowledgeStore — 向量知识库 for 私人用户数据.

L3 层：基于 chromadb + sentence-transformers 做语义检索。
写入点：diary_agent / insight_agent / memory_agent
检索点：knowledge_base.build_context()

设计原则：上层调用不需要知道底层是 SQL 还是向量检索。
所有 import 都是懒加载，不依赖 chromadb / torch 也能启动。
"""

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# ── App-level shared resources ──
_shared_model = None
_shared_chroma = None
_vector_available = False


def init_vector_store(persist_dir: str = "./instance/chroma"):
    """Initialize shared resources at app startup. Call once from create_app().

    Safe to call even when chromadb/torch is not installed — fails gracefully.
    """
    global _shared_model, _shared_chroma, _vector_available

    try:
        import os
        os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        os.environ["HF_HUB_OFFLINE"] = "1"

        import chromadb
        from sentence_transformers import SentenceTransformer
        logger.info("Loading embedding model: all-MiniLM-L6-v2 (offline)")
        _shared_model = SentenceTransformer("all-MiniLM-L6-v2")
        logger.info("Connecting to chromadb: %s", persist_dir)
        _shared_chroma = chromadb.PersistentClient(path=persist_dir)
        _vector_available = True
        logger.info("Vector store initialized")
    except ImportError as e:
        logger.warning("Vector store unavailable (dependencies not installed): %s", e)
        _vector_available = False
    except Exception as e:
        logger.warning("Vector store init skipped: %s", e)
        _vector_available = False


def is_vector_available() -> bool:
    return _vector_available


class KnowledgeStore:
    """私人知识库向量存储。每个用户一个 collection。

    可安全使用，即使向量引擎不可用也只是返回空结果。
    """

    def __init__(self, user_id: int, persist_dir: str = "./instance/chroma"):
        self.user_id = user_id

        if not _vector_available:
            self.client = None
            self.model = None
            self.collection = None
            return

        self.client = _shared_chroma
        self.model = _shared_model
        self.collection = self._get_or_create_collection()

    def _get_or_create_collection(self):
        if not self.client:
            return None
        name = f"user_{self.user_id}"
        try:
            return self.client.get_collection(name)
        except ValueError:
            return self.client.create_collection(name)

    # ── Write ──

    def add_diary(self, diary_id: int, title: str, content: str,
                  emotion_tags: list[str] | None = None,
                  date_str: str | None = None) -> None:
        if not _vector_available or not self.collection:
            return
        tag_str = "、".join(emotion_tags or [])
        text = f"[日记] {title}\n{content[:500]}\n情绪：{tag_str}"
        embedding = self.model.encode(text).tolist()
        self.collection.upsert(
            ids=[f"diary_{diary_id}"],
            embeddings=[embedding],
            metadatas=[{
                "type": "diary",
                "date": date_str or str(datetime.now(timezone.utc).date()),
                "title": title[:80],
            }],
            documents=[text],
        )

    def add_insight(self, insight_id: int, insight_text: str,
                    emotion_tags: list[str] | None = None,
                    date_str: str | None = None) -> None:
        if not _vector_available or not self.collection:
            return
        tag_str = "、".join(emotion_tags or [])
        text = f"[洞察] {insight_text[:500]}\n情绪：{tag_str}"
        embedding = self.model.encode(text).tolist()
        self.collection.upsert(
            ids=[f"insight_{insight_id}"],
            embeddings=[embedding],
            metadatas=[{
                "type": "insight",
                "date": date_str or str(datetime.now(timezone.utc).date()),
            }],
            documents=[text],
        )

    def add_session_summary(self, session_id: int, summary_text: str,
                            date_str: str | None = None) -> None:
        if not _vector_available or not self.collection:
            return
        if not summary_text or len(summary_text) < 20:
            return
        embedding = self.model.encode(summary_text[:500]).tolist()
        self.collection.upsert(
            ids=[f"session_{session_id}"],
            embeddings=[embedding],
            metadatas=[{
                "type": "session",
                "date": date_str or str(datetime.now(timezone.utc).date()),
            }],
            documents=[summary_text[:500]],
        )

    def delete(self, doc_id: str) -> None:
        if not _vector_available or not self.collection:
            return
        self.collection.delete(ids=[doc_id])

    # ── Search ──

    def search(self, query: str, top_k: int = 3) -> list[dict]:
        if not _vector_available or not self.collection:
            return []
        if not query or len(query.strip()) < 2:
            return []

        query_emb = self.model.encode(query).tolist()
        results = self.collection.query(
            query_embeddings=[query_emb],
            n_results=top_k,
        )

        scored = []
        for i in range(len(results["ids"][0])):
            doc_id = results["ids"][0][i]
            text = results["documents"][0][i]
            meta = results["metadatas"][0][i]
            distance = results["distances"][0][i]
            similarity = 1.0 - distance

            # 时间衰减
            date_str = meta.get("date", "")
            time_weight = 1.0
            if date_str:
                try:
                    days_ago = (
                        datetime.now(timezone.utc).date()
                        - datetime.fromisoformat(date_str).date()
                    ).days
                    time_weight = max(0.3, 1.0 - days_ago * 0.02)
                except ValueError:
                    pass

            final_score = similarity * 0.7 + time_weight * 0.3
            scored.append({
                "id": doc_id,
                "text": text[:200],
                "type": meta.get("type", "unknown"),
                "date": date_str,
                "score": round(final_score, 3),
            })

        return sorted(scored, key=lambda x: -x["score"])[:top_k]

    # ── Sync ──

    def clear(self) -> None:
        if not _vector_available or not self.client:
            return
        try:
            self.client.delete_collection(f"user_{self.user_id}")
        except ValueError:
            pass
        self.collection = self._get_or_create_collection()

    def sync_all(self, user) -> int:
        if not _vector_available:
            return 0
        from models.diary import Diary
        from models.insight import Insight

        count = 0
        diaries = Diary.query.filter_by(user_id=user.id).all()
        for d in diaries:
            try:
                self.add_diary(
                    diary_id=d.id, title=d.title,
                    content=d.content or "",
                    emotion_tags=d.emotion_tags,
                    date_str=str(d.date) if d.date else None,
                )
                count += 1
            except Exception as e:
                logger.warning(f"Skip diary {d.id}: {e}")

        insights = Insight.query.filter_by(user_id=user.id).all()
        for i in insights:
            try:
                self.add_insight(
                    insight_id=i.id,
                    insight_text=i.insight_text or "",
                    emotion_tags=i.emotion_tags,
                    date_str=str(i.created_at.date()) if i.created_at else None,
                )
                count += 1
            except Exception as e:
                logger.warning(f"Skip insight {i.id}: {e}")

        logger.info(f"KnowledgeStore synced {count} items for user {user.id}")
        return count
