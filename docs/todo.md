## TODO ##
---
[ ] <Specific Action/Title> | <Reason/Why this is a problem> | <Affected Files> | <How to verify/Test criteria>
---
core/ports/llm.py   45  stream() — AsyncIterator[str] без stop/error сигнала    CORE CHANGE REQUIRED: AsyncIterator[StreamChunk]

core/ports/vector_store.py  45  save(self, path: str, ...) — path дублирует self.config.index_path  CORE CHANGE REQUIRED: убрать path



---
api/lifespan.py 68  Startup: цикл vector_store.load — только AdapterError/VersionMismatchError ловятся, остальное крашит startup    except Exception as exc: внутри цикла, log + skip


api/lifespan.py 140 Shutdown order: vector_store закрывается до storage Поменять: chunker -> reranker -> storage -> vector_store -> llm -> embedder -> tokenizer


features/chat/manager.py    77  rag_steps параметр принимается, но игнорируется Использовать в _build_pipeline или убрать параметр_


core/config.py  180 tokenizer_local_dir — deprecated=True не добавлен в Pydantic field  Field(..., deprecated=True) (Pydantic v2)

core/query_parser.py    15  RAG_NS_MAP hardcoded, не синхронизирован с config.namespaces    Убрать constants.py map, читать из config.namespaces
