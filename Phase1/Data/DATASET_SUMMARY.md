# BPMN Training Dataset Generation - Summary

## Overview
Successfully scraped and generated comprehensive BPMN 2.0 training datasets from the official OMG specification and GitHub repositories.

## Data Sources
- **Primary**: Official BPMN 2.0 XSD schemas from bpmn-io GitHub repository
  - Main BPMN Schema: https://raw.githubusercontent.com/bpmn-io/bpmn-moddle/master/resources/bpmn/xsd/BPMN20.xsd
  - Semantic Schema: https://raw.githubusercontent.com/bpmn-io/bpmn-moddle/master/resources/bpmn/xsd/Semantic.xsd
  
- **Enrichment**: Hand-crafted enrichment database with 40+ core BPMN elements including:
  - All event types (Start, End, Intermediate, Boundary)
  - All task types (User, Service, Script, Manual, Business Rule, Send, Receive)
  - All gateway types (Exclusive, Parallel, Inclusive, Event-Based, Complex)
  - Subprocesses, Pools, Lanes, Data Objects, and more

## Generated Datasets

### 1. bpmn_elements_structured.json (164 KB)
- **322 total BPMN elements** extracted from official schemas
- **100 elements with full enrichment** (purpose, patterns, constraints, variants)
- Each element includes:
  - Element type and category
  - Attributes with types and requirements
  - XML example
  - Purpose and description
  - Common usage patterns
  - Connection rules (can_connect_from, can_connect_to)
  - Constraints and best practices
  - Variants (for events, tasks, gateways)

### 2. bpmn_natural_language.jsonl (81 KB)
- **322 natural language descriptions**
- Format: Human-readable paragraph describing each element
- Includes: category, purpose, attributes, connections, patterns, constraints
- Optimized for language model training

### 3. bpmn_qa_pairs.jsonl (110 KB)
- **1,318 question-answer pairs**
- Question types:
  - "What is X in BPMN?"
  - "What category does X belong to?"
  - "When should I use X?"
  - "What are the attributes of X?"
  - "What can X connect to?"
  - "What are common patterns for X?"
  - "What are the constraints for X?"
  - "Show me an XML example of X"
- Instruction-tuning format compatible with modern LLMs

### 4. bpmn_comparisons.jsonl (147 KB)
- **620 comparison pairs**
- Compares similar elements within same category
- Highlights similarities and differences
- Helps model learn distinctions between related concepts

## Category Breakdown
| Category | Count |
|----------|-------|
| Other (Schema/Infrastructure) | 157 |
| Flow Object - Event | 43 |
| Flow Object - Activity | 40 |
| Data Element | 27 |
| Connecting Object | 19 |
| Swimlane | 14 |
| Artifact | 12 |
| Flow Object - Gateway | 10 |

## Key Enriched Elements
The following core BPMN elements have full enrichment with patterns, constraints, and examples:

### Events (10 types)
- StartEvent, EndEvent
- IntermediateCatchEvent, IntermediateThrowEvent
- BoundaryEvent
- EventSubProcess

### Tasks & Activities (9 types)
- Task, UserTask, ServiceTask
- ScriptTask, ManualTask, BusinessRuleTask
- SendTask, ReceiveTask, CallActivity
- SubProcess, Transaction

### Gateways (5 types)
- ExclusiveGateway, ParallelGateway
- InclusiveGateway, EventBasedGateway
- ComplexGateway

### Connecting Objects (4 types)
- SequenceFlow, MessageFlow
- Association, DataAssociation

### Swimlanes (3 types)
- Pool, Lane, Participant

### Artifacts (4 types)
- DataObject, DataStore
- TextAnnotation, Group

## Usage
These datasets can be used for:
1. **Fine-tuning LLMs** on BPMN knowledge
2. **Training chatbots** to answer BPMN questions
3. **Building BPMN assistants** for process modeling
4. **Generating BPMN documentation** automatically
5. **Validating BPMN models** against specifications

## Sample Data Quality

### Enriched Element Example (StartEvent):
```json
{
  "element_type": "startEvent",
  "category": "Flow Object - Event",
  "subcategory": "Start Event",
  "description": "Indicates where a process begins. Triggers the start of a process instance.",
  "purpose": "Indicates where a process begins. Triggers the start of a process instance.",
  "constraints": [
    "Start Events must have no incoming Sequence Flows",
    "Start Events must have at least one outgoing Sequence Flow",
    "Only one None Start Event per Process (unless in Event Sub-Process)"
  ],
  "can_connect_to": ["SequenceFlow"],
  "common_patterns": [
    "None Start Event - process starts immediately",
    "Message Start Event - triggered by incoming message",
    "Timer Start Event - triggered at specific time or interval",
    "Signal Start Event - triggered by signal broadcast",
    "Conditional Start Event - triggered when condition is met"
  ],
  "variants": ["None", "Message", "Timer", "Signal", "Conditional", "Error", "Escalation", "Compensation", "Multiple", "Parallel Multiple"]
}
```

### Q&A Example:
**Q:** When should I use a globalUserTask in my BPMN process?  
**A:** A task performed by a human user with the help of a software application.

**Q:** What BPMN elements can a globalUserTask connect to?  
**A:** A globalUserTask can connect to: SequenceFlow, MessageFlow

## Technical Details
- **Scraper**: Python-based using requests, BeautifulSoup, xml.etree
- **Schema Parsing**: XSD namespace-aware parsing
- **Enrichment**: Pattern matching with case-insensitive lookup
- **Output Formats**: JSON (structured), JSONL (streaming)
- **Encoding**: UTF-8 with ensure_ascii=False for international characters

## Files Generated
```
bpmn_training_data/
├── bpmn_elements_structured.json  (164 KB, 322 elements)
├── bpmn_natural_language.jsonl    (81 KB, 322 entries)
├── bpmn_qa_pairs.jsonl            (110 KB, 1318 Q&A pairs)
└── bpmn_comparisons.jsonl         (147 KB, 620 comparisons)
```

## Next Steps
1. ✅ **COMPLETED**: Scrape BPMN elements from official specification
2. ✅ **COMPLETED**: Enrich with detailed descriptions and patterns
3. ✅ **COMPLETED**: Generate training datasets in multiple formats
4. **TODO**: Use datasets to fine-tune language model in Phase 1
5. **TODO**: Build BPMN-aware chatbot/assistant

---
Generated on: January 30, 2026
Source: Official OMG BPMN 2.0 Specification (via bpmn-io GitHub)
