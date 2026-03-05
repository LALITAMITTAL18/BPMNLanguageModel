"""
BPMN 2.0 Training Dataset Generator (Offline Version)
Generates training data from comprehensive BPMN element definitions
"""

import json
from typing import Dict, List, Any
from pathlib import Path


class BPMNElementDatabase:
    """Comprehensive BPMN element definitions"""
    
    ELEMENTS = {
        # FLOW OBJECTS - EVENTS
        'StartEvent': {
            'category': 'Flow Object - Event',
            'subcategory': 'Start Event',
            'description': 'A Start Event indicates where a particular Process will start. It is the beginning point of a process flow.',
            'purpose': 'Triggers the start of a process. Can be triggered by different conditions (message, timer, signal, etc.)',
            'attributes': [
                {'name': 'id', 'type': 'string', 'required': True},
                {'name': 'name', 'type': 'string', 'required': False},
                {'name': 'isInterrupting', 'type': 'boolean', 'required': False, 'default': 'true'},
            ],
            'xml_example': '<startEvent id="StartEvent_1" name="Process Started"/>',
            'can_connect_from': [],
            'can_connect_to': ['SequenceFlow'],
            'parent_elements': ['Process', 'SubProcess', 'Lane'],
            'common_patterns': [
                'None Start Event - process starts immediately',
                'Message Start Event - triggered by incoming message',
                'Timer Start Event - triggered at specific time or interval',
                'Signal Start Event - triggered by signal broadcast',
                'Conditional Start Event - triggered when condition is met'
            ],
            'constraints': [
                'Start Events must have no incoming Sequence Flows',
                'Start Events must have at least one outgoing Sequence Flow',
                'Only one None Start Event per Process (unless in Event Sub-Process)',
            ],
            'variants': ['None', 'Message', 'Timer', 'Signal', 'Conditional', 'Error', 'Escalation', 'Compensation', 'Multiple', 'Parallel Multiple']
        },
        
        'EndEvent': {
            'category': 'Flow Object - Event',
            'subcategory': 'End Event',
            'description': 'An End Event indicates where a Process will end. It is the termination point of a process flow path.',
            'purpose': 'Marks the completion of a process flow. Can trigger different outcomes (message, error, termination, etc.)',
            'attributes': [
                {'name': 'id', 'type': 'string', 'required': True},
                {'name': 'name', 'type': 'string', 'required': False},
            ],
            'xml_example': '<endEvent id="EndEvent_1" name="Process Completed"/>',
            'can_connect_from': ['SequenceFlow'],
            'can_connect_to': [],
            'parent_elements': ['Process', 'SubProcess', 'Lane'],
            'common_patterns': [
                'None End Event - process completes normally',
                'Message End Event - sends message upon completion',
                'Error End Event - terminates with error',
                'Terminate End Event - immediately ends all process instances',
                'Signal End Event - broadcasts signal when reached'
            ],
            'constraints': [
                'End Events must have no outgoing Sequence Flows',
                'End Events must have at least one incoming Sequence Flow',
            ],
            'variants': ['None', 'Message', 'Error', 'Escalation', 'Cancel', 'Compensation', 'Signal', 'Terminate', 'Multiple']
        },
        
        'IntermediateEvent': {
            'category': 'Flow Object - Event',
            'subcategory': 'Intermediate Event',
            'description': 'An Intermediate Event represents something that happens during the process flow, between start and end.',
            'purpose': 'Used to catch or throw events during process execution, such as waiting for messages or triggering signals.',
            'attributes': [
                {'name': 'id', 'type': 'string', 'required': True},
                {'name': 'name', 'type': 'string', 'required': False},
            ],
            'xml_example': '<intermediateThrowEvent id="IntermediateEvent_1" name="Send Notification"/>',
            'can_connect_from': ['SequenceFlow'],
            'can_connect_to': ['SequenceFlow'],
            'parent_elements': ['Process', 'SubProcess', 'Lane'],
            'common_patterns': [
                'Catch events - wait for something to happen (Message, Timer, Signal)',
                'Throw events - trigger something to happen (Message, Signal, Escalation)',
                'Boundary events - attached to activities to handle exceptions'
            ],
            'constraints': [
                'Catching events must have incoming and outgoing Sequence Flows',
                'Throwing events must have incoming and outgoing Sequence Flows',
                'Boundary events are attached to activities'
            ],
            'variants': ['Message (Catch/Throw)', 'Timer (Catch)', 'Signal (Catch/Throw)', 'Conditional (Catch)', 'Link (Catch/Throw)', 'Error (Catch)', 'Escalation (Catch/Throw)', 'Compensation (Catch/Throw)', 'Cancel (Catch)']
        },
        
        # FLOW OBJECTS - ACTIVITIES
        'Task': {
            'category': 'Flow Object - Activity',
            'subcategory': 'Task',
            'description': 'A Task is an atomic activity within a Process flow. It represents work that is performed within a business process.',
            'purpose': 'Used to represent a unit of work that needs to be performed, such as sending an email, updating a database, or calling a service.',
            'attributes': [
                {'name': 'id', 'type': 'string', 'required': True},
                {'name': 'name', 'type': 'string', 'required': False},
                {'name': 'isForCompensation', 'type': 'boolean', 'required': False, 'default': 'false'},
                {'name': 'completionQuantity', 'type': 'integer', 'required': False, 'default': '1'},
            ],
            'xml_example': '<task id="Task_1" name="Review Application"/>',
            'can_connect_from': ['SequenceFlow', 'MessageFlow'],
            'can_connect_to': ['SequenceFlow', 'MessageFlow'],
            'parent_elements': ['Process', 'SubProcess', 'Lane'],
            'common_patterns': [
                'Generic tasks for unspecified work',
                'Manual tasks requiring human interaction',
                'User tasks with forms and assignments',
                'Service tasks calling external systems',
                'Script tasks executing code',
                'Business rule tasks evaluating rules',
                'Send tasks sending messages',
                'Receive tasks waiting for messages'
            ],
            'constraints': [
                'Tasks typically have at least one incoming and one outgoing Sequence Flow',
                'Tasks must be contained within a Process or SubProcess',
            ],
            'variants': ['Task (Generic)', 'User Task', 'Service Task', 'Send Task', 'Receive Task', 'Manual Task', 'Business Rule Task', 'Script Task']
        },
        
        'SubProcess': {
            'category': 'Flow Object - Activity',
            'subcategory': 'Sub-Process',
            'description': 'A Sub-Process is a compound activity that contains other activities, gateways, and events within it.',
            'purpose': 'Used to encapsulate complex logic, improve diagram readability, or create reusable process components.',
            'attributes': [
                {'name': 'id', 'type': 'string', 'required': True},
                {'name': 'name', 'type': 'string', 'required': False},
                {'name': 'triggeredByEvent', 'type': 'boolean', 'required': False, 'default': 'false'},
            ],
            'xml_example': '<subProcess id="SubProcess_1" name="Handle Order"/>',
            'can_connect_from': ['SequenceFlow', 'MessageFlow'],
            'can_connect_to': ['SequenceFlow', 'MessageFlow'],
            'parent_elements': ['Process', 'SubProcess', 'Lane'],
            'common_patterns': [
                'Collapsed subprocess - hides complexity',
                'Expanded subprocess - shows internal flow',
                'Event subprocess - handles exceptions or parallel flows',
                'Transaction subprocess - groups activities with compensation',
                'Ad-hoc subprocess - flexible ordering of activities'
            ],
            'constraints': [
                'SubProcesses can contain all BPMN elements except Pools and Lanes',
                'Event SubProcesses must have a Start Event',
            ],
            'variants': ['Embedded SubProcess', 'Event SubProcess', 'Transaction', 'Ad-Hoc SubProcess', 'Call Activity']
        },
        
        # FLOW OBJECTS - GATEWAYS
        'ExclusiveGateway': {
            'category': 'Flow Object - Gateway',
            'subcategory': 'Exclusive Gateway (XOR)',
            'description': 'An Exclusive Gateway (XOR) is a decision point that routes the flow to exactly one of multiple outgoing paths based on conditions.',
            'purpose': 'Used for making exclusive decisions where only one path should be taken.',
            'attributes': [
                {'name': 'id', 'type': 'string', 'required': True},
                {'name': 'name', 'type': 'string', 'required': False},
                {'name': 'default', 'type': 'string', 'required': False},
            ],
            'xml_example': '<exclusiveGateway id="Gateway_1" name="Approved?"/>',
            'can_connect_from': ['SequenceFlow'],
            'can_connect_to': ['SequenceFlow'],
            'parent_elements': ['Process', 'SubProcess', 'Lane'],
            'common_patterns': [
                'If-then-else decisions',
                'Switch/case logic with multiple options',
                'Binary choices (approved/rejected)',
                'Merging exclusive paths back together'
            ],
            'constraints': [
                'When splitting, exactly one outgoing path is taken',
                'When merging, waits for one incoming token',
                'One path should be marked as default if no conditions match',
            ],
            'notation': 'Diamond shape with X marker (or empty for data-based)'
        },
        
        'ParallelGateway': {
            'category': 'Flow Object - Gateway',
            'subcategory': 'Parallel Gateway (AND)',
            'description': 'A Parallel Gateway (AND) splits the flow into multiple concurrent paths or synchronizes multiple paths.',
            'purpose': 'Used to execute multiple activities in parallel or to synchronize parallel flows.',
            'attributes': [
                {'name': 'id', 'type': 'string', 'required': True},
                {'name': 'name', 'type': 'string', 'required': False},
            ],
            'xml_example': '<parallelGateway id="Gateway_1" name="Fork"/>',
            'can_connect_from': ['SequenceFlow'],
            'can_connect_to': ['SequenceFlow'],
            'parent_elements': ['Process', 'SubProcess', 'Lane'],
            'common_patterns': [
                'Fork - split into parallel activities',
                'Join - synchronize parallel activities',
                'Fork-Join pattern - split and later merge parallel flows'
            ],
            'constraints': [
                'When splitting, all outgoing paths are activated',
                'When merging, waits for all incoming tokens',
                'No conditions on outgoing flows',
            ],
            'notation': 'Diamond shape with + marker'
        },
        
        'InclusiveGateway': {
            'category': 'Flow Object - Gateway',
            'subcategory': 'Inclusive Gateway (OR)',
            'description': 'An Inclusive Gateway (OR) can activate one or more outgoing paths based on conditions.',
            'purpose': 'Used when multiple paths can be taken simultaneously based on different conditions.',
            'attributes': [
                {'name': 'id', 'type': 'string', 'required': True},
                {'name': 'name', 'type': 'string', 'required': False},
                {'name': 'default', 'type': 'string', 'required': False},
            ],
            'xml_example': '<inclusiveGateway id="Gateway_1" name="Check Options"/>',
            'can_connect_from': ['SequenceFlow'],
            'can_connect_to': ['SequenceFlow'],
            'parent_elements': ['Process', 'SubProcess', 'Lane'],
            'common_patterns': [
                'Multiple optional activities that may run in parallel',
                'Conditional parallel execution',
                'Variable number of parallel paths based on conditions'
            ],
            'constraints': [
                'When splitting, evaluates all conditions and activates matching paths',
                'When merging, waits for all activated paths',
                'At least one path must be taken',
            ],
            'notation': 'Diamond shape with O marker'
        },
        
        'EventBasedGateway': {
            'category': 'Flow Object - Gateway',
            'subcategory': 'Event-Based Gateway',
            'description': 'An Event-Based Gateway represents a branching point where the decision is based on events rather than conditions.',
            'purpose': 'Used to wait for one of multiple possible events and route the flow based on which event occurs first.',
            'attributes': [
                {'name': 'id', 'type': 'string', 'required': True},
                {'name': 'name', 'type': 'string', 'required': False},
                {'name': 'instantiate', 'type': 'boolean', 'required': False, 'default': 'false'},
            ],
            'xml_example': '<eventBasedGateway id="Gateway_1" name="Wait for Response"/>',
            'can_connect_from': ['SequenceFlow'],
            'can_connect_to': ['SequenceFlow'],
            'parent_elements': ['Process', 'SubProcess', 'Lane'],
            'common_patterns': [
                'Wait for first of multiple messages',
                'Race condition between timer and message',
                'Alternative event triggers'
            ],
            'constraints': [
                'Outgoing flows must lead to catching events or receive tasks',
                'Only one event is consumed, others are discarded',
            ],
            'notation': 'Diamond shape with pentagon marker'
        },
        
        'ComplexGateway': {
            'category': 'Flow Object - Gateway',
            'subcategory': 'Complex Gateway',
            'description': 'A Complex Gateway is used for complex synchronization scenarios that cannot be expressed with other gateways.',
            'purpose': 'Used for advanced scenarios like M-out-of-N joins or complex activation conditions.',
            'attributes': [
                {'name': 'id', 'type': 'string', 'required': True},
                {'name': 'name', 'type': 'string', 'required': False},
                {'name': 'activationCondition', 'type': 'expression', 'required': False},
            ],
            'xml_example': '<complexGateway id="Gateway_1" name="2 out of 3"/>',
            'can_connect_from': ['SequenceFlow'],
            'can_connect_to': ['SequenceFlow'],
            'parent_elements': ['Process', 'SubProcess', 'Lane'],
            'common_patterns': [
                'M-out-of-N synchronization (wait for 2 out of 3 paths)',
                'Complex business rules for merging',
                'Advanced conditional logic'
            ],
            'constraints': [
                'Requires explicit activation conditions',
                'Less commonly used than other gateway types',
            ],
            'notation': 'Diamond shape with * marker'
        },
        
        # CONNECTING OBJECTS
        'SequenceFlow': {
            'category': 'Connecting Object',
            'subcategory': 'Sequence Flow',
            'description': 'A Sequence Flow represents the order in which activities are performed in a Process.',
            'purpose': 'Connects elements to define the execution order and flow of control within a process.',
            'attributes': [
                {'name': 'id', 'type': 'string', 'required': True},
                {'name': 'name', 'type': 'string', 'required': False},
                {'name': 'sourceRef', 'type': 'string', 'required': True},
                {'name': 'targetRef', 'type': 'string', 'required': True},
                {'name': 'conditionExpression', 'type': 'expression', 'required': False},
            ],
            'xml_example': '<sequenceFlow id="Flow_1" sourceRef="Task_1" targetRef="Task_2"/>',
            'can_connect_from': ['Task', 'Event', 'Gateway', 'SubProcess'],
            'can_connect_to': ['Task', 'Event', 'Gateway', 'SubProcess'],
            'parent_elements': ['Process', 'SubProcess'],
            'common_patterns': [
                'Unconditional flow - always follows this path',
                'Conditional flow - evaluates expression to determine if path is taken',
                'Default flow - taken when no other conditions match'
            ],
            'constraints': [
                'Cannot cross Pool boundaries',
                'Must connect compatible element types',
                'Conditional flows must have expressions',
            ],
            'notation': 'Solid arrow line'
        },
        
        'MessageFlow': {
            'category': 'Connecting Object',
            'subcategory': 'Message Flow',
            'description': 'A Message Flow shows the flow of messages between two participants (pools) in a collaboration.',
            'purpose': 'Represents communication between different process participants, organizations, or systems.',
            'attributes': [
                {'name': 'id', 'type': 'string', 'required': True},
                {'name': 'name', 'type': 'string', 'required': False},
                {'name': 'sourceRef', 'type': 'string', 'required': True},
                {'name': 'targetRef', 'type': 'string', 'required': True},
            ],
            'xml_example': '<messageFlow id="MessageFlow_1" sourceRef="Task_1" targetRef="Task_2"/>',
            'can_connect_from': ['Task', 'Event', 'Pool'],
            'can_connect_to': ['Task', 'Event', 'Pool'],
            'parent_elements': ['Collaboration'],
            'common_patterns': [
                'Request-response patterns between participants',
                'Notifications from one organization to another',
                'Cross-pool communication',
                'Customer-Service Provider interactions'
            ],
            'constraints': [
                'Must cross Pool boundaries',
                'Cannot connect elements within same Pool',
                'Often connects to Message Events or Tasks',
            ],
            'notation': 'Dashed arrow line with open circle at start'
        },
        
        'Association': {
            'category': 'Connecting Object',
            'subcategory': 'Association',
            'description': 'An Association is used to link artifacts (like text annotations) to flow objects.',
            'purpose': 'Used to associate data objects, text annotations, or other artifacts with process elements.',
            'attributes': [
                {'name': 'id', 'type': 'string', 'required': True},
                {'name': 'sourceRef', 'type': 'string', 'required': True},
                {'name': 'targetRef', 'type': 'string', 'required': True},
                {'name': 'associationDirection', 'type': 'string', 'required': False},
            ],
            'xml_example': '<association id="Association_1" sourceRef="Task_1" targetRef="DataObject_1"/>',
            'can_connect_from': ['Task', 'Event', 'Gateway', 'Artifact'],
            'can_connect_to': ['Task', 'Event', 'Gateway', 'Artifact'],
            'parent_elements': ['Process', 'SubProcess', 'Collaboration'],
            'common_patterns': [
                'Linking data objects to activities',
                'Connecting text annotations for documentation',
                'Showing data input/output relationships'
            ],
            'constraints': [
                'Does not affect process flow',
                'Used for documentation and data relationships',
            ],
            'notation': 'Dotted line'
        },
        
        # SWIMLANES
        'Pool': {
            'category': 'Swimlane',
            'subcategory': 'Pool',
            'description': 'A Pool represents a participant in a collaboration, containing the process flow for that participant.',
            'purpose': 'Used to separate different participants, organizations, or systems in a process diagram.',
            'attributes': [
                {'name': 'id', 'type': 'string', 'required': True},
                {'name': 'name', 'type': 'string', 'required': False},
                {'name': 'processRef', 'type': 'string', 'required': False},
                {'name': 'isHorizontal', 'type': 'boolean', 'required': False, 'default': 'true'},
            ],
            'xml_example': '<participant id="Pool_1" name="Customer" processRef="Process_1"/>',
            'can_connect_from': ['MessageFlow'],
            'can_connect_to': ['MessageFlow'],
            'parent_elements': ['Collaboration'],
            'common_patterns': [
                'Separate organizations (Company A vs Company B)',
                'Different departments (Sales, Finance, IT)',
                'Customer vs Service Provider',
                'Internal vs External participants'
            ],
            'constraints': [
                'Sequence Flows cannot cross Pool boundaries',
                'Message Flows connect between Pools',
                'Pools can contain one Process',
            ],
            'notation': 'Large rectangle containing process'
        },
        
        'Lane': {
            'category': 'Swimlane',
            'subcategory': 'Lane',
            'description': 'A Lane is a subdivision within a Pool, used to organize activities by role, responsibility, or system.',
            'purpose': 'Used to assign activities to specific roles, departments, or systems within an organization.',
            'attributes': [
                {'name': 'id', 'type': 'string', 'required': True},
                {'name': 'name', 'type': 'string', 'required': False},
            ],
            'xml_example': '<lane id="Lane_1" name="Manager"/>',
            'can_connect_from': [],
            'can_connect_to': [],
            'parent_elements': ['Pool'],
            'common_patterns': [
                'Role-based organization (Manager, Employee, Executive)',
                'Department organization (Sales, Finance, Operations)',
                'System organization (Manual, Automated, System A)',
                'Responsibility assignment'
            ],
            'constraints': [
                'Lanes are contained within Pools',
                'Lanes can be nested',
                'Activities in a Lane are performed by that role/system',
            ],
            'notation': 'Horizontal or vertical subdivision within Pool'
        },
        
        # ARTIFACTS
        'DataObject': {
            'category': 'Artifact',
            'subcategory': 'Data Object',
            'description': 'A Data Object represents information flowing through the process, such as documents, data records, or business objects.',
            'purpose': 'Used to show what data is required or produced by activities, and how data moves through the process.',
            'attributes': [
                {'name': 'id', 'type': 'string', 'required': True},
                {'name': 'name', 'type': 'string', 'required': False},
                {'name': 'isCollection', 'type': 'boolean', 'required': False, 'default': 'false'},
            ],
            'xml_example': '<dataObject id="DataObject_1" name="Invoice"/>',
            'can_connect_from': ['DataAssociation'],
            'can_connect_to': ['DataAssociation'],
            'parent_elements': ['Process', 'SubProcess'],
            'common_patterns': [
                'Input data for tasks (read)',
                'Output data from tasks (write)',
                'Shared data across activities',
                'Documents and forms'
            ],
            'constraints': [
                'Connected to activities via Data Associations',
                'Does not affect process flow',
            ],
            'notation': 'Document icon (folded corner rectangle)'
        },
        
        'DataStore': {
            'category': 'Artifact',
            'subcategory': 'Data Store',
            'description': 'A Data Store represents a persistent storage location for data, such as a database or file system.',
            'purpose': 'Used to indicate where data is permanently stored and can be accessed by multiple processes.',
            'attributes': [
                {'name': 'id', 'type': 'string', 'required': True},
                {'name': 'name', 'type': 'string', 'required': False},
            ],
            'xml_example': '<dataStoreReference id="DataStore_1" name="Customer Database"/>',
            'can_connect_from': ['DataAssociation'],
            'can_connect_to': ['DataAssociation'],
            'parent_elements': ['Process', 'SubProcess', 'Collaboration'],
            'common_patterns': [
                'Database access',
                'File system storage',
                'Shared repositories',
                'Persistent data storage'
            ],
            'constraints': [
                'Connected to activities via Data Associations',
                'Represents persistent storage',
            ],
            'notation': 'Database icon (cylinder)'
        },
        
        'TextAnnotation': {
            'category': 'Artifact',
            'subcategory': 'Text Annotation',
            'description': 'A Text Annotation provides additional information or documentation about process elements.',
            'purpose': 'Used to add comments, notes, or clarifying information to a BPMN diagram.',
            'attributes': [
                {'name': 'id', 'type': 'string', 'required': True},
                {'name': 'text', 'type': 'string', 'required': False},
            ],
            'xml_example': '<textAnnotation id="Annotation_1"><text>This task requires manager approval</text></textAnnotation>',
            'can_connect_from': ['Association'],
            'can_connect_to': ['Association'],
            'parent_elements': ['Process', 'SubProcess', 'Collaboration'],
            'common_patterns': [
                'Explaining business rules',
                'Documenting process details',
                'Adding notes for developers',
                'Clarifying exceptions'
            ],
            'constraints': [
                'Does not affect process execution',
                'Connected via Associations',
            ],
            'notation': 'Rectangle with wavy bottom edge'
        },
        
        'Group': {
            'category': 'Artifact',
            'subcategory': 'Group',
            'description': 'A Group is a visual grouping of process elements for documentation purposes.',
            'purpose': 'Used to visually organize and categorize related elements in a diagram without affecting execution.',
            'attributes': [
                {'name': 'id', 'type': 'string', 'required': True},
                {'name': 'categoryValueRef', 'type': 'string', 'required': False},
            ],
            'xml_example': '<group id="Group_1"/>',
            'can_connect_from': [],
            'can_connect_to': [],
            'parent_elements': ['Process', 'SubProcess', 'Collaboration'],
            'common_patterns': [
                'Grouping related activities',
                'Highlighting process phases',
                'Visual organization',
                'Documentation purposes'
            ],
            'constraints': [
                'Does not affect process execution',
                'Purely visual element',
            ],
            'notation': 'Rounded rectangle with dashed border'
        },
    }


