import json

# Load and display enriched elements
with open('bpmn_training_data/bpmn_elements_structured.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# Find StartEvent
start_events = [e for e in data if 'start' in e['element_type'].lower() and 'event' in e['element_type'].lower()]
print(f"Found {len(start_events)} start event elements")

if start_events:
    print("\n" + "="*60)
    print("STARTEVENT EXAMPLE (Enriched):")
    print("="*60)
    print(json.dumps(start_events[0], indent=2))

# Find UserTask
user_tasks = [e for e in data if 'user' in e['element_type'].lower() and 'task' in e['element_type'].lower()]
if user_tasks:
    print("\n" + "="*60)
    print("USERTASK EXAMPLE (Enriched):")
    print("="*60)
    print(json.dumps(user_tasks[0], indent=2))

# Find ExclusiveGateway
gateways = [e for e in data if 'exclusive' in e['element_type'].lower() and 'gateway' in e['element_type'].lower()]
if gateways:
    print("\n" + "="*60)
    print("EXCLUSIVEGATEWAY EXAMPLE (Enriched):")
    print("="*60)
    print(json.dumps(gateways[0], indent=2))
