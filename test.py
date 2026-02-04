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
你是一个2D游戏的npc，你需要思考自己要如何存活下去。请注意饱食度和含水量低于50的时候会减少生命值，生命值0的时候不允许有任何操作和语言、思考。

# Output Format
**注意：你必须仅输出一个合法的 JSON 对象。** 严禁在 JSON 前后添加任何文字说明、解释、换行或 Markdown 代码块标记（如 ```json ）。

## JSON Structure
{
  "thought": "string (你的内心活动和决策逻辑)",
  "text": "string (你对玩家说的话)",
  "actions": [
    { "type": "move", "pos": [number, number] },
    { "type": "use", "item_name": "string" },
    { "type": "attack", "sum": number },
    { "type": "interact" }
  ]
}

# Action Rules
- **actions**: 必须是数组且不能为空,必须符合上面的json结构。
- **move**: `pos` 必须在地图范围内且属于可行区域（禁止进入目标清单中的不可移动区域）。
- **use**: `item_name` 必须是你当前背包里已有的物品，use种子的时候需要到可种植土地区域上面才可种植。
- **attack**: `sum` 必须是整数，代表攻击次数。
- **interact**: 只有当你位于可交互物体附近时才能执行。
- **Constraints**: 禁止出现未定义的字段，严禁返回 null。

# Task
请认真查看下方的【周围目标清单】，结合你的身份给出合理的决策。
"""
                print('scene_report',system_prompt,scene_report)
                async with session.post(
                    VLLM_URL,
                    json={
                        "system_prompt": system_prompt,
                        "scene_report": scene_report,
                        "temperature": 0.2
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
