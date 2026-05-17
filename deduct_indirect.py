#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
间接消耗扣减脚本（调料 + 包材）
======================================
背景：
  调料和包材不会出现在销售汇总里（菜品销量 → 直接扣减不到它们），
  必须按"日均消耗 × 销售期天数"独立扣减。

数据来源：
  data/seasoning_daily.csv   —— 字段：sku_id, 日均消耗_g
  data/packaging_daily.csv   —— 字段：sku_id, 日均消耗（个/天）

销售期天数：
  从 data/sku_sales_summary.csv 顶部元数据 "# sales_days,N" 读取，
  与 inventory_integration.py 走同一份汇总，避免日期对不上。

扣减原则：
  - 不重复扣：last_indirect_deduction 字段记录上次扣减区间，与本次区间重合则中止
  - 单位一致：调料按 g 扣（base_unit=g），包材按 个 扣（base_unit=个）
  - 库存允许扣到负数（与销售扣减一致），但会打 ⚠️ 提示

用法：
  python3 deduct_indirect.py [--force] [--dry-run]
"""
from __future__ import annotations

import argparse
import csv
import math
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from inventory_manager import InventoryManager  # noqa: E402

DATA = Path("data")
SUMMARY_FILE = DATA / "sku_sales_summary.csv"
SEASONING_FILE = DATA / "seasoning_daily.csv"
PACKAGING_FILE = DATA / "packaging_daily.csv"


def read_summary_meta(path: Path) -> dict:
    """读销售汇总顶部元数据（# 开头）"""
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


def load_daily_csv(path: Path, qty_field: str) -> list[dict]:
    """读取 daily 消耗 CSV，返回 [{sku_id, sku_name, daily_qty}]"""
    rows: list[dict] = []
    if not path.exists():
        print(f"⚠️  {path} 不存在，跳过")
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="忽略日期重复检测，强制扣减")
    ap.add_argument("--dry-run", action="store_true", help="只演练，不写库存")
    args = ap.parse_args()

    print("=" * 70)
    print("🔄 间接消耗扣减（调料 + 包材）")
    print("=" * 70)

    # ============ 1. 读销售期天数 ============
    meta = read_summary_meta(SUMMARY_FILE)
    start = meta.get("sales_start_date")
    end = meta.get("sales_end_date")
    days = int(meta.get("sales_days", 0) or 0)
    if not (start and end and days > 0):
        print(f"❌ {SUMMARY_FILE} 缺少 sales_days/start/end 元数据，请先跑 summarize_by_sku.py")
        sys.exit(1)
    print(f"\n📅 销售期: {start} ~ {end} ({days} 天)")

    # ============ 2. 读两份消耗 CSV ============
    seasoning = load_daily_csv(SEASONING_FILE, "日均消耗_g")  # g/天
    packaging = load_daily_csv(PACKAGING_FILE, "日均消耗")     # 个/天
    print(f"   调料 {len(seasoning)} 项，包材 {len(packaging)} 项")

    # ============ 3. 防呆：检测是否已扣过本期 ============
    inv = InventoryManager()
    last = inv.inventory.get("last_indirect_deduction")
    if last and not args.force:
        if last.get("start_date") == start and last.get("end_date") == end:
            print(f"\n❌ 本期 ({start}~{end}) 已扣减过间接消耗:")
            print(f"   上次扣减时间: {last.get('deducted_at')}")
            print(f"   要重新扣，加 --force（建议先回滚库存）")
            sys.exit(1)
        else:
            print(f"   上次间接扣减: {last.get('start_date')} ~ {last.get('end_date')}")

    # ============ 4. 演练 / 实扣 ============
    print("\n" + "=" * 90)
    print(f"{'类型':<6}{'SKU':<10}{'名称':<20}{'日均':>10}{'×天数':>8}{'扣减量':>12}{'扣后库存':>14}")
    print("-" * 90)

    # 拉一遍当前库存做预览
    inv_now = inv.inventory["skus"]
    plan: list[tuple[str, dict, float]] = []
    for typ, items in [("调料", seasoning), ("包材", packaging)]:
        for it in items:
            sku_id = it["sku_id"]
            qty = it["daily_qty"] * days
            cur = float(inv_now.get(sku_id, {}).get("quantity", 0))
            after = cur - qty
            unit = inv_now.get(sku_id, {}).get("unit", "?")
            warn = " ⚠️" if after < 0 else ""
            print(f"{typ:<6}{sku_id:<10}{it['sku_name']:<20}"
                  f"{it['daily_qty']:>10.1f}{days:>8d}"
                  f"{qty:>10.1f}{unit:<2}{after:>12.1f}{warn}")
            plan.append((typ, it, qty))

    print("=" * 90)
    print(f"合计 {len(plan)} 项 SKU 待扣")

    if args.dry_run:
        print("\n🧪 演练模式，未写入库存。去掉 --dry-run 真实扣减。")
        return

    # ============ 5. 执行扣减 ============
    print("\n📥 执行扣减...")
    success = 0
    for typ, it, qty in plan:
        reason = f"{typ}消耗 {start}~{end}: {qty:.2f} (日均{it['daily_qty']:.1f} × {days}天)"
        if inv.deduct_sales(it["sku_id"], qty, reason):
            success += 1

    # ============ 6. 记录本期已扣减 ============
    from datetime import datetime
    inv.inventory["last_indirect_deduction"] = {
        "start_date": start,
        "end_date": end,
        "days": days,
        "deducted_at": datetime.now().isoformat(),
    }
    inv._save_inventory()

    print(f"\n✅ 间接消耗扣减完成: {success}/{len(plan)}")
    print(f"   已记录 last_indirect_deduction: {start} ~ {end}")


if __name__ == "__main__":
    main()
