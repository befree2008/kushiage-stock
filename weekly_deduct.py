#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
合并销售扣减 + 间接消耗（调料/包材）扣减脚本
================================================
v1.0 2026-05-17 by 蜜蜡
  - 把 inventory_integration.auto_deduct_from_sales + deduct_indirect.main 合并为一步
  - 输入：1 份销售汇总 sku_sales_summary.csv（必须含 # sales_start_date / sales_end_date / sales_days 元数据）
  - 三类扣减：油炸品（销售直扣）+ 调料（日均×天数）+ 包材（日均×天数）
  - 防呆：last_sales_deduction 和 last_indirect_deduction 同时检查（共享一个区间）
  - 演练：--dry-run 不写库存
  - 强制：--force 跳过期间防呆和警告

数据来源：
  data/sku_sales_summary.csv  —— 销售汇总（油炸品扣减 + 元数据来源）
  data/seasoning_daily.csv    —— 调料日均消耗（g/天）
  data/packaging_daily.csv    —— 包材日均消耗（个/天）

跳过分类：蔬菜（当天进当天用，避免负数）

使用：
  python3 weekly_deduct.py                # 真扣减
  python3 weekly_deduct.py --dry-run      # 演练
  python3 weekly_deduct.py --force        # 跳过日期防呆
  python3 weekly_deduct.py --force --dry-run
"""
from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from inventory_manager import InventoryManager  # noqa: E402

DATA = Path("data")
SUMMARY_FILE = DATA / "sku_sales_summary.csv"
SEASONING_FILE = DATA / "seasoning_daily.csv"
PACKAGING_FILE = DATA / "packaging_daily.csv"

# 销售汇总里不走库存扣减的分类（菜叶等当天进当天用，本身不在长期库存里）
SKIP_CATEGORIES = {"蔬菜"}


# ----------------------------- 解析 -----------------------------

def read_summary_meta(path: Path) -> dict:
    """读销售汇总顶部 # 元数据，返回 dict"""
    meta: dict = {}
    if not path.exists():
        return meta
    with path.open(encoding="utf-8-sig") as f:
        for line in f:
            if not line.startswith("#"):
                break
            try:
                key, val = line.lstrip("# ").strip().split(",", 1)
                meta[key.strip()] = val.strip()
            except ValueError:
                continue
    return meta


def read_summary_rows(path: Path) -> list[dict]:
    """读销售汇总（跳过 # 元数据行）"""
    rows: list[dict] = []
    with path.open(encoding="utf-8-sig") as f:
        reader = csv.DictReader(r for r in f if not r.startswith("#"))
        rows = list(reader)
    return rows


