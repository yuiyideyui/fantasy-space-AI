import os
import re
import json
import uvicorn
from fastapi import FastAPI, Request
from vllm import LLM, SamplingParams

# --- 环境配置 ---
os.environ["VLLM_USE_V1"] = "0"

app = FastAPI()

# --- 静态 Prompt 部分 (全局只定义一次，放在最前面以最大化缓存命中) ---
# 🔑 优化：完全静态的规则放最前面，所有 NPC 共享这部分缓存
STATIC_PROMPT_PREFIX = (
    "<｜begin of sentence｜>"
    "### 任务\n请分析现状并给出下一步动作，必须以 JSON 格式输出。\n"
    "结果样例：{\"thought\": \"需要补水\", \"text\": \"我得找点水喝\", \"actions\": [{ \"type\": \"use\", \"item_name\": \"水壶\" }]}\n"
    "# Output Format\n"
    "**注意：你必须仅输出一个合法的 JSON 对象。** 严禁在 JSON 前后添加任何文字说明、解释、换行或 Markdown 代码块标记（如 ```json ）。\n"
    "\n"
    "## JSON Structure\n"
    "{\n"
    "  \"thought\": \"string (你的内心活动和决策逻辑)\",\n"
    "  \"text\": \"string (你对玩家说的话)\",\n"
    "  \"experience\": \"string (你的经验总结)\",\n"
    "  \"actions\": [\n"
    "    { \"type\": \"move\", \"pos\": [number, number] },\n"
    "    { \"type\": \"use\", \"item_name\": \"string\" },\n"
    "    { \"type\": \"attack\", \"sum\": number },\n"
    "    { \"type\": \"interact\" }\n"
    "  ]\n"
    "}\n"
    "\n"
    "# Action Rules\n"
    "- **main**: 请注意饱食度或含水量低于0的时候会减少生命值，饱食度和含水量高于50的时候会回复生命值，生命值0的时候不允许有任何操作和语言、思考。\n"
    "- **experience**: 你的经验总结，请根据你之前的记录进行总结。\n"
    "- **actions**: 必须是数组且不能为空,必须符合上面的json结构。\n"
    "- **move**: `pos` 必须在地图范围内且属于可行区域（禁止进入目标清单中的不可移动区域），移动后的位置可以会有1-3个单位的误差。\n"
    "- **use**: `item_name` 必须是你当前背包里已有的物品，use种子的时候需要到可种植土地区域上面才可种植。use不能给别他人使用。\n"
    "- **attack**: `sum` 必须是整数，代表攻击次数。\n"
    "- **interact**: 只有当你位于可交互物体附近时才能执行。\n"
    "- **Constraints**: 禁止出现未定义的字段，严禁返回 null。\n"
)

# --- 1. 模型初始化 ---
print("正在加载 DeepSeek-R1-14B-AWQ 模型...")
llm = LLM(
    model="/home/yuiyi/models/DeepSeek-R1-14B-AWQ",
    trust_remote_code=True,
    # enable_prefix_caching=True,  # 👈 核心优化：开启前缀缓存
    max_model_len=4096,
    gpu_memory_utilization=0.85,
    enforce_eager=True,
    kv_cache_dtype="fp8"
)

# --- 2. 增强型 JSON 提取函数 ---
def extract_json(text: str):
    """
    专门适配 DeepSeek-R1 的提取逻辑：
    1. 先剔除 <think> 标签内容，避免干扰。
    2. 使用贪婪匹配 r"({[\s\S]*})" 抓取最外层 JSON，确保 actions 数组内的嵌套花括号不被截断。
    """
    # 移除思维链内容
    clean_text = re.sub(r'<think>[\s\S]*?</think>', '', text).strip()
    
    # 贪婪匹配：找到第一个 { 和最后一个 } 之间的所有内容
    match = re.search(r"(\{[\s\S]*\})", clean_text)
    
    if match:
        json_str = match.group(1)
        # 移除可能误加的 Markdown 标识
        json_str = json_str.replace('```json', '').replace('```', '').strip()
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            # 尝试修复末尾多余逗号的常见错误
            try:
                json_str = re.sub(r',\s*([\]}])', r'\1', json_str) 
                return json.loads(json_str)
            except:
                return None
    return None

# --- 3. 路由定义 ---
@app.post("/generate")
async def generate(request: Request):
    try:
        body = await request.json()
        scene_report = body.get("scene_report", "")
        system_prompt = body.get("system_prompt", "你是一个资深游戏玩家。")

        if not scene_report:
            return {"status": "error", "message": "缺少环境报告"}

        # 🔑 优化后的 prompt 组装顺序：
        # 1. 先放完全静态的规则 (所有 NPC 共享这部分缓存)
        # 2. 再放每个 NPC 的个性设定 (system_prompt)
        # 3. 最后放当前环境报告
        full_prompt = (
            f"{STATIC_PROMPT_PREFIX}"
            f"### 角色设定\n{system_prompt}\n"
            f"### 环境报告\n{scene_report}\n"
            f"你的决策："
        )
        # print('full_prompt',full_prompt)
        sampling_params = SamplingParams(
            temperature=body.get("temperature", 0.1),
            max_tokens=body.get("max_tokens", 2048),
            presence_penalty=0.3,
            stop=["<｜end of sentence｜>", "###"]
        )

        # 运行推理
        outputs = llm.generate([full_prompt], sampling_params)
        raw_output = outputs[0].outputs[0].text

        # 解析 JSON
        action_json = extract_json(raw_output)
        
        if action_json:
            # 提取思维链（可选，用于调试）
            think_match = re.search(r'<think>([\s\S]*?)</think>', raw_output)
            thinking_process = think_match.group(1).strip() if think_match else "无显式思考过程"

            return {
                "status": "success",
                "response": action_json,
                "thinking_raw": thinking_process
            }
        else:
            return {
                "status": "warning",
                "message": "未能解析出符合结构的 JSON",
                "raw_output": raw_output
            }

    except Exception as e:
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)