# 🏗️ Architecture Documentation

## System Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        CLIENT LAYER                                  │
│  ┌──────────────────┐              ┌──────────────────┐            │
│  │   Web Browser    │              │   Demo Script    │            │
│  │  (Human Review   │              │   (Automated     │            │
│  │      UI)         │              │    Execution)    │            │
│  └────────┬─────────┘              └────────┬─────────┘            │
│           │                                  │                       │
└───────────┼──────────────────────────────────┼───────────────────────┘
            │                                  │
            │         HTTP REST API            │
            │                                  │
┌───────────▼──────────────────────────────────▼───────────────────────┐
│                       API LAYER (Flask)                              │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  Endpoints:                                                    │  │
│  │  - POST /api/workflow/execute                                 │  │
│  │  - GET  /api/human-review/pending                             │  │
│  │  - GET  /api/human-review/checkpoint/{id}                     │  │
│  │  - POST /api/human-review/decision                            │  │
│  │  - GET  /api/workflow/status/{id}                             │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                              │                                       │
└──────────────────────────────┼───────────────────────────────────────┘
                               │
┌──────────────────────────────▼───────────────────────────────────────┐
│                   ORCHESTRATION LAYER                                │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │         LangGraph Workflow Engine                             │  │
│  │  ┌────────────────────────────────────────────────────────┐  │  │
│  │  │  State Graph (12 Stages)                               │  │  │
│  │  │                                                          │  │  │
│  │  │  1. INTAKE ──────────────────────────────────┐        │  │  │
│  │  │  2. UNDERSTAND                                │        │  │  │
│  │  │  3. PREPARE                                   │        │  │  │
│  │  │  4. RETRIEVE                                  │        │  │  │
│  │  │  5. MATCH_TWO_WAY                             │        │  │  │
│  │  │  6. CHECKPOINT_HITL ◄─ Human Review ─┐       │        │  │  │
│  │  │  7. HITL_DECISION ◄─────────────────┘       │        │  │  │
│  │  │  8. RECONCILE                                 │        │  │  │
│  │  │  9. APPROVE                                   │        │  │  │
│  │  │  10. POSTING                                  │        │  │  │
│  │  │  11. NOTIFY                                   │        │  │  │
│  │  │  12. COMPLETE ──────────────────────────────►│        │  │  │
│  │  └────────────────────────────────────────────────────────┘  │  │
│  │                                                               │  │
│  │  State Management:                                            │  │
│  │  - WorkflowState (persisted across all stages)               │  │
│  │  - Checkpoint support (pause/resume)                         │  │
│  │  - LangGraph SQLite checkpointer                             │  │
│  └──────────────────────────────────────────────────────────────┘  │
└──────────────────────────────┬───────────────────────────────────────┘
                               │
              ┌────────────────┴────────────────┐
              │                                  │
┌─────────────▼──────────┐          ┌──────────▼─────────────┐
│   TOOL SELECTION       │          │   MCP CLIENT           │
│   LAYER (Bigtool)      │          │   ORCHESTRATION        │
│                        │          │                        │
│  ┌──────────────────┐ │          │  ┌──────────────────┐ │
│  │ Tool Pools:      │ │          │  │ COMMON Server    │ │
│  │                  │ │          │  │ - validate_schema│ │
│  │ - OCR            │ │          │  │ - normalize      │ │
│  │   • tesseract    │ │          │  │ - compute_flags  │ │
│  │   • google_vision│ │          │  │ - match_score    │ │
│  │   • aws_textract │ │          │  │ - accounting     │ │
│  │                  │ │          │  └──────────────────┘ │
│  │ - Enrichment     │ │          │                        │
│  │   • vendor_db    │ │          │  ┌──────────────────┐ │
│  │   • clearbit     │ │          │  │ ATLAS Server     │ │
│  │   • pdl          │ │          │  │ - ocr_extract    │ │
│  │                  │ │          │  │ - enrich_vendor  │ │
│  │ - ERP            │ │          │  │ - fetch_po       │ │
│  │   • mock_erp     │ │          │  │ - fetch_grn      │ │
│  │   • sap_sandbox  │ │          │  │ - fetch_history  │ │
│  │   • netsuite     │ │          │  │ - post_to_erp    │ │
│  │                  │ │          │  │ - schedule_pay   │ │
│  │ - Database       │ │          │  │ - notify         │ │
│  │   • sqlite       │ │          │  └──────────────────┘ │
│  │   • postgres     │ │          │                        │
│  │   • dynamodb     │ │          │  Ability Routing:     │
│  │                  │ │          │  - Deterministic      │
│  │ - Email          │ │          │  - Based on stage     │
│  │   • ses          │ │          │  - Mock impl for demo │
│  │   • sendgrid     │ │          └────────────────────────┘
│  │   • smartlead    │ │
│  └──────────────────┘ │
│                        │
│  Selection Strategy:   │
│  - Rule-based          │
│  - Priority-based      │
│  - Context-aware       │
└────────────────────────┘
              │
              │
