# Future Ideas -- Do Not Implement Without Discussion

| Feature | Status | Blocker | Target Location |
|---------|--------|---------|-----------------|
| TTS/STT | research | No local engine | adapters/stt_*.py, features/chat/handlers.py |
| Vision | research | No vision model, PipelineData needs attachments | adapters/llm_vision_*.py, core/domain/pipeline.py |
| MCP | planned | IToolRegistry has no implementation | adapters/mcp_client.py |
| Native function calling | blocked | Needs MCP first | core/pipeline_steps.py, core/domain/messages.py (ToolCall dataclass), core/domain/pipeline.py (tool_calls field + with_tool_calls() accessor) |
| Agents | research | Needs function calling + long-term memory | features/agents/ |
| Long-term memory | research | No storage format | core/ports/memory.py |
| Code sandbox | research | Needs security sandbox | adapters/code_sandbox.py |
| Web RAG (crawling) | research | No crawler | adapters/crawler_simple.py |
| Index sync (git/cloud) | research | FAISS is binary/large | scripts/sync_*.py |
| Plugin system | research | Conflicts with "no magic discovery" | adapters/plugin_loader.py |
| A2A protocol | research | Spec is unstable | adapters/a2a_client.py |
| Obsidian/Notion RAG | research | Needs parsers + auth | adapters/source_*.py |
| Quantization routing | research | Needs complexity estimator | adapters/router_quantized.py |
| **GraphRAG** | research | Needs graph DB, entity extraction logic | adapters/graph_store_*.py, core/ports/graph.py (CORE CHANGE) |
| **Computer Use** | research | OS permissions, safety sandbox for actions | adapters/computer_use_*.py, core/ports/tools.py |
| **LLM-as-a-Judge** | planned | Needs secondary local model, eval datasets | features/eval/judge.py, adapters/llm_judge_*.py |
| **Continuous Local Learning** | research | Needs LoRA training loop, VRAM management | scripts/fine_tune.py, adapters/llm_lora_*.py |
| **PII Redaction & Encryption** | planned | Needs local NER model, crypto library | adapters/pii_redactor.py, core/io_utils.py (AES) |
| **OpenTelemetry Tracing** | planned | Needs opentelemetry-api/sdk dependencies | core/tracing.py, api/middleware.py |
| **Desktop UX / Wake-word** | research | Needs native bindings, audio stream access | adapters/wake_word_*.py, desktop/ (new top-level dir) |

Rule: If feature needs core/ change, discuss first. If solvable in adapters/, do it.
