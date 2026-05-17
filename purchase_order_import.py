#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
进货单通用入库脚本 v3.0
==========================================
工作流：
  1. 进货单图片 → OCR → 生成进货 CSV
  2. 本脚本读 CSV → 按 sku_dictionary 匹配 SKU
  3. 校验全部命中后 → 批量入库（写日志、备份）

使用：
  python purchase_order_import.py <order.csv> [--order-no DQK2026...] [--dry-run] [--yes]

进货 CSV 格式（见 data/purchase_order_template.csv）：
  item_name,boxes,per_box_base,note
  小串纸桶(小号),1,500,10条/箱 × 50个/条

匹配规则（优先级从高到低）：
  1. 精确匹配 sku_name
  2. 精确匹配 aliases（分号分隔，可选列）
  3. 包含匹配 sku_name 或 aliases（双向，子串）
匹配不到/匹配多个 → 报错并列出待确认项，不执行入库。
"""
from __future__ import annotations

import argparse
import csv
import datetime
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from inventory_manager import InventoryManager  # noqa: E402

DATA_DIR = SCRIPT_DIR / "data"
SKU_DICT_FILE = DATA_DIR / "sku_dictionary.csv"


# ============================================================
# 数据结构
# ============================================================

class PurchaseLine:
    """进货单一行"""
    __slots__ = ("item_name", "boxes", "per_box_base", "note",
                 "matched_sku", "match_reason")

    def __init__(self, item_name: str, boxes: float,
                 per_box_base: float, note: str = ""):
        self.item_name = item_name.strip()
        self.boxes = boxes
        self.per_box_base = per_box_base
        self.note = note.strip()
        self.matched_sku: Optional[Dict] = None
        self.match_reason: str = ""

    @property
    def qty(self) -> float:
        """折算成 base_unit 的总数量"""
        return self.boxes * self.per_box_base


# ============================================================
# 加载 SKU 字典
# ============================================================

def load_sku_dictionary() -> List[Dict]:
    """加载 SKU 字典，返回 list of dict。"""
    if not SKU_DICT_FILE.exists():
        sys.exit(f"❌ SKU 字典不存在: {SKU_DICT_FILE}")
    with open(SKU_DICT_FILE, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        return list(reader)


def parse_aliases(raw: str) -> List[str]:
    """解析 aliases 字段。支持中文分号、英文分号、|、逗号。"""
    if not raw:
        return []
    for sep in ("；", ";", "|"):
        raw = raw.replace(sep, ",")
    return [a.strip() for a in raw.split(",") if a.strip()]


# ============================================================
# SKU 匹配
# ============================================================

def match_sku(item_name: str, skus: List[Dict]) -> Tuple[List[Dict], str]:
    """
    匹配 SKU。返回 (候选列表, 匹配方式说明)。
    候选 == 1 → 唯一命中；> 1 → 歧义；== 0 → 未命中。
    """
    name = item_name.strip()
    name_low = name.lower()

    # 1. 精确匹配 sku_name
    exact = [s for s in skus if s["sku_name"].strip() == name]
    if exact:
        return exact, "精确匹配 sku_name"

    # 2. 精确匹配 aliases
    alias_hits = []
    for s in skus:
        aliases = parse_aliases(s.get("aliases", ""))
        if name in aliases:
            alias_hits.append(s)
    if alias_hits:
        return alias_hits, "精确匹配 aliases"

    # 3. 包含匹配（双向子串）
    contain_hits = []
    for s in skus:
        candidates = [s["sku_name"]] + parse_aliases(s.get("aliases", ""))
        for c in candidates:
            c = c.strip()
            if not c:
                continue
            if c in name or name in c or c.lower() in name_low or name_low in c.lower():
                contain_hits.append(s)
                break
    if contain_hits:
        return contain_hits, "包含匹配（子串）"

    return [], "未匹配"


# ============================================================
# 加载进货单
# ============================================================

def load_purchase_order(csv_path: Path) -> List[PurchaseLine]:
    """加载进货单 CSV，跳过空行和 # 注释行。"""
    if not csv_path.exists():
        sys.exit(f"❌ 进货单文件不存在: {csv_path}")

    lines: List[PurchaseLine] = []
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row_no, row in enumerate(reader, start=2):  # 表头是第 1 行
            # 跳过空行
            if not row or all(not (v or "").strip() for v in row.values()):
                continue
            item_name = (row.get("item_name") or "").strip()
            # 跳过注释行
            if not item_name or item_name.startswith("#"):
                continue

            try:
                boxes = float(row.get("boxes") or 0)
                per_box = float(row.get("per_box_base") or 0)
            except ValueError as e:
                sys.exit(f"❌ 第 {row_no} 行数值解析失败: {row} -> {e}")

            if boxes <= 0 or per_box <= 0:
                sys.exit(f"❌ 第 {row_no} 行 boxes 或 per_box_base 必须 > 0: {row}")

            lines.append(PurchaseLine(
                item_name=item_name,
                boxes=boxes,
                per_box_base=per_box,
                note=(row.get("note") or "").strip(),
            ))
    if not lines:
        sys.exit(f"❌ 进货单为空: {csv_path}")
    return lines


# ============================================================
# 备份 & 报告
# ============================================================

def backup_inventory():
    """入库前备份 inventory.json。"""
    src = DATA_DIR / "inventory.json"
    if not src.exists():
        return None
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    dst = DATA_DIR / f"inventory.json.before_purchase_{ts}"
    shutil.copy2(src, dst)
    return dst


