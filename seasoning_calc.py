#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
调料消耗计算（老王 2026-05-12 定版）
=====================================

输入：
  data/taste_stats.csv   —— 5 种标准口味的日均份数
  data/sku_dictionary.csv —— SKU 主数据

输出：
  data/seasoning_daily.csv —— 每个调料 SKU 的日均消耗（克）+ 配方溯源
  控制台打印汇总

每份口味的调料克数（老王 2026-05-12 v2 拍板）：
  不辣:   卤油3 + 咖喱5  + 孜然10
  微微辣: 卤油3 + 麻辣5  + 孜然10
  微辣:   卤油3 + 麻辣10 + 香辣4
  中辣:   卤油3 + 麻辣10 + 香辣4 + 特辣8
  特辣:   卤油3 + 麻辣10 + 香辣4 + 特辣15
"""
import csv
from pathlib import Path

DATA = Path(__file__).parent / "data"

# ============ 配方表（单位：g/份）============
# taste -> {sku_id: grams_per_portion}
RECIPE = {
    "不辣":   {"SKU039": 3, "SKU035": 5,  "SKU036": 10},
    "微微辣": {"SKU039": 3, "SKU034": 5,  "SKU036": 10},
    "微辣":   {"SKU039": 3, "SKU034": 10, "SKU037": 4},
    "中辣":   {"SKU039": 3, "SKU034": 10, "SKU037": 4, "SKU038": 8},
    "特辣":   {"SKU039": 3, "SKU034": 10, "SKU037": 4, "SKU038": 15},
}

# ============ 菜品维的调料/辅料配方（单位：g/串）============
# dish_sku_id -> {seasoning_sku_id: grams_per_stick}
# 与口味无关，按菜品串数算
# 老王 2026-05-12：每串轰炸大鱿鱼用 8g 大鱿鱼腌料
# (dish_sku, filter_keyword) → {seasoning_sku: (amount, unit)}
# filter_keyword=None → 该菜品 SKU 全部销量
# filter_keyword="轰炸" → 仅 item_name 包含"轰炸"的行
# unit:
#   "per_stick" —— 串数 × amount（base_unit=串）
#   "per_kg"    —— kg数 × amount（base_unit=kg）
# 老王 2026-05-12：
#   • 每串轰炸大鱿鱼 → 腌料 8g、裹粉 30g（只轰炸才用）
#   • 无骨鸡柳 1份=150g，每份用裹粉 30g → 每 kg 原料 200g
DISH_RECIPE = {
    ("SKU020", "轰炸"): {"SKU041": (8,  "per_stick"),
                        "SKU040": (30, "per_stick")},
    ("SKU033", None):   {"SKU040": (200, "per_kg")},
}

# SKU 名字对照（显示用）
SKU_NAMES = {
    "SKU034": "麻辣油炸料2号",
    "SKU035": "美味咖喱",
    "SKU036": "紫苏孜然撒粉",
    "SKU037": "香辣辣椒粉",
    "SKU038": "特辣辣椒粉",
    "SKU039": "卤油",
    "SKU040": "大鱿鱼裹粉",
    "SKU041": "大鱿鱼腌料",
}


def load_taste_daily():
    """读 taste_stats.csv 返回 {taste: 日均份数}"""
    taste_daily = {}
    with (DATA / "taste_stats.csv").open(encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if r["标准口味"] == "合计":
                continue
            taste_daily[r["标准口味"]] = float(r["日均份数"])
    return taste_daily


def load_dish_daily_filtered(sku_id: str, filter_keyword=None) -> float:
    """读 sales_map_draft.csv 返回指定 SKU（可选 item_name 包含 keyword）的日均消耗量。
    返回 base_unit 量（串 或 kg）。
    """
    WINDOW = 40
    total = 0.0
    with (DATA / "sales_map_draft.csv").open(encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if r["sku_id"] != sku_id:
                continue
            if filter_keyword and filter_keyword not in r["item_name"]:
                continue
            total += float(r["total_consumption"])
    return total / WINDOW


def main():
    taste_daily = load_taste_daily()

    sku_daily = {sku_id: 0.0 for sku_id in SKU_NAMES}
    trace = {sku_id: [] for sku_id in SKU_NAMES}

    # 源一：口味配方
    for taste, recipe in RECIPE.items():
        portions = taste_daily.get(taste, 0)
        for sku_id, g_per in recipe.items():
            daily_g = portions * g_per
            sku_daily[sku_id] += daily_g
            trace[sku_id].append((taste, portions, g_per, daily_g))

    # 源二：菜品配方（支持按菜名过滤 + per_stick/per_kg）
    for (dish_sku, kw), recipe in DISH_RECIPE.items():
        qty = load_dish_daily_filtered(dish_sku, kw)
        label = dish_sku + (f"·{kw}" if kw else "")
        for sku_id, (amount, unit) in recipe.items():
            daily_g = qty * amount
            sku_daily[sku_id] = sku_daily.get(sku_id, 0) + daily_g
            unit_label = "串" if unit == "per_stick" else "kg"
            src_str = f"{label}({qty:.2f}{unit_label}/天×{amount}g)"
            trace[sku_id].append((src_str, qty, amount, daily_g))

    # ========== 打印汇总 ==========
    print("=" * 86)
    print(f"🧂 调料日均消耗计算（基于 40 天口味统计 · 老王 2026-05-12 v2 配方）")
    print("=" * 86)

    # 各口味份数一览
    print("\n📊 口味日均份数：")
    total_portions = 0
    for taste in ["不辣", "微微辣", "微辣", "中辣", "特辣"]:
        p = taste_daily.get(taste, 0)
        total_portions += p
        print(f"  {taste:<6} {p:>7.2f} 份/天")
    print(f"  {'合计':<6} {total_portions:>7.2f} 份/天")

    # 配方展示
    print("\n🧪 单份配方（老王 2026-05-12 v2）：")
    for taste in ["不辣", "微微辣", "微辣", "中辣", "特辣"]:
        items = RECIPE[taste]
        total_g = sum(items.values())
        item_str = ", ".join(f"{SKU_NAMES[s].replace('紫苏','')}:{g}g"
                             for s, g in items.items())
        print(f"  {taste:<6} 合计 {total_g:>3}g  →  {item_str}")

    # 每 SKU 日均消耗
    print("\n📦 各调料 SKU 日均消耗（克）：")
    print(f"  {'SKU':<8}{'名称':<16}{'日均':>9}  {'配方来源':<60}")
    print("  " + "-" * 93)
    for sku_id in sorted(sku_daily.keys(), key=lambda x: -sku_daily[x]):
        name = SKU_NAMES[sku_id]
        daily = sku_daily[sku_id]
        parts = trace[sku_id]
        parts.sort(key=lambda x: -x[3])
        src = ", ".join(f"{t}({p:.1f}份×{g}g={dg:.1f})"
                        for t, p, g, dg in parts if dg > 0)
        print(f"  {sku_id:<8}{name:<16}{daily:>7.1f}g  {src:<60}")

    # ========== 写 seasoning_daily.csv ==========
    out = DATA / "seasoning_daily.csv"
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["sku_id", "sku_name", "日均消耗_g",
                    "日均消耗_kg", "周消耗_kg", "配方来源"])
        for sku_id in sorted(sku_daily.keys(), key=lambda x: -sku_daily[x]):
            daily_g = sku_daily[sku_id]
            src = "; ".join(f"{t}{p:.1f}份×{g}g"
                            for t, p, g, dg in trace[sku_id] if dg > 0)
            w.writerow([
                sku_id,
                SKU_NAMES[sku_id],
                round(daily_g, 1),
                round(daily_g / 1000, 3),
                round(daily_g * 7 / 1000, 2),
                src,
            ])
    print(f"\n📄 日均消耗已写入: {out}")

    # ========== 同步写入 sku_sales_summary.csv（purchase_plan 读取） ==========
    summary_path = DATA / "sku_sales_summary.csv"
    if summary_path.exists():
        # 读入现有 summary
        with summary_path.open(encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            fields = reader.fieldnames
            rows = list(reader)

        # 更新调料 SKU 的日均/周均消耗列
        updated = 0
        for r in rows:
            sku_id = r["sku_id"]
            if sku_id in sku_daily and sku_daily[sku_id] > 0:
                daily_g = sku_daily[sku_id]
                r["日均消耗"] = f"{daily_g:.1f}"
                r["周均消耗"] = f"{daily_g * 7:.1f}"
                # 保留 40 天总量以供参考
                r["40天消耗"] = f"{daily_g * 40:.0f}"
                # 调料没有源自菜品的订单数，用口味总份数标记
                src_taste_portions = sum(
                    p for _, p, _, dg in trace[sku_id] if dg > 0
                )
                r["40天订单数"] = f"{src_taste_portions * 40:.0f}"
                r["Top平台"] = "(来自口味统计)"
                r["平台数"] = "-"
                updated += 1

        with summary_path.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)
        print(f"📊 已同步更新 {updated} 个调料 SKU 到: {summary_path}")
    else:
        print(f"⚠️  {summary_path} 不存在，跳过同步")


if __name__ == "__main__":
    main()
