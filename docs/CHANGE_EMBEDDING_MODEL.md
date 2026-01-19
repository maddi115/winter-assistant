# Change Embedding Model

**Files to modify:**
1. `core/config.py` → `embedding_model`
2. `storage/lancedb_storage.py` → `"vector": [0.0] * DIMS`
3. `core/ai_engine.py` → system prompt
4. `memory/system.txt` → `AI_EMBEDDING`

**Then:** `rm -rf storage/conversations.lance/`
