from fastapi import FastAPI, Request
import uvicorn
import os
import re
import json
from vllm import LLM, SamplingParams

# 强制兼容模式（WSL / 4070Ti Super 友好）
os.environ["VLLM_USE_V1"] = "0"

app = FastAPI()

# ✅ 启动时加载模型
llm = LLM(
    model="/home/yuiyi/models/DeepSeek-R1-14B-AWQ",
    trust_remote_code=True,
    max_model_len=4096,
    # 💡 关键修改点 1：调高到 0.9。16GB * 0.9 = 14.4GB，减去 10GB 权重，还有 4.4GB 给 Cache，足够了。
    gpu_memory_utilization=0.9, 
    # 💡 关键修改点 2：显存吃紧时，如果不做分布式推理，不要开这个（除非是单卡多并发出现算力瓶颈）
    enforce_eager=True, 
    # 💡 建议增加：
    kv_cache_dtype="fp8", # 如果 vLLM 版本支持，开启 FP8 缓存能让 Cache 空间翻倍，支持更多并发
    disable_log_stats=True
)

@app.post("/generate")
async def generate(request: Request):
    body = await request.json()

    scene_report = body.get("scene_report")
    if not scene_report:
        return {"error": "scene_report is required"}

    system_prompt = body.get("system_prompt")
    if not system_prompt:
        return {"error": "system_prompt is required"}

    full_prompt = f"""
{system_prompt}
# 环境报告
{scene_report}
# 任务
请根据以上信息，生成你的下一步行动。
"""

    sampling_params = SamplingParams(
        temperature=body.get("temperature", 0.3),
        max_tokens=body.get("max_tokens", 512),
    )

    outputs = llm.generate([full_prompt], sampling_params)
    raw_text = outputs[0].outputs[0].text.strip()

    # 🛡 JSON 裁剪保险
    match = re.search(r"\{[\s\S]*\}", raw_text)
    if not match:
        return {"error": "Model did not return JSON", "raw": raw_text}

    json_text = match.group(0)

    try:
        parsed = json.loads(json_text)
    except json.JSONDecodeError:
        return {"error": "Invalid JSON", "raw": raw_text}

    return {"response": parsed}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