┌─────────────▼──────────────────────────────────────────────┐
│              DATA PERSISTENCE LAYER                         │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────┐ │
│  │ Checkpoints      │  │ Review Queue     │  │ Workflow │ │
│  │ Table            │  │ Table            │  │ Execution│ │
│  │                  │  │                  │  │ Table    │ │
│  │ - checkpoint_id  │  │ - checkpoint_id  │  │ - wf_id  │ │
│  │ - workflow_id    │  │ - invoice_id     │  │ - status │ │
│  │ - state_blob     │  │ - vendor_name    │  │ - stage  │ │
│  │ - status         │  │ - amount         │  │ - data   │ │
│  │ - reason         │  │ - status         │  └──────────┘ │
│  │ - match_score    │  │ - priority       │               │
│  │ - decision       │  └──────────────────┘  ┌──────────┐ │
│  │ - reviewer_id    │                        │ Audit Log│ │
│  │ - resume_token   │                        │ Table    │ │
│  └──────────────────┘                        │          │ │
│                                               │ - action │ │
│         SQLite Database (demo.db)            │ - stage  │ │
│         LangGraph Checkpointer (checkpoints.db)│ - actor│ │
│                                               └──────────┘ │
└─────────────────────────────────────────────────────────────┘
```

## Component Interaction Flow

### 1. Normal Workflow Execution (No HITL)

```
User/Demo Script
    │
    │ POST /api/workflow/execute
    │ {invoice_payload}
    ▼
Flask API
    │
    │ invoke()
    ▼
LangGraph Workflow Engine
    │
    ├─► INTAKE
    │   ├─► Bigtool.select("db")        → sqlite
    │   └─► MCP.execute("validate")     → COMMON
    │
    ├─► UNDERSTAND
    │   ├─► Bigtool.select("ocr")       → tesseract
    │   └─► MCP.execute("ocr_extract")  → ATLAS
    │
    ├─► PREPARE
    │   ├─► Bigtool.select("enrichment")→ vendor_db
    │   ├─► MCP.execute("normalize")    → COMMON
    │   └─► MCP.execute("enrich")       → ATLAS
    │
    ├─► RETRIEVE
    │   ├─► Bigtool.select("erp")       → mock_erp
    │   ├─► MCP.execute("fetch_po")     → ATLAS
    │   ├─► MCP.execute("fetch_grn")    → ATLAS
    │   └─► MCP.execute("fetch_history")→ ATLAS
    │
    ├─► MATCH_TWO_WAY
    │   └─► MCP.execute("match_score")  → COMMON
    │       │
    │       └─► match_result = "MATCHED"
    │
    ├─► RECONCILE
    │   └─► MCP.execute("accounting")   → COMMON
    │
    ├─► APPROVE
    │   └─► MCP.execute("approval")     → ATLAS
    │
    ├─► POSTING
    │   ├─► Bigtool.select("erp")       → mock_erp
    │   ├─► MCP.execute("post_to_erp")  → ATLAS
    │   └─► MCP.execute("schedule_pay") → ATLAS
    │
    ├─► NOTIFY
    │   ├─► Bigtool.select("email")     → ses
    │   ├─► MCP.execute("notify_vendor")→ ATLAS
    │   └─► MCP.execute("notify_finance")→ ATLAS
    │
    └─► COMPLETE
        └─► Generate final_payload
        └─► Return to API
            │
            ▼
        Response to User
```

### 2. HITL Workflow (Match Failure)

```
User/Demo Script
    │
    │ POST /api/workflow/execute
    ▼
