# Future Ideas -- Do Not Implement Without Discussion

| Feature | Status | Blocker | Target Location |
|---------|--------|---------|-----------------|
| TTS/STT | research | No local engine | adapters/stt_*.py, features/chat/handlers.py |
| Vision | research | No vision model, PipelineData needs attachments | adapters/llm_vision_*.py, core/domain/pipeline.py |
| MCP | planned | IToolRegistry has no implementation | adapters/mcp_client.py |
| Native function calling | blocked | Needs MCP first | core/pipeline_steps.py |
| Agents | research | Needs function calling + long-term memory | features/agents/ |
| Long-term memory | research | No storage format | core/ports/memory.py |
| Code sandbox | research | Needs security sandbox | adapters/code_sandbox.py |
| Web RAG (crawling) | research | No crawler | adapters/crawler_simple.py |
| Index sync (git/cloud) | research | FAISS is binary/large | scripts/sync_*.py |
| Plugin system | research | Conflicts with "no magic discovery" | adapters/plugin_loader.py |
| Prometheus metrics | research | Needs prometheus_client | api/metrics.py |
| A2A protocol | research | Spec is unstable | adapters/a2a_client.py |
| Obsidian/Notion RAG | research | Needs parsers + auth | adapters/source_*.py |
| Quantization routing | research | Needs complexity estimator | adapters/router_quantized.py |

Rule: If feature needs core/ change, discuss first. If solvable in adapters/, do it.
