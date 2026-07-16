import asyncio
import httpx

BASE_URL = "http://localhost:8001/api"

async def run_test():
    async with httpx.AsyncClient() as client:
        print("📞 Testing AI Phone Call Flow...")

        # 1. Start Call
        print("\n[1] Starting Call Session...")
        try:
            resp = await client.post(f"{BASE_URL}/phone/call/start", json={
                "user_id": "test_user",
                "contact_id": "ai-assistant",
                "mode": "voice"
            })
            if resp.status_code == 200:
                data = resp.json()
                session_id = data['session_id']
                print(f"✅ Call Started. Session ID: {session_id}")
            else:
                print(f"❌ Failed to start call: {resp.text}")
                return
        except Exception as e:
            print(f"❌ Connection error: {e}")
            return

        # 2. Simulate User Speaking (Text Input fallback for testing)
        print("\n[2] Sending Voice Input (Simulated as Text)...")
        user_message = "Hello, who is this?"
        try:
            # interacting with Form data
            form_data = {
                "user_id": "test_user",
                "session_id": session_id,
                "text_input": user_message
            }
            
            resp = await client.post(f"{BASE_URL}/phone/chat", data=form_data)
            
            if resp.status_code == 200:
                reply = resp.json()
                print(f"✅ AI Responded: '{reply['text']}'")
                if reply['status'] == 'success':
                    print("✅ Status OK")
            else:
                print(f"❌ AI Failed to respond: {resp.text}")

        except Exception as e:
            print(f"❌ Chat Error: {e}")

        # 3. Simulate Follow-up
        print("\n[3] Sending Follow-up...")
        user_message = "Tell me a short joke."
        try:
            form_data = {
                "user_id": "test_user",
                "session_id": session_id,
                "text_input": user_message
            }
            resp = await client.post(f"{BASE_URL}/phone/chat", data=form_data)
            if resp.status_code == 200:
                print(f"✅ AI Responded: '{resp.json()['text']}'")
            else:
                print(f"❌ Error: {resp.text}")
        except Exception as e:
            print(f"❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(run_test())