class BPMNDatasetGenerator:
    """Generate training datasets in various formats"""
    
    def __init__(self, elements: Dict[str, Dict[str, Any]]):
        self.elements = elements
    
    def generate_structured_json(self) -> List[Dict[str, Any]]:
        """Generate structured JSON format"""
        structured_data = []
        for elem_type, elem_data in self.elements.items():
            structured_data.append({
                'element_type': elem_type,
                **elem_data
            })
        return structured_data
    
    def generate_natural_language_format(self) -> List[Dict[str, Any]]:
        """Generate natural language training examples"""
        dataset = []
        
        for elem_type, elem_data in self.elements.items():
            text_parts = []
            
            # Main description
            text_parts.append(f"A {elem_type} is a BPMN element. {elem_data['description']}")
            
            # Category
            text_parts.append(f"It is categorized as: {elem_data['category']}.")
            if elem_data.get('subcategory'):
                text_parts.append(f"Specifically, it is a {elem_data['subcategory']}.")
            
            # Purpose
            text_parts.append(f"\nPurpose: {elem_data['purpose']}")
            
            # Attributes
            if elem_data.get('attributes'):
                text_parts.append("\n\nAttributes:")
                for attr in elem_data['attributes']:
                    required = "required" if attr.get('required') else "optional"
                    default = f", default: {attr['default']}" if attr.get('default') else ""
                    text_parts.append(f"- {attr['name']} ({required}, type: {attr['type']}{default})")
            
            # Connections
            if elem_data.get('can_connect_from'):
                text_parts.append(f"\n\nCan receive connections from: {', '.join(elem_data['can_connect_from'])}")
            if elem_data.get('can_connect_to'):
                text_parts.append(f"Can connect to: {', '.join(elem_data['can_connect_to'])}")
            
            # Parent elements
            if elem_data.get('parent_elements'):
                text_parts.append(f"\n\nCan be contained in: {', '.join(elem_data['parent_elements'])}")
            
            # Common patterns
            if elem_data.get('common_patterns'):
                text_parts.append("\n\nCommon usage patterns:")
                for i, pattern in enumerate(elem_data['common_patterns'], 1):
                    text_parts.append(f"{i}. {pattern}")
            
            # Constraints
            if elem_data.get('constraints'):
                text_parts.append("\n\nConstraints and rules:")
                for constraint in elem_data['constraints']:
                    text_parts.append(f"- {constraint}")
            
            # Variants
            if elem_data.get('variants'):
                text_parts.append(f"\n\nVariants: {', '.join(elem_data['variants'])}")
            
            # XML Example
            if elem_data.get('xml_example'):
                text_parts.append(f"\n\nXML Example:\n{elem_data['xml_example']}")
            
            dataset.append({
                'text': ' '.join(text_parts),
                'element_type': elem_type,
                'category': elem_data['category']
            })
        
        return dataset
    
    def generate_qa_pairs(self) -> List[Dict[str, Any]]:
        """Generate question-answer training pairs"""
        qa_pairs = []
        
        for elem_type, elem_data in self.elements.items():
            
            # What is X?
            qa_pairs.append({
                'instruction': f"What is a {elem_type} in BPMN?",
                'input': '',
                'output': elem_data['description'],
                'element_type': elem_type
            })
            
            # When to use X?
            qa_pairs.append({
                'instruction': f"When should I use a {elem_type} in BPMN?",
                'input': '',
                'output': elem_data['purpose'],
                'element_type': elem_type
            })
            
            # What category is X?
            qa_pairs.append({
                'instruction': f"What category does {elem_type} belong to in BPMN?",
                'input': '',
                'output': f"{elem_type} belongs to the {elem_data['category']} category in BPMN.",
                'element_type': elem_type
            })
            
            # Attributes
            if elem_data.get('attributes'):
                attr_list = []
                for attr in elem_data['attributes'][:5]:  # Limit to first 5
                    required = "required" if attr.get('required') else "optional"
                    attr_list.append(f"{attr['name']} ({attr['type']}, {required})")
                
                qa_pairs.append({
                    'instruction': f"What are the main attributes of a {elem_type}?",
                    'input': '',
                    'output': f"The main attributes of a {elem_type} are: {', '.join(attr_list)}",
                    'element_type': elem_type
                })
            
            # Connections
            if elem_data.get('can_connect_to'):
                qa_pairs.append({
                    'instruction': f"What BPMN elements can a {elem_type} connect to?",
                    'input': '',
                    'output': f"A {elem_type} can connect to: {', '.join(elem_data['can_connect_to'])}",
                    'element_type': elem_type
                })
            
            # Common patterns
            if elem_data.get('common_patterns'):
                patterns_text = ' '.join([f"({i+1}) {p}" for i, p in enumerate(elem_data['common_patterns'])])
                qa_pairs.append({
                    'instruction': f"What are common usage patterns for {elem_type}?",
                    'input': '',
                    'output': f"Common usage patterns for {elem_type} include: {patterns_text}",
                    'element_type': elem_type
                })
            
            # XML generation
            if elem_data.get('xml_example'):
                qa_pairs.append({
                    'instruction': f"Generate a BPMN XML snippet for a {elem_type}",
                    'input': '',
                    'output': elem_data['xml_example'],
                    'element_type': elem_type
                })
            
            # Constraints
            if elem_data.get('constraints'):
                constraints_text = ' '.join([f"({i+1}) {c}" for i, c in enumerate(elem_data['constraints'])])
                qa_pairs.append({
                    'instruction': f"What are the constraints for using {elem_type}?",
                    'input': '',
                    'output': f"The constraints for {elem_type} are: {constraints_text}",
                    'element_type': elem_type
                })
            
            # Variants
            if elem_data.get('variants'):
                qa_pairs.append({
                    'instruction': f"What are the different types or variants of {elem_type}?",
                    'input': '',
                    'output': f"The variants of {elem_type} include: {', '.join(elem_data['variants'])}",
                    'element_type': elem_type
                })
        
        return qa_pairs
    
    def generate_comparison_pairs(self) -> List[Dict[str, Any]]:
        """Generate comparison questions between similar elements"""
        comparison_pairs = []

        elements = [(name, data) for name, data in self.elements.items()]
        elements.sort(key=lambda item: item[0].lower())

        # For small offline sets, compare all pairs to avoid sparse output
        if len(elements) <= 50:
            for i, (name1, elem1) in enumerate(elements):
                for name2, elem2 in elements[i + 1:]:
                    comparison = self._compare_elements(name1, elem1, name2, elem2)
                    if comparison:
                        comparison_pairs.append(comparison)
            return comparison_pairs

        # For larger sets, compare within categories to keep size reasonable
        by_category = {}
        for elem_type, elem_data in self.elements.items():
            category = elem_data.get('category', 'Other')
            by_category.setdefault(category, []).append((elem_type, elem_data))

        for _, elements_in_category in by_category.items():
            if len(elements_in_category) < 2:
                continue

            elements_in_category.sort(key=lambda item: item[0].lower())

            for i, (name1, elem1) in enumerate(elements_in_category):
                for name2, elem2 in elements_in_category[i + 1:i + 3]:
                    comparison = self._compare_elements(name1, elem1, name2, elem2)
                    if comparison:
                        comparison_pairs.append(comparison)

        return comparison_pairs

    def _compare_elements(
        self,
        name1: str,
        elem1: Dict[str, Any],
        name2: str,
        elem2: Dict[str, Any]
    ) -> Dict[str, Any] | None:
        """Compare two BPMN elements and return a comparison entry"""
        similarities = []
        differences = []

        # Category and subcategory
        category1 = elem1.get('category')
        category2 = elem2.get('category')
        if category1 and category2:
            if category1 == category2:
                similarities.append(f"Both are {category1} elements")
            else:
                differences.append(f"Category differs: {name1} is {category1}; {name2} is {category2}")
        if elem1.get('subcategory') and elem1.get('subcategory') == elem2.get('subcategory'):
            similarities.append(f"Both are {elem1['subcategory']}s")

        # Purpose comparison
        purpose1 = elem1.get('purpose', '')
        purpose2 = elem2.get('purpose', '')
        if purpose1 and purpose2 and purpose1 != purpose2:
            differences.append(f"Purpose differs: {name1} {purpose1}; {name2} {purpose2}")

        # Connection capabilities
        can_to_1 = set(elem1.get('can_connect_to', []))
        can_to_2 = set(elem2.get('can_connect_to', []))
        if can_to_1 and can_to_1 == can_to_2:
            similarities.append(f"Both can connect to: {', '.join(sorted(can_to_1))}")
        elif can_to_1 != can_to_2:
            differences.append("Connection targets differ")

        can_from_1 = set(elem1.get('can_connect_from', []))
        can_from_2 = set(elem2.get('can_connect_from', []))
        if can_from_1 and can_from_1 == can_from_2:
            similarities.append(f"Both can connect from: {', '.join(sorted(can_from_1))}")
        elif can_from_1 != can_from_2:
            differences.append("Connection sources differ")

        # Constraints presence
        has_constraints_1 = bool(elem1.get('constraints'))
        has_constraints_2 = bool(elem2.get('constraints'))
        if has_constraints_1 != has_constraints_2:
            differences.append("Constraints coverage differs")

        if not similarities and not differences:
            return None

        return {
            'instruction': f"What is the difference between {name1} and {name2} in BPMN?",
            'input': '',
            'output': (
                f"Similarities: {' '.join(similarities) if similarities else 'None'}. "
                f"Differences: {' '.join(differences) if differences else 'None'}"
            ),
            'element1': name1,
            'element2': name2
        }
    
    def save_to_jsonl(self, data: List[Dict[str, Any]], filename: str):
        """Save data to JSONL format"""
        with open(filename, 'w', encoding='utf-8') as f:
            for item in data:
                f.write(json.dumps(item, ensure_ascii=False) + '\n')
        print(f"Saved {len(data)} items to {filename}")
    
    def save_to_json(self, data: List[Dict[str, Any]], filename: str):
        """Save data to JSON format"""
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"Saved {len(data)} items to {filename}")


