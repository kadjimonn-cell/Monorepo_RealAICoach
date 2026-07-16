"""
Test Workflow Builder Phase 2 - Action Node Types

Tests 8 new action types:
1. transform_json - JSON transformation using JSONPath
2. filter_array - Array filtering/mapping/reducing
3. parse_text - Text parsing with regex
4. condition - Conditional branching
5. loop - Loop iteration
6. ai_chat - AI chat completion
7. ai_image_gen - AI image generation
8. send_email - Email sending (SKIPPED - requires RESEND_API_KEY)
"""

import os
import time
import uuid

import pytest
import requests


# ── Test Configuration ──

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://127.0.0.1:8001")
API_BASE = f"{BASE_URL}/api"

# Generate unique guest user ID for this test run
GUEST_USER_ID = f"user_workflow_phase2_{uuid.uuid4().hex[:12]}"


# ── Helper Functions ──


def create_workflow(name: str, nodes: list, edges: list = None) -> dict:
    """Create a workflow and return the workflow_id."""
    if edges is None:
        edges = []
    
    response = requests.post(
        f"{API_BASE}/workflows",
        json={
            "name": name,
            "description": f"Test workflow for {name}",
            "nodes": nodes,
            "edges": edges,
            "enabled": True,
            "fallback_user_id": GUEST_USER_ID,
        },
        timeout=10,
    )
    
    assert response.status_code == 200, f"Failed to create workflow: {response.text}"
    data = response.json()
    return data["workflow_id"]


def execute_workflow(workflow_id: str, input_data: dict = None) -> dict:
    """Execute a workflow and return the execution result."""
    if input_data is None:
        input_data = {}
    
    response = requests.post(
        f"{API_BASE}/workflows/{workflow_id}/execute",
        json={
            "input_data": input_data,
            "fallback_user_id": GUEST_USER_ID,
        },
        timeout=30,
    )
    
    assert response.status_code == 200, f"Failed to execute workflow: {response.text}"
    return response.json()


def get_node_result(execution: dict, node_id: str) -> dict:
    """Extract node result from execution."""
    node_results = execution.get("node_results", {})
    assert node_id in node_results, f"Node {node_id} not found in results"
    return node_results[node_id]


# ── Priority 1: Data Operations (Fast Tests) ──


def test_transform_json():
    """Test transform_json action - Extract data using JSONPath."""
    # Create workflow with transform_json action
    nodes = [
        {
            "node_id": "trigger_1",
            "type": "trigger",
            "action": "manual",
            "label": "Manual Trigger",
            "config": {},
        },
        {
            "node_id": "action_1",
            "type": "action",
            "action": "transform_json",
            "label": "Transform JSON",
            "config": {
                "source_key": "data",
                "json_path": "$.user.name",
                "output_key": "username",
            },
        },
    ]
    
    workflow_id = create_workflow("test_transform_json", nodes)
    
    # Execute with test data
    input_data = {
        "data": {
            "user": {
                "name": "Alice",
                "age": 30,
            }
        }
    }
    
    execution = execute_workflow(workflow_id, input_data)
    
    # Verify execution
    assert execution["status"] == "completed", f"Execution failed: {execution.get('error')}"
    
    # Verify node result
    result = get_node_result(execution, "action_1")
    assert result["status"] == "success", f"Node failed: {result.get('error')}"
    assert result["output"]["username"] == "Alice", f"Expected 'Alice', got {result['output']}"
    assert result["duration_ms"] < 3000, f"Execution too slow: {result['duration_ms']}ms"
    
    print(f"✅ transform_json: Extracted 'Alice' in {result['duration_ms']}ms")


def test_filter_array():
    """Test filter_array action - Filter array with condition."""
    nodes = [
        {
            "node_id": "trigger_1",
            "type": "trigger",
            "action": "manual",
            "label": "Manual Trigger",
            "config": {},
        },
        {
            "node_id": "action_1",
            "type": "action",
            "action": "filter_array",
            "label": "Filter Array",
            "config": {
                "source_key": "items",
                "operation": "filter",
                "condition": "item > 3",
                "output_key": "filtered",
            },
        },
    ]
    
    workflow_id = create_workflow("test_filter_array", nodes)
    
    # Execute with test data
    input_data = {
        "items": [1, 2, 3, 4, 5, 6]
    }
    
    execution = execute_workflow(workflow_id, input_data)
    
    # Verify execution
    assert execution["status"] == "completed", f"Execution failed: {execution.get('error')}"
    
    # Verify node result
    result = get_node_result(execution, "action_1")
    assert result["status"] == "success", f"Node failed: {result.get('error')}"
    assert result["output"]["filtered"] == [4, 5, 6], f"Expected [4, 5, 6], got {result['output']['filtered']}"
    assert result["duration_ms"] < 3000, f"Execution too slow: {result['duration_ms']}ms"
    
    print(f"✅ filter_array: Filtered to [4, 5, 6] in {result['duration_ms']}ms")


