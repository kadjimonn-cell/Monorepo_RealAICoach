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
        print("--- Testing AI Photo ---")
        # Use a real user_id if needed, or 'guest'
        await test_endpoint(client, "AI Photo Gen", "POST", f"{BASE_URL}/ai-image/generate", {
            "user_id": "test_user",
            "prompt": "A futuristic city",
            "response_format": "url"
        })

if __name__ == "__main__":
    asyncio.run(main())
