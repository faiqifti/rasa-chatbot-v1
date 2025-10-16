# Rasa Chatbot Local

Rasa 3.6 chatbot that answers questions using retrieval-augmented generation (RAG) with local GGUF embeddings. The project includes optional integrations with Qdrant vector search, Redis caching, RabbitMQ messaging, Kafka, and several static web chat front-ends.

## Features
- Custom action server with reusable embedder, retriever, and ranker helpers.
- Local embeddings powered by `llama-cpp-python` and configurable GGUF models.
- Qdrant vector database search with optional Redis result caching.
- RabbitMQ publishing for chatbot events; Kafka scaffolding included.
- Multiple action variants that disable specific dependencies for quick prototyping.
- Static web chat demos (Socket.IO) for serving the assistant via a browser.
- Smoke tests and focused unit tests for embedding, retrieval, caching, and messaging utilities.

## Project Structure
```
actions/                # Custom action modules and helpers
├── actions.py          # Main RAG-enabled action (Qdrant + Redis + RabbitMQ)
├── actions_*.py        # Alternative actions without specific services
├── embedder.py         # GGUF embedder wrapper around llama_cpp
├── retriever.py        # Mini knowledge-base retriever helper
├── ranker.py           # Threshold-based top-1 selector
├── redis_cache.py      # Redis caching utilities
├── rabbitmq_producer.py
├── qdrant_ingest*.py   # Utilities for populating Qdrant
└── test_*.py           # Unit tests for action helpers
config.yml              # Rasa NLU pipeline and policies
credentials.yml         # Messaging channel credentials (REST, Socket.IO, etc.)
domain.yml              # Intents, responses, entities, slots
data/                   # Training data (NLU, stories, rules)
models/                 # GGUF embedding models & exported Rasa models
tests/                  # Additional smoke tests / utilities
web/                    # Static web chat demos
requirements.txt        # Python dependencies
.env                    # Environment configuration (not committed)
```

## Prerequisites
- Python 3.10
- GGUF embedding model(s) placed under `models/`
- Optional services:
  - [Qdrant](https://qdrant.tech/) (vector search)
  - [Redis](https://redis.io/) (cache)
  - [RabbitMQ](https://www.rabbitmq.com/) (event streaming)
  - Kafka (if you enable Kafka integration)

## Setup
```bash
git clone https://github.com/<your-user>/rasa-chatbot-local.git
cd rasa-chatbot-local

python3.10 -m venv .venv
source .venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt
```

Copy `.env` (or create it manually) and adjust values as needed. Important environment variables include:

| Variable | Description | Default |
| --- | --- | --- |
| `EMBED_MODEL_PATH` | Path to GGUF embedding model | auto-detected from `models/` |
| `EMBED_THREADS` | CPU threads for llama_cpp | `4` |
| `RAG_THRESHOLD` | Minimum similarity score | `0.35` |
| `RAG_TOPK` | Number of retrieved candidates | `5` |
| `QDRANT_URL` / `QDRANT_API_KEY` | Qdrant connection details | `http://localhost:6333` / None |
| `QDRANT_COLLECTION` | Qdrant collection name | `kb_documents` |
| `REDIS_HOST` / `REDIS_PORT` / `REDIS_URL` | Redis configuration | `localhost` / `6379` |
| `RABBITMQ_URL` / `RABBITMQ_QUEUE` | RabbitMQ connection | `amqp://guest:guest@localhost:5672/` / `rasa_events` |
| `KAFKA_BOOTSTRAP` / `KAFKA_TOPIC` | Kafka configuration | optional |

Place embedding models (e.g., `nomic-embed-text-v1.5.Q2_K.gguf`, `bge-m3-q4_k_m.gguf`) in the `models/` directory or set `EMBED_MODEL_PATH` to your preferred location.

## Running the Bot
1. (Optional) Start external services:
   ```bash
   docker run -p 6333:6333 qdrant/qdrant
   docker run -p 6379:6379 redis:alpine
   docker run -p 5672:5672 -p 15672:15672 rabbitmq:3-management
   ```

2. Start the action server:
   ```bash
   rasa run actions --debug
   ```

3. Start the Rasa server with API + Socket.IO support:
   ```bash
   rasa run \
     --enable-api \
     --cors "*" \
     --credentials credentials.yml \
     --endpoints endpoints.yml \
     --debug
   ```

4. Test via REST:
   ```bash
   curl -X POST http://localhost:5005/webhooks/rest/webhook \
        -H "Content-Type: application/json" \
        -d '{"sender":"test","message":"limit transfer"}'
   ```

5. Serve static web chat demo (optional):
   ```bash
   python3 -m http.server 8080 -d web
   ```
   Visit `http://localhost:8080/chatv1.html`. Ensure the Rasa server was launched with `--enable-api` and matching CORS settings.

## Testing
- Unit tests for embedder, retriever, Redis cache, and RabbitMQ producer:
  ```bash
  python -m pytest actions/test_embedder.py actions/test_retriever.py actions/test_redis_cache.py actions/test_rabbitmq_producer.py
  ```
- Smoke tests:
  ```bash
  python -m smoke_actions
  python -m tests.check_kb_index
  ```

## Utilities & Variants
- `actions/actions_without_qdrant.py`, `actions/actions_without_redis.py`, `actions/actions_without_kafka.py`, `actions/actions_singleEmbedding.py` show how to run without specific infrastructure components.
- `actions/qdrant_ingest.py` and `actions/qdrant_ingest_singleEmbedding.py` help populate Qdrant with knowledge base entries.
- `web/` contains multiple chat widget variants (`chatv1.html`, `chatv2.html`, `chat_notpopup.html`, `index.html`, etc.) that connect through Socket.IO.

## Troubleshooting
- **Embedding model fails to load**: verify the GGUF file is compatible with the installed `llama_cpp_python`. Some quantizations (e.g., Q8) require building with `GGML_USE_K_QUANTS=1`. Try Q4 variants if necessary.
- **RabbitMQ queue stays empty**: check action server logs for `[LOG] Event successfully published to RabbitMQ.` and ensure `RABBITMQ_URL` reaches the broker (use container hostname if running via Docker).
- **Web chat not receiving responses**: launch Rasa with `--enable-api --cors "*"` and confirm Socket.IO credentials are enabled in `credentials.yml`.
- **Redis/Qdrant failures**: ensure services are running and environment variables point to the correct host/port/API key.

## License
Add licensing information here.

## Acknowledgements
- [Rasa Open Source](https://rasa.com/)
- [llama-cpp-python](https://github.com/abetlen/llama-cpp-python)
- [Qdrant](https://qdrant.tech/)
- [Redis](https://redis.io/)
- [RabbitMQ](https://www.rabbitmq.com/)
