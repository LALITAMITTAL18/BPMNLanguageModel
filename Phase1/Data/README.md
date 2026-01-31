# BPMN Training Dataset Generator

## Overview
This package contains scripts and generated training data for building a specialized BPMN language model. The data is scraped from the **official OMG BPMN 2.0 specification** and enriched with comprehensive patterns, constraints, and examples. The dataset covers **322 BPMN elements** with **100 fully enriched** core elements.

## Generated Files

### Training Data (`bpmn_training_data/` folder)

1. **bpmn_elements_structured.json** (164 KB)
   - **322 BPMN elements** with structured definitions
   - Includes attributes, constraints, connection rules, variants
   - **100 elements with full enrichment** (patterns, purpose, constraints)
   - Best for: Understanding element structure, building validators, semantic analysis

2. **bpmn_natural_language.jsonl** (81 KB)
   - **322 natural language descriptions** of each element
   - Format: One JSON object per line
   - Includes purpose, patterns, constraints in readable format
   - Best for: Pre-training or fine-tuning with natural text

3. **bpmn_qa_pairs.jsonl** (110 KB, 1318 examples)
   - **1,318 question-answer pairs** about BPMN elements
   - Format: instruction, input, output
   - Question types: "What is X?", "When to use X?", "What can X connect to?", etc.
   - Best for: Instruction fine-tuning (like Alpaca, Llama-2-chat)

4. **bpmn_comparisons.jsonl** (147 KB, 620 examples)
   - **620 comparison pairs** between similar elements
   - Highlights similarities and differences within categories
   - Best for: Teaching distinctions between element types

## Dataset Statistics
- **Total Elements**: 322 (from official BPMN 2.0 XSD schemas)
- **Fully Enriched Elements**: 100 core BPMN elements
- **Total Training Examples**: 2,260+ (across all formats)
- **Data Source**: Official OMG BPMN specification via bpmn-io GitHub repository

## Category Breakdown
| Category | Count |
|----------|-------|
| Flow Object - Event | 43 |
| Flow Object - Activity | 40 |
| Flow Object - Gateway | 10 |
| Connecting Object | 19 |
| Swimlane | 14 |
| Artifact | 12 |
| Data Element | 27 |
| Other (Schema/Infrastructure) | 157 |

## Element Coverage

### Events (10+ types, 43 total elements)
- **Start Events**: None, Message, Timer, Signal, Conditional, Error, Escalation, Compensation
- **End Events**: None, Message, Error, Terminate, Escalation, Cancel, Compensation, Signal
- **Intermediate Events**: Catch (Message, Timer, Signal, Conditional) & Throw (Message, Signal, Escalation)
- **Boundary Events**: Message, Timer, Error, Signal, Escalation, Conditional, Cancel, Compensation

### Activities (9+ types, 40 total elements)
- **Tasks**: User, Service, Script, Manual, BusinessRule, Send, Receive, Generic
- **Call Activities**: Reusable subprocess invocation
- **Subprocesses**: Embedded, Event, Transaction, Ad-Hoc

### Gateways (5 types, 10 total elements)
- **ExclusiveGateway** (XOR): If-then-else decision logic
- **ParallelGateway** (AND): Concurrent execution/synchronization
- **InclusiveGateway** (OR): Conditional parallel paths
- **EventBasedGateway**: Wait for first event
- **ComplexGateway**: Custom merge conditions

### Connecting Objects (3)
- SequenceFlow, MessageFlow, Association

### Swimlanes (2)
- Pool, Lane

### Artifacts (4)
- DataObject, DataStore, TextAnnotation, Group

## Scripts Included

### 1. bpmn_dataset_generator.py (RECOMMENDED)
**Offline version** - Works without internet connection
- Contains comprehensive BPMN element definitions
- Generates all 4 training data formats
- Ready to use immediately

**Usage:**
```bash
python bpmn_dataset_generator.py
```

### 2. bpmn_scraper.py (ADVANCED)
Online version - Attempts to fetch BPMN XSD schema from OMG
- Requires internet connection
- Parses official BPMN 2.0 specification
- Use if you want to extend with additional elements

**Usage:**
```bash
pip install -r requirements.txt
python bpmn_scraper.py
```

## How to Use This Data for Training

### Option 1: Fine-Tuning with Q&A Pairs (Recommended for Phase 1)

Use `bpmn_qa_pairs.jsonl` for instruction fine-tuning:

