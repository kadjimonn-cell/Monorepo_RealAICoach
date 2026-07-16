"""
Feature 4 Workflow Actions Test - Model Alias Normalization and Execution

Tests:
1. POST /api/workflows creates workflows successfully
2. POST /api/workflows/{id}/execute succeeds for ai_chat action with claude-sonnet-4
3. POST /api/workflows/{id}/execute succeeds for ai_image_gen action with nano-banana
4. No UTF-8 serialization crash in image action outputs
5. GET /api/workflows/usage/stats works with fallback_user_id
"""

import os
import uuid
import pytest
import requests

# Test Configuration
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://coach-web-preview.preview.emergentagent.com")
API_BASE = f"{BASE_URL}/api"

# Generate unique guest user ID for this test run
GUEST_USER_ID = f"user_feature4_test_{uuid.uuid4().hex[:12]}"


class TestWorkflowUsageStats:
    """Test GET /api/workflows/usage/stats with fallback_user_id"""
    
    def test_usage_stats_with_fallback_user_id(self):
        """Test that usage stats endpoint works with fallback_user_id"""
        response = requests.get(
            f"{API_BASE}/workflows/usage/stats",
            params={"fallback_user_id": GUEST_USER_ID},
            timeout=10,
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "workflow_count" in data, "Missing workflow_count"
        assert "workflow_limit" in data, "Missing workflow_limit"
        assert "executions_this_month" in data, "Missing executions_this_month"
        assert "execution_limit" in data, "Missing execution_limit"
        assert "tier" in data, "Missing tier"
        assert "can_create_workflow" in data, "Missing can_create_workflow"
        assert "can_execute" in data, "Missing can_execute"
        
        print(f"✅ Usage stats: tier={data['tier']}, workflows={data['workflow_count']}/{data['workflow_limit']}")


class TestWorkflowCreation:
    """Test POST /api/workflows creates workflows successfully"""
    
    def test_create_workflow_success(self):
        """Test creating a basic workflow"""
        response = requests.post(
            f"{API_BASE}/workflows",
            json={
                "name": f"TEST_Feature4_Workflow_{uuid.uuid4().hex[:8]}",
                "description": "Test workflow for Feature 4 validation",
                "nodes": [
                    {
                        "node_id": "trigger_1",
                        "type": "trigger",
                        "action": "manual",
                        "label": "Manual Trigger",
                        "config": {},
                    }
                ],
                "edges": [],
                "enabled": True,
                "fallback_user_id": GUEST_USER_ID,
            },
            timeout=10,
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert "workflow_id" in data, "Missing workflow_id in response"
        assert data["name"].startswith("TEST_Feature4_Workflow_"), "Workflow name mismatch"
        assert data["enabled"] is True, "Workflow should be enabled"
        
        print(f"✅ Workflow created: {data['workflow_id']}")
        return data["workflow_id"]


class TestAIChatExecution:
    """Test ai_chat action execution with claude-sonnet-4 model alias"""
    
    def test_ai_chat_with_claude_sonnet_4(self):
        """Test ai_chat action with claude-sonnet-4 model alias"""
        # Create workflow with ai_chat node
        workflow_response = requests.post(
            f"{API_BASE}/workflows",
            json={
                "name": f"TEST_AIChatClaude_{uuid.uuid4().hex[:8]}",
                "description": "Test ai_chat with claude-sonnet-4",
                "nodes": [
                    {
                        "node_id": "trigger_1",
                        "type": "trigger",
                        "action": "manual",
                        "label": "Manual Trigger",
                        "config": {},
                    },
                    {
                        "node_id": "ai_chat_1",
                        "type": "action",
                        "action": "ai_chat",
                        "label": "AI Chat Claude",
                        "config": {
                            "provider": "anthropic",
                            "model": "claude-sonnet-4",
                            "messages": [
                                {"role": "user", "content": "Say only the word: VERIFIED"}
                            ],
                            "system_message": "You are a test assistant.",
                        },
                    },
                ],
                "edges": [],
                "enabled": True,
                "fallback_user_id": GUEST_USER_ID,
            },
            timeout=10,
        )
        
        assert workflow_response.status_code == 200, f"Failed to create workflow: {workflow_response.text}"
        workflow_id = workflow_response.json()["workflow_id"]
        
        # Execute workflow
        exec_response = requests.post(
            f"{API_BASE}/workflows/{workflow_id}/execute",
            json={
                "input_data": {},
                "fallback_user_id": GUEST_USER_ID,
            },
            timeout=30,
        )
        
        assert exec_response.status_code == 200, f"Execution failed: {exec_response.text}"
        execution = exec_response.json()
        
        # Verify execution completed
        assert execution["status"] == "completed", f"Execution status: {execution['status']}, error: {execution.get('error')}"
        
        # Verify ai_chat node result
        node_results = execution.get("node_results", {})
        assert "ai_chat_1" in node_results, "ai_chat_1 node result missing"
        
        ai_chat_result = node_results["ai_chat_1"]
        assert ai_chat_result["status"] == "success", f"ai_chat failed: {ai_chat_result.get('error')}"
        
        # Verify response contains expected content
        output = ai_chat_result.get("output", {})
        assert "response" in output, "Missing response in ai_chat output"
        assert "VERIFIED" in output["response"].upper(), f"Expected 'VERIFIED' in response: {output['response']}"
        
        # Verify model was normalized correctly
        assert "model" in output, "Missing model in output"
        assert "anthropic" in output["model"].lower() or "claude" in output["model"].lower(), f"Model not normalized: {output['model']}"
        
        print(f"✅ ai_chat with claude-sonnet-4 succeeded: {output['response'][:50]}...")


class TestAIImageGenExecution:
    """Test ai_image_gen action execution with nano-banana model alias"""
    
    def test_ai_image_gen_with_nano_banana(self):
        """Test ai_image_gen action with nano-banana model alias"""
        # Create workflow with ai_image_gen node
        workflow_response = requests.post(
            f"{API_BASE}/workflows",
            json={
                "name": f"TEST_AIImageNanoBanana_{uuid.uuid4().hex[:8]}",
                "description": "Test ai_image_gen with nano-banana",
                "nodes": [
                    {
                        "node_id": "trigger_1",
                        "type": "trigger",
                        "action": "manual",
                        "label": "Manual Trigger",
                        "config": {},
                    },
                    {
                        "node_id": "ai_image_1",
                        "type": "action",
                        "action": "ai_image_gen",
                        "label": "AI Image Generation",
                        "config": {
                            "model": "nano-banana",
                            "prompt": "A simple red circle on white background",
                        },
                    },
                ],
                "edges": [],
                "enabled": True,
                "fallback_user_id": GUEST_USER_ID,
            },
            timeout=10,
        )
        
        assert workflow_response.status_code == 200, f"Failed to create workflow: {workflow_response.text}"
        workflow_id = workflow_response.json()["workflow_id"]
        
        # Execute workflow
        exec_response = requests.post(
            f"{API_BASE}/workflows/{workflow_id}/execute",
            json={
                "input_data": {},
                "fallback_user_id": GUEST_USER_ID,
            },
            timeout=60,  # Image generation can take longer
        )
        
        assert exec_response.status_code == 200, f"Execution failed: {exec_response.text}"
        execution = exec_response.json()
        
        # Verify execution completed
        assert execution["status"] == "completed", f"Execution status: {execution['status']}, error: {execution.get('error')}"
        
        # Verify ai_image_gen node result
        node_results = execution.get("node_results", {})
        assert "ai_image_1" in node_results, "ai_image_1 node result missing"
        
        ai_image_result = node_results["ai_image_1"]
        assert ai_image_result["status"] == "success", f"ai_image_gen failed: {ai_image_result.get('error')}"
        
        # Verify output structure
        output = ai_image_result.get("output", {})
        assert "image_url" in output, "Missing image_url in ai_image_gen output"
        assert output["image_url"], "image_url is empty"
        
        # Verify no UTF-8 serialization crash (image_url should be a string, not bytes)
        assert isinstance(output["image_url"], str), f"image_url should be string, got {type(output['image_url'])}"
        
        # Verify model was normalized correctly
        assert "model" in output, "Missing model in output"
        assert output["model"] == "gpt-image-1", f"Model not normalized: {output['model']}"
        
        # Verify images array exists and is properly serialized
        if "images" in output:
            assert isinstance(output["images"], list), "images should be a list"
            for img in output["images"]:
                assert isinstance(img, str), f"Image should be string, got {type(img)}"
        
        print(f"✅ ai_image_gen with nano-banana succeeded: image_url={output['image_url'][:50]}...")


class TestModelNormalization:
    """Test model alias normalization helpers"""
    
    def test_ai_chat_model_aliases(self):
        """Test various model aliases for ai_chat"""
        test_cases = [
            ("claude-sonnet-4", "anthropic"),
            ("gpt-4o", "openai"),
            ("gpt-4o-mini", "openai"),
        ]
        
        for model_alias, expected_provider in test_cases:
            workflow_response = requests.post(
                f"{API_BASE}/workflows",
                json={
                    "name": f"TEST_ModelAlias_{model_alias}_{uuid.uuid4().hex[:6]}",
                    "description": f"Test model alias: {model_alias}",
                    "nodes": [
                        {
                            "node_id": "trigger_1",
                            "type": "trigger",
                            "action": "manual",
                            "label": "Manual Trigger",
                            "config": {},
                        },
                        {
                            "node_id": "ai_chat_1",
                            "type": "action",
                            "action": "ai_chat",
                            "label": "AI Chat",
                            "config": {
                                "model": model_alias,
                                "messages": [{"role": "user", "content": "Say: OK"}],
                            },
                        },
                    ],
                    "edges": [],
                    "enabled": True,
                    "fallback_user_id": GUEST_USER_ID,
                },
                timeout=10,
            )
            
            assert workflow_response.status_code == 200, f"Failed to create workflow for {model_alias}"
            workflow_id = workflow_response.json()["workflow_id"]
            
            exec_response = requests.post(
                f"{API_BASE}/workflows/{workflow_id}/execute",
                json={"input_data": {}, "fallback_user_id": GUEST_USER_ID},
                timeout=30,
            )
            
            assert exec_response.status_code == 200, f"Execution failed for {model_alias}: {exec_response.text}"
            execution = exec_response.json()
            
            assert execution["status"] == "completed", f"Execution failed for {model_alias}: {execution.get('error')}"
            
            node_result = execution.get("node_results", {}).get("ai_chat_1", {})
            assert node_result["status"] == "success", f"ai_chat failed for {model_alias}: {node_result.get('error')}"
            
            print(f"✅ Model alias {model_alias} -> {expected_provider} works correctly")


class TestUTF8Serialization:
    """Test that image outputs don't cause UTF-8 serialization crashes"""
    
    def test_image_output_serialization(self):
        """Verify image outputs are properly serialized as strings"""
        # Create and execute workflow with ai_image_gen
        workflow_response = requests.post(
            f"{API_BASE}/workflows",
            json={
                "name": f"TEST_UTF8Serialization_{uuid.uuid4().hex[:8]}",
                "description": "Test UTF-8 serialization of image outputs",
                "nodes": [
                    {
                        "node_id": "trigger_1",
                        "type": "trigger",
                        "action": "manual",
                        "label": "Manual Trigger",
                        "config": {},
                    },
                    {
                        "node_id": "ai_image_1",
                        "type": "action",
                        "action": "ai_image_gen",
                        "label": "AI Image",
                        "config": {
                            "model": "nano-banana",
                            "prompt": "A blue square",
                        },
                    },
                ],
                "edges": [],
                "enabled": True,
                "fallback_user_id": GUEST_USER_ID,
            },
            timeout=10,
        )
        
        assert workflow_response.status_code == 200
        workflow_id = workflow_response.json()["workflow_id"]
        
        # Execute and verify response is valid JSON (no UTF-8 crash)
        exec_response = requests.post(
            f"{API_BASE}/workflows/{workflow_id}/execute",
            json={"input_data": {}, "fallback_user_id": GUEST_USER_ID},
            timeout=60,
        )
        
        # If we get here without exception, JSON serialization worked
        assert exec_response.status_code == 200, f"Execution failed: {exec_response.text}"
        
        # Verify we can parse the response as JSON
        try:
            execution = exec_response.json()
        except Exception as e:
            pytest.fail(f"Failed to parse response as JSON (UTF-8 serialization issue): {e}")
        
        # Verify image output is a string
        node_result = execution.get("node_results", {}).get("ai_image_1", {})
        if node_result.get("status") == "success":
            output = node_result.get("output", {})
            image_url = output.get("image_url", "")
            
            # Verify it's a string (not bytes)
            assert isinstance(image_url, str), f"image_url should be string, got {type(image_url)}"
            
            # If it's a data URL, verify it's properly encoded
            if image_url.startswith("data:"):
                assert "base64," in image_url, "Data URL should contain base64 encoding"
        
        print("✅ UTF-8 serialization test passed - no crashes, valid JSON response")


if __name__ == "__main__":
    print("\n" + "="*60)
    print("Feature 4 Workflow Actions Test")
    print("="*60)
    print(f"Backend URL: {BASE_URL}")
    print(f"Guest User ID: {GUEST_USER_ID}")
    print("="*60 + "\n")
    
    # Run tests
    test_classes = [
        TestWorkflowUsageStats,
        TestWorkflowCreation,
        TestAIChatExecution,
        TestAIImageGenExecution,
        TestModelNormalization,
        TestUTF8Serialization,
    ]
    
    for test_class in test_classes:
        print(f"\n--- {test_class.__name__} ---")
        instance = test_class()
        for method_name in dir(instance):
            if method_name.startswith("test_"):
                try:
                    getattr(instance, method_name)()
                except Exception as e:
                    print(f"❌ {method_name}: {e}")
