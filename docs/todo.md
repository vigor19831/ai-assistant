## TODO ##
---
[ ] <Specific Action/Title> | <Reason/Why this is a problem> | <Affected Files> | <How to verify/Test criteria>
---
core/ports/llm.py   45  stream() — AsyncIterator[str] без stop/error сигнала    CORE CHANGE REQUIRED: AsyncIterator[StreamChunk]

core/ports/vector_store.py  45  save(self, path: str, ...) — path дублирует self.config.index_path  CORE CHANGE REQUIRED: убрать path

