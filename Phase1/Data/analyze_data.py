import json

# Load and analyze the generated training data
with open('bpmn_training_data/bpmn_elements_structured.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# Find elements with full enrichment
enriched = [e for e in data if e.get('purpose') and e.get('common_patterns')]
print(f"✅ Total elements: {len(data)}")
print(f"✅ Elements with full enrichment: {len(enriched)}")

print("\n📋 Sample enriched elements:")
for elem in enriched[:15]:
    print(f"  - {elem['element_type']}: {elem['category']}")
    if elem.get('purpose'):
        print(f"    Purpose: {elem['purpose'][:80]}...")

print("\n📊 Category breakdown:")
categories = {}
for elem in data:
    cat = elem['category']
    categories[cat] = categories.get(cat, 0) + 1

for cat, count in sorted(categories.items(), key=lambda x: x[1], reverse=True):
    print(f"  {cat}: {count}")

print("\n🎯 Sample Q&A Pairs:")
with open('bpmn_training_data/bpmn_qa_pairs.jsonl', 'r', encoding='utf-8') as f:
    qa_lines = f.readlines()[:5]
    for i, line in enumerate(qa_lines, 1):
        qa = json.loads(line)
        print(f"\n  Q{i}: {qa['instruction']}")
        print(f"  A{i}: {qa['output'][:100]}...")
