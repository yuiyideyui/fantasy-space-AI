import asyncio
import json
import aiohttp
import uvicorn
from typing import List
from datetime import datetime
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from motor.motor_asyncio import AsyncIOMotorClient

# --- Connection Manager ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception as e:
                print(f" [Error] Broadcasting failed: {e}")

web_connection_manager = ConnectionManager()

# 假设 MapAnalyzer 在同级目录下
try:
    from MapAnalyzer import MapAnalyzer
except ImportError:
    # 模拟 MapAnalyzer 用于演示，如果没有该文件请确保它存在
    class MapAnalyzer:
        @staticmethod
        def get_scene_summary(data):
            return f"场景包含 {len(data.get('entities', []))} 个实体"

app = FastAPI(title="Game AI Gateway")

# --- 配置参数 ---
VLLM_URL = "http://127.0.0.1:8000/generate"
MONGO_URI = "mongodb://192.168.31.64:27017"
DB_NAME = "game_ai_db"
COLLECTION_NAME = "npc_history"

# --- 数据库初始化 ---
client = AsyncIOMotorClient(MONGO_URI)
db = client[DB_NAME]
collection = db[COLLECTION_NAME]

async def save_to_mongo(npc_id: str, scene_report: str, ai_content: any,timestamp:datetime):
    """将决策数据异步存入 MongoDB"""
    try:
        document = {
            "npc_id": npc_id,
            "timestamp": timestamp,
            "scene_report": scene_report,
            "ai_content": ai_content
        }
        result = await collection.insert_one(document)
        print(f" [DB] 数据已持久化, ID: {result.inserted_id}")
    except Exception as e:
        print(f" [DB] 存储至 MongoDB 失败: {e}")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """处理来自 Godot 游戏后端的 WebSocket 决策请求"""
    await websocket.accept()
    print(" [System] Godot 客户端已连接")
    
    async with aiohttp.ClientSession() as session:
        try:
            while True:
                message = await websocket.receive_text()
                raw_data = json.loads(message)
                
                player_status = raw_data.get("player_status", {})
                npc_id = player_status.get("player_id", "unknown_npc")
                npc_name = player_status.get("player_name", "unknown_npc")
                
                print(f" [Request] 收到来自 {npc_id} 的决策请求")

                # 1. 场景分析
                try:
                    scene_report = MapAnalyzer.get_scene_summary(raw_data)
                except Exception as e:
                    scene_report = "场景解析异常"
                    print(f" [Error] MapAnalyzer 报错: {e}")

                # 2. 构建 AI Prompt
                system_prompt = (
                    "你是一个2D游戏的NPC，你需要思考自己要如何存活下去。\n"
                    "请认真查看下方的【周围目标清单】，结合你的身份给出合理的决策。"
                )
                
                # 3. 请求 AI 后端
                ai_content = "AI 无法决策"
                try:
                    payload = {
                        "system_prompt": system_prompt,
                        "scene_report": scene_report,
                        "temperature": 0.1
                    }
                    async with session.post(VLLM_URL, json=payload, timeout=10) as resp:
                        if resp.status == 200:
                            result = await resp.json()
                            ai_content = result.get("response", result) 
                        else:
                            print(f" [AI] 后端响应异常, 状态码: {resp.status}")
                except Exception as e:
                    print(f" [AI] 请求失败: {e}")
                timestamp=datetime.now()
                # 4. 后台异步存储
                asyncio.create_task(save_to_mongo(npc_id, scene_report, ai_content,timestamp))

                # 5. 回传结果
                response_payload = {
                    "type": "ai_decision",
                    "npc_id": npc_id,
                    "npc_name": npc_name,
                    "ai_content": ai_content,
                    "timestamp": timestamp.isoformat(),
                    "scene_report":scene_report
                }
                response_json = json.dumps(response_payload)
                await websocket.send_text(response_json)
                # Broadcast to web clients
                await web_connection_manager.broadcast(response_json)

        except WebSocketDisconnect:
            print(f" [System] Godot 客户端已断开")
        except Exception as e:
            print(f" [Error] Godot 路由异常: {e}")

@app.websocket("/ws/web")
async def web_websocket_endpoint(websocket: WebSocket):
    """处理来自 Web 前端（如监控面板、数据展示）的 WebSocket 连接"""
    await web_connection_manager.connect(websocket)
    print(" [System] Web 客户端已连接")
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        web_connection_manager.disconnect(websocket)
        print(" [System] Web 客户端已断开")
    except Exception as e:
        print(f" [Error] Web 路由异常: {e}")

@app.get("/history")
async def get_history():
    """获取 MongoDB 中的历史决策数据"""
    try:
        # 1. 获取最近的 100 条记录
        cursor = collection.find().sort("timestamp", -1).limit(100)
        history = await cursor.to_list(length=100)
        
        npc_name_map = {}
        
        for item in history:
            # 2. 处理 ObjectId 序列化问题
            if "_id" in item:
                item["_id"] = str(item["_id"])
            
            # 3. 简化分组逻辑
            npc_id = item.get("npc_id", "unknown")
            if npc_id not in npc_name_map:
                npc_name_map[npc_id] = []
            npc_name_map[npc_id].append(item)
            
        return {
            "code": 200,
            "status": "success",
            "data": npc_name_map,
        }
    except Exception as e:
        # 4. 使用 HTTPException 返回标准的 500 错误
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    # 启动后：
    # Godot 连接地址: ws://localhost:8765/ws
    # Web 连接地址:   ws://localhost:8765/ws/web
    print(f" [Init] WebSocket 多路由网关尝试启动...")
    uvicorn.run(app, host="0.0.0.0", port=8765)