```python
# Example with Hugging Face transformers
from datasets import load_dataset

dataset = load_dataset('json', data_files='bpmn_qa_pairs.jsonl')

# Format for instruction tuning
def format_instruction(example):
    return f"### Instruction:\n{example['instruction']}\n\n### Response:\n{example['output']}"

# Use with your fine-tuning framework (Axolotl, LoRA, etc.)
```

### Option 2: Pre-training with Natural Language

Use `bpmn_natural_language.jsonl` for continued pre-training:

```python
# Example for causal language modeling
from datasets import load_dataset

dataset = load_dataset('json', data_files='bpmn_natural_language.jsonl')

# Each 'text' field contains a comprehensive element description
# Use for next-token prediction training
```

### Option 3: RAG (Retrieval Augmented Generation)

Use `bpmn_elements_structured.json` as a knowledge base:

```python
import json
from sentence_transformers import SentenceTransformer

# Load element definitions
with open('bpmn_elements_structured.json') as f:
    elements = json.load(f)

# Create embeddings for semantic search
model = SentenceTransformer('all-MiniLM-L6-v2')

for elem in elements:
    elem['embedding'] = model.encode(elem['description'])

# Now you can retrieve relevant elements for any query
```

## Model Recommendations

### Small Language Models (Best for Phase 1)
- **Phi-3-mini** (3.8B parameters) - Microsoft, good at reasoning
- **Llama-3.2** (3B parameters) - Meta, strong instruction following
- **Gemma-2** (2B parameters) - Google, efficient
- **Qwen2.5** (1.5B parameters) - Alibaba, multilingual

### Training Approach
1. Start with instruction fine-tuning using `bpmn_qa_pairs.jsonl`
2. Use LoRA (Low-Rank Adaptation) for efficient fine-tuning
3. Train for 3-5 epochs with small learning rate (1e-5 to 5e-5)
4. Expected training time: 30 minutes to 2 hours on single GPU

## Extending the Dataset

### Adding More Elements
Edit `bpmn_dataset_generator.py` and add to `ELEMENTS` dictionary:

```python
'YourNewElement': {
    'category': 'Category Name',
    'subcategory': 'Subcategory',
    'description': 'What it is...',
    'purpose': 'When to use it...',
    'attributes': [...],
    'xml_example': '<yourElement id="..." />',
    'can_connect_from': [...],
    'can_connect_to': [...],
    'common_patterns': [...],
    'constraints': [...]
}
```

### Adding Real Process Examples
For Phase 2, you'll want to add actual process examples:

```python
# Create a new file: bpmn_process_examples.jsonl
{
    "process_description": "Purchase order approval process",
    "bpmn_xml": "<definitions>...</definitions>",
    "elements_used": ["StartEvent", "Task", "ExclusiveGateway", "EndEvent"],
    "complexity": "simple"
}
```

## Next Steps for Your Project

### Phase 1: BPMN Grammar Model ✓ (Current)
- [x] Generate BPMN element training data
- [ ] Fine-tune small LLM on Q&A pairs
- [ ] Test parsing and validation capabilities
- [ ] Benchmark accuracy on element recognition

### Phase 2: Process Pattern Understanding
- [ ] Collect 50-100 real BPMN processes
- [ ] Annotate with descriptions and common patterns
- [ ] Fine-tune on process generation tasks
- [ ] Test natural language → BPMN generation

### Phase 3: Domain Expertise
- [ ] Add your specific business domain processes
- [ ] Fine-tune for your industry patterns
- [ ] Build automation suggestion capabilities

## Training Tips

1. **Start Small**: Use 10-20% of data for initial experiments
2. **Validate Early**: Test on held-out elements to check generalization
3. **Monitor Overfitting**: BPMN has strict rules, so model might memorize
4. **Use Constraints**: Implement rule-based validators alongside LLM
5. **Human in Loop**: Always have humans review generated BPMN

## Resources

- BPMN 2.0 Specification: https://www.omg.org/spec/BPMN/2.0/
- BPMN.io Documentation: https://bpmn.io/
- Camunda BPMN Guide: https://docs.camunda.org/manual/latest/reference/bpmn20/

## License
This training data is derived from public BPMN specifications and is provided for educational and research purposes.

## Questions?
This dataset covers Phase 1 (BPMN Grammar). For Phase 2, you'll need to:
1. Collect real process examples
2. Create process description → BPMN XML pairs
3. Generate synthetic process variations

Would you like help with Phase 2 data collection strategies?