LangGraph Workflow
    │
    ├─► [Stages 1-5 execute normally]
    │
    ├─► MATCH_TWO_WAY
    │   └─► match_result = "FAILED"
    │       match_score = 0.75 (< 0.90 threshold)
    │
    ├─► CHECKPOINT_HITL
    │   ├─► Create checkpoint in DB
    │   │   - Store complete WorkflowState
    │   │   - Generate checkpoint_id
    │   │   - Generate review_url
    │   │
    │   ├─► Add to human_review_queue
    │   │   - Set priority based on score
    │   │   - Mark status: AWAITING_REVIEW
    │   │
    │   └─► PAUSE WORKFLOW ⏸️
    │       Return to API with checkpoint info
    │
    ▼
Response to User:
{
    "requires_human_review": true,
    "checkpoint_id": "chk_abc123",
    "review_url": "/human-review/review/chk_abc123",
    "status": "AWAITING_HUMAN"
}

─────────────────────────────────────────────────────

Human Reviewer
    │
    │ Open Web Browser
    │ Navigate to http://localhost:5000
    ▼
Human Review UI
    │
    │ GET /api/human-review/pending
    ▼
Display Pending Reviews
    │
    │ User clicks "Accept" or "Reject"
    │ Enters notes and reviewer_id
    │
    │ POST /api/human-review/decision
    │ {
    │   checkpoint_id: "chk_abc123",
    │   decision: "ACCEPT",
    │   reviewer_id: "john@company.com",
    │   notes: "Verified with vendor"
    │ }
    ▼
Flask API
    │
    │ Update checkpoint in DB
    │ - Set decision = "ACCEPT"
    │ - Set reviewer_id
    │ - Generate resume_token
    │ - Mark checkpoint as REVIEWED
    │
    │ workflow_engine.resume(checkpoint_id, decision)
    ▼
LangGraph Workflow RESUMES ▶️
    │
    ├─► HITL_DECISION
    │   └─► Read human_decision from state
    │       └─► Route to next_stage = "RECONCILE"
    │
    ├─► RECONCILE
    ├─► APPROVE
    ├─► POSTING
    ├─► NOTIFY
    └─► COMPLETE
        │
        ▼
    Final Response
```

## Data Models

### WorkflowState
```python
class WorkflowState:
    workflow_id: str
    workflow_name: str
    status: WorkflowStatus
    current_stage: str
    
    # Input
    invoice_payload: InvoicePayload
    
    # Stage outputs (persisted)
    raw_id: str
    parsed_invoice: dict
    vendor_profile: VendorProfile
    matched_pos: list
    match_score: float
    match_result: str
    checkpoint_id: str
    human_decision: str
    accounting_entries: list
    ...
    
    # Tracking
    bigtool_selections: dict
    mcp_server_calls: list
    stage_outputs: list
    errors: list
```

### Checkpoint
```python
class Checkpoint:
    checkpoint_id: str
    workflow_id: str
    state_blob: dict  # Full WorkflowState
    status: CheckpointStatus
    reason_for_hold: str
    
    # Context for review
    invoice_id: str
    vendor_name: str
    amount: float
    match_score: float
    
    # Review info
    reviewer_id: str
    decision: HumanDecision
    reviewer_notes: str
    resume_token: str
```

## Configuration Files

### workflow.json
Defines the complete 12-stage workflow structure with:
- Stage IDs and execution modes
- Instructions for each stage
- Tool requirements
- Output schemas
- MCP server mappings

### tools.yaml
Configures Bigtool pools with:
- Available providers for each capability
- Priority ordering
- Selection conditions
- Cost/latency metadata
- Fallback strategies

## Security & Best Practices

### Environment Variables
- All sensitive config in `.env`
- `.env.example` for documentation
- Never commit actual `.env` to git

### Database
- Checkpoint state encrypted in production
- Regular backups of workflow state
- Audit logging for compliance

### API Security
- JWT authentication (production)
- Rate limiting
- Input validation with Pydantic

### Error Handling
- Retry policies for transient failures
- Graceful degradation
- Complete error logging

## Scalability Considerations

### Horizontal Scaling
- Stateless API layer
- Database connection pooling
- LangGraph checkpointer supports distributed execution

### Performance
- Parallel tool execution where possible
- Caching for enrichment data
- Batch processing for high volume

### Monitoring
- Stage-level timing metrics
- Bigtool selection analytics
- MCP server health checks
- Checkpoint queue depth

---

This architecture provides a robust, scalable, and maintainable solution
for invoice processing with human oversight capabilities.
