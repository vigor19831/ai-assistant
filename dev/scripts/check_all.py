"""Проверка всего проекта одной командой."""

import sys
import asyncio
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

errors = []
warnings = []

def error(msg):
    errors.append(msg)

def warn(msg):
    warnings.append(msg)

print("=" * 60)
print("ПРОВЕРКА ПРОЕКТА")
print("=" * 60)

# ===================================================================
# 1. БАЗОВЫЕ ИМПОРТЫ
# ===================================================================
print("\n[1/10] Проверка импортов...")

try:
    from ai_assistant.core.config import load_config, AppConfig
    from ai_assistant.core.constants import RAG_NS_MAP, RAG_PREFIX_RE
    from ai_assistant.core.domain.pipeline import PipelineData
    from ai_assistant.core.domain.messages import UserMessage
    print("   OK: core импорты")
except Exception as e:
    error("Core импорты сломаны: " + str(e))

try:
    from ai_assistant.core.pipeline_steps import STEP_REGISTRY, embed_query, retrieve, build_context, generate, rerank
    print("   OK: pipeline steps")
except Exception as e:
    error("Pipeline steps сломаны: " + str(e))

try:
    from ai_assistant.features.chat.manager import ChatManager
    print("   OK: ChatManager")
except Exception as e:
    error("ChatManager не импортируется: " + str(e))

try:
    from ai_assistant.features.rag.manager import RAGManager, IndexingManager
    print("   OK: RAG managers")
except Exception as e:
    error("RAG managers не импортируются: " + str(e))

try:
    from ai_assistant.adapters.factory import create_adapter
    print("   OK: adapter factory")
except Exception as e:
    error("Factory не импортируется: " + str(e))

try:
    from ai_assistant.main import create_app
    print("   OK: main app")
except Exception as e:
    error("main.py сломан: " + str(e))

# ===================================================================
# 2. КОНФИГ
# ===================================================================
print("\n[2/10] Проверка config.yaml...")

try:
    cfg = load_config(PROJECT_ROOT / "config.yaml")
    print("   OK: config загружен")
except Exception as e:
    error("Config не загружается: " + str(e))
    cfg = None

if cfg:
    # dim match
    if cfg.embedder.dim != cfg.vector_store.dim:
        error("embedder.dim (" + str(cfg.embedder.dim) + ") != vector_store.dim (" + str(cfg.vector_store.dim) + ")")
    else:
        print("   OK: dim совпадает (" + str(cfg.embedder.dim) + ")")

    # namespace consistency
    config_ns = set(cfg.namespaces.keys())
    map_ns = set(RAG_NS_MAP.values())
    if config_ns != map_ns:
        error("Несовпадение namespace'ов:")
        error("  config.yaml: " + str(sorted(config_ns)))
        error("  constants.py: " + str(sorted(map_ns)))
    else:
        print("   OK: namespace'ы совпадают (" + str(len(config_ns)) + ")")

    # RAG steps registered
    from ai_assistant.core.config import RAGStep
    for step in cfg.rag.steps:
        if step.value not in STEP_REGISTRY:
            error("Pipeline step не зарегистрирован: " + step.value)
        else:
            print("   OK: step '" + step.value + "' зарегистрирован")

    # Check required adapters can be created (mock mode)
    print("\n[3/10] Проверка создания адаптеров (mock)...")
    try:
        mock_cfg = type("MC", (), {"dim": cfg.embedder.dim, "timeout": 1.0, "model": "mock", "api_base": "", "api_key": None})()
        emb = create_adapter("embedder", "mock", mock_cfg)
        print("   OK: mock embedder (dim=" + str(emb.dimension) + ")")
    except Exception as e:
        error("Mock embedder не создается: " + str(e))

    try:
        vs_cfg = type("VC", (), {"dim": cfg.vector_store.dim, "metric": "l2", "max_chunks": 1000})()
        vs = create_adapter("vector_store", "memory", vs_cfg)
        print("   OK: memory vector store")
    except Exception as e:
        error("Memory vector store не создается: " + str(e))

# ===================================================================
# 3. ШАБЛОНЫ
# ===================================================================
print("\n[4/10] Проверка шаблонов...")

prompts_dir = PROJECT_ROOT / "src" / "ai_assistant" / "core" / "prompts" / "v1"
required_templates = ["rag_strict", "rag_creative", "rag_default"]

for name in required_templates:
    template = prompts_dir / (name + ".j2")
    if not template.exists():
        error("Шаблон не найден: " + str(template))
    else:
        content = template.read_text(encoding="utf-8")
        if "{{ context }}" in content:
            print("   OK: " + name + ".j2 использует {{ context }}")
        elif "{{ chunks }}" in content:
            error("Шаблон " + name + ".j2 использует УСТАРЕВШИЙ {{ chunks }} — нужно {{ context }}")
        else:
            warn("Шаблон " + name + ".j2 не использует ни context, ни chunks")

# ===================================================================
# 4. LIFESPAN
# ===================================================================
print("\n[5/10] Проверка lifespan.py...")

lifespan = PROJECT_ROOT / "src" / "ai_assistant" / "api" / "lifespan.py"
if lifespan.exists():
    content = lifespan.read_text()
    has_load = "vector_store.load" in content or "await state.vector_store.load" in content
    has_save = "vector_store.save" in content or "await state.vector_store.save" in content

    if has_load:
        print("   OK: lifespan загружает индексы (.load)")
    else:
        error("lifespan.py НЕ загружает индексы при старте!")

    if has_save:
        print("   OK: lifespan сохраняет индексы (.save)")
    else:
        error("lifespan.py НЕ сохраняет индексы при остановке!")

