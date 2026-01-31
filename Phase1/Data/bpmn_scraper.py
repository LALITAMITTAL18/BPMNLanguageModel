"""
BPMN 2.0 Specification Scraper and Parser
Extracts BPMN element definitions from the official OMG specification
"""

import requests
import json
import xml.etree.ElementTree as ET
from typing import Dict, List, Any, Optional
from pathlib import Path
import re
from bs4 import BeautifulSoup
import time


class BPMNSchemaParser:
    """Parse BPMN XSD Schema to extract element definitions"""
    
    def __init__(self):
        # OMG BPMN 2.0 Specification XSD URLs
        self.xsd_url = "https://www.omg.org/spec/BPMN/2.0/bpmn20.xsd"
        self.semantic_url = "https://www.omg.org/spec/BPMN/2.0/Semantic.xsd"
        # Alternative: Use direct GitHub raw content
        self.github_xsd = "https://raw.githubusercontent.com/bpmn-io/bpmn-moddle/master/resources/bpmn/xsd/BPMN20.xsd"
        self.github_semantic = "https://raw.githubusercontent.com/bpmn-io/bpmn-moddle/master/resources/bpmn/xsd/Semantic.xsd"
        
        self.namespace = {
            'xsd': 'http://www.w3.org/2001/XMLSchema',
            'bpmn': 'http://www.omg.org/spec/BPMN/20100502/MODEL',
            'semantic': 'http://www.omg.org/spec/BPMN/20100524/MODEL',
            'bpmn2': 'http://schema.omg.org/spec/BPMN/2.0'
        }
        self.elements = []
        self.element_hierarchy = {}
        
    def download_schema(self, url: str) -> str:
        """Download BPMN XSD schema from URL"""
        print(f"Downloading schema from {url}...")
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            return response.text
        except Exception as e:
            print(f"Warning: Could not download {url}: {e}")
            return ""
    
    def parse_element(self, element: ET.Element, element_name: str = None) -> Dict[str, Any]:
        """Parse a single XSD element definition"""
        name = element_name or element.get('name', '')
        elem_data = {
            'element_type': name,
            'category': self._determine_category(name),
            'subcategory': self._determine_subcategory(name),
            'attributes': [],
            'description': '',
            'xml_example': '',
            'constraints': [],
            'parent_elements': [],
            'child_elements': [],
            'can_connect_from': [],
            'can_connect_to': [],
            'common_patterns': [],
            'purpose': '',
            'variants': []
        }
        
        # Extract documentation
        doc = element.find('.//xsd:annotation/xsd:documentation', self.namespace)
        if doc is not None and doc.text:
            elem_data['description'] = self._clean_description(doc.text)
        
        # Extract attributes from element itself
        for attr in element.findall('.//xsd:attribute', self.namespace):
            attr_data = {
                'name': attr.get('name', ''),
                'type': self._clean_type(attr.get('type', '')),
                'required': attr.get('use') == 'required'
            }
            default_val = attr.get('default', '')
            if default_val:
                attr_data['default'] = default_val
            
            # Get attribute documentation
            attr_doc = attr.find('.//xsd:annotation/xsd:documentation', self.namespace)
            if attr_doc is not None and attr_doc.text:
                attr_data['description'] = self._clean_description(attr_doc.text)
            
            if attr_data['name']:
                elem_data['attributes'].append(attr_data)
        
        # Extract complex type structure
        complex_type = element.find('.//xsd:complexContent', self.namespace)
        if complex_type is not None:
            extension = complex_type.find('.//xsd:extension', self.namespace)
            if extension is not None:
                base = extension.get('base', '')
                if base:
                    elem_data['parent_elements'].append(self._clean_type(base))
        
        # Extract child elements from sequences and choices
        for seq in element.findall('.//xsd:sequence/xsd:element', self.namespace):
            child_ref = seq.get('ref', '') or seq.get('name', '')
            if child_ref:
                child_name = self._clean_type(child_ref)
                if child_name not in elem_data['child_elements']:
                    elem_data['child_elements'].append(child_name)
        
        for choice in element.findall('.//xsd:choice/xsd:element', self.namespace):
            child_ref = choice.get('ref', '') or choice.get('name', '')
            if child_ref:
                child_name = self._clean_type(child_ref)
                if child_name not in elem_data['child_elements']:
                    elem_data['child_elements'].append(child_name)
        
        # Generate XML example
        elem_data['xml_example'] = self._generate_xml_example(elem_data)
        
        return elem_data
    
    def _clean_type(self, type_str: str) -> str:
        """Remove namespace prefixes from type names"""
        if ':' in type_str:
            return type_str.split(':')[-1]
        return type_str
    
    def _clean_description(self, text: str) -> str:
        """Clean and format description text"""
        # Remove extra whitespace and newlines
        text = re.sub(r'\s+', ' ', text).strip()
        # Remove XML artifacts
        text = re.sub(r'<[^>]+>', '', text)
        return text
    
    def _generate_xml_example(self, elem_data: Dict[str, Any]) -> str:
        """Generate a simple XML example for the element"""
        elem_type = elem_data['element_type']
        elem_lower = elem_type[0].lower() + elem_type[1:] if elem_type else 'element'
        
        # Build attributes
        attrs = [f'id="{elem_type}_1"']
        if elem_data['attributes']:
            for attr in elem_data['attributes'][:2]:  # Include first 2 attributes
                if attr['name'] not in ['id', 'ID']:
                    if attr['type'] == 'string':
                        attrs.append(f'{attr["name"]}="Example"')
                    elif attr['type'] == 'boolean':
                        attrs.append(f'{attr["name"]}="true"')
        
        return f'<{elem_lower} {" ".join(attrs)}/>'
    
    def _determine_category(self, element_name: str) -> str:
        """Determine BPMN category based on element name"""
        name_lower = element_name.lower()
        
        # Events
        if 'event' in name_lower:
            return 'Flow Object - Event'
        
        # Tasks and Activities
        if any(kw in name_lower for kw in ['task', 'activity', 'subprocess', 'callactivity']):
            return 'Flow Object - Activity'
        
        # Gateways
        if 'gateway' in name_lower:
            return 'Flow Object - Gateway'
        
        # Connecting Objects
        if any(kw in name_lower for kw in ['sequenceflow', 'messageflow', 'association']):
            return 'Connecting Object'
        
        # Swimlanes
        if any(kw in name_lower for kw in ['pool', 'lane', 'participant', 'collaboration']):
            return 'Swimlane'
        
        # Artifacts
        if any(kw in name_lower for kw in ['dataobject', 'group', 'annotation', 'text']):
            return 'Artifact'
        
        # Data
        if any(kw in name_lower for kw in ['data', 'message', 'signal', 'error']):
            return 'Data Element'
        
        return 'Other'
    
    def _determine_subcategory(self, element_name: str) -> str:
        """Determine specific subcategory for BPMN element"""
        name_lower = element_name.lower()
        
        # Event types
        if 'startevent' in name_lower:
            return 'Start Event'
        elif 'endevent' in name_lower:
            return 'End Event'
        elif 'intermediatecatchevent' in name_lower or 'intermediatethrowevent' in name_lower:
            return 'Intermediate Event'
        elif 'boundaryevent' in name_lower:
            return 'Boundary Event'
        
        # Task types
        if 'usertask' in name_lower:
            return 'User Task'
        elif 'servicetask' in name_lower:
            return 'Service Task'
        elif 'scripttask' in name_lower:
            return 'Script Task'
        elif 'manualtask' in name_lower:
            return 'Manual Task'
        elif 'businessruletask' in name_lower:
            return 'Business Rule Task'
        elif 'sendtask' in name_lower:
            return 'Send Task'
        elif 'receivetask' in name_lower:
            return 'Receive Task'
        elif 'task' in name_lower:
            return 'Task'
        
        # Gateway types
        if 'exclusivegateway' in name_lower:
            return 'Exclusive Gateway'
        elif 'parallelgateway' in name_lower:
            return 'Parallel Gateway'
        elif 'inclusivegateway' in name_lower:
            return 'Inclusive Gateway'
        elif 'eventbasedgateway' in name_lower:
            return 'Event-Based Gateway'
        elif 'complexgateway' in name_lower:
            return 'Complex Gateway'
        
        return ''
    
    def parse_schema(self, schema_content: str) -> List[Dict[str, Any]]:
        """Parse the entire XSD schema"""
        if not schema_content:
            return self.elements
            
        print("Parsing BPMN schema...")
        try:
            root = ET.fromstring(schema_content)
        except ET.ParseError as e:
            print(f"Error parsing schema XML: {e}")
            return self.elements
        
        # Find all top-level elements
        for elem in root.findall('.//xsd:element[@name]', self.namespace):
            elem_name = elem.get('name')
            if elem_name and not any(e['element_type'] == elem_name for e in self.elements):
                elem_data = self.parse_element(elem, elem_name)
                if elem_data['element_type']:
                    self.elements.append(elem_data)
        
        # Find all complex types (they represent BPMN elements)
        for complex_type in root.findall('.//xsd:complexType[@name]', self.namespace):
            type_name = complex_type.get('name')
            if type_name and not any(e['element_type'] == type_name for e in self.elements):
                elem_data = self.parse_element(complex_type, type_name)
                if elem_data['element_type']:
                    self.elements.append(elem_data)
        
        return self.elements
    
    def fetch_all_schemas(self) -> List[Dict[str, Any]]:
        """Download and parse all BPMN schema files"""
        # Try official OMG URLs first, then GitHub as fallback
        schemas = [
            ('Main BPMN Schema (OMG)', self.xsd_url),
            ('Main BPMN Schema (GitHub)', self.github_xsd),
            ('Semantic Schema (OMG)', self.semantic_url),
            ('Semantic Schema (GitHub)', self.github_semantic),
        ]
        
        downloaded_count = 0
        for schema_name, schema_url in schemas:
            print(f"\nAttempting {schema_name}...")
            content = self.download_schema(schema_url)
            if content:
                self.parse_schema(content)
                downloaded_count += 1
                if downloaded_count >= 2:  # Stop after successfully downloading 2 schemas
                    break
        
        # Remove duplicates
        seen = set()
        unique_elements = []
        for elem in self.elements:
            if elem['element_type'] not in seen:
                seen.add(elem['element_type'])
                unique_elements.append(elem)
        
        self.elements = unique_elements
        print(f"\nTotal unique elements extracted: {len(self.elements)}")
        return self.elements


