#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 stock_template.csv 导入初始库存（修复 TBD 问题）
"""
import csv
from pathlib import Path
from inventory_manager import InventoryManager

DATA = Path("data")
TEMPLATE_FILE = DATA / "stock_template.csv"


def import_from_template():
    """从 stock_template.csv 导入库存"""
    print("=" * 70)
    print("📥 从 stock_template.csv 导入初始库存（支持 TBD）")
    print("=" * 70)

    if not TEMPLATE_FILE.exists():
        print(f"❌ 找不到文件: {TEMPLATE_FILE}")
        return

    with open(TEMPLATE_FILE, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    print(f"\n📋 共找到 {len(rows)} 个 SKU")

    inv = InventoryManager()

    # 先清空现有库存
    if inv.inventory["skus"]:
        print("\n⚠️  检测到已有库存数据")
        confirm = input("确定要覆盖并重新初始化吗？ [y/N]: ").strip().lower()
        if confirm != 'y':
            print("\n👋 已取消")
            return
        inv.inventory["skus"] = {}
        inv._save_inventory()
        print("✅ 已清空原有库存\n")

    print("-" * 80)
    print(f"{'SKU':<12} {'名称':<18} {'件数':>8} {'基准单位':>8} {'基准数量':>12} {'状态'}")
    print("-" * 80)

    success_count = 0
    zero_count = 0
    tbd_count = 0

    for row in rows:
        sku_id = row.get("sku_id", "").strip()
        sku_name = row.get("sku_name", "").strip()
        base_unit = row.get("基准单位", "").strip()
        per_piece = row.get("1件=多少基准单位", "").strip()
        current_pieces = row.get("当前库存_件（请填）", "").strip()

        if not sku_id:
            continue

        try:
            # ✅ 处理 TBD：如果件数是 TBD，或者 1件=多少基准单位 是 TBD
            if per_piece.upper() == "TBD" or current_pieces.upper() == "TBD":
                # 基准单位未知，先按件数算，单位暂时用 "件"
                pieces = 0.0
                per_piece_float = 1.0
                base_quantity = 0.0
                tbd_count += 1
                status = "⏳ TBD(待定)"
            elif not current_pieces or current_pieces == "0" or current_pieces == "":
                pieces = 0.0
                per_piece_float = float(per_piece) if per_piece else 1.0
                base_quantity = 0.0
                zero_count += 1
                status = "⚠️ 0件"
            else:
                pieces = float(current_pieces)
                per_piece_float = float(per_piece) if per_piece else 1.0
                base_quantity = round(pieces * per_piece_float, 2)
                status = "✅"

            print(f"{sku_id:<12} {sku_name:<18} {pieces:>8.0f} {base_unit:>8} "
                  f"{base_quantity:>12.2f} {status}")

            inv.init_sku(sku_id, base_quantity, base_unit, sku_name)
            success_count += 1

        except Exception as e:
            print(f"❌ SKU [{sku_id}] 处理失败: {e}")

    print("-" * 80)
    print(f"\n✅ 导入完成！共 {success_count} 个 SKU")
    print(f"   - {zero_count} 个 SKU 当前库存为 0")
    print(f"   - {tbd_count} 个 SKU 单位待定（TBD）")

    # 显示最终库存
    inv.print_inventory()

    print("\n💡 提示：")
    print("   TBD/0 库存的 SKU，以后可以：")
    print("   1. 运行 python3 inventory_manager.py")
    print("   2. 选择 '2. 手动入库' 或 '4. 调账' 来修正数量")


if __name__ == "__main__":
    import_from_template()