# ===================================================================
# 5. PIPELINE DATA (immutability)
# ===================================================================
print("\n[6/10] Проверка PipelineData...")

try:
    from ai_assistant.core.domain.documents import Chunk
    from ai_assistant.core.domain.pipeline import PipelineData

    d1 = PipelineData(query=UserMessage(text="test"))
    d2 = d1.with_context("hello")

    if d1.context == "" and d2.context == "hello":
        print("   OK: PipelineData immutable (with_context)")
    else:
        error("PipelineData мутирует!")

    d3 = d2.add_error("err")
    if len(d3.errors) == 1 and len(d2.errors) == 0:
        print("   OK: PipelineData immutable (add_error)")
    else:
        error("add_error мутирует!")

except Exception as e:
    error("PipelineData проверка сломана: " + str(e))

# ===================================================================
# 6. RAG PREFIX REGEX
# ===================================================================
print("\n[7/10] Проверка RAG_PREFIX_RE...")

test_cases = [
    ("[p] hello", "p", "hello"),
    ("[w] work", "w", "work"),
    ("[c] code", "c", "code"),
    ("[b] books", "b", "books"),
    ("[o] other", "o", "other"),
    ("no prefix", None, None),
    ("p] missing bracket", None, None),
]

for text, expected_short, expected_query in test_cases:
    m = RAG_PREFIX_RE.match(text)
    if expected_short:
        if m and m.group(1).lower() == expected_short and m.group(2) == expected_query:
            print("   OK: '" + text + "' → ns=" + expected_short)
        else:
            error("RAG_PREFIX_RE не парсит: '" + text + "'")
    else:
        if m is None:
            print("   OK: '" + text + "' → no match (correct)")
        else:
            error("RAG_PREFIXRE ложно парсит: '" + text + "'")

# ===================================================================
# 7. MOCK PIPELINE RUN
# ===================================================================
print("\n[8/10] Тестовый прогон pipeline (mock)...")

async def test_pipeline():
    from dataclasses import replace

    class FakeEmbedder:
        dimension = 384
        async def embed(self, texts):
            return [[0.1] * 384 for _ in texts]

    class FakeVectorStore:
        async def search(self, emb, top_k=5, namespace="default"):
            from ai_assistant.core.domain.documents import Chunk, ChunkMetadata
            return [Chunk(id="c1", text="ответ: синий", metadata=ChunkMetadata(source="doc", index=0, total_chunks=1))]

    class FakeLLM:
        async def complete(self, messages, **kw):
            from ai_assistant.core.domain.messages import AssistantMessage
            return AssistantMessage(text="синий")

    data = PipelineData(query=UserMessage(text="какой цвет"))
    data = replace(data, metadata={
        "embedder": FakeEmbedder(),
        "vector_store": FakeVectorStore(),
        "llm": FakeLLM(),
        "top_k": 5,
        "namespace": "personal",
        "prompt_version": "v1",
        "prompt_name": "rag_strict",
    })

    try:
        data = await embed_query(data)
        print("   OK: embed_query")

        data = await retrieve(data)
        if len(data.chunks) > 0:
            print("   OK: retrieve → " + str(len(data.chunks)) + " chunks")
        else:
            error("retrieve вернул 0 chunks!")

        data = await build_context(data)
        if len(data.context) > 0:
            print("   OK: build_context → " + str(len(data.context)) + " chars")
        else:
            error("build_context вернул пустую строку!")

        data = await generate(data)
        if data.response and data.response.text:
            print("   OK: generate → '" + data.response.text + "'")
        else:
            error("generate вернул пустой ответ!")

    except Exception as e:
        error("Pipeline сломался: " + str(e))

asyncio.run(test_pipeline())

# ===================================================================
# 8. ФАЙЛЫ ДОКУМЕНТОВ
# ===================================================================
print("\n[9/10] Проверка documents/...")

docs_root = PROJECT_ROOT / "documents"
expected_folders = ["personal", "work", "other", "code", "books"]
for folder in expected_folders:
    path = docs_root / folder
    if path.exists():
        files = list(path.iterdir())
        print("   OK: " + folder + "/ (" + str(len(files)) + " файлов)")
    else:
        warn("Папка documents/" + folder + " не существует")

# ===================================================================
# 9. ИНДЕКСЫ
# ===================================================================
print("\n[10/10] Проверка data/indices/...")

indices_root = PROJECT_ROOT / "data" / "indices"
if indices_root.exists():
    for idx_dir in indices_root.iterdir():
        if idx_dir.is_dir():
            files = list(idx_dir.iterdir())
            print("   OK: indices/" + idx_dir.name + "/ (" + str(len(files)) + " файлов)")
else:
    warn("Папка data/indices/ не существует — индексы не созданы")

# ===================================================================
# РЕЗУЛЬТАТ
# ===================================================================
print("\n" + "=" * 60)
if errors:
    print("ОШИБКИ (" + str(len(errors)) + ") — нужно исправить:")
    for e in errors:
        print("  ❌ " + e)
if warnings:
    print("ПРЕДУПРЕЖДЕНИЯ (" + str(len(warnings)) + "):")
    for w in warnings:
        print("  ⚠️  " + w)
if not errors and not warnings:
    print("✅ ВСЁ В ПОРЯДКЕ")
print("=" * 60)

sys.exit(1 if errors else 0)