class BPMNElementEnricher:
    """Enrich parsed elements with additional BPMN-specific context"""
    
    # Comprehensive element-specific enrichment data from BPMN 2.0 specification
    ELEMENT_ENRICHMENT = {
        # ===== EVENTS =====
        'StartEvent': {
            'purpose': 'Indicates where a process begins. Triggers the start of a process instance.',
            'common_patterns': [
                'None Start Event - process starts immediately',
                'Message Start Event - triggered by incoming message',
                'Timer Start Event - triggered at specific time or interval',
                'Signal Start Event - triggered by signal broadcast',
                'Conditional Start Event - triggered when condition is met'
            ],
            'can_connect_from': [],
            'can_connect_to': ['SequenceFlow'],
            'constraints': [
                'Start Events must have no incoming Sequence Flows',
                'Start Events must have at least one outgoing Sequence Flow',
                'Only one None Start Event per Process (unless in Event Sub-Process)'
            ],
            'variants': ['None', 'Message', 'Timer', 'Signal', 'Conditional', 'Error', 'Escalation', 'Compensation', 'Multiple', 'Parallel Multiple']
        },
        'EndEvent': {
            'purpose': 'Indicates where a process path ends. Marks the completion of a process flow.',
            'common_patterns': [
                'None End Event - process completes normally',
                'Message End Event - sends message upon completion',
                'Error End Event - terminates with error',
                'Terminate End Event - terminates entire process instance',
                'Escalation End Event - triggers escalation'
            ],
            'can_connect_from': ['SequenceFlow'],
            'can_connect_to': [],
            'constraints': [
                'End Events must have at least one incoming Sequence Flow',
                'End Events cannot have outgoing Sequence Flows'
            ],
            'variants': ['None', 'Message', 'Error', 'Escalation', 'Cancel', 'Compensation', 'Signal', 'Terminate', 'Multiple']
        },
        'IntermediateCatchEvent': {
            'purpose': 'Represents a point where the process waits for a trigger before continuing.',
            'common_patterns': [
                'Message Intermediate Catch - wait for message',
                'Timer Intermediate Catch - wait for time/duration',
                'Signal Intermediate Catch - wait for signal',
                'Conditional Intermediate Catch - wait for condition to be true'
            ],
            'can_connect_from': ['SequenceFlow'],
            'can_connect_to': ['SequenceFlow'],
            'constraints': [
                'Must have exactly one incoming and one outgoing Sequence Flow',
                'Causes process to wait until event occurs'
            ],
            'variants': ['Message', 'Timer', 'Signal', 'Conditional', 'Link', 'Multiple', 'Parallel Multiple']
        },
        'IntermediateThrowEvent': {
            'purpose': 'Represents a point where the process generates or throws an event.',
            'common_patterns': [
                'Message Intermediate Throw - send message during flow',
                'Signal Intermediate Throw - broadcast signal',
                'Escalation Intermediate Throw - trigger escalation',
                'Link Intermediate Throw - go-to target for off-page connector'
            ],
            'can_connect_from': ['SequenceFlow'],
            'can_connect_to': ['SequenceFlow'],
            'constraints': [
                'Must have exactly one incoming and one outgoing Sequence Flow',
                'Does not interrupt the process flow'
            ],
            'variants': ['None', 'Message', 'Escalation', 'Signal', 'Compensation', 'Link', 'Multiple']
        },
        'BoundaryEvent': {
            'purpose': 'Attached to an activity boundary to handle exceptions or events during activity execution.',
            'common_patterns': [
                'Error Boundary Event - catch errors from activity',
                'Timer Boundary Event - timeout handling',
                'Message Boundary Event - receive message while activity executes',
                'Interrupting vs Non-interrupting behavior'
            ],
            'can_connect_from': [],
            'can_connect_to': ['SequenceFlow'],
            'constraints': [
                'Must be attached to the boundary of an Activity',
                'Cannot have incoming Sequence Flows',
                'Must have exactly one outgoing Sequence Flow',
                'Can be interrupting (cancels activity) or non-interrupting (activity continues)'
            ],
            'variants': ['Message', 'Timer', 'Error', 'Signal', 'Escalation', 'Conditional', 'Cancel', 'Compensation', 'Multiple', 'Parallel Multiple']
        },
        
        # ===== TASKS & ACTIVITIES =====
        'Task': {
            'purpose': 'Represents an atomic activity within a process. A unit of work to be performed.',
            'common_patterns': [
                'Generic task without specific type',
                'Placeholder for work that will be detailed later',
                'Work performed by a person or system'
            ],
            'can_connect_from': ['SequenceFlow', 'MessageFlow'],
            'can_connect_to': ['SequenceFlow', 'MessageFlow'],
            'constraints': [
                'Tasks must have at least one incoming and one outgoing Sequence Flow',
                'Tasks can have boundary events attached'
            ],
            'variants': ['Task', 'UserTask', 'ServiceTask', 'ScriptTask', 'ManualTask', 'BusinessRuleTask', 'SendTask', 'ReceiveTask']
        },
        'UserTask': {
            'purpose': 'A task performed by a human user with the help of a software application.',
            'common_patterns': [
                'Form filling and data entry',
                'Review and approval tasks',
                'Manual decision making',
                'Human interaction points in automated processes'
            ],
            'can_connect_from': ['SequenceFlow', 'MessageFlow'],
            'can_connect_to': ['SequenceFlow', 'MessageFlow'],
            'constraints': [
                'Typically assigned to a specific user or group',
                'May have associated forms or user interfaces',
                'Execution waits for human completion'
            ]
        },
        'ServiceTask': {
            'purpose': 'A task that uses a service (web service, automated application, etc.) to perform work.',
            'common_patterns': [
                'Calling REST APIs or web services',
                'Database operations',
                'System integrations',
                'Automated calculations or processing'
            ],
            'can_connect_from': ['SequenceFlow'],
            'can_connect_to': ['SequenceFlow'],
            'constraints': [
                'Executed automatically by the process engine',
                'Should specify implementation details (service endpoint, operation)',
                'No human interaction required'
            ]
        },
        'ScriptTask': {
            'purpose': 'A task that executes a script in a specified scripting language.',
            'common_patterns': [
                'Data transformation and manipulation',
                'Simple calculations',
                'Variable assignments',
                'Inline business logic'
            ],
            'can_connect_from': ['SequenceFlow'],
            'can_connect_to': ['SequenceFlow'],
            'constraints': [
                'Script language must be specified',
                'Executed by process engine',
                'Should be simple and stateless'
            ]
        },
        'ManualTask': {
            'purpose': 'A task performed by a human without the aid of any software application.',
            'common_patterns': [
                'Physical tasks (package assembly, shipping)',
                'Tasks outside the IT system',
                'Phone calls, meetings',
                'Manual approvals without system interaction'
            ],
            'can_connect_from': ['SequenceFlow'],
            'can_connect_to': ['SequenceFlow'],
            'constraints': [
                'Process engine does not track task execution',
                'Used for modeling purposes to show manual work'
            ]
        },
        'BusinessRuleTask': {
            'purpose': 'A task that executes business rules using a business rules engine.',
            'common_patterns': [
                'Decision making based on complex rules',
                'Policy evaluation',
                'Eligibility checks',
                'Risk assessment calculations'
            ],
            'can_connect_from': ['SequenceFlow'],
            'can_connect_to': ['SequenceFlow'],
            'constraints': [
                'Typically invokes a rules engine',
                'Rules should be externalized from process logic',
                'Executed automatically'
            ]
        },
        'SendTask': {
            'purpose': 'A task that sends a message to an external participant.',
            'common_patterns': [
                'Sending emails or notifications',
                'Posting messages to message queues',
                'Triggering external systems',
                'One-way message sending'
            ],
            'can_connect_from': ['SequenceFlow'],
            'can_connect_to': ['SequenceFlow'],
            'constraints': [
                'Sends message and continues immediately',
                'Does not wait for response',
                'Can be associated with Message Flow'
            ]
        },
        'ReceiveTask': {
            'purpose': 'A task that waits for an incoming message from an external participant.',
            'common_patterns': [
                'Waiting for email or message response',
                'Receiving from message queues',
                'Waiting for external system callback',
                'Asynchronous message reception'
            ],
            'can_connect_from': ['SequenceFlow', 'MessageFlow'],
            'can_connect_to': ['SequenceFlow'],
            'constraints': [
                'Process waits until message is received',
                'Message must match expected criteria',
                'Can be instantiating (starts process instance)'
            ]
        },
        'CallActivity': {
            'purpose': 'A task that calls and executes another process (reusable subprocess).',
            'common_patterns': [
                'Calling shared/reusable processes',
                'Process modularization',
                'Cross-process orchestration',
                'Global subprocess invocation'
            ],
            'can_connect_from': ['SequenceFlow'],
            'can_connect_to': ['SequenceFlow'],
            'constraints': [
                'References a separate process definition',
                'Can pass data in/out via parameters',
                'Creates new process instance for called process'
            ]
        },
        
        # ===== SUBPROCESSES =====
        'SubProcess': {
            'purpose': 'A compound activity containing other activities, gateways, events, and data.',
            'common_patterns': [
                'Collapsed subprocess - hides internal complexity',
                'Expanded subprocess - shows detailed flow',
                'Event subprocess - handles exceptions or events',
                'Reusable process components'
            ],
            'can_connect_from': ['SequenceFlow', 'MessageFlow'],
            'can_connect_to': ['SequenceFlow', 'MessageFlow'],
            'constraints': [
                'Must have at least one Start Event',
                'Must have at least one End Event',
                'Can have boundary events attached',
                'Contains complete valid process flow'
            ],
            'variants': ['Embedded', 'Event', 'Transaction', 'Ad-Hoc']
        },
        'EventSubProcess': {
            'purpose': 'A subprocess triggered by an event, used for exception handling or event-driven logic.',
            'common_patterns': [
                'Error handling subprocess',
                'Escalation handling',
                'Timer-based periodic tasks',
                'Message-triggered parallel flows'
            ],
            'can_connect_from': [],
            'can_connect_to': [],
            'constraints': [
                'Must have exactly one Start Event (no incoming flows)',
                'Start Event must be of specific event type (Message, Timer, Error, etc.)',
                'Can be interrupting or non-interrupting',
                'Cannot have incoming or outgoing Sequence Flows'
            ]
        },
        'Transaction': {
            'purpose': 'A specialized subprocess that groups activities into a transaction with commit/rollback semantics.',
            'common_patterns': [
                'Financial transactions',
                'Atomic operations requiring rollback capability',
                'Coordinated multi-party transactions',
                'Compensatable business transactions'
            ],
            'can_connect_from': ['SequenceFlow'],
            'can_connect_to': ['SequenceFlow'],
            'constraints': [
                'Supports cancel events for rollback',
                'All activities must complete or all rollback',
                'Can have compensation defined'
            ]
        },
        
        # ===== GATEWAYS =====
        'ExclusiveGateway': {
            'purpose': 'Creates alternative paths in the process flow. Only one path is taken based on conditions.',
            'common_patterns': [
                'If-then-else decision logic',
                'Switch/case branching',
                'Binary decisions (approved/rejected)',
                'Routing based on data values'
            ],
            'can_connect_from': ['SequenceFlow'],
            'can_connect_to': ['SequenceFlow'],
            'constraints': [
                'Exactly one outgoing path must be selected',
                'Should have a default path when used for splitting',
                'Conditions on outgoing flows must be mutually exclusive',
                'Evaluates conditions in order until one is true'
            ],
            'variants': ['Data-Based (XOR)', 'Event-Based']
        },
        'ParallelGateway': {
            'purpose': 'Splits the flow into concurrent paths or synchronizes concurrent paths.',
            'common_patterns': [
                'Fork - execute multiple activities in parallel',
                'Join - wait for all parallel activities to complete',
                'Fork-Join pattern - split and later merge parallel flows',
                'Concurrent task execution'
            ],
            'can_connect_from': ['SequenceFlow'],
            'can_connect_to': ['SequenceFlow'],
            'constraints': [
                'When splitting: activates all outgoing paths simultaneously',
                'When joining: waits for all incoming paths to complete',
                'No conditions on outgoing sequence flows',
                'All paths are always taken when splitting'
            ]
        },
        'InclusiveGateway': {
            'purpose': 'Allows activation of one or more paths based on conditions (inclusive OR).',
            'common_patterns': [
                'Multiple optional activities based on conditions',
                'Conditional parallel execution',
                'Variable number of parallel paths',
                'At least one path must be taken'
            ],
            'can_connect_from': ['SequenceFlow'],
            'can_connect_to': ['SequenceFlow'],
            'constraints': [
                'At least one outgoing path must be activated',
                'When joining: waits for all active incoming paths',
                'Evaluates all conditions (multiple can be true)',
                'More complex than Exclusive, use when needed'
            ]
        },
        'EventBasedGateway': {
            'purpose': 'Creates alternative paths based on events. Process continues on path of first event to occur.',
            'common_patterns': [
                'Wait for first of multiple possible messages',
                'Timeout handling (timer vs message race)',
                'Event-driven routing',
                'Responsive process patterns'
            ],
            'can_connect_from': ['SequenceFlow'],
            'can_connect_to': ['IntermediateCatchEvent', 'ReceiveTask'],
            'constraints': [
                'Must be followed by Intermediate Catch Events or Receive Tasks',
                'Only one event will trigger continuation',
                'Other paths are abandoned once one event occurs',
                'Cannot have conditions on outgoing flows'
            ],
            'variants': ['Exclusive', 'Parallel', 'Instantiating']
        },
        'ComplexGateway': {
            'purpose': 'Handles complex synchronization and branching scenarios using custom expressions.',
            'common_patterns': [
                'M out of N synchronization',
                'Custom merge conditions',
                'Complex decision logic that doesn\'t fit other gateways',
                'Advanced routing scenarios'
            ],
            'can_connect_from': ['SequenceFlow'],
            'can_connect_to': ['SequenceFlow'],
            'constraints': [
                'Uses activation condition expression',
                'Should only be used when other gateways are insufficient',
                'More difficult to understand - use sparingly'
            ]
        },
        
        # ===== CONNECTING OBJECTS =====
        'SequenceFlow': {
            'purpose': 'Defines the order of activities in a process. Shows the execution path.',
            'common_patterns': [
                'Unconditional flow between activities',
                'Conditional flow with expressions',
                'Default flow from gateways',
                'Normal process flow path'
            ],
            'can_connect_from': ['FlowNode', 'Activity', 'Gateway', 'Event'],
            'can_connect_to': ['FlowNode', 'Activity', 'Gateway', 'Event'],
            'constraints': [
                'Cannot cross pool boundaries',
                'Must connect flow objects within same pool/subprocess',
                'Can have conditions (except from Parallel Gateway)',
                'Exactly one source and one target'
            ]
        },
        'MessageFlow': {
            'purpose': 'Shows communication between different participants (pools) in a collaboration.',
            'common_patterns': [
                'Request-response patterns',
                'Notifications between organizations',
                'Cross-pool communication',
                'Message exchange between participants'
            ],
            'can_connect_from': ['InteractionNode', 'Activity', 'Event', 'Pool'],
            'can_connect_to': ['InteractionNode', 'Activity', 'Event', 'Pool'],
            'constraints': [
                'Must cross pool boundaries',
                'Cannot connect elements within the same pool',
                'Can connect to/from tasks, events, and pool boundaries',
                'Represents asynchronous communication'
            ]
        },
        'Association': {
            'purpose': 'Links artifacts (text annotations, data objects) to flow objects for documentation.',
            'common_patterns': [
                'Linking text annotations to elements',
                'Connecting data objects to activities',
                'Documentation and clarification',
                'Non-executable associations'
            ],
            'can_connect_from': ['FlowElement', 'Artifact'],
            'can_connect_to': ['FlowElement', 'Artifact'],
            'constraints': [
                'Does not affect process execution',
                'Used for documentation only',
                'Can be directional or non-directional'
            ]
        },
        'DataAssociation': {
            'purpose': 'Shows data flow between data objects and activities.',
            'common_patterns': [
                'Input data to activity (DataInputAssociation)',
                'Output data from activity (DataOutputAssociation)',
                'Data transformation',
                'Variable mapping'
            ],
            'can_connect_from': ['DataObject', 'DataStore', 'Property'],
            'can_connect_to': ['Activity', 'Event'],
            'constraints': [
                'Specifies which data is read or written',
                'Can include transformation expressions',
                'Direction matters (input vs output)'
            ]
        },
        
        # ===== SWIMLANES =====
        'Pool': {
            'purpose': 'Represents a participant in a collaboration. Contains the complete process for that participant.',
            'common_patterns': [
                'Different organizations in a process',
                'Customer vs Service Provider',
                'Department separation',
                'System vs Human participants'
            ],
            'can_connect_from': ['MessageFlow'],
            'can_connect_to': ['MessageFlow'],
            'constraints': [
                'Can only interact with other pools via Message Flows',
                'Sequence Flows cannot cross pool boundaries',
                'Represents independent process participant',
                'Can contain lanes for internal organization'
            ]
        },
        'Lane': {
            'purpose': 'Subdivides a pool to organize activities by role, responsibility, or department.',
            'common_patterns': [
                'Role-based organization (Manager, Employee, Customer Service)',
                'Department organization (Sales, Finance, HR)',
                'System vs Manual activity separation',
                'Functional responsibility areas'
            ],
            'can_connect_from': [],
            'can_connect_to': [],
            'constraints': [
                'Lanes exist within pools',
                'Sequence Flows can cross lane boundaries within same pool',
                'Used for organizational clarity',
                'Does not affect execution semantics'
            ]
        },
        'Participant': {
            'purpose': 'Represents an entity (person, system, organization) that participates in a collaboration.',
            'common_patterns': [
                'External systems',
                'Partner organizations',
                'Different business units',
                'Service providers and consumers'
            ],
            'can_connect_from': ['MessageFlow'],
            'can_connect_to': ['MessageFlow'],
            'constraints': [
                'Typically represented as a pool',
                'Communicates via Message Flows',
                'Can have its own internal process'
            ]
        },
        
        # ===== ARTIFACTS =====
        'DataObject': {
            'purpose': 'Represents information flowing through the process, such as documents or business data.',
            'common_patterns': [
                'Documents required as input',
                'Data produced as output',
                'Shared information between activities',
                'Business objects manipulated in the process'
            ],
            'can_connect_from': ['DataAssociation'],
            'can_connect_to': ['DataAssociation'],
            'constraints': [
                'Connected to activities via Data Associations',
                'Can have different states represented',
                'Shows lifecycle of data in process',
                'Not executable - for modeling only'
            ]
        },
        'DataStore': {
            'purpose': 'Represents a persistent data store (database, file system, etc.) accessed by the process.',
            'common_patterns': [
                'Database read/write operations',
                'Shared data repository',
                'Persistent storage',
                'Data lookup sources'
            ],
            'can_connect_from': ['DataAssociation'],
            'can_connect_to': ['DataAssociation'],
            'constraints': [
                'Data persists beyond process instance',
                'Multiple activities can access same store',
                'Can be read from or written to'
            ]
        },
        'TextAnnotation': {
            'purpose': 'Provides additional text information or comments about the process model.',
            'common_patterns': [
                'Explanatory notes on process elements',
                'Business rules documentation',
                'Clarifying complex logic',
                'Modeling guidelines and tips'
            ],
            'can_connect_from': ['Association'],
            'can_connect_to': [],
            'constraints': [
                'Does not affect process execution',
                'Purely for documentation',
                'Can be linked via Association'
            ]
        },
        'Group': {
            'purpose': 'Groups elements for documentation or categorization purposes without affecting execution.',
            'common_patterns': [
                'Logically grouping related activities',
                'Highlighting process phases',
                'Visual organization',
                'Documenting functional areas'
            ],
            'can_connect_from': [],
            'can_connect_to': [],
            'constraints': [
                'Does not affect process execution',
                'Purely visual grouping',
                'Can span multiple elements',
                'Cannot affect sequence flow'
            ]
        },
    }
    
    def enrich_element(self, element: Dict[str, Any]) -> Dict[str, Any]:
        """Add additional BPMN-specific context to parsed element"""
        elem_type = element['element_type']
        
        # Find matching enrichment data (case-insensitive, handle variations)
        enrichment = None
        
        # Try exact match first
        if elem_type in self.ELEMENT_ENRICHMENT:
            enrichment = self.ELEMENT_ENRICHMENT[elem_type]
        else:
            # Try case-insensitive match
            elem_lower = elem_type.lower()
            for key, value in self.ELEMENT_ENRICHMENT.items():
                if key.lower() == elem_lower:
                    enrichment = value
                    break
            
            # Try partial match for variations (e.g., 'startEvent' matches 'StartEvent')
            if not enrichment:
                for key, value in self.ELEMENT_ENRICHMENT.items():
                    key_lower = key.lower()
                    if key_lower in elem_lower or elem_lower in key_lower:
                        # Be careful with short names - require substantial overlap
                        if len(key_lower) > 4 and len(elem_lower) > 4:
                            enrichment = value
                            break
        
        if enrichment:
            # Only override if not already populated
            if not element.get('purpose'):
                element['purpose'] = enrichment.get('purpose', '')
            if not element.get('common_patterns'):
                element['common_patterns'] = enrichment.get('common_patterns', [])
            if not element.get('can_connect_from'):
                element['can_connect_from'] = enrichment.get('can_connect_from', [])
            if not element.get('can_connect_to'):
                element['can_connect_to'] = enrichment.get('can_connect_to', [])
            if not element.get('constraints'):
                element['constraints'] = enrichment.get('constraints', [])
            if not element.get('variants'):
                element['variants'] = enrichment.get('variants', [])
            
            # Enhance description if empty or too short
            if not element['description'] or len(element['description']) < 50:
                if enrichment.get('purpose'):
                    element['description'] = enrichment['purpose']
        
        return element


