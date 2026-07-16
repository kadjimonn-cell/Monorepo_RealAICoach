import asyncio
import httpx

BASE_URL = "http://localhost:8001/api"

async def test_endpoint(client, name, method, url, payload=None):
    try:
        if method == "GET":
            response = await client.get(url, params=payload)
        else:
            response = await client.post(url, json=payload)
        
        if response.status_code == 200:
            print(f"✅ {name}: Success")
            print(f"   Response Preview: {response.text[:150]}...")
            return True
        else:
            print(f"❌ {name}: Failed ({response.status_code})")
            print(f"   Error: {response.text}")
            return False
    except Exception as e:
        print(f"❌ {name}: Error ({str(e)})")
        return False

async def main():
    async with httpx.AsyncClient(timeout=30) as client:
        print("--- Testing PRO Prompts ---")
        
        # Test HealthHalo to see if it uses the new persona
        await test_endpoint(client, "HealthHalo", "POST", f"{BASE_URL}/healthhalo/consult", {
            "user_id": "test_pro",
            "query": "I have a headache and fatigue."
        })

        # Test Universal Chat with a specific feature
        await test_endpoint(client, "PennyPilot (FinWise Persona)", "POST", f"{BASE_URL}/ai-chat", {
            "user_id": "test_pro",
            "feature": "pennypilot",
            "message": "How do I start a budget?"
        })

if __name__ == "__main__":
    asyncio.run(main())
