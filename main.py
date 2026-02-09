import asyncio
import websockets
import json
import aiohttp
from MapAnalyzer import MapAnalyzer

VLLM_URL = "http://127.0.0.1:8000/generate"

async def handle_godot_request(websocket):
    print("Godot 已连接")

    async with aiohttp.ClientSession() as session:
        try:
            async for message in websocket:
                raw_data = json.loads(message)
                npc_id = raw_data.get("player_status", {}).get("player_id", "unknown")

                print(f"收到来自 {npc_id} 的决策请求")

                scene_report = MapAnalyzer.get_scene_summary(raw_data)

                system_prompt = """
# Role
你是一个2D游戏的npc，你需要思考自己要如何存活下去。
# Task
请认真查看下方的【周围目标清单】，结合你的身份给出合理的决策。
"""
                # print('scene_report',system_prompt,scene_report)
                async with session.post(
                    VLLM_URL,
                    json={
                        "system_prompt": system_prompt,
                        "scene_report": scene_report,
                        "temperature": 0.1
                    }
                ) as resp:
                    result = await resp.json()
                ai_content = result.get("response", {})
                print('ai_content',ai_content)
                payload = {
                    "npc_id": npc_id,
                    "content": ai_content
                }

                await websocket.send(json.dumps(payload))
                print(f"已回传决策给 {npc_id}")

        except websockets.exceptions.ConnectionClosed:
            print("Godot 连接已断开")

async def main():
    async with websockets.serve(handle_godot_request, "0.0.0.0", 8765):
        print("WebSocket 网关已启动 ws://localhost:8765")
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())
