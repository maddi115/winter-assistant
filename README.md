# Winter Assistant ❄️

GPU-accelerated AI assistant with auto-curated project memories. NO conversation dumps - only compressed semantic sculptures.

## 🎯 Core Concept

**conversations → checkpoint → sculpture**

Traditional AI: Dumps entire chat history every session (wastes tokens)
Winter: Loads compressed knowledge graph (perfect context, zero waste)

## 🗿 Memory Hierarchy

1. **Sacred Foundation** - Immutable core principles (requires confirmation)
2. **Checkpoints** - Compressed summaries (~100 words, 100% context)
3. **Facts** - Immutable knowledge
4. **State** - Mutable context with confidence weights
5. **Outcomes** - Learned insights

## 🚀 Quick Start
```bash
cd ~/winter-assistant
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Start Redis:
```bash
sudo service redis-server start
```

Run:
```bash
ai
```

## 📋 Features

- **Project Isolation** - Each project = separate memory sculpture
- **WASD Navigation** - All menus use keyboard navigation
- **Multi-File Browse** - Select & analyze multiple files
- **Auto-Sculptor** - LLM decides what to remember
- **Sacred Foundation** - Lock in permanent principles
- **Export** - Save sculptures to JSON

## 🎮 Commands

- `ai` - Start assistant
- `memory` - View sculpture
- `checkpoint` - Create summary
- `projects` - List all projects

## 🔧 Requirements

- Python 3.12+
- Redis server
- Ollama with deepseek-r1:8b
- WSL2 (for Windows folder integration)

## 📊 Architecture
```
Conversations (raw logs)
    ↓
Checkpoints (compressed summaries)
    ↓
Sculpture (semantic knowledge graph)
```

**Current Status:** Projects sculpt automatically. Conversations log only (integration pending).

## 🗂️ File Structure

- `assistant.py` - Main entry point
- `winter_core.py` - Memory & chat logic
- `winter_ui.py` - WASD menus
- `file_browser.py` - Single file selector
- `multi_file_selector.py` - Multi-file browser
- `conversation_manager.py` - Conversation logging
- `view_project_memory.py` - Memory viewer
- `create_checkpoint.py` - Checkpoint generator
- `add_foundation.py` - Sacred foundation adder

## 📝 License

MIT