def main():
    """Main execution function"""
    print("=" * 70)
    print(" " * 20 + "BPMN Training Dataset Generator")
    print("=" * 70)
    print()
    
    # Load element definitions
    db = BPMNElementDatabase()
    print(f"📚 Loaded {len(db.ELEMENTS)} BPMN element definitions")
    print()
    
    # Generate datasets
    generator = BPMNDatasetGenerator(db.ELEMENTS)
    
    # Create output directory
    output_dir = Path('bpmn_training_data')
    output_dir.mkdir(exist_ok=True)
    print(f"📁 Output directory: {output_dir.absolute()}")
    print()
    
    print("Generating training datasets...")
    print("-" * 70)
    
    # 1. Structured JSON
    structured_data = generator.generate_structured_json()
    generator.save_to_json(structured_data, output_dir / 'bpmn_elements_structured.json')
    
    # 2. Natural language format (JSONL)
    nl_data = generator.generate_natural_language_format()
    generator.save_to_jsonl(nl_data, output_dir / 'bpmn_natural_language.jsonl')
    
    # 3. Q&A pairs (JSONL)
    qa_data = generator.generate_qa_pairs()
    generator.save_to_jsonl(qa_data, output_dir / 'bpmn_qa_pairs.jsonl')
    
    # 4. Comparison pairs
    comparison_data = generator.generate_comparison_pairs()
    generator.save_to_jsonl(comparison_data, output_dir / 'bpmn_comparisons.jsonl')
    
    print()
    print("=" * 70)
    print(" " * 25 + "Generation Complete!")
    print("=" * 70)
    print()
    
    # Statistics
    print("📊 Dataset Statistics:")
    print(f"   • Total elements: {len(structured_data)}")
    print(f"   • Natural language examples: {len(nl_data)}")
    print(f"   • Q&A pairs: {len(qa_data)}")
    print(f"   • Comparison pairs: {len(comparison_data)}")
    print(f"   • Total training examples: {len(nl_data) + len(qa_data) + len(comparison_data)}")
    print()
    
    # Categories breakdown
    categories = {}
    for elem in structured_data:
        cat = elem['category']
        categories[cat] = categories.get(cat, 0) + 1
    
    print("📋 Elements by Category:")
    for cat, count in sorted(categories.items()):
        print(f"   • {cat}: {count}")
    print()
    
    # Print samples
    print("=" * 70)
    print("Sample Natural Language Entry:")
    print("-" * 70)
    if nl_data:
        sample = nl_data[0]['text']
        print(sample[:600] + "..." if len(sample) > 600 else sample)
    print()
    
    print("=" * 70)
    print("Sample Q&A Pairs:")
    print("-" * 70)
    for i, qa in enumerate(qa_data[:3], 1):
        print(f"{i}. Q: {qa['instruction']}")
        answer = qa['output']
        print(f"   A: {answer[:150]}..." if len(answer) > 150 else f"   A: {answer}")
        print()
    
    print("=" * 70)
    print("✅ All datasets generated successfully!")
    print(f"📂 Files saved in: {output_dir.absolute()}")
    print("=" * 70)


if __name__ == "__main__":
    main()
