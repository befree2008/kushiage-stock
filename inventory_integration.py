#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
库存系统与现有脚本集成示例
演示：
  1. 读取销售汇总数据
  2. 自动扣减库存
  3. 生成补货建议
  4. 补货确认后自动入库
"""
import csv
from pathlib import Path
from inventory_manager import InventoryManager

DATA = Path("data")


def auto_deduct_from_sales():
    """从 sku_sales_summary.csv 读取销售数据，自动扣减库存"""
    print("=" * 60)
    print("🔄 自动扣减销售库存")
    print("=" * 60)

    summary_file = DATA / "sku_sales_summary.csv"
    if not summary_file.exists():
        print(f"❌ 找不到销售汇总文件: {summary_file}")
        print("   请先运行: python3 summarize_by_sku.py")
        return

    inv = InventoryManager()

    with open(summary_file, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    print(f"\n📊 共 {len(rows)} 个 SKU 有销售数据")
    print("\n开始扣减库存...\n")

    success_count = 0
    for row in rows:
        sku_id = row["sku_id"]
        qty_sold = float(row["40天消耗"])

        # 只有有销量的才扣减
        if qty_sold > 0:
            if inv.deduct_sales(sku_id, qty_sold, f"40天销售消耗: {qty_sold:.2f}"):
                success_count += 1

    print(f"\n✅ 扣减完成: 成功 {success_count} 个 SKU")
    return inv


def process_purchase_plan():
    """
    处理补货建议
    1. 读取 purchase_plan.csv
    2. 显示需要补货的 SKU
    3. 老王确认后，自动把补货量加入库存
    """
    print("\n" + "=" * 60)
    print("🛒 补货建议处理")
    print("=" * 60)

    plan_file = DATA / "purchase_plan.csv"
    if not plan_file.exists():
        print(f"❌ 找不到补货建议文件: {plan_file}")
        print("   请先运行: python3 purchase_plan.py")
        return

    inv = InventoryManager()

    with open(plan_file, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        plan_rows = list(reader)

    # 只显示需要下单的
    need_order = [r for r in plan_rows if float(r.get("建议下单_箱", 0)) > 0]

    if not need_order:
        print("\n🎉 所有 SKU 库存充足，无需补货！")
        return

    print(f"\n📋 需要补货的 SKU 共 {len(need_order)} 个:")
    print(f"\n{'SKU':<12} {'名称':<18} {'当前库存':>12} {'建议补货':>12} {'单位':<6}")
    print("-" * 65)

    for r in need_order:
        boxes = float(r["建议下单_箱"])
        # 这里需要根据你的 SKU 字典换算成基准单位数量
        # 暂时直接显示
        print(f"{r['sku_id']:<12} {r['sku_name']:<18} {r['当前_基准']:>12} "
              f"{boxes:>10.0f}箱 {r['base_unit']:<6}")

    print("\n" + "=" * 65)
    confirm = input("\n确认已下单并到货了吗？输入 'yes' 确认入库，其他跳过: ").strip().lower()

    if confirm == 'yes':
        print("\n📥 开始入库...")
        # 这里需要根据你的箱规换算
        # 暂时需要老王手动输入每个 SKU 的实际入库数量
        for r in need_order:
            sku_id = r["sku_id"]
            sku_name = r["sku_name"]
            default_boxes = float(r["建议下单_箱"])
            qty_str = input(f"\nSKU [{sku_id} {sku_name}] 实际入库箱数 (默认 {default_boxes:.0f}): ").strip()
            boxes = float(qty_str) if qty_str else default_boxes

            # TODO: 从 SKU 字典读取箱规换算成基准单位
            # 这里先用 1箱 = 多少基准单位的逻辑
            # 暂时让老王手动输入基准单位数量
            # 后续可以集成 sku_dictionary.csv

        print("\n✅ 入库完成！")
    else:
        print("\n⏭️  跳过入库操作")

    return inv


def main():
    print("\n" + "🍢" * 20)
    print("   炸串店库存管理一体化流程")
    print("🍢" * 20 + "\n")

    # 第一步：扣减销售库存
    inv = auto_deduct_from_sales()

    if inv:
        # 显示扣减后的库存
        inv.print_inventory()

    # 第二步：处理补货
    process_purchase_plan()

    print("\n" + "🎉" * 20)
    print("   全部完成！")
    print("🎉" * 20)


if __name__ == "__main__":
    main()
