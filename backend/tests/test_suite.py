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
            # print(f"   Response: {json.dumps(response.json())[:100]}...")
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
        print("--- Testing Core AI Chat Features ---")
        
        features = [
            "medimate", "pennypilot", "ai-writer", "ai-copywriter", 
            "ai-chatbot", "ai-cognitive", "ai-enterprise", 
            "ai-private-search", "ai-speech", "ai-automations"
        ]
        
        for feature in features:
            await test_endpoint(client, f"Chat: {feature}", "POST", f"{BASE_URL}/ai-chat", {
                "user_id": "test_user",
                "feature": feature,
                "message": "Hello, explain what you do in one sentence."
            })

        print("\n--- Testing Specialized AI Services ---")
        await test_endpoint(client, "HealthHalo", "POST", f"{BASE_URL}/healthhalo/consult", {"user_id": "u1", "query": "Headache tips"})
        await test_endpoint(client, "FinWise", "POST", f"{BASE_URL}/finwise/advise", {"user_id": "u1", "question": "Save money"})
        await test_endpoint(client, "SmartBuy", "POST", f"{BASE_URL}/smartbuy/search", {"user_id": "u1", "query": "Laptops", "budget": 1000})
        await test_endpoint(client, "HomeMate", "POST", f"{BASE_URL}/homemate/consult", {"user_id": "u1", "query": "Design tips"})
        await test_endpoint(client, "AutoGenie", "POST", f"{BASE_URL}/autogenie/consult", {"user_id": "u1", "query": "SUV suggestions"})
        await test_endpoint(client, "DisasterGuard", "POST", f"{BASE_URL}/disasterguard/prepare", {"user_id": "u1", "query": "Earthquake"})
        await test_endpoint(client, "AssetPilot", "POST", f"{BASE_URL}/assetpilot/advise", {"user_id": "u1", "query": "ETF vs Stocks"})
        await test_endpoint(client, "TimeSaver", "POST", f"{BASE_URL}/timesaver/optimize", {"user_id": "u1", "query": "Morning routine"})
        await test_endpoint(client, "TravelPal", "POST", f"{BASE_URL}/travelpal/plan-trip", {"user_id": "u1", "destination": "Paris", "duration": "3 days"})
        
        print("\n--- Testing AI Search ---")
        await test_endpoint(client, "AI Search", "POST", f"{BASE_URL}/ai-search", {"user_id": "u1", "query": "Benefits of AI"})

        print("\n--- Testing Content Studio ---")
        await test_endpoint(client, "Script Gen", "POST", f"{BASE_URL}/content-studio/script", {"user_id": "u1", "topic": "AI", "platform": "youtube"})

if __name__ == "__main__":
    asyncio.run(main())
