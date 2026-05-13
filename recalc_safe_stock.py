#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
按真实销量重算安全库存（以"袋"为单位）。

策略：
  - 盘货单位 = 袋；进货单位 = 箱
  - 覆盖天数 = COVER_DAYS（默认 4 天，可用 --days 或 CLI 参数改）
  - safe_bags = ceil(N天消耗 / 1袋基准量)，至少 1 袋
  - 无销量/已下架/未启用的 SKU：safe_bags = 原 safe_stock_base 的值（保持不变）
  - 蔬菜等进货规格未知（purchase_units 为空）的 SKU：safe_bags 留空，safe_base 按 N 天消耗向上取整
"""
import argparse
import csv
import json
import math
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--days", type=float, default=4.5,
                help="覆盖天数（默认 4.5：最长空档 4 天 + buffer 0.5 天）")
ap.add_argument("--seasoning-days", type=float, default=10,
                help="调料类的覆盖天数（默认 10）")
args = ap.parse_args()

DATA = Path("data")
COVER_DAYS = args.days
SEASONING_COVER_DAYS = args.seasoning_days
DAYS = 40


def pack_sizes(purchase_json: str, base_unit: str):
    """
    解析 purchase_units 图，返回 {unit -> base_qty}。
    例: {"袋": 300, "箱": 3000}
    """
    try:
        g = json.loads(purchase_json)
    except Exception:
        return {}
    if not g:
        return {}

    def resolve(unit, seen=None):
        if seen is None: seen = set()
        if unit == base_unit: return 1.0
        if unit in seen: return None
        seen.add(unit)
        if unit not in g: return None
        edge = g[unit]
        sub = resolve(edge["to"], seen)
        if sub is None: return None
        return float(edge["rate"]) * sub

    out = {}
    for u in g:
        size = resolve(u)
        if size is not None:
            out[u] = size
    return out


def pick_bag_and_box(sizes: dict):
    """
    按名称严格选 '袋' 和 '箱'；如果没有叫 '袋' 的键，退回到常见别名。
    不再把最小层当袋，避免把 '把'/'条'/'提' 误作盘货单位。
    """
    if not sizes: return None, None
    # 包材的中间单位有 捆/条/提/袋/桶 等，这里都算"盘货件"
    bag_keys = ["袋", "捆", "条", "提", "桶", "罐", "瓶", "包"]
    box_keys = ["箱", "大箱"]
    bag = next((sizes[k] for k in bag_keys if k in sizes), None)
    box = next((sizes[k] for k in box_keys if k in sizes), None)
    return bag, box


# ============ 加载 SKU 字典 ============
with (DATA / "sku_dictionary.csv").open(encoding="utf-8-sig") as f:
    sku_rows = list(csv.DictReader(f))
fields_old = list(sku_rows[0].keys())

# ============ 加载菜品销售消耗 ============
consumption = {}
with (DATA / "sales_map_draft.csv").open(encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        consumption[r["sku_id"]] = consumption.get(r["sku_id"], 0) + float(r["total_consumption"])

# ============ 加载调料消耗（来自口味统计）============
seasoning_path = DATA / "seasoning_daily.csv"
if seasoning_path.exists():
    with seasoning_path.open(encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            # seasoning_daily 是日均 g，换算成 40 天总量对齐 consumption 表语义
            daily_g = float(r["日均消耗_g"])
            consumption[r["sku_id"]] = daily_g * DAYS

# ============ 加载包材日均消耗（手工填）============
packaging_path = DATA / "packaging_daily.csv"
if packaging_path.exists():
    with packaging_path.open(encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            v = (r.get("日均消耗") or "").strip()
            if not v:
                continue
            try:
                daily = float(v)
            except ValueError:
                continue
            # 仿照调料：日均 × 40 天 存到 consumption（保持和食品/调料同语义）
            consumption[r["sku_id"]] = daily * DAYS

# ============ 计算 ============
updates = []
for row in sku_rows:
    sku_id = row["sku_id"]
    base_unit = row["base_unit"]
    old_safe_base = float(row["safe_stock_base"])
    cons40 = consumption.get(sku_id, 0)
    daily = cons40 / DAYS
    weekly = daily * 7
    # 调料类用更长的覆盖天数；包材和食材一起进货，用同样的下次到货天数
    this_cover_days = SEASONING_COVER_DAYS if row["category"] == "调料" else COVER_DAYS
    cover = daily * this_cover_days

    sizes = pack_sizes(row["purchase_units"], base_unit)
    bag_size, box_size = pick_bag_and_box(sizes)

    if cons40 == 0:
        # 无销量：保持原值，袋数留空
        new_safe_base = old_safe_base
        new_safe_bags = ""
        reason = "无销量，保持原值"
    elif bag_size is None:
        # 没配袋（如蔬菜 TBD）
        new_safe_base = math.ceil(cover)
        new_safe_bags = ""
        reason = f"{this_cover_days:g}天消耗≈{cover:.1f}{base_unit}，进货规格TBD"
    else:
        bags_needed = max(1, math.ceil(cover / bag_size))
        new_safe_bags = bags_needed
        new_safe_base = bags_needed * bag_size
        reason = f"{this_cover_days:g}天消耗≈{cover:.1f}{base_unit} → {bags_needed}袋×{bag_size:g}{base_unit}/袋"

    updates.append({
        "row": row,
        "bag_size": bag_size,
        "box_size": box_size,
        "weekly": round(weekly, 1),
        "daily": round(daily, 2),
        "old_safe_base": old_safe_base,
        "new_safe_base": new_safe_base,
        "new_safe_bags": new_safe_bags,
        "reason": reason,
        "cover": cover,
    })


# ============ 写新 SKU 字典（确保列: pack_size_base, safe_stock_bags 存在且不重复）============
new_fields = fields_old.copy()
idx = new_fields.index("safe_stock_base")
# 在 safe_stock_base 前插 pack_size_base（若已存在则跳过）
if "pack_size_base" not in new_fields:
    new_fields.insert(idx, "pack_size_base")
    idx += 1   # safe_stock_base 的位置右移了 1
# 在 safe_stock_base 后插 safe_stock_bags（若已存在则跳过）
if "safe_stock_bags" not in new_fields:
    new_fields.insert(idx + 1, "safe_stock_bags")

out_sku = DATA / "sku_dictionary_v4.csv"
with out_sku.open("w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=new_fields)
    w.writeheader()
    for u in updates:
        row = dict(u["row"])
        row["pack_size_base"] = (
            int(u["bag_size"]) if u["bag_size"] and u["bag_size"] == int(u["bag_size"])
            else (u["bag_size"] if u["bag_size"] else "")
        )
        ns = u["new_safe_base"]
        row["safe_stock_base"] = int(ns) if ns == int(ns) else ns
        row["safe_stock_bags"] = u["new_safe_bags"]
        w.writerow(row)


# ============ 写 diff 对照 ============
diff_out = DATA / "safe_stock_diff.csv"
with diff_out.open("w", encoding="utf-8-sig", newline="") as f:
    w = csv.writer(f)
    w.writerow([
        "SKU", "名称", "分类", "基准单位",
        "袋大小", "箱大小", "周消耗", f"{COVER_DAYS}天消耗",
        "老safe(基准)", "新safe(袋)", "新safe(基准)", "计算依据"
    ])
    for u in updates:
        r = u["row"]
        bag = u["bag_size"]
        box = u["box_size"]
        w.writerow([
            r["sku_id"], r["sku_name"], r["category"], r["base_unit"],
            f"{bag:g}" if bag else "TBD",
            f"{box:g}" if box else "TBD",
            u["weekly"],
            round(u["cover"], 1),
            int(u["old_safe_base"]) if u["old_safe_base"] == int(u["old_safe_base"]) else u["old_safe_base"],
            u["new_safe_bags"] if u["new_safe_bags"] != "" else "-",
            u["new_safe_base"] if u["new_safe_base"] != int(u["new_safe_base"]) else int(u["new_safe_base"]),
            u["reason"],
        ])


# ============ 生成盘货模板（食品 + 调料）============
template_out = DATA / "stock_template.csv"
with template_out.open("w", encoding="utf-8-sig", newline="") as f:
    w = csv.writer(f)
    # 表头用"件"（食材=袋，包材=捆/提/条/袋，各自根据 sku_dictionary 中的中间单位）
    w.writerow(["sku_id", "sku_name", "category", "基准单位",
                "1件=多少基准单位", "safe_件", "当前库存_件（请填）", "备注"])
    # 食品 → 调料 → 包材，按各自周消耗降序
    food_us = [u for u in updates if u["row"]["category"] not in ("调料", "包材")]
    seas_us = [u for u in updates if u["row"]["category"] == "调料"]
    pkg_us  = [u for u in updates if u["row"]["category"] == "包材"]
    ordered = (sorted(food_us, key=lambda x: -x["weekly"])
               + sorted(seas_us, key=lambda x: -x["weekly"])
               + sorted(pkg_us,  key=lambda x: -x["weekly"]))
    for u in ordered:
        r = u["row"]
        if r["status"] != "active": continue
        bag = u["bag_size"]
        # 备注根据有无销量调整描述
        if u["weekly"] > 0:
            note = f"周消耗≈{u['weekly']:g}{r['base_unit']}"
            if r["category"] in ("调料", "包材"):
                note += f"，日均≈{u['daily']:g}{r['base_unit']}"
        else:
            note = "待评估消耗量" if r["category"] != "包材" else "待填日均消耗"
        w.writerow([
            r["sku_id"], r["sku_name"], r["category"], r["base_unit"],
            f"{bag:g}" if bag else "TBD",
            u["new_safe_bags"] if u["new_safe_bags"] != "" else "TBD",
            "",  # 留空给老王填
            note,
        ])


# ============ 控制台打印 ============
print(f"{'SKU':<8}{'名称':<16}{'分类':<6}{'周消耗':>8}{'袋大小':>8}{'新safe':>10}{'原safe':>10}")
print("-" * 95)
# 按周消耗降序，分类分组
food = [u for u in updates if u["row"]["category"] not in ("调料", "包材")]
other = [u for u in updates if u["row"]["category"] in ("调料", "包材")]

print(">>> 食品 SKU（按周消耗降序）")
for u in sorted(food, key=lambda x: -x["weekly"]):
    r = u["row"]
    bag = u["bag_size"]
    bag_str = f"{bag:g}{r['base_unit']}" if bag else "TBD"
    if u["new_safe_bags"] != "":
        new_str = f"{u['new_safe_bags']}袋={u['new_safe_base']}{r['base_unit']}"
    else:
        new_str = f"{u['new_safe_base']}{r['base_unit']}"
    old_str = f"{int(u['old_safe_base']) if u['old_safe_base'] == int(u['old_safe_base']) else u['old_safe_base']}"
    mark = "📈" if u["new_safe_base"] > u["old_safe_base"] else ("📉" if u["new_safe_base"] < u["old_safe_base"] else "  ")
    print(f"{r['sku_id']:<8}{r['sku_name']:<16}{r['category']:<6}{u['weekly']:>8.1f}{bag_str:>8}{new_str:>12} {old_str:>8} {mark}")

print(f"\n>>> 调料/包材 SKU: {len(other)} 个（调料按 {SEASONING_COVER_DAYS:g} 天；包材按食材同口径 {COVER_DAYS:g} 天 + 读 packaging_daily.csv）")

print(f"\n✅ 新 SKU 字典:  {out_sku}")
print(f"📄 变更对照:    {diff_out}")
print(f"📋 盘货模板:    {template_out}")
