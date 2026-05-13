#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
按 SKU 汇总 4/1–5/10（40天）销量报表。
输出:
  sku_sales_summary.csv
  控制台打印排行榜
"""
import csv
from collections import defaultdict
from pathlib import Path

DATA = Path("data")
DAYS = 40  # 4/1 - 5/10

# 加载 SKU 字典，保证没卖过的 SKU 也出现在报表里（销量=0）
skus = {}
with (DATA / "sku_dictionary.csv").open(encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        if r["status"] != "active":
            continue
        skus[r["sku_id"]] = {
            "name": r["sku_name"],
            "category": r["category"],
            "base_unit": r["base_unit"],
        }

# 聚合销售：按 SKU 汇总 "被点单次数" 和 "基准单位消耗量"
agg = defaultdict(lambda: {"orders": 0, "consumption": 0.0, "platforms": defaultdict(float)})

# 先把"被点单次数"按 (平台, 菜名, 规格) 去重统计
# 因为一个套餐/加工品会拆成多行写入，但 qty 是同一份数不应重复加
seen_orders = {}  # key=(platform,item,spec,unit) → qty

with (DATA / "sales_map_draft.csv").open(encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        sku_id = r["sku_id"]
        qty = float(r["qty"])
        consumption = float(r["total_consumption"])
        platform = r["platform"]
        key = (platform, r["item_name"], r["spec"], r["unit"])

        # 消耗量直接累加（一个套餐拆多行，每行消耗不同 SKU）
        agg[sku_id]["consumption"] += consumption
        agg[sku_id]["platforms"][platform] += consumption

        # 点单次数只在第一次看到该 key 时算（按 SKU 维度一样避免重复）
        order_key = (sku_id, platform, r["item_name"], r["spec"], r["unit"])
        if order_key not in seen_orders:
            seen_orders[order_key] = qty
            agg[sku_id]["orders"] += qty

# 合成完整报表
rows = []
for sku_id, info in skus.items():
    a = agg.get(sku_id, {"orders": 0, "consumption": 0, "platforms": {}})
    cons = a["consumption"]
    daily = cons / DAYS
    weekly = daily * 7
    rows.append({
        "sku_id": sku_id,
        "sku_name": info["name"],
        "category": info["category"],
        "base_unit": info["base_unit"],
        "40天订单数": round(a["orders"], 1),
        "40天消耗": round(cons, 2),
        "日均消耗": round(daily, 2),
        "周均消耗": round(weekly, 1),
        "Top平台": max(a["platforms"].items(), key=lambda x: x[1])[0] if a["platforms"] else "",
        "平台数": len(a["platforms"]),
    })

# 按周均消耗降序
rows.sort(key=lambda r: -r["周均消耗"])

# 导出 CSV
out = DATA / "sku_sales_summary.csv"
with out.open("w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)

# ==== 打印报表 ====
print("=" * 92)
print(f"{'排名':<4}{'SKU':<8}{'名称':<16}{'分类':<6}{'40天订单':>9}{'40天消耗':>10}{'日均':>8}{'周均':>9} 单位")
print("=" * 92)

cat_totals = defaultdict(lambda: {"weekly": 0, "sku_count": 0, "sold_count": 0})
for i, r in enumerate(rows, 1):
    mark = "  " if r["周均消耗"] > 0 else "💤"
    print(f"{i:<4}{r['sku_id']:<8}{r['sku_name']:<16}{r['category']:<6}"
          f"{r['40天订单数']:>9.0f}{r['40天消耗']:>10.1f}{r['日均消耗']:>8.1f}{r['周均消耗']:>9.1f} {r['base_unit']} {mark}")
    cat_totals[r["category"]]["weekly"] += r["周均消耗"] if r["base_unit"] == "串" else 0
    cat_totals[r["category"]]["sku_count"] += 1
    if r["周均消耗"] > 0:
        cat_totals[r["category"]]["sold_count"] += 1

print("\n" + "=" * 60)
print("📊 分类统计")
print("=" * 60)
for cat, t in cat_totals.items():
    print(f"  {cat:<6}  SKU数: {t['sku_count']:>3} (在售 {t['sold_count']})   周消耗合计: {t['weekly']:>7.0f} 串")

print(f"\n📄 详细报表: {out}")
