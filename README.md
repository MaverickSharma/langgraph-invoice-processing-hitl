# 🚀 LangGraph Invoice Processing Agent with HITL

> A sophisticated invoice processing workflow using LangGraph with Human-In-The-Loop checkpoints, MCP client orchestration, and dynamic tool selection via Bigtool.

## 📋 Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Features](#features)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Workflow Stages](#workflow-stages)
- [API Documentation](#api-documentation)
- [Configuration](#configuration)
- [Demo Video](#demo-video)

## 🎯 Overview

**Langie** is an autonomous invoice processing agent that:
- ✅ Models invoice processing as a 12-stage LangGraph workflow
- ✅ Persists and passes state variables across stages
- ✅ Creates checkpoints for Human-In-The-Loop (HITL) reviews
- ✅ Resumes execution after human decisions
- ✅ Integrates with MCP Clients (ATLAS & COMMON servers)
- ✅ Dynamically selects tools using Bigtool
- ✅ Supports both deterministic and non-deterministic stages

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                   LangGraph Workflow Engine                  │
│  ┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────┐    │
│  │ INTAKE  │──▶│UNDERSTAND──▶│ PREPARE │──▶│RETRIEVE │    │
│  └─────────┘   └─────────┘   └─────────┘   └─────────┘    │
│                                                               │
│  ┌─────────┐   ┌──────────┐  ┌──────────┐  ┌─────────┐    │
│  │  MATCH  │──▶│CHECKPOINT│──▶│   HITL   │──▶│RECONCILE    │
│  │ 2-WAY   │   │   HITL   │  │ DECISION │  └─────────┘    │
│  └─────────┘   └──────────┘  └──────────┘                  │
│                      │              │                        │
│                      ▼              ▼                        │
│                 [Checkpoint]   [Human Review]               │
│                   Database         Queue                     │
│                                                               │
│  ┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────┐    │
│  │ APPROVE │──▶│ POSTING │──▶│ NOTIFY  │──▶│COMPLETE │    │
│  └─────────┘   └─────────┘   └─────────┘   └─────────┘    │
└─────────────────────────────────────────────────────────────┘
         │                    │                    │
         ▼                    ▼                    ▼
   ┌──────────┐        ┌──────────┐        ┌──────────┐
   │  Bigtool │        │   MCP    │        │ State DB │
   │  Picker  │        │ Clients  │        │          │
   └──────────┘        └──────────┘        └──────────┘
        │                    │
        ▼                    ▼
   Tool Pools         COMMON / ATLAS
   - OCR              Ability Servers
   - Enrichment
   - ERP
   - DB
   - Email
```

## ✨ Features

### 🧩 12-Stage Invoice Processing Pipeline

1. **INTAKE** - Accept and validate invoice payload
2. **UNDERSTAND** - OCR extraction and line item parsing
3. **PREPARE** - Vendor normalization and enrichment
4. **RETRIEVE** - Fetch POs, GRNs, and historical data
5. **MATCH_TWO_WAY** - Perform 2-way matching (Invoice vs PO)
6. **CHECKPOINT_HITL** - Create checkpoint for human review
7. **HITL_DECISION** - Process human accept/reject decision
8. **RECONCILE** - Build accounting entries
9. **APPROVE** - Apply approval policies
10. **POSTING** - Post to ERP and schedule payment
11. **NOTIFY** - Send notifications to stakeholders
12. **COMPLETE** - Finalize and output results

### 🎯 Key Capabilities

- **State Management**: Persistent state across all stages
- **Checkpointing**: Pause workflow at critical decision points
- **HITL Integration**: Human review queue with web UI
- **Resume Capability**: Continue from checkpoint after human action
- **Bigtool Selection**: Dynamic tool selection from pools
- **MCP Orchestration**: Route abilities to COMMON/ATLAS servers
- **Error Handling**: Retry policies and graceful degradation

## 📦 Installation

### Prerequisites

- Python 3.10+
- SQLite (included with Python)
- Tesseract OCR (optional, for OCR capabilities)

### Setup

```bash
# Clone the repository
cd /Users/aryansharma/Desktop/data\ science\ project

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install Tesseract (optional, for OCR)
# macOS
brew install tesseract

# Ubuntu
# sudo apt-get install tesseract-ocr

# Copy environment configuration
cp .env.example .env

# Edit .env and add your OpenAI API key
nano .env  # or use any text editor
```

## 🚀 Quick Start

### 1. Initialize the Database

```bash
python init_db.py
```

### 2. Start the API Server

```bash
python app.py
```

The API will be available at `http://localhost:5000`

### 3. Run a Demo Workflow

```bash
python demo.py
```

### 4. Access the Human Review UI

Open your browser and navigate to:
```
http://localhost:5000/human-review
```

## 🔄 Workflow Stages

### Stage Details

| Stage | Type | MCP Server | Bigtool Capability | Description |
|-------|------|------------|-------------------|-------------|
| INTAKE | Deterministic | COMMON | storage | Validate and persist invoice |
| UNDERSTAND | Deterministic | ATLAS | ocr | Extract text via OCR |
| PREPARE | Deterministic | COMMON/ATLAS | enrichment | Normalize and enrich vendor |
| RETRIEVE | Deterministic | ATLAS | erp_connector | Fetch PO/GRN data |
| MATCH_TWO_WAY | Deterministic | COMMON | - | Compute match score |
| CHECKPOINT_HITL | Deterministic | COMMON | db | Create checkpoint if match fails |
| HITL_DECISION | Non-Deterministic | ATLAS | - | Process human decision |
| RECONCILE | Deterministic | COMMON | - | Build accounting entries |
| APPROVE | Deterministic | ATLAS | - | Apply approval policies |
| POSTING | Deterministic | ATLAS | erp_connector | Post to ERP |
| NOTIFY | Deterministic | ATLAS | email | Send notifications |
| COMPLETE | Deterministic | COMMON | db | Finalize workflow |

## 📡 API Documentation

### Workflow Execution

**POST** `/api/workflow/execute`

```json
{
  "invoice_payload": {
    "invoice_id": "INV-2024-001",
    "vendor_name": "Acme Corp",
    "amount": 15000,
    "currency": "USD",
    "line_items": [...]
  }
}
```

### Human Review

**GET** `/api/human-review/pending`

Returns list of invoices pending review.

**POST** `/api/human-review/decision`

```json
{
  "checkpoint_id": "chk_123",
  "decision": "ACCEPT",
  "notes": "Verified with vendor",
  "reviewer_id": "user@example.com"
}
```

### Workflow Status

**GET** `/api/workflow/status/<workflow_id>`

Returns current status and stage information.

## ⚙️ Configuration

### workflow.json

Defines the complete workflow structure with stages, tools, and routing.

### tools.yaml

Configures tool pools for Bigtool selection.

### .env

Environment variables for API keys, database, and MCP servers.

## 🎥 Demo Video

**[Link to Demo Video]** - Coming soon

### Video Contents:
1. **Self Introduction** (1 min)
2. **Solution Demo** (4 min)
   - Frontend UI walkthrough
   - Workflow execution logs
   - HITL checkpoint and resume
   - Bigtool tool selection
   - MCP client orchestration

## 🧪 Testing

```bash
# Run tests
pytest tests/

# Run specific test
pytest tests/test_workflow.py -v

# Run with coverage
pytest --cov=src tests/
```

## 📚 Project Structure

```
data science project/
├── app.py                      # Flask API server
├── demo.py                     # Demo script
├── init_db.py                  # Database initialization
├── requirements.txt            # Python dependencies
├── .env.example               # Environment template
├── README.md                  # This file
│
├── config/
│   ├── workflow.json          # Workflow definition
│   └── tools.yaml             # Tool pool configuration
│
├── src/
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── workflow_engine.py # Main LangGraph engine
│   │   └── nodes/             # Stage node implementations
│   │       ├── __init__.py
│   │       ├── intake_node.py
│   │       ├── understand_node.py
│   │       ├── prepare_node.py
│   │       ├── retrieve_node.py
│   │       ├── match_node.py
│   │       ├── checkpoint_node.py
│   │       ├── hitl_node.py
│   │       ├── reconcile_node.py
│   │       ├── approve_node.py
│   │       ├── posting_node.py
│   │       ├── notify_node.py
│   │       └── complete_node.py
│   │
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── bigtool.py         # Dynamic tool selector
│   │   └── tool_implementations/
│   │       ├── ocr_tools.py
│   │       ├── enrichment_tools.py
│   │       ├── erp_tools.py
│   │       └── notification_tools.py
│   │
│   ├── mcp/
│   │   ├── __init__.py
│   │   ├── mcp_client.py      # MCP client orchestrator
│   │   ├── common_server.py   # COMMON server abilities
│   │   └── atlas_server.py    # ATLAS server abilities
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── state.py           # Workflow state models
│   │   ├── checkpoint.py      # Checkpoint models
│   │   └── invoice.py         # Invoice data models
│   │
│   └── database/
│       ├── __init__.py
│       ├── db.py              # Database connection
│       └── repositories/
│           ├── checkpoint_repo.py
│           └── review_queue_repo.py
│
├── static/
│   ├── index.html             # Human review UI
│   └── styles.css
│
├── sample_data/
│   ├── invoice_sample_1.json
│   └── invoice_sample_2.json
│
└── tests/
    ├── __init__.py
    ├── test_workflow.py
    ├── test_bigtool.py
    └── test_mcp_client.py
```

## 🤝 Contributing

This is a demo project for the LangGraph Invoice Processing Task submission.

## 📧 Contact

**Submission to**: santosh.thota@analytos.ai

**Subject**: LangGraph Invoice Processing Task with HITL – Aryan Sharma

## 📄 License

MIT License - See LICENSE file for details

---

**Built with ❤️ using LangGraph, MCP, and Bigtool**
