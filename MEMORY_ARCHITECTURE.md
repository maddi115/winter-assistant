# Memory Architecture

## Hierarchy (Top to Bottom)
```
conversations → checkpoint → final_foundation_context_sculpture
```

### 1. Conversations (Raw)
- Full chat logs saved to `conversations/*.jsonl`
- Every user/AI turn recorded with timestamps
- NOT compressed, NOT sculpted
- Storage: Complete conversation history

### 2. Checkpoint (Compressed Summary) 🍄
- Generated from conversations/memory
- Compressed to ~100 words
- 100% context retained through compression
- Purpose: Quick session context without reading full history
- Storage: `project:name:checkpoint:latest`

### 3. Final Foundation Context Sculpture (Core)
- Ultimate compressed knowledge base
- Facts (immutable) + State (mutable with weights) + Outcomes (insights)
- NO conversation text stored
- Only semantic knowledge graph
- Purpose: AI starts new session with zero token waste
- Storage: Redis with hierarchical keys

## Key Principle

**Context sculpting base is the LAST thing that happens to finalized docs**

Conversations → Checkpoints → Sculpture

The sculpture holds:
- ✅ Key facts, states, outcomes
- ✅ Compressed semantic knowledge
- ✅ 100% context retention
- ❌ NO raw conversation text
- ❌ NO redundant information

## Current Gap

**Conversations are NOT yet integrated**
- Typing in "New conversation" saves logs but does NOT sculpt
- Projects sculpt memory automatically
- Need: Pipeline to convert conversation logs → checkpoints → sculpture

## Why This Matters

Starting a new AI session:
- ❌ Bad: Dump entire conversation (wastes tokens, slow, expensive)
- ✅ Good: Load sculpture (instant context, zero waste, perfect memory)

The sculpture IS the context. Nothing else needed.