def print_match_report(lines: List[PurchaseLine], inv: InventoryManager):
    """打印匹配结果表。"""
    print("\n" + "=" * 90)
    print(f"{'进货单货品':<24} {'匹配 SKU':<10} {'SKU 名称':<18} "
          f"{'箱数':>6} {'入库数':>10} {'单位':<6} {'当前库存':>10}")
    print("-" * 90)
    for line in lines:
        sku = line.matched_sku
        if sku is None:
            print(f"{line.item_name:<24} {'❌未匹配':<10}")
            continue
        sku_id = sku["sku_id"]
        cur = inv.inventory["skus"].get(sku_id, {}).get("quantity", 0)
        unit = sku.get("base_unit") or inv.inventory["skus"].get(sku_id, {}).get("unit", "?")
        print(f"{line.item_name:<24} {sku_id:<10} {sku['sku_name']:<18} "
              f"{line.boxes:>6g} {line.qty:>10.2f} {unit:<6} {cur:>10.2f}")
    print("=" * 90)


# ============================================================
# 主流程
# ============================================================

def main():
    ap = argparse.ArgumentParser(description="进货单通用入库脚本")
    ap.add_argument("order_csv", help="进货单 CSV 路径")
    ap.add_argument("--order-no", default="", help="进货单号（写入日志原因）")
    ap.add_argument("--dry-run", action="store_true",
                    help="只演练匹配，不写库存")
    ap.add_argument("--yes", "-y", action="store_true",
                    help="跳过确认提示直接入库")
    args = ap.parse_args()

    order_csv = Path(args.order_csv)
    print("=" * 70)
    print("📦 进货单通用入库 v3.0")
    print("=" * 70)
    print(f"进货单文件: {order_csv}")
    if args.order_no:
        print(f"单号: {args.order_no}")
    if args.dry_run:
        print("🧪 演练模式（不会修改库存）")
    print()

    # 1. 加载数据
    skus = load_sku_dictionary()
    lines = load_purchase_order(order_csv)
    print(f"读取进货单 {len(lines)} 行，SKU 字典 {len(skus)} 条")

    # 2. 匹配
    unmatched: List[PurchaseLine] = []
    ambiguous: List[Tuple[PurchaseLine, List[Dict]]] = []
    for line in lines:
        candidates, reason = match_sku(line.item_name, skus)
        if len(candidates) == 1:
            line.matched_sku = candidates[0]
            line.match_reason = reason
        elif len(candidates) > 1:
            ambiguous.append((line, candidates))
        else:
            unmatched.append(line)

    # 3. 加载库存（用于显示当前数量）
    inv = InventoryManager()
    print_match_report(lines, inv)

    # 4. 阻断条件：有歧义或未匹配
    if ambiguous:
        print("\n⚠️ 以下货品匹配到多个 SKU，请通过 aliases 或修改进货单消除歧义：")
        for line, cands in ambiguous:
            ids = ", ".join(f"{c['sku_id']}({c['sku_name']})" for c in cands)
            print(f"  - {line.item_name}  →  {ids}")
    if unmatched:
        print("\n❌ 以下货品未匹配到 SKU：")
        for line in unmatched:
            print(f"  - {line.item_name}（备注: {line.note}）")
        print("\n💡 解决方法：")
        print("   1) 在 sku_dictionary.csv 增加 aliases 列，把进货单上的别名补进去")
        print("   2) 或修改进货单 CSV 的 item_name 与字典对齐")

    if ambiguous or unmatched:
        sys.exit(1)

    # 5. 确认
    if args.dry_run:
        print("\n✅ 演练完成，全部命中。去掉 --dry-run 执行真实入库。")
        return

    if not args.yes:
        ans = input("\n确认执行入库？[y/N]: ").strip().lower()
        if ans not in ("y", "yes"):
            print("已取消。")
            return

    # 6. 备份
    bak = backup_inventory()
    if bak:
        print(f"📁 已备份: {bak.name}")

    # 7. 入库
    print("\n" + "=" * 70)
    print("📥 执行入库")
    print("=" * 70)
    success = 0
    failed: List[str] = []
    for line in lines:
        sku = line.matched_sku
        sku_id = sku["sku_id"]
        unit = sku.get("base_unit", "")
        order_tag = f", 单号 {args.order_no}" if args.order_no else ""
        reason = (
            f"进货单入库: {line.boxes:g}箱 × {line.per_box_base:g}{unit}/箱"
            f"{order_tag}"
        )
        if line.note:
            reason += f" [{line.note}]"

        # 库存中 SKU 不存在则自动初始化
        if sku_id not in inv.inventory["skus"]:
            print(f"ℹ️  SKU [{sku_id}] {sku['sku_name']} 在库存中不存在，自动初始化为 0 {unit}")
            inv.init_sku(sku_id, 0, unit, sku["sku_name"])

        if inv.add_restock(sku_id, line.qty, reason):
            success += 1
        else:
            failed.append(f"{sku_id} {sku['sku_name']}")

    # 8. 总结
    print("\n" + "=" * 70)
    print(f"✅ 入库完成: {success}/{len(lines)}")
    if failed:
        print("❌ 失败项:")
        for f in failed:
            print(f"  - {f}")
    print("=" * 70)
    inv.print_inventory()


if __name__ == "__main__":
    main()