def test_parse_text():
    """Test parse_text action - Extract emails using regex."""
    nodes = [
        {
            "node_id": "trigger_1",
            "type": "trigger",
            "action": "manual",
            "label": "Manual Trigger",
            "config": {},
        },
        {
            "node_id": "action_1",
            "type": "action",
            "action": "parse_text",
            "label": "Parse Text",
            "config": {
                "source_key": "text",
                "pattern": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
                "output_key": "emails",
            },
        },
    ]
    
    workflow_id = create_workflow("test_parse_text", nodes)
    
    # Execute with test data
    input_data = {
        "text": "Contact: john@example.com and jane@test.org"
    }
    
    execution = execute_workflow(workflow_id, input_data)
    
    # Verify execution
    assert execution["status"] == "completed", f"Execution failed: {execution.get('error')}"
    
    # Verify node result
    result = get_node_result(execution, "action_1")
    assert result["status"] == "success", f"Node failed: {result.get('error')}"
    
    # Check that both emails were extracted
    emails = result["output"]["emails"]
    assert isinstance(emails, list), f"Expected list, got {type(emails)}"
    assert len(emails) == 2, f"Expected 2 emails, got {len(emails)}"
    assert "john@example.com" in emails, f"Expected 'john@example.com' in {emails}"
    assert "jane@test.org" in emails, f"Expected 'jane@test.org' in {emails}"
    assert result["duration_ms"] < 3000, f"Execution too slow: {result['duration_ms']}ms"
    
    print(f"✅ parse_text: Extracted 2 emails in {result['duration_ms']}ms")


def test_condition():
    """Test condition action - Conditional branching."""
    nodes = [
        {
            "node_id": "trigger_1",
            "type": "trigger",
            "action": "manual",
            "label": "Manual Trigger",
            "config": {},
        },
        {
            "node_id": "action_1",
            "type": "action",
            "action": "condition",
            "label": "Condition",
            "config": {
                "condition": "temperature > 20",
                "then": "warm",
                "else": "cold",
            },
        },
    ]
    
    workflow_id = create_workflow("test_condition", nodes)
    
    # Execute with test data
    input_data = {
        "temperature": 25
    }
    
    execution = execute_workflow(workflow_id, input_data)
    
    # Verify execution
    assert execution["status"] == "completed", f"Execution failed: {execution.get('error')}"
    
    # Verify node result
    result = get_node_result(execution, "action_1")
    assert result["status"] == "success", f"Node failed: {result.get('error')}"
    assert result["output"]["branch_taken"] == "then", f"Expected 'then', got {result['output']['branch_taken']}"
    assert result["output"]["output"] == "warm", f"Expected 'warm', got {result['output']['output']}"
    assert result["duration_ms"] < 3000, f"Execution too slow: {result['duration_ms']}ms"
    
    print(f"✅ condition: Branch 'then' taken, output 'warm' in {result['duration_ms']}ms")


def test_loop():
    """Test loop action - Iterate over array."""
    nodes = [
        {
            "node_id": "trigger_1",
            "type": "trigger",
            "action": "manual",
            "label": "Manual Trigger",
            "config": {},
        },
        {
            "node_id": "action_1",
            "type": "action",
            "action": "loop",
            "label": "Loop",
            "config": {
                "source_key": "colors",
                "max_iterations": 10,
            },
        },
    ]
    
    workflow_id = create_workflow("test_loop", nodes)
    
    # Execute with test data
    input_data = {
        "colors": ["red", "green", "blue"]
    }
    
    execution = execute_workflow(workflow_id, input_data)
    
    # Verify execution
    assert execution["status"] == "completed", f"Execution failed: {execution.get('error')}"
    
    # Verify node result
    result = get_node_result(execution, "action_1")
    assert result["status"] == "success", f"Node failed: {result.get('error')}"
    assert result["output"]["total_iterations"] == 3, f"Expected 3 iterations, got {result['output']['total_iterations']}"
    
    # Verify iterations
    iterations = result["output"]["iterations"]
    assert len(iterations) == 3, f"Expected 3 iterations, got {len(iterations)}"
    assert iterations[0]["index"] == 0 and iterations[0]["item"] == "red"
    assert iterations[1]["index"] == 1 and iterations[1]["item"] == "green"
    assert iterations[2]["index"] == 2 and iterations[2]["item"] == "blue"
    assert result["duration_ms"] < 3000, f"Execution too slow: {result['duration_ms']}ms"
    
    print(f"✅ loop: 3 iterations completed in {result['duration_ms']}ms")


