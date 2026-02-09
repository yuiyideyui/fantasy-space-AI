import math

class MapAnalyzer:
    @staticmethod
    def get_scene_summary(data: dict) -> str:
        """将原始 JSON 转换为 Markdown 结构的深度环境报告"""
        player = data.get("player_status", {})
        p_pos = player.get("current_pos", [0, 0])
        
        # 1. 角色基本状态 (Markdown 标题 + 列表)
        report = "## 1. 角色详细状态报告\n"
        report += f"- **基本信息**: {player.get('player_name', '未知')} (ID: {player.get('player_id', '0')})\n"
        report += f"- **性格特质**: {player.get('personality', '普通')}\n"
        report += f"- **当前坐标**: `{p_pos}`\n"
        report += f"- **生存状态**: {'正在睡觉' if player.get('is_sleep', False) else '清醒'}\n"
        report += "### 核心指标\n"
        report += f"- **生命值 (HP)**: {player.get('hp', 0)}\n"
        report += f"- **饱食度**: {player.get('satiety', 0)} | **含水量**: {player.get('hydration', 0)}\n"
        report += f"- **理智值 (Sanity)**: {player.get('sanity', 0)}\n"
        report += "### 战斗属性\n"
        report += f"- **攻击力**: {player.get('attack_power', 0)} | **防御力**: {player.get('defense', 0)}\n"

        report += "### 历史记录\n"
        report += f"- **记录**: {player.get('chat_history', [])}\n"
        report += f"- **经验**: {player.get('experiences', [])}\n"
        # 2. 导航边界
        nav_data = data.get("map_metadata", {}).get("nav_polygons", [])
        if nav_data and len(nav_data[0]) > 0:
            points = nav_data[0]
            xs, ys = [p[0] for p in points], [p[1] for p in points]
            report += f"- **世界边界**: X: `[{min(xs)} ~ {max(xs)}]`, Y: `[{min(ys)} ~ {max(ys)}]`\n"

        # 3. 背包处理
        inventory = player.get("inventory", [])
        items = [i for i in inventory if i is not None]
        if items:
            item_desc = " | ".join([f"`{i['name']}`x{i['amount']}({i['describe']})" for i in items])
            report += f"- **当前背包**: {item_desc}\n"
        else:
            report += "- **当前背包**: (空)\n"

        # 2. 其他玩家/NPC 状态 (新加部分)
        report += "\n## 2. 周围实体/玩家状态\n"
        other_players = data.get("orther_players_status", []) # 获取你在 Godot 中塞进去的列表

        if not other_players:
            report += "> 当前感知范围内没有其他玩家。\n"
        else:
            # 使用 Markdown 表格可以让 AI 更清晰地对比位置
            report += "| 角色名称 | 当前位置 | 状态备注 |\n"
            report += "| :--- | :--- | :--- |\n"
            
            for p in other_players:
                p_name = p.get("npc_name", "未知实体")
                p_pos_info = p.get("position", "未知位置")
                # 将字典或数组格式的坐标转为可读字符串
                if isinstance(p_pos_info, dict):
                    pos_str = f"({p_pos_info.get('x', 0)}, {p_pos_info.get('y', 0)})"
                else:
                    pos_str = str(p_pos_info)
                    
                report += f"| {p_name} | `{pos_str}` | 在场 |\n"

        # 4. 环境实体分析 (使用表格结构，模型对表格的坐标对比能力极强)
        report += "\n## 3. 周围目标清单\n"
        report += "| 目标名称 | 坐标(Center) | 距离 | 状态/描述 | 移动限制 | 状态 | \n"
        report += "| :--- | :--- | :--- | :--- | :--- | :--- |\n"
        
        entities = data.get("entities", [])
        for e in entities:
            dist = math.sqrt((e["center"][0] - p_pos[0])**2 + (e["center"][1] - p_pos[1])**2)
            e["_tmp_dist"] = round(dist, 1)
        
        entities.sort(key=lambda x: x["_tmp_dist"])

        for e in entities:
            dist = e["_tmp_dist"]
            t_center = f"`{e['center']}`"
            
            # 状态与描述合并
            status_tags = []
            if e.get("is_crop"):
                status_tags.append(f"[{e.get('stage_name', '生长中')}]")
                if e.get("time_left_sec", 0) > 0:
                    status_tags.append(f"剩{e['time_left_sec']}s")
            if e.get("can_water"): status_tags.append("🚿需浇水")
            if e.get("can_harvest"): status_tags.append("🌾可收割")
            
            hp_info = f" (HP:{e['hp']})" if "hp" in e else ""
            full_desc = f"{' '.join(status_tags)} {e['describe']}{hp_info}"
            statusInfo = f"{'可攻击' if e['can_attack'] else '不可攻击'}|{'可交互' if e['can_interact'] else '不可交互'}"

            # 移动限制逻辑
            limit_desc = "-"
            t_rect = e.get("rect", [])
            if len(t_rect) == 4 and e.get("has_physics_layer"):
                x1, y1, w, h = t_rect
                limit_desc = f"禁止进入:({x1},{y1}) to ({x1+w},{y1+h})"
            elif len(t_rect) == 4:
                x1, y1, w, h = t_rect
                limit_desc = f"区域范围:({x1},{y1}) to ({x1+w},{y1+h})"

            report += f"| {e['name']} | {t_center} | {dist} | {full_desc} | {limit_desc} | {statusInfo} |\n"

        return report