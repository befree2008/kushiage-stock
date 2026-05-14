#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
进货单自动入库脚本 v2.0
完整 11 件货品入库
"""
from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from inventory_manager import InventoryManager

# ============================================================
# 完整进货单货品清单（已确认）
# ============================================================
PURCHASE_ORDER = [
    # (货品名称, SKU ID, 箱数, 每箱基准数量, 单位, 备注)
    ("卤油", "SKU039", 1, 10000, "g", "20袋/箱 × 500g/袋"),
    ("小串纸桶(小号)", "SKU043", 1, 500, "个", "10条/箱 × 50个/条"),
    ("紫苏孜然撒粉", "SKU036", 1, 10000, "g", "20袋/箱 × 500g/袋"),
    ("卤山川巴掌大鸡排", "SKU018", 1, 120, "串", "12袋/箱 × 10串/袋"),
    ("台湾无骨鸡柳", "SKU033", 1, 10, "kg", "10袋/箱 × 1kg/袋"),
    ("开花肠", "SKU014", 1, 200, "串", "10袋/箱 × 20串/袋"),
    ("椒盐烧饼", "SKU021", 1, 160, "串", "16袋/箱 × 10串/袋"),
    ("玉米粒小串", "SKU005", 1, 1000, "串", "10袋/箱 × 10把/袋 × 10串/把"),
    ("生炸鸡腿串", "SKU024", 1, 80, "串", "10袋/箱 × 8串/袋"),
    ("脆皮年糕", "SKU013", 1, 200, "串", "10袋/箱 × 20串/袋"),
    ("鸡叉骨", "SKU031", 1, 15, "kg", "6袋/箱 × 2.5kg/袋"),
]


def main():
    print("=" * 70)
    print("📦 进货单自动入库 v2.0")
    print("=" * 70)
    print(f"单号: ODK2026051309342")
    print(f"共 {len(PURCHASE_ORDER)} 件货品")
    print()

    inv = InventoryManager()

    # 显示入库前库存
    print("📊 入库前库存:")
    print("-" * 70)
    for name, sku_id, boxes, per_box, unit, note in PURCHASE_ORDER:
        sku = inv.inventory["skus"].get(sku_id, {})
        current = sku.get("quantity", 0)
        sku_name = sku.get("sku_name", sku_id)
        print(f"  {sku_id} {sku_name:<20} 当前: {current:>8.2f} {unit}")

    print("\n" + "=" * 70)
    print("📋 开始入库:")
    print("=" * 70)
    print(f"{'货品名称':<20} {'SKU':<8} {'箱数':>6} {'入库数量':>12} {'单位':<6}")
    print("-" * 70)

    success_count = 0
    for name, sku_id, boxes, per_box, unit, note in PURCHASE_ORDER:
        qty = boxes * per_box
        print(f"{name:<20} {sku_id:<8} {boxes:>6} {qty:>12.2f} {unit:<6}")
        print(f"  备注: {note}")
        
        # 执行入库
        reason = f"进货单入库: {boxes}箱 × {per_box}{unit}/箱, 单号 ODK2026051309342"
        if inv.add_restock(sku_id, qty, reason):
            success_count += 1
        print()

    print("-" * 70)
    print(f"✅ 成功入库: {success_count}/{len(PURCHASE_ORDER)} 个 SKU")

    # 显示入库后库存
    print("\n" + "=" * 70)
    print("📊 入库后库存清单:")
    print("=" * 70)
    inv.print_inventory()

    print("\n" + "🎉" * 20)
    print("   进货单入库全部完成！")
    print("🎉" * 20)


if __name__ == "__main__":
    main()