# ── Priority 2: AI Operations (Slower Tests) ──


def test_ai_chat():
    """Test ai_chat action - AI chat completion."""
    nodes = [
        {
            "node_id": "trigger_1",
            "type": "trigger",
            "action": "manual",
            "label": "Manual Trigger",
            "config": {},
        },
        {
            "node_id": "action_1",
            "type": "action",
            "action": "ai_chat",
            "label": "AI Chat",
            "config": {
                "provider": "anthropic",
                "model": "claude-sonnet-4",
                "messages": [
                    {
                        "role": "user",
                        "content": "Say only the word: WORKING"
                    }
                ],
            },
        },
    ]
    
    workflow_id = create_workflow("test_ai_chat", nodes)
    
    # Execute
    execution = execute_workflow(workflow_id, {})
    
    # Verify execution
    assert execution["status"] == "completed", f"Execution failed: {execution.get('error')}"
    
    # Verify node result
    result = get_node_result(execution, "action_1")
    assert result["status"] == "success", f"Node failed: {result.get('error')}"
    
    # Check response contains "WORKING"
    response = result["output"]["response"]
    assert "WORKING" in response.upper(), f"Expected 'WORKING' in response, got: {response}"
    assert result["duration_ms"] < 15000, f"Execution too slow: {result['duration_ms']}ms"
    
    print(f"✅ ai_chat: Response contains 'WORKING' in {result['duration_ms']}ms")


def test_ai_image_generation():
    """Test ai_image_gen action - AI image generation."""
    nodes = [
        {
            "node_id": "trigger_1",
            "type": "trigger",
            "action": "manual",
            "label": "Manual Trigger",
            "config": {},
        },
        {
            "node_id": "action_1",
            "type": "action",
            "action": "ai_image_gen",
            "label": "AI Image Generation",
            "config": {
                "model": "nano-banana",
                "prompt": "A red circle",
            },
        },
    ]
    
    workflow_id = create_workflow("test_ai_image_gen", nodes)
    
    # Execute
    execution = execute_workflow(workflow_id, {})
    
    # Verify execution
    assert execution["status"] == "completed", f"Execution failed: {execution.get('error')}"
    
    # Verify node result
    result = get_node_result(execution, "action_1")
    assert result["status"] == "success", f"Node failed: {result.get('error')}"
    
    # Check image_url field exists
    assert "image_url" in result["output"], f"Expected 'image_url' in output, got: {result['output']}"
    assert result["output"]["image_url"], "Expected non-empty image_url"
    assert result["duration_ms"] < 20000, f"Execution too slow: {result['duration_ms']}ms"
    
    print(f"✅ ai_image_gen: Image generated in {result['duration_ms']}ms")


# ── Skip send_email (requires RESEND_API_KEY) ──


@pytest.mark.skip(reason="Requires RESEND_API_KEY configuration")
def test_send_email():
    """Test send_email action - Email sending (SKIPPED)."""
    pass


# ── Test Summary ──


if __name__ == "__main__":
    print("\n" + "="*60)
    print("Workflow Builder Phase 2 - Action Node Types Test")
    print("="*60)
    print(f"Backend URL: {BASE_URL}")
    print(f"Guest User ID: {GUEST_USER_ID}")
    print("="*60 + "\n")
    
    print("Priority 1: Data Operations (Fast Tests)")
    print("-" * 60)
    
    try:
        test_transform_json()
    except Exception as e:
        print(f"❌ transform_json: {e}")
    
    try:
        test_filter_array()
    except Exception as e:
        print(f"❌ filter_array: {e}")
    
    try:
        test_parse_text()
    except Exception as e:
        print(f"❌ parse_text: {e}")
    
    try:
        test_condition()
    except Exception as e:
        print(f"❌ condition: {e}")
    
    try:
        test_loop()
    except Exception as e:
        print(f"❌ loop: {e}")
    
    print("\n" + "Priority 2: AI Operations (Slower Tests)")
    print("-" * 60)
    
    try:
        test_ai_chat()
    except Exception as e:
        print(f"❌ ai_chat: {e}")
    
    try:
        test_ai_image_generation()
    except Exception as e:
        print(f"❌ ai_image_generation: {e}")
    
    print("\n" + "="*60)
    print("Test Summary: 7 action types tested (send_email skipped)")
    print("="*60 + "\n")
