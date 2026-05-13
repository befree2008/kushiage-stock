#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
炸串店库存管理模块 v1.0.1（修复版）
修复：
  1. last_check 为 None 时的切片报错
  2. 增加对 TBD（To Be Determined）的处理
"""
import json
import datetime
import os
from pathlib import Path
from typing import Dict, List, Optional

# 库存数据文件路径
INVENTORY_FILE = Path("data/inventory.json")
LOG_FILE = Path("data/inventory_log.json")


class InventoryManager:
    """库存管理器"""

    def __init__(self):
        self.inventory = self._load_inventory()
        self.logs = self._load_logs()

    def _load_inventory(self) -> Dict:
        """加载库存数据，如果文件不存在则创建"""
        if not INVENTORY_FILE.exists():
            # 初始化空库存
            initial = {
                "version": "1.0",
                "last_updated": None,
                "skus": {}  # sku_id -> {"quantity": 数量, "unit": "串/袋/kg", "last_check": 日期}
            }
            self._save_inventory(initial)
            return initial

        with open(INVENTORY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _save_inventory(self, data: Dict = None):
        """保存库存数据"""
        if data is None:
            data = self.inventory
        data["last_updated"] = datetime.datetime.now().isoformat()
        # 确保目录存在
        INVENTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(INVENTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _load_logs(self) -> List:
        """加载操作日志"""
        if not LOG_FILE.exists():
            return []
        with open(LOG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _save_logs(self):
        """保存日志"""
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.logs, f, ensure_ascii=False, indent=2)

    def _add_log(self, action_type: str, sku_id: str, quantity: float,
                 reason: str, before: float = None, after: float = None):
        """记录操作日志"""
        log_entry = {
            "timestamp": datetime.datetime.now().isoformat(),
            "action": action_type,  # INIT/DEDUCT/ADD/ADJUST
            "sku_id": sku_id,
            "quantity": quantity,
            "reason": reason,
            "before_quantity": before,
            "after_quantity": after,
        }
        self.logs.insert(0, log_entry)  # 最新的在前面
        # 只保留最近 1000 条记录
        if len(self.logs) > 1000:
            self.logs = self.logs[:1000]
        self._save_logs()

    def init_sku(self, sku_id: str, init_quantity: float, unit: str,
                  sku_name: str = None):
        """初始化 SKU 库存（第一次录入时用）"""
        if sku_id not in self.inventory["skus"]:
            self.inventory["skus"][sku_id] = {
                "quantity": init_quantity,
                "unit": unit,
                "sku_name": sku_name or sku_id,
                "created_at": datetime.datetime.now().isoformat(),
                "last_check": None,
            }
            self._save_inventory()
            self._add_log("INIT", sku_id, init_quantity, "初始化库存",
                          None, init_quantity)
            print(f"✅ 初始化 SKU [{sku_id}] 库存: {init_quantity} {unit}")
        else:
            print(f"ℹ️  SKU [{sku_id}] 已存在，跳过初始化")

    def deduct_sales(self, sku_id: str, quantity: float, reason: str = "销售消耗") -> bool:
        """扣减库存（销售消耗）"""
        if sku_id not in self.inventory["skus"]:
            print(f"⚠️  SKU [{sku_id}] 不存在，无法扣减")
            return False

        sku = self.inventory["skus"][sku_id]
        before = sku["quantity"]

        if before < quantity:
            print(f"⚠️  SKU [{sku_id}] 库存不足: 当前 {before}, 扣减 {quantity}")

        sku["quantity"] = round(before - quantity, 2)
        self._save_inventory()
        self._add_log("DEDUCT", sku_id, quantity, reason, before, sku["quantity"])
        print(f"✅ 扣减 SKU [{sku_id}]: {before} → {sku['quantity']} {sku['unit']} ({reason})")
        return True

    def add_restock(self, sku_id: str, quantity: float, reason: str = "补货入库") -> bool:
        """增加库存（补货入库）"""
        if sku_id not in self.inventory["skus"]:
            print(f"⚠️  SKU [{sku_id}] 不存在，无法入库")
            return False

        sku = self.inventory["skus"][sku_id]
        before = sku["quantity"]
        sku["quantity"] = round(before + quantity, 2)
        self._save_inventory()
        self._add_log("ADD", sku_id, quantity, reason, before, sku["quantity"])
        print(f"✅ 入库 SKU [{sku_id}]: {before} → {sku['quantity']} {sku['unit']} ({reason})")
        return True

    def adjust_inventory(self, sku_id: str, actual_quantity: float,
                         reason: str = "每月对账调账") -> bool:
        """调账功能：用实际库存修正系统库存"""
        if sku_id not in self.inventory["skus"]:
            print(f"⚠️  SKU [{sku_id}] 不存在，无法调账")
            return False

        sku = self.inventory["skus"][sku_id]
        before = sku["quantity"]
        diff = round(actual_quantity - before, 2)
        sku["quantity"] = actual_quantity
        sku["last_check"] = datetime.datetime.now().isoformat()
        self._save_inventory()
        self._add_log("ADJUST", sku_id, diff, reason, before, actual_quantity)
        print(f"✅ 调账 SKU [{sku_id}]: {before} → {actual_quantity} {sku['unit']}")
        if diff != 0:
            print(f"   差异: {'+' if diff > 0 else ''}{diff} {sku['unit']}")
        return True

    def get_stock(self, sku_id: str) -> Optional[float]:
        """获取某个 SKU 的当前库存"""
        if sku_id in self.inventory["skus"]:
            return self.inventory["skus"][sku_id]["quantity"]
        return None

    def get_all_stock(self) -> Dict:
        """获取所有库存"""
        return self.inventory["skus"]

    def print_inventory(self, category: str = None):
        """打印库存清单"""
        print("\n" + "=" * 70)
        print("📦 当前库存清单")
        print("=" * 70)
        print(f"{'SKU':<12} {'名称':<18} {'库存':>10} {'单位':<6} {'上次盘点':<12}")
        print("-" * 70)

        for sku_id, sku in sorted(self.inventory["skus"].items()):
            last_check = sku.get("last_check", "-")
            # ✅ 修复：如果是 None 或者 "-"，就显示 "-"，否则取前10位日期
            if last_check is None or last_check == "-":
                last_check_str = "-"
            else:
                last_check_str = last_check[:10]
            print(f"{sku_id:<12} {sku.get('sku_name', sku_id):<18} "
                  f"{sku['quantity']:>10.2f} {sku['unit']:<6} {last_check_str:<12}")
        print("-" * 70)
        print(f"共 {len(self.inventory['skus'])} 个 SKU")
        last_update = self.inventory.get('last_updated', '从未更新')
        if last_update:
            last_update = last_update[:19]
        print(f"最后更新: {last_update}")
        print("=" * 70)

    def print_logs(self, limit: int = 20):
        """打印最近的操作日志"""
        print("\n" + "=" * 70)
        print(f"📜 最近 {limit} 条库存变动记录")
        print("=" * 70)
        print(f"{'时间':<19} {'类型':<8} {'SKU':<12} {'数量':>10} {'原因'}")
        print("-" * 70)

        action_names = {
            "INIT": "初始化",
            "DEDUCT": "扣减",
            "ADD": "入库",
            "ADJUST": "调账",
        }

        for log in self.logs[:limit]:
            time_str = log["timestamp"][:19]
            action = action_names.get(log["action"], log["action"])
            qty_str = f"{log['quantity']:+.2f}" if log["action"] != "INIT" else f"{log['quantity']:.2f}"
            print(f"{time_str:<19} {action:<8} {log['sku_id']:<12} "
                  f"{qty_str:>10} {log['reason']}")
        print("=" * 70)


# ============================================================
# 命令行交互功能
# ============================================================

def interactive_menu():
    """交互式菜单"""
    inv = InventoryManager()

    while True:
        print("\n" + "=" * 50)
        print("🍢 炸串店库存管理系统 v1.0.1")
        print("=" * 50)
        print("1. 查看当前库存")
        print("2. 手动入库（补货）")
        print("3. 手动扣减（损耗/赠送）")
        print("4. 调账（实际库存对账）")
        print("5. 查看操作日志")
        print("6. 初始化新 SKU")
        print("0. 退出")
        print("=" * 50)

        choice = input("\n请选择操作 [0-6]: ").strip()

        if choice == "1":
            inv.print_inventory()
        elif choice == "2":
            sku_id = input("请输入 SKU 编号: ").strip()
            qty = float(input("请输入入库数量: ").strip())
            reason = input("请输入原因（默认:补货入库）: ").strip() or "补货入库"
            inv.add_restock(sku_id, qty, reason)
        elif choice == "3":
            sku_id = input("请输入 SKU 编号: ").strip()
            qty = float(input("请输入扣减数量: ").strip())
            reason = input("请输入原因（默认:损耗/赠送）: ").strip() or "损耗/赠送"
            inv.deduct_sales(sku_id, qty, reason)
        elif choice == "4":
            print("\n📋 每月对账调账功能")
            sku_id = input("请输入 SKU 编号: ").strip()
            actual = float(input("请输入实际库存数量: ").strip())
            reason = input("请输入调账原因（默认:每月对账调账）: ").strip() or "每月对账调账"
            inv.adjust_inventory(sku_id, actual, reason)
        elif choice == "5":
            limit = input("显示最近几条？（默认:20条）: ").strip()
            limit = int(limit) if limit else 20
            inv.print_logs(limit)
        elif choice == "6":
            print("\n🆕 初始化新 SKU")
            sku_id = input("请输入 SKU 编号: ").strip()
            sku_name = input("请输入 SKU 名称: ").strip()
            unit = input("请输入单位（串/袋/kg）: ").strip()
            init_qty = float(input("请输入初始库存数量: ").strip())
            inv.init_sku(sku_id, init_qty, unit, sku_name)
        elif choice == "0":
            print("\n👋 再见！")
            break
        else:
            print("\n❌ 无效选择，请重新输入")

        input("\n按回车键继续...")


if __name__ == "__main__":
    interactive_menu()