class BPMNDatasetGenerator:
    """Generate training datasets in various formats"""
    
    def __init__(self, elements: List[Dict[str, Any]]):
        self.elements = elements
    
    def generate_natural_language_format(self) -> List[Dict[str, Any]]:
        """Generate natural language training examples"""
        dataset = []
        
        for elem in self.elements:
            text_parts = []
            
            # Main description
            text_parts.append(f"A {elem['element_type']} is a BPMN element in the {elem['category']} category.")
            
            if elem.get('subcategory'):
                text_parts.append(f"Specifically, it is a {elem['subcategory']}.")
            
            if elem['description']:
                text_parts.append(f"{elem['description']}")
            
            # Purpose
            if elem.get('purpose'):
                text_parts.append(f"\nPurpose: {elem['purpose']}")
            
            # Attributes
            if elem['attributes']:
                text_parts.append("\nKey attributes:")
                for attr in elem['attributes'][:5]:  # Limit to first 5
                    required = "required" if attr.get('required') else "optional"
                    text_parts.append(f"- {attr['name']} ({required}, type: {attr['type']})")
            
            # Connections
            if elem.get('can_connect_from'):
                text_parts.append(f"\nCan receive connections from: {', '.join(elem['can_connect_from'])}")
            if elem.get('can_connect_to'):
                text_parts.append(f"Can connect to: {', '.join(elem['can_connect_to'])}")
            
            # Common patterns
            if elem.get('common_patterns'):
                text_parts.append("\nCommon usage patterns:")
                for pattern in elem['common_patterns']:
                    text_parts.append(f"- {pattern}")
            
            # Constraints
            if elem.get('constraints'):
                text_parts.append("\nKey constraints:")
                for constraint in elem['constraints']:
                    text_parts.append(f"- {constraint}")
            
            # Variants
            if elem.get('variants'):
                text_parts.append(f"\nVariants: {', '.join(elem['variants'])}")
            
            # XML Example
            if elem.get('xml_example'):
                text_parts.append(f"\nXML Example: {elem['xml_example']}")
            
            dataset.append({
                'text': ' '.join(text_parts),
                'element_type': elem['element_type'],
                'category': elem['category'],
                'subcategory': elem.get('subcategory', '')
            })
        
        return dataset
    
    def generate_qa_pairs(self) -> List[Dict[str, Any]]:
        """Generate question-answer training pairs"""
        qa_pairs = []
        
        for elem in self.elements:
            elem_type = elem['element_type']
            
            # What is X?
            if elem['description']:
                qa_pairs.append({
                    'instruction': f"What is a {elem_type} in BPMN?",
                    'input': '',
                    'output': elem['description']
                })
            
            # What category?
            qa_pairs.append({
                'instruction': f"What category does {elem_type} belong to in BPMN?",
                'input': '',
                'output': f"{elem_type} belongs to the {elem['category']} category."
            })
            
            # When to use X?
            if elem.get('purpose'):
                qa_pairs.append({
                    'instruction': f"When should I use a {elem_type} in my BPMN process?",
                    'input': '',
                    'output': elem['purpose']
                })
            
            # What are the attributes of X?
            if elem['attributes']:
                attr_list = []
                for attr in elem['attributes'][:5]:
                    req_text = "required" if attr.get('required') else "optional"
                    attr_list.append(f"{attr['name']} ({req_text}, {attr['type']})")
                
                qa_pairs.append({
                    'instruction': f"What are the main attributes of a {elem_type}?",
                    'input': '',
                    'output': f"A {elem_type} has the following attributes: {', '.join(attr_list)}"
                })
            
            # What can connect to X?
            if elem.get('can_connect_to'):
                qa_pairs.append({
                    'instruction': f"What BPMN elements can a {elem_type} connect to?",
                    'input': '',
                    'output': f"A {elem_type} can connect to: {', '.join(elem['can_connect_to'])}"
                })
            
            # What can connect from X?
            if elem.get('can_connect_from'):
                qa_pairs.append({
                    'instruction': f"What elements can connect to a {elem_type}?",
                    'input': '',
                    'output': f"The following elements can connect to a {elem_type}: {', '.join(elem['can_connect_from'])}"
                })
            
            # Common patterns
            if elem.get('common_patterns'):
                pattern_text = '\n'.join([f"{i+1}. {p}" for i, p in enumerate(elem['common_patterns'])])
                qa_pairs.append({
                    'instruction': f"What are common usage patterns for {elem_type}?",
                    'input': '',
                    'output': f"Common patterns for {elem_type} include:\n{pattern_text}"
                })
            
            # Constraints
            if elem.get('constraints'):
                constraint_text = '\n'.join([f"- {c}" for c in elem['constraints']])
                qa_pairs.append({
                    'instruction': f"What are the constraints or rules for using {elem_type}?",
                    'input': '',
                    'output': f"Constraints for {elem_type}:\n{constraint_text}"
                })
            
            # XML example
            if elem.get('xml_example'):
                qa_pairs.append({
                    'instruction': f"Show me an XML example of {elem_type}",
                    'input': '',
                    'output': elem['xml_example']
                })
        
        return qa_pairs
    
    def generate_comparison_pairs(self) -> List[Dict[str, Any]]:
        """Generate comparison questions between similar elements"""
        comparisons = []
        
        # Group elements by category
        by_category = {}
        for elem in self.elements:
            category = elem['category']
            if category not in by_category:
                by_category[category] = []
            by_category[category].append(elem)
        
        # Generate comparisons within categories
        for category, elements in by_category.items():
            if len(elements) >= 2:
                for i, elem1 in enumerate(elements):
                    for elem2 in elements[i+1:i+3]:  # Compare with next 2 elements
                        comparison = self._compare_elements(elem1, elem2)
                        if comparison:
                            comparisons.append(comparison)
        
        return comparisons
    
    def _compare_elements(self, elem1: Dict[str, Any], elem2: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Compare two BPMN elements"""
        name1 = elem1['element_type']
        name2 = elem2['element_type']
        
        differences = []
        similarities = []
        
        # Purpose comparison
        if elem1.get('purpose') and elem2.get('purpose'):
            differences.append(f"{name1}: {elem1['purpose']} vs {name2}: {elem2['purpose']}")
        
        # Category
        if elem1['category'] == elem2['category']:
            similarities.append(f"Both are {elem1['category']}s")
        
        # Connection capabilities
        can_connect_to_1 = set(elem1.get('can_connect_to', []))
        can_connect_to_2 = set(elem2.get('can_connect_to', []))
        
        if can_connect_to_1 == can_connect_to_2 and can_connect_to_1:
            similarities.append(f"Both can connect to: {', '.join(can_connect_to_1)}")
        elif can_connect_to_1 != can_connect_to_2:
            differences.append(f"Connection capabilities differ")
        
        if not differences and not similarities:
            return None
        
        return {
            'instruction': f"What is the difference between {name1} and {name2} in BPMN?",
            'input': '',
            'output': f"Similarities: {' '.join(similarities) if similarities else 'None'}. Differences: {' '.join(differences) if differences else 'None'}",
            'element1': name1,
            'element2': name2
        }
    
    def save_to_jsonl(self, data: List[Dict[str, Any]], filename: str):
        """Save data to JSONL format"""
        output_path = Path(filename)
        with output_path.open('w', encoding='utf-8') as f:
            for item in data:
                f.write(json.dumps(item, ensure_ascii=False) + '\n')
        print(f"Saved {len(data)} items to {filename}")
    
    def save_structured_json(self, filename: str):
        """Save structured element data as JSON"""
        output_path = Path(filename)
        with output_path.open('w', encoding='utf-8') as f:
            json.dump(self.elements, f, indent=2, ensure_ascii=False)
        print(f"Saved {len(self.elements)} elements to {filename}")


def main():
    """Main execution function"""
    print("=" * 60)
    print("BPMN 2.0 Specification Scraper")
    print("Scraping from Official OMG BPMN Specification")
    print("=" * 60)
    
    # Parse XSD Schemas
    parser = BPMNSchemaParser()
    try:
        elements = parser.fetch_all_schemas()
        print(f"\nExtracted {len(elements)} elements from XSD schemas")
    except Exception as e:
        print(f"Error downloading/parsing schemas: {e}")
        print("Falling back to minimal element set...")
        elements = []
    
    # Enrich elements with additional BPMN context
    enricher = BPMNElementEnricher()
    enriched_elements = [enricher.enrich_element(elem) for elem in elements]
    
    # If we couldn't scrape, create minimal set from enrichment data
    if len(enriched_elements) == 0:
        print("\nCreating dataset from BPMN knowledge base...")
        for elem_name, enrichment in enricher.ELEMENT_ENRICHMENT.items():
            elem_data = {
                'element_type': elem_name,
                'category': '',
                'subcategory': '',
                'attributes': [],
                'description': enrichment.get('purpose', ''),
                'xml_example': '',
                'constraints': enrichment.get('constraints', []),
                'parent_elements': [],
                'child_elements': [],
                'can_connect_from': enrichment.get('can_connect_from', []),
                'can_connect_to': enrichment.get('can_connect_to', []),
                'common_patterns': enrichment.get('common_patterns', []),
                'purpose': enrichment.get('purpose', ''),
                'variants': enrichment.get('variants', [])
            }
            enriched_elements.append(elem_data)
    
    print(f"Final dataset contains {len(enriched_elements)} enriched elements")
    
    # Generate datasets
    generator = BPMNDatasetGenerator(enriched_elements)
    
    # Create output directory
    output_dir = Path('bpmn_training_data')
    output_dir.mkdir(exist_ok=True)
    
    # Save in different formats
    print("\nGenerating training datasets...")
    
    # 1. Structured JSON
    generator.save_structured_json(output_dir / 'bpmn_elements_structured.json')
    
    # 2. Natural language format (JSONL)
    nl_data = generator.generate_natural_language_format()
    generator.save_to_jsonl(nl_data, output_dir / 'bpmn_natural_language.jsonl')
    
    # 3. Q&A pairs (JSONL)
    qa_data = generator.generate_qa_pairs()
    generator.save_to_jsonl(qa_data, output_dir / 'bpmn_qa_pairs.jsonl')
    
    # 4. Comparison pairs (JSONL)
    comparison_data = generator.generate_comparison_pairs()
    generator.save_to_jsonl(comparison_data, output_dir / 'bpmn_comparisons.jsonl')
    
    print("\n" + "=" * 60)
    print("Dataset generation complete!")
    print(f"Output directory: {output_dir.absolute()}")
    print("=" * 60)
    
    # Print samples
    print("\n📝 Sample Natural Language Entry:")
    print("-" * 60)
    if nl_data:
        sample = nl_data[0]['text']
        print(sample[:400] + "..." if len(sample) > 400 else sample)
    
    print("\n❓ Sample Q&A Pair:")
    print("-" * 60)
    if qa_data:
        print(f"Q: {qa_data[0]['instruction']}")
        print(f"A: {qa_data[0]['output']}")
    
    print("\n🔄 Sample Comparison:")
    print("-" * 60)
    if comparison_data:
        print(f"Q: {comparison_data[0]['instruction']}")
        print(f"A: {comparison_data[0]['output'][:200]}...")
    
    print("\n✅ All training data files generated successfully!")


if __name__ == "__main__":
    main()
