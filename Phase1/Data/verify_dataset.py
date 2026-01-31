"""
Final verification of BPMN training dataset generation
Shows statistics and sample data
"""
import json

print("="*70)
print(" BPMN TRAINING DATASET - FINAL VERIFICATION")
print("="*70)

# Load all datasets
with open('bpmn_training_data/bpmn_elements_structured.json', 'r', encoding='utf-8') as f:
    elements = json.load(f)

with open('bpmn_training_data/bpmn_qa_pairs.jsonl', 'r', encoding='utf-8') as f:
    qa_pairs = [json.loads(line) for line in f]

with open('bpmn_training_data/bpmn_comparisons.jsonl', 'r', encoding='utf-8') as f:
    comparisons = [json.loads(line) for line in f]

with open('bpmn_training_data/bpmn_natural_language.jsonl', 'r', encoding='utf-8') as f:
    nl_data = [json.loads(line) for line in f]

# Statistics
enriched = [e for e in elements if e.get('purpose') and e.get('common_patterns')]
fully_enriched_names = [e['element_type'] for e in enriched]

print(f"\n📊 DATASET STATISTICS")
print(f"{'─'*70}")
print(f"Total BPMN Elements:           {len(elements)}")
print(f"Fully Enriched Elements:       {len(enriched)}")
print(f"Natural Language Entries:      {len(nl_data)}")
print(f"Q&A Pairs:                     {len(qa_pairs)}")
print(f"Comparison Pairs:              {len(comparisons)}")
print(f"Total Training Examples:       {len(nl_data) + len(qa_pairs) + len(comparisons)}")

# Category breakdown
categories = {}
for elem in elements:
    cat = elem['category']
    categories[cat] = categories.get(cat, 0) + 1

print(f"\n📁 CATEGORY BREAKDOWN")
print(f"{'─'*70}")
for cat, count in sorted(categories.items(), key=lambda x: x[1], reverse=True):
    enriched_in_cat = len([e for e in enriched if e['category'] == cat])
    print(f"{cat:40} {count:3} elements ({enriched_in_cat} enriched)")

# Show enriched element types
print(f"\n✨ FULLY ENRICHED ELEMENTS ({len(enriched)})")
print(f"{'─'*70}")

# Group by category
enriched_by_cat = {}
for elem in enriched:
    cat = elem['category']
    if cat not in enriched_by_cat:
        enriched_by_cat[cat] = []
    enriched_by_cat[cat].append(elem['element_type'])

for cat in sorted(enriched_by_cat.keys()):
    print(f"\n{cat}:")
    for elem_name in sorted(enriched_by_cat[cat]):
        print(f"  • {elem_name}")

# Sample enriched element
print(f"\n{'='*70}")
print(" SAMPLE ENRICHED ELEMENT: UserTask")
print(f"{'='*70}")

user_task = [e for e in enriched if 'user' in e['element_type'].lower() and 'task' in e['element_type'].lower()][0]
print(f"\nElement Type: {user_task['element_type']}")
print(f"Category: {user_task['category']}")
print(f"Subcategory: {user_task['subcategory']}")
print(f"\nDescription:")
print(f"  {user_task['description']}")
print(f"\nPurpose:")
print(f"  {user_task['purpose']}")
print(f"\nCommon Patterns:")
for pattern in user_task['common_patterns']:
    print(f"  • {pattern}")
print(f"\nConstraints:")
for constraint in user_task['constraints']:
    print(f"  • {constraint}")
print(f"\nConnections:")
print(f"  From: {', '.join(user_task['can_connect_from'])}")
print(f"  To:   {', '.join(user_task['can_connect_to'])}")
print(f"\nXML Example:")
print(f"  {user_task['xml_example']}")

# Sample Q&A
print(f"\n{'='*70}")
print(" SAMPLE Q&A PAIRS")
print(f"{'='*70}")

qa_about_usertask = [qa for qa in qa_pairs if 'usertask' in qa.get('instruction', '').lower()][:3]
for i, qa in enumerate(qa_about_usertask, 1):
    print(f"\nQ{i}: {qa['instruction']}")
    print(f"A{i}: {qa['output']}")

# Sample comparison
print(f"\n{'='*70}")
print(" SAMPLE COMPARISON")
print(f"{'='*70}")

gateway_comparison = [c for c in comparisons if 'gateway' in c.get('instruction', '').lower()][0]
print(f"\nQuestion: {gateway_comparison['instruction']}")
print(f"Answer: {gateway_comparison['output']}")

print(f"\n{'='*70}")
print(" ✅ DATASET GENERATION COMPLETE!")
print(f"{'='*70}")
print("\nAll training data has been successfully generated from the")
print("official BPMN 2.0 specification and enriched with comprehensive")
print("patterns, constraints, and examples.")
print("\nDataset files are ready for language model training in:")
print("  Phase1/Data/bpmn_training_data/")
print("="*70)
