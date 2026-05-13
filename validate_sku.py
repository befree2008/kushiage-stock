#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SKU 字典一致性校验
------------------
对 sku_dictionary.csv 做 5 类检查：
  1. sku_id 是否唯一、是否连续
  2. purchase_units 图是否能走到 base_unit（连通性）
  3. purchase_units 的换算链与 notes 描述是否一致
  4. sale_units 的单位是否都能换算到 base_unit
  5. 同 category 的基准单位/安全库存是否统一（仅提示）
"""

from __future__ import annotations
import csv
import json
import re
import sys
from collections import defaultdict, Counter
from pathlib import Path


def parse_notes_chain(notes: str) -> list[tuple[float, str, str]]:
    """从 notes 里解析出 '10串/把' 这种 (rate, from, to) 三元组。
    例: '10串/把 | 20把/袋 | 10袋/箱' →
        [(10,串,把), (20,把,袋), (10,袋,箱)]
    注意 notes 的写法是 "数量+被装单位/装载单位"，即 rate 个被装单位 = 1 装载单位
    """
    chain = []
    for seg in notes.split("|"):
        seg = seg.strip()
        if not seg:
            continue
        m = re.match(r"([\d.]+)\s*([^\s/]+)\s*/\s*(\S+)", seg)
        if m:
            rate, sub, cont = m.groups()
            chain.append((float(rate), sub, cont))
    return chain


def graph_to_base(purchase: dict, base_unit: str) -> tuple[bool, dict]:
    """从 purchase_units 图出发，计算每个单位 → base_unit 的系数。
    返回 (是否连通, {unit: base_per_unit})
    """
    # 图：from_unit -> (to_unit, rate)  含义："1 from_unit = rate to_unit"
    edges = {}
    units = {base_unit}
    for from_u, info in purchase.items():
        edges[from_u] = (info["to"], float(info["rate"]))
        units.add(from_u)
        units.add(info["to"])

    result = {base_unit: 1.0}
    changed = True
    while changed:
        changed = False
        for u in list(units):
            if u in result:
                continue
            if u in edges:
                to_u, rate = edges[u]
                if to_u in result:
                    result[u] = rate * result[to_u]
                    changed = True

    connected = all(u in result for u in units)
    return connected, result


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/sku_dictionary.csv")
    rows = list(csv.DictReader(path.open("r", encoding="utf-8-sig")))

    errors: list[str] = []
    warnings: list[str] = []

    # 1) sku_id 唯一 & 连续
    ids = [r["sku_id"] for r in rows]
    dup = [k for k, v in Counter(ids).items() if v > 1]
    if dup:
        errors.append(f"[1] sku_id 重复: {dup}")
    nums = sorted(int(s[3:]) for s in ids if s.startswith("SKU"))
    missing = [n for n in range(nums[0], nums[-1] + 1) if n not in nums]
    if missing:
        warnings.append(f"[1] sku_id 编号有跳号(可能是已下架): {['SKU%03d' % n for n in missing]}")

    for r in rows:
        sid = r["sku_id"]
        name = r["sku_name"]
        base_unit = r["base_unit"]

        # 2) purchase_units 连通性
        try:
            purchase = json.loads(r["purchase_units"])
        except Exception as e:
            errors.append(f"[2] {sid} {name}: purchase_units JSON 解析失败: {e}")
            continue

        ok, rates = graph_to_base(purchase, base_unit)
        if not ok:
            errors.append(
                f"[2] {sid} {name}: 进货单位图无法全部走到基准单位 "
                f"{base_unit}，已解析={rates}, 图={purchase}"
            )

        # 3) 与 notes 对比
        chain = parse_notes_chain(r.get("notes", ""))
        # 只做一个粗糙检查：chain 中每一段 rate 是否出现在 purchase 或 sale 里
        purchase_rates = {float(v["rate"]) for v in purchase.values()}
        try:
            sale = json.loads(r["sale_units"])
        except Exception as e:
            errors.append(f"[3] {sid} {name}: sale_units JSON 解析失败: {e}")
            sale = {}
        sale_rates = {float(v) for v in sale.values()}
        for rate, sub, cont in chain:
            if rate not in purchase_rates and rate not in sale_rates:
                warnings.append(
                    f"[3] {sid} {name}: notes 里 '{rate:g}{sub}/{cont}' 在 purchase_units/sale_units 中都找不到"
                )

        # 4) sale_units 单位要能换算到 base_unit
        for u, v in sale.items():
            if u == base_unit:
                if float(v) != 1:
                    warnings.append(
                        f"[4] {sid} {name}: sale_units 里基准单位 {u} 的系数应为 1，实际 {v}"
                    )
                continue
            # 特殊单位"份"当作 1 个基准单位（kg 类商品），由脚本策略决定，这里只提示
            if u == "份":
                continue
            if u not in rates:
                # sale 单位可能不在 purchase 图里 → 试图用声明的系数直接换算，不判错
                warnings.append(
                    f"[4] {sid} {name}: 销售单位 '{u}' 不在进货图里，将直接用 sale_units 的系数 {v} 当作 {u}=>{v}{base_unit}"
                )
            else:
                if abs(float(v) - rates[u]) > 1e-6:
                    errors.append(
                        f"[4] {sid} {name}: 销售单位 '{u}' 的系数 {v} 与进货图推导值 {rates[u]:g} 不一致"
                    )

    # 5) 同 category 统一性提示
    cat_base = defaultdict(Counter)
    cat_safe = defaultdict(Counter)
    for r in rows:
        cat_base[r["category"]][r["base_unit"]] += 1
        cat_safe[r["category"]][r["safe_stock_base"]] += 1
    for cat, c in cat_base.items():
        if len(c) > 1:
            warnings.append(f"[5] 类别 '{cat}' 出现多种基准单位: {dict(c)}")
    for cat, c in cat_safe.items():
        if len(c) > 1:
            warnings.append(f"[5] 类别 '{cat}' 安全库存取值分布: {dict(c)}（仅供参考）")

    print(f"\n校验 {len(rows)} 个 SKU")
    print(f"  ❌ 错误 {len(errors)} 条")
    print(f"  ⚠️  警告 {len(warnings)} 条\n")
    for e in errors:
        print("ERROR  ", e)
    print()
    for w in warnings:
        print("WARN   ", w)

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
