#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
炸串店每周一键运行脚本
老王你每周只需要运行这一个脚本就搞定了！

流程：
  1. 汇总销售数据（summarize_by_sku）
  2. 计算调料消耗（seasoning_calc）
  3. 扣减库存（根据销售数据）
  4. 重算安全库存（recalc_safe_stock）
  5. 生成补货建议（purchase_plan）
  6. 显示当前库存清单
"""
import subprocess
import sys
import os
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent


def run_script(script_name: str, description: str) -> bool:
    """运行一个脚本"""
    print("\n" + "=" * 70)
    print(f"🚀 正在运行: {description}")
    print("=" * 70)

    script_path = SCRIPT_DIR / script_name
    if not script_path.exists():
        print(f"❌ 找不到脚本: {script_path}")
        return False

    try:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=str(SCRIPT_DIR),
            capture_output=False,
            text=True
        )
        success = result.returncode == 0
        print(f"\n{'✅' if success else '❌'} {description} 完成")
        return success
    except Exception as e:
        print(f"❌ 运行失败: {e}")
        return False


def pause():
    """暂停一下让老王看结果"""
    input("\n按回车键继续下一步...")


def main():
    print("\n" + "🍢" * 25)
    print("   炸串店每周库存管理 - 一键运行 v1.0")
    print("🍢" * 25 + "\n")

    print("📋 将要执行的流程:")
    print("  1. 汇总销售数据")
    print("  2. 计算调料消耗")
    print("  3. 自动扣减库存")
    print("  4. 重算安全库存 + 生成盘货模板")
    print("  5. 生成补货建议")
    print("  6. 显示当前库存清单")
    print("  7. 交互式入库/调账\n")

    confirm = input("确认开始吗？ [Y/n]: ").strip().lower()
    if confirm not in ['', 'y', 'yes']:
        print("\n👋 已取消")
        return

    # 1. 汇总销售数据
    run_script("summarize_by_sku.py", "销售数据汇总")
    pause()

    # 2. 计算调料消耗
    run_script("seasoning_calc.py", "调料消耗计算")
    pause()

    # 3. 扣减库存
    print("\n" + "=" * 70)
    print("📉 步骤 3: 自动扣减销售库存")
    print("=" * 70)

    # 导入库存模块
    sys.path.insert(0, str(SCRIPT_DIR))
    from inventory_integration import auto_deduct_from_sales
    inv = auto_deduct_from_sales()

    # 显示扣减后的库存
    if inv:
        inv.print_inventory()
    else:
        print("❌ 库存扣减失败或已取消")
        pause()
        return

    pause()

    # 4. 重算安全库存
    run_script("recalc_safe_stock.py", "安全库存重算 + 盘货模板生成")
    pause()

    # 5. 生成补货建议
    run_script("purchase_plan.py", "补货建议生成")
    pause()

    # 6. 显示最终库存
    print("\n" + "=" * 70)
    print("📦 步骤 6: 当前库存清单")
    print("=" * 70)
    if inv:
        inv.print_inventory()
    else:
        from inventory_manager import InventoryManager
        InventoryManager().print_inventory()

    pause()

    # 7. 交互式菜单（入库/调账）
    print("\n" + "=" * 70)
    print("🎮 步骤 7: 库存管理（入库/调账）")
    print("=" * 70)

    while True:
        print("\n请选择:")
        print("  1. 补货入库（货到了）")
        print("  2. 调账（实际库存对账）")
        print("  3. 查看操作日志")
        print("  0. 完成，退出")

        choice = input("\n请选择 [0-3]: ").strip()

        if choice == "0":
            break
        elif choice == "1":
            from inventory_manager import InventoryManager
            inv = InventoryManager()
            sku_id = input("SKU 编号: ").strip()
            qty = float(input("入库数量: ").strip())
            reason = input("原因（默认:补货入库）: ").strip() or "补货入库"
            inv.add_restock(sku_id, qty, reason)
        elif choice == "2":
            from inventory_manager import InventoryManager
            inv = InventoryManager()
            sku_id = input("SKU 编号: ").strip()
            actual = float(input("实际库存数量: ").strip())
            reason = input("原因（默认:对账调账）: ").strip() or "对账调账"
            inv.adjust_inventory(sku_id, actual, reason)
        elif choice == "3":
            from inventory_manager import InventoryManager
            InventoryManager().print_logs(20)
        else:
            print("❌ 无效选择")

        pause()

    print("\n" + "🎉" * 25)
    print("   本周库存管理全部完成！")
    print("🎉" * 25)
    print("\n📄 生成的文件:")
    print(f"  - {SCRIPT_DIR}/data/inventory.json      库存数据文件")
    print(f"  - {SCRIPT_DIR}/data/inventory_log.json  操作日志")
    print(f"  - {SCRIPT_DIR}/data/purchase_plan.csv   补货建议")
    print(f"  - {SCRIPT_DIR}/data/safe_stock_diff.csv 安全库存差异")
    print("\n下周见！👋")


if __name__ == "__main__":
    main()
