"""本地 RAG 降级方案：TF-IDF + BM25 内存检索。

当 Dify 不可用时，使用本地知识库做检索增强生成。
纯 CPU 运行，零 GPU 依赖，无需下载任何模型。

降级链路：Dify RAG → LocalRAG + DeepSeek → 通义千问
"""

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

_KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent.parent / "knowledge"
_TOP_K = 3


class LocalRAG:
    """本地知识库检索。

    读取 knowledge/ 下文档 → 分块 → TF-IDF 向量化 → cosine 相似度检索。
    完全离线，无需下载模型。
    """

    def __init__(self) -> None:
        self._vectorizer = None
        self._tfidf_matrix = None
        self._chunks: list[dict] = []
        self._index_ready = False

    def _load_chunks(self) -> list[dict]:
        """加载 knowledge/ 下所有 .md 文档并按段落分块。

        Returns:
            分块列表，每项含 text/source/title
        """
        chunks: list[dict] = []
        if not _KNOWLEDGE_DIR.exists():
            logger.warning("[LocalRAG] 知识目录不存在: %s", _KNOWLEDGE_DIR)
            return chunks

        for md_file in sorted(_KNOWLEDGE_DIR.glob("*.md")):
            try:
                text = md_file.read_text(encoding="utf-8")
                if not text.strip():
                    continue

                # 按章节和段落分割
                paragraphs = re.split(r"\n\s*\n", text)
                for para in paragraphs:
                    para = para.strip()
                    if len(para) < 20:
                        continue
                    chunks.append(
                        {
                            "text": para,
                            "source": md_file.name,
                            "title": md_file.stem,
                        }
                    )

                logger.info(
                    "[LocalRAG] 加载文档: %s → %d 段落",
                    md_file.name,
                    sum(1 for p in paragraphs if len(p.strip()) >= 20),
                )
            except Exception as e:
                logger.error("[LocalRAG] 加载文档失败 %s: %s", md_file.name, e)

        return chunks

    def build_index(self) -> bool:
        """构建 TF-IDF 向量索引。

        Returns:
            成功返回 True
        """
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer

            chunks = self._load_chunks()
            if not chunks:
                logger.warning("[LocalRAG] 无文档可索引")
                return False

            texts = [c["text"] for c in chunks]

            # 使用带中文支持的 TF-IDF 向量化器
            self._vectorizer = TfidfVectorizer(
                analyzer="char",
                ngram_range=(1, 3),
                max_features=50000,
                min_df=1,
                sublinear_tf=True,
            )
            self._tfidf_matrix = self._vectorizer.fit_transform(texts)
            self._chunks = chunks
            self._index_ready = True
            logger.info(
                "[LocalRAG] 索引构建成功: %d 个段落, 词表大小 %d",
                len(chunks),
                len(self._vectorizer.get_feature_names_out()),
            )
            return True

        except ImportError as e:
            logger.error("[LocalRAG] 依赖缺失: %s，请安装 scikit-learn", e)
            self._index_ready = False
            return False
        except Exception as e:
            logger.error(
                "[LocalRAG] 索引构建失败: %s",
                e,
                exc_info=True,
            )
            self._index_ready = False
            return False

    def search(self, query: str, k: int = _TOP_K) -> str:
        """检索与 query 最相关的文档上下文。

        Args:
            query: 用户查询
            k: 返回最相关的前 k 个块

        Returns:
            拼接后的上下文文本，无结果返回空字符串
        """
        if not self._index_ready:
            logger.warning("[LocalRAG] 索引未就绪，尝试构建")
            success = self.build_index()
            if not success:
                logger.warning("[LocalRAG] 索引构建失败，无法检索")
                return ""

        try:
            import numpy as np
            from sklearn.metrics.pairwise import cosine_similarity

            query_vec = self._vectorizer.transform([query])
            similarities = cosine_similarity(query_vec, self._tfidf_matrix).flatten()
            top_indices = np.argsort(similarities)[::-1][:k]

            contexts: list[str] = []
            for idx in top_indices:
                if similarities[idx] < 0.01:
                    continue
                chunk = self._chunks[idx]
                source = chunk["source"]
                text = chunk["text"][:200]
                contexts.append(f"[来源: {source}]\n{text}...")

            if not contexts:
                logger.info("[LocalRAG] 检索无匹配: query=%s", query[:30])
                return ""

            context = "\n\n".join(contexts)
            logger.info(
                "[LocalRAG] 检索成功: query=%s, top_k=%d → %d 结果",
                query[:30],
                k,
                len(contexts),
            )
            return context
        except Exception as e:
            logger.error("[LocalRAG] 检索失败: %s", e)
            return ""

    def rebuild_index(self) -> bool:
        """强制重建索引（文档更新后调用）。

        Returns:
            成功返回 True
        """
        self._vectorizer = None
        self._tfidf_matrix = None
        self._chunks = []
        self._index_ready = False
        return self.build_index()


local_rag = LocalRAG()
