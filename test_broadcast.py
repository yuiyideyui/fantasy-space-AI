import asyncio
import aiohttp
import json
import sys

async def test_broadcast():
    uri_godot = "ws://localhost:8765/ws"
    uri_web = "ws://localhost:8765/ws/web"

    async with aiohttp.ClientSession() as session:
        # 1. Connect Web Client
        print(" [Test] Connecting Web Client...")
        try:
            async with session.ws_connect(uri_web) as ws_web:
                print(" [Test] Web Client Connected.")

                # 2. Connect Godot Client
                print(" [Test] Connecting Godot Client...")
                async with session.ws_connect(uri_godot) as ws_godot:
                    print(" [Test] Godot Client Connected.")

                    # 3. Godot Client sends a message
                    payload = {
                        "player_status": {
                            "player_id": "test_npc_01",
                            "player_name": "Test NPC"
                        },
                        "entities": [] # Mock data for MapAnalyzer
                    }
                    print(f" [Test] Godot Client sending: {json.dumps(payload)}")
                    await ws_godot.send_json(payload)

                    # 4. Web Client waits for broadcast
                    print(" [Test] Web Client waiting for message...")
                    
                    # Set a timeout for receiving message
                    msg = await asyncio.wait_for(ws_web.receive(), timeout=15.0)
                    
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        data = json.loads(msg.data)
                        print(f" [Test] Web Client received: {data}")
                        
                        # Assertions
                        assert data["type"] == "ai_decision"
                        assert data["npc_id"] == "test_npc_01"
                        print(" [Test] SUCCESS: Broadcast received and verified!")
                    else:
                        print(f" [Test] Web Client received unexpected message type: {msg.type}")

        except Exception as e:
            print(f" [Test] FAILED: {e}")
            sys.exit(1)

if __name__ == "__main__":
    asyncio.run(test_broadcast())
