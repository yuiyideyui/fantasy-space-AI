import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient

async def test_mongodb_connection():
    # 1. 自动提取 WSL 识别到的 Windows 宿主机 IP
    # 这比手动输入 169.x.x.x 靠谱得多
    host_ip = "192.168.31.64"
        

    uri = f"mongodb://{host_ip}:27017"
    
    print(f"--- 跨环境连接诊断 ---")
    print(f"WSL 尝试访问 Windows IP: {host_ip}")
    print(f"完整连接串: {uri}")
    print("-" * 25)

    # 2. 设置连接客户端（增加 2 秒超时，防止无限等待）
    client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=2000)

    try:
        # 发起真实连接（这步失败说明 IP 或端口不通）
        await client.server_info()
        print("✅ 第一步：物理连接成功！")

        # 3. 尝试写入一条数据（这步失败说明权限或数据库只读）
        db = client["test_database"]
        collection = db["test_collection"]
        result = await collection.insert_one({"message": "WSL 握手测试", "status": "ok"})
        print(f"✅ 第二步：数据写入成功！ID: {result.inserted_id}")

        # 4. 尝试读取刚才的数据
        doc = await collection.find_one({"_id": result.inserted_id})
        print(f"✅ 第三步：数据回读成功！内容: {doc['message']}")
        
        print("-" * 25)
        print("🎉 结论：WSL 访问 Windows MongoDB 彻底通畅！")

    except Exception as e:
        print(f"❌ 测试失败！")
        print(f"详细错误: {e}")
        print("\n[请检查以下两项：]")
        print(f"1. Windows CMD 启动命令是否带了: --bind_ip_all")
        print(f"2. 尝试在 WSL 终端输入: ping {host_ip}")
    finally:
        client.close()

if __name__ == "__main__":
    asyncio.run(test_mongodb_connection())