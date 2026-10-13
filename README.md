# Parent Model System

A local prototype for putting an OpenAI-compatible routing gateway in front of existing AI applications. Each child app can keep its prompts, system instructions, tools, response schema, business rules, and existing model ID. The parent maps that existing model ID to a provider and target model, forwards the request, and sends operational traces to Langfuse.

## What changes in a child app

An app that currently sends requests directly to a provider must be pointed at the parent once. For OpenAI SDK clients, set `OPENAI_BASE_URL` to the parent URL and `OPENAI_API_KEY` to that app's generated gateway key. The child continues to send the same model ID and request body. The gateway changes the `model` field for the provider request and supplies the provider credential held by the parent.

The parent cannot intercept a direct provider call without this endpoint or network-routing change. It does not rewrite prompts or guarantee identical model behavior. A different model can change quality, latency, cost, tool support, and output shape; compare representative evaluations before changing a route.

## Run the parent

Use Python 3.10 or newer. From PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
if (!(Test-Path .env)) { Copy-Item .env.example .env }
# Preserve any existing .env. Add provider and Langfuse credentials there; keep it private.
python demo.py
```

Open <http://127.0.0.1:5001> (change `PARENT_PORT` if needed). The server binds to localhost. Provider credentials are read from the server environment, never returned by the management API, and child gateway keys are shown once and stored as hashes. Langfuse capture of prompt and response content is off by default; the local request activity table stores routing metadata and provider-reported usage only.

The default route provider is Azure OpenAI. Configure `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, and `AZURE_OPENAI_MODEL` in `.env`; the `model` forwarded to Azure must be the deployment name configured in that Azure resource. The local setup uses `gpt-5-mini` for text generation and `text-embedding-3-small` for RAG embeddings. The existing Qdrant corpus must be re-ingested when changing embedding dimensions. See Microsoft's [Azure OpenAI v1 API guidance](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/embeddings) for the deployment-name requirement.

The local Qdrant RAG demo uses Azure `gpt-5-mini` for query expansion and answer generation and `text-embedding-3-small` for embeddings. Its optional log-probability reranker is disabled because the available Azure deployment does not support the requested logprobs and the `gpt-4.1-nano` deployment is not present. Retrieval therefore ranks by vector similarity. The assistant system prompt, retrieval prompts, and grounding rules remain unchanged. To demonstrate the reranker too, configure an Azure deployment that exists and supports its logprob request; the gateway should not silently invent or remove those scores.

The parent route for the RAG app's requested `gpt-4.1-nano` reranker remains disabled because that Azure deployment is missing. This is expected while the demo config has reranking off. If reranking is turned back on, add a compatible model deployment and route before using the RAG chat.

The current Qdrant library contains 15 documents. Its company-history document is titled `01 Company Overview And History`; the ingested document list does not contain the ID `DOC-CO-0001`. Use the title or an ID returned by `/knowledge/documents` when testing a document-specific question.

The comparison workspace is under **Evaluations**. It compares provider deployment names directly and now rejects identical baseline/candidate IDs, since that is a repeatability check rather than a model comparison. A real comparison needs two distinct Azure deployments. The tool-definition field supports the local `calculate_budget` tool case. Exact-match and JSON checks are a starting point, not proof of semantic quality; review representative outputs before promotion.

## Gateway behavior

- App-scoped bearer keys identify the child application.
- Exact model aliases map to a configured provider and target model. Multiple aliases can be configured for one app.
- The request payload is forwarded without changing messages, instructions, tools, or response-format rules; the model field is mapped. A route may optionally set a maximum output-token ceiling for Responses or Chat Completions requests.
- The OpenAI-compatible proxy allowlist currently covers Chat Completions, Responses, Embeddings, Moderations, Models, Files, Vector Stores, Assistants, Threads, Batches, and Uploads. Each target provider still needs to support the endpoint and features the child app uses.
- Streaming responses and multipart file uploads are relayed. Latency and provider-reported token usage are recorded. Cost is shown only when the provider returns cost data; Langfuse may also calculate cost when its model pricing configuration supports the routed model.
- There is no automatic quality-based fallback. Quality degradation cannot be ruled out by a transparent proxy; use the evaluation dataset and controlled rollout.

Supported provider adapters are OpenAI, OpenRouter, Azure OpenAI's v1-compatible endpoint, and a configurable OpenAI-compatible endpoint. Langfuse handles traces and evaluation; the parent gateway handles routing. This prototype does not include LiteLLM.

