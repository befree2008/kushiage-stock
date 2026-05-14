#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
进货单自动入库脚本
功能：
1. 自动匹配货品名称 → SKU ID
2. 自动换算箱规 → 基准单位数量
3. 批量更新库存
4. 完整记录操作日志
"""
import csv
from pathlib import Path
from inventory_manager import InventoryManager

DATA = Path("data")

# ============================================================
# 进货单货品清单（从图片识别）
# ============================================================
PURCHASE_ORDER = [
    # (货品名称, SKU ID, 箱数, 备注, 每箱基准单位数量)
    ("小由纸桶(小号)", "SKU043", 1, "20条/箱 × 50个/条 = 500个/箱", 500),
    ("紫苏孜然辣椒粉", "SKU036", 1, "70条/箱 × 500g/条 = 35000g/箱", 35000),
    ("卤山川巴蜀大鸡排", "SKU018", 1, "10袋/箱 × 10串/袋 = 100串/箱", 100),
    ("台湾无骨鸡柳", "SKU033", 1, "12袋/箱 × 1kg/袋 = 12kg/箱", 12),
    ("开花肠", "SKU014", 1, "10袋/箱 × 20串/袋 = 200串/箱", 200),
    ("锅包烧饼", "SKU021", 1, "10袋/箱 × 10串/袋 = 100串/箱", 100),
    ("玉米粒小串", "SKU005", 1, "10袋/箱 × 10把/袋 × 10串/把 = 1000串/箱", 1000),
    ("生炸鸡脆甲(鸡叉骨)", "SKU031", 1, "10袋/箱 × 2.5kg/袋 = 25kg/箱", 25),
    ("脆皮年糕", "SKU013", 1, "6袋/箱 × 20串/袋 = 120串/箱", 120),
]

# 待确认/新 SKU
UNCONFIRMED_ITEMS = [
    ("玉米鸡翅串", "⚠️ 系统中无此 SKU，需新增后手动入库"),
    ("第7个货品(识别被本页合计遮挡)", "⚠️ OCR识别混乱，需确认具体货品"),
]


def load_sku_dictionary() -> dict:
    """加载 SKU 字典"""
    skus = {}
    with open(DATA / "sku_dictionary.csv", "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            skus[row["sku_id"]] = row
    return skus


def main():
    print("=" * 70)
    print("📦 进货单自动入库")
    print("=" * 70)

    inv = InventoryManager()
    skus = load_sku_dictionary()

    # 显示当前库存
    print("\n📊 入库前库存摘要:")
    print("-" * 70)

    # 显示本次入库的 SKU 当前库存
    for name, sku_id, boxes, note, per_box in PURCHASE_ORDER:
        sku = inv.inventory["skus"].get(sku_id, {})
        current = sku.get("quantity", 0)
        unit = sku.get("unit", "?")
        sku_name = sku.get("sku_name", sku_id)
        print(f"  {sku_id} {sku_name:<20} 当前: {current:>8.2f} {unit}")

    print("\n" + "=" * 70)
    print("📋 本次入库清单:")
    print("=" * 70)
    print(f"{'货品名称':<20} {'SKU':<8} {'箱数':>6} {'入库数量':>12} {'单位':<6}")
    print("-" * 70)

    total_value = 0
    success_count = 0

    for name, sku_id, boxes, note, per_box in PURCHASE_ORDER:
        sku = inv.inventory["skus"].get(sku_id, {})
        unit = sku.get("unit", "?")
        qty = boxes * per_box

        print(f"{name:<20} {sku_id:<8} {boxes:>6} {qty:>12.2f} {unit:<6}")
        print(f"  备注: {note}")

        # 执行入库
        reason = f"进货单入库: {boxes}箱 × {per_box}{unit}/箱, 单号 DQK2026051309342"
        if inv.add_restock(sku_id, qty, reason):
            success_count += 1
        print()

    print("-" * 70)
    print(f"✅ 成功入库: {success_count}/{len(PURCHASE_ORDER)} 个 SKU")

    # 显示待确认项目
    if UNCONFIRMED_ITEMS:
        print("\n" + "=" * 70)
        print("⚠️ 待确认/待处理项目:")
        print("=" * 70)
        for name, note in UNCONFIRMED_ITEMS:
            print(f"  {name:<20} {note}")

    # 显示入库后库存
    print("\n" + "=" * 70)
    print("📊 入库后库存清单:")
    print("=" * 70)
    inv.print_inventory()

    print("\n" + "🎉" * 20)
    print("   进货单入库完成！")
    print("🎉" * 20)


if __name__ == "__main__":
    main()