def load_daily_csv(path: Path, qty_field: str) -> list[dict]:
    """读取调料/包材的 daily 消耗 CSV"""
    rows: list[dict] = []
    if not path.exists():
        print(f"⚠️  {path} 不存在，跳过该类")
        return rows
    with path.open(encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            try:
                qty = float(row.get(qty_field, 0) or 0)
            except ValueError:
                qty = 0.0
            if qty <= 0:
                continue
            rows.append({
                "sku_id": row["sku_id"].strip(),
                "sku_name": row.get("sku_name", "").strip(),
                "daily_qty": qty,
            })
    return rows


# ----------------------------- 校验 -----------------------------

def validate_dates(inv: InventoryManager, start: str, end: str, force: bool, dry_run: bool = False) -> bool:
    """校验销售扣减 + 间接扣减的日期防呆。返回 True=可继续
    dry_run=True 时跳过交互确认（不写库存，没有数据风险）
    """
    # 1. 共用 InventoryManager 的销售日期校验（包含基础重叠检测）
    validation = inv.validate_sales_date_range(start, end)
    if validation["errors"]:
        print("\n❌ 销售扣减日期校验失败：")
        for e in validation["errors"]:
            print(f"   {e}")
        if not force:
            print("\n   要强制扣减请加 --force（建议先回滚库存）")
            return False
        print("   --force 已启用，忽略错误继续")

    if validation["warnings"]:
        print("\n⚠️  注意：")
        for w in validation["warnings"]:
            print(f"   {w}")
        if not force and not dry_run:
            ans = input("\n   确认继续？(yes/no): ").strip().lower()
            if ans != "yes":
                return False

    # 2. 单独检查间接扣减的同期防呆
    last_indir = inv.inventory.get("last_indirect_deduction")
    if last_indir and not force:
        if last_indir.get("start_date") == start and last_indir.get("end_date") == end:
            print(f"\n❌ 本期 ({start}~{end}) 已扣减过间接消耗:")
            print(f"   上次扣减时间: {last_indir.get('deducted_at')}")
            print(f"   要重新扣，加 --force（建议先回滚库存）")
            return False

    return True


# ----------------------------- 计划 -----------------------------

def build_plan(rows_sales: list[dict], rows_seasoning: list[dict],
               rows_packaging: list[dict], days: int,
               inv: InventoryManager) -> list[dict]:
    """生成完整扣减计划，返回 [{type, sku_id, sku_name, qty, before, after, unit, reason}]"""
    plan: list[dict] = []
    inv_now = inv.inventory["skus"]

    # 1. 油炸品（含部分调料和包材都可能在此，因销售汇总以 SKU 为粒度）
    for row in rows_sales:
        sku_id = row["sku_id"].strip()
        category = row.get("category", "").strip()
        try:
            qty = float(row.get("本期消耗") or row.get("40天消耗") or 0)
        except ValueError:
            qty = 0
        if qty <= 0:
            continue
        if category in SKIP_CATEGORIES:
            plan.append({
                "type": "跳过",
                "sku_id": sku_id, "sku_name": row.get("sku_name", ""),
                "category": category, "qty": qty, "before": None, "after": None,
                "unit": row.get("base_unit", ""), "reason": f"分类={category}（跳过）",
                "skip": True,
            })
            continue
        cur = inv_now.get(sku_id, {})
        before = float(cur.get("quantity", 0))
        after = before - qty
        plan.append({
            "type": "销售",
            "sku_id": sku_id, "sku_name": row.get("sku_name", ""),
            "category": category, "qty": qty,
            "before": before, "after": after, "unit": cur.get("unit", "?"),
            "reason": f"销售消耗: {qty:.2f}",
            "skip": False,
        })

    # 2. 调料（按日均×天数）
    for it in rows_seasoning:
        sku_id = it["sku_id"]
        qty = it["daily_qty"] * days
        cur = inv_now.get(sku_id, {})
        before = float(cur.get("quantity", 0))
        after = before - qty
        plan.append({
            "type": "调料",
            "sku_id": sku_id, "sku_name": it["sku_name"],
            "category": "调料", "qty": qty,
            "before": before, "after": after, "unit": cur.get("unit", "?"),
            "reason": f"调料消耗: {qty:.2f} (日均{it['daily_qty']:.1f} × {days}天)",
            "skip": False,
        })

    # 3. 包材（按日均×天数）
    for it in rows_packaging:
        sku_id = it["sku_id"]
        qty = it["daily_qty"] * days
        cur = inv_now.get(sku_id, {})
        before = float(cur.get("quantity", 0))
        after = before - qty
        plan.append({
            "type": "包材",
            "sku_id": sku_id, "sku_name": it["sku_name"],
            "category": "包材", "qty": qty,
            "before": before, "after": after, "unit": cur.get("unit", "?"),
            "reason": f"包材消耗: {qty:.2f} (日均{it['daily_qty']:.1f} × {days}天)",
            "skip": False,
        })

    return plan


# ----------------------------- 展示 -----------------------------

def print_plan(plan: list[dict], days: int):
    print("\n" + "=" * 100)
    print(f"{'类型':<6}{'SKU':<10}{'名称':<20}{'扣减量':>12}{'单位':<5}"
          f"{'扣前':>10}{'扣后':>10}  备注")
    print("-" * 100)
    summary = {"销售": 0, "调料": 0, "包材": 0, "跳过": 0}
    warns = 0
    for p in plan:
        warn = ""
        if not p["skip"] and p["after"] is not None and p["after"] < 0:
            warn = " ⚠️负"
            warns += 1
        before = f"{p['before']:.1f}" if p["before"] is not None else "-"
        after = f"{p['after']:.1f}" if p["after"] is not None else "-"
        print(f"{p['type']:<6}{p['sku_id']:<10}{p['sku_name'][:18]:<20}"
              f"{p['qty']:>12.2f}{p['unit']:<5}{before:>10}{after:>10}{warn}  {p['reason'][:30]}")
        summary[p["type"]] = summary.get(p["type"], 0) + 1
    print("-" * 100)
    print(f"小计：销售扣减 {summary['销售']} | 调料 {summary['调料']} | 包材 {summary['包材']} "
          f"| 跳过(蔬菜) {summary['跳过']} | 扣后为负 {warns} 条")


# ----------------------------- 执行 -----------------------------

def execute_plan(plan: list[dict], inv: InventoryManager, start: str, end: str, days: int):
    success = 0
    fail = 0
    for p in plan:
        if p["skip"]:
            continue
        # 复用 deduct_sales（不限制扣到负数，包材/调料也走这条路径）
        reason = f"[{p['type']}] {p['reason']} ({start}~{end})"
        ok = inv.deduct_sales(p["sku_id"], p["qty"], reason)
        if ok:
            success += 1
        else:
            fail += 1
    # 同时记录两个时间锚点（合并扣减后这两个区间一定一致）
    inv.record_sales_deduction(start, end, days)
    inv.inventory["last_indirect_deduction"] = {
        "start_date": start,
        "end_date": end,
        "days": days,
        "deducted_at": datetime.now().isoformat(),
    }
    inv._save_inventory()
    return success, fail


# ----------------------------- main -----------------------------

def main():
    ap = argparse.ArgumentParser(
        description="合并销售扣减 + 调料/包材扣减（一份销售数据 → 三类同时扣）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("--force", action="store_true", help="跳过日期防呆和确认")
    ap.add_argument("--dry-run", action="store_true", help="只演练，不写库存")
    args = ap.parse_args()

    print("=" * 70)
    print("🔄 周度合并扣减（销售 + 调料 + 包材）")
    print("=" * 70)

    # 1. 读元数据
    if not SUMMARY_FILE.exists():
        print(f"❌ 找不到销售汇总: {SUMMARY_FILE}")
        print("   请先跑 summarize_by_sku.py")
        sys.exit(1)
    meta = read_summary_meta(SUMMARY_FILE)
    start = meta.get("sales_start_date")
    end = meta.get("sales_end_date")
    try:
        days = int(meta.get("sales_days", 0) or 0)
    except ValueError:
        days = 0
    if not (start and end and days > 0):
        print(f"❌ {SUMMARY_FILE} 缺少 sales_start_date / sales_end_date / sales_days 元数据")
        sys.exit(1)
    print(f"\n📅 销售期: {start} ~ {end} ({days} 天)")

    # 2. 读三份数据
    rows_sales = read_summary_rows(SUMMARY_FILE)
    rows_seasoning = load_daily_csv(SEASONING_FILE, "日均消耗_g")
    rows_packaging = load_daily_csv(PACKAGING_FILE, "日均消耗")
    print(f"   销售 SKU: {len(rows_sales)} | 调料: {len(rows_seasoning)} | 包材: {len(rows_packaging)}")

    # 3. 校验
    inv = InventoryManager()
    last_sales = inv.get_last_sales_deduction()
    last_indir = inv.inventory.get("last_indirect_deduction")
    if last_sales:
        print(f"   上次销售扣减: {last_sales['start_date']} ~ {last_sales['end_date']}")
    if last_indir:
        print(f"   上次间接扣减: {last_indir['start_date']} ~ {last_indir['end_date']}")

    if not validate_dates(inv, start, end, args.force, dry_run=args.dry_run):
        print("\n❌ 已取消")
        sys.exit(1)

    # 4. 构建计划
    plan = build_plan(rows_sales, rows_seasoning, rows_packaging, days, inv)
    print_plan(plan, days)

    if args.dry_run:
        print("\n🧪 演练模式，未写入库存。去掉 --dry-run 真扣减。")
        return

    # 5. 执行
    print("\n📥 执行扣减...")
    success, fail = execute_plan(plan, inv, start, end, days)
    print(f"\n✅ 完成: 成功 {success} 项，失败 {fail} 项")
    print(f"   已记录 last_sales_deduction + last_indirect_deduction: {start} ~ {end}")


if __name__ == "__main__":
    main()