## Cloned representative apps

The `github_apps/` directory contains separate shallow clones; the parent does not edit their prompts or rules.

| Sample | Repository | Existing model ID in the sample |
| --- | --- | --- |
| RAG / knowledge retrieval | [openai/openai-knowledge-retrieval](https://github.com/openai/openai-knowledge-retrieval) | `gpt-5`; the included ChatKit backend also uses `gpt-5-mini` |
| Tool-using support agent | [openai/openai-support-agent-demo](https://github.com/openai/openai-support-agent-demo) | `gpt-5.2` |
| Streaming structured output | [openai/openai-structured-outputs-samples](https://github.com/openai/openai-structured-outputs-samples) (`resume-extraction/`) | `gpt-4o-mini` |

For the two Next.js samples, run `npm ci` and `npm run dev` from their respective folders. Set `OPENAI_BASE_URL=http://127.0.0.1:5001/v1` and an app-specific `OPENAI_API_KEY` in the sample's environment. For the Python RAG sample, its repository requires Python 3.10+ and has its own dependencies, data setup, and backend/frontend steps; see its README. Add each model ID the app actually calls as a route in the parent before trying the app. Provider-specific features (for example, File Search or strict JSON schema streaming) need a target provider/model that implements them.

The support-agent sample has 10 fictional orders for customer `cus_28X44`. Find their exact IDs in the representative view under **Sample order IDs**, in [`github_apps/agent/data/demo_orders.json`](github_apps/agent/data/demo_orders.json), or as JSON at <http://127.0.0.1:3002/api/orders>. The first request seeds them into SQLite at `github_apps/agent/data/support_demo.sqlite` using [`github_apps/agent/data/schema.sql`](github_apps/agent/data/schema.sql); `get_order` and `get_order_history` read from that database. Each JSON object has six fields: `id`, `customer_id`, `date`, `status`, `product`, and `total`. The support sample uses Node.js 22.5+ for built-in SQLite.

For this local RAG demo, use the Qdrant corpus and the Azure-compatible routes already registered for `rag-knowledge-retrieval`. In `github_apps/rag/.env`, set `OPENAI_BASE_URL=http://127.0.0.1:5001/v1`, `OPENAI_API_KEY` to the one-time key generated for **Knowledge Retrieval RAG** in the parent dashboard, and `RAG_CONFIG=configs/default.qdrant.yaml`. Start the backend from `github_apps/rag/app/backend` with `..\..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8003`. Start the Vite frontend with `BACKEND_URL=http://127.0.0.1:8003` on port 5173. Keep the app key in the ignored `.env` file; do not commit or paste it into source code.

The cloned apps are for compatibility demonstrations. Their upstream licenses and setup instructions apply.

### Current local run

These services are running on localhost in this workspace, except the RAG backend, which needs its app-scoped key restored and a restart using the commands above:

| Service | URL |
| --- | --- |
| Parent dashboard and gateway | <http://127.0.0.1:5001> |
| Langfuse observability | <http://127.0.0.1:3000> |
| Support-agent sample | <http://127.0.0.1:3002> |
| Resume-extraction sample | <http://127.0.0.1:3003> |
| RAG sample frontend | <http://127.0.0.1:5173> |
| RAG sample backend health | <http://127.0.0.1:8003/knowledge/health> (currently stopped) |

The RAG sample includes both OpenAI-hosted File Search and local Qdrant configurations. Hosted File Search requires a populated vector store and a provider that implements that feature. The local Qdrant configuration is available for OpenAI-compatible providers that support embeddings and tool calls. Add routes for every model ID the sample uses, set an app-scoped key, and ingest the bundled documents before chatting. The support-agent sample's dynamic route handlers use the Next.js 15 promise-style route parameters.

## Tests

The gateway tests use a mocked upstream, so they do not call or bill a model provider:

```powershell
py -3.11 -m unittest discover -v
node --check app.js
```

## Prototype limits before deployment

The control dashboard is intended for local development and is not an authenticated multi-tenant admin console. Do not expose it to a network as-is. A production product needs administrator authentication and authorization, tenant isolation, secret management, TLS, durable database migrations, rate limits/quotas, abuse controls, provider-specific compatibility checks, and deployment monitoring. The local SQLite activity view is not a replacement for Langfuse's trace store.
