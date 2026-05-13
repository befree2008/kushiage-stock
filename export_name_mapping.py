#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 sales_map_draft.csv 生成一份"菜品名 → SKU"的去重核对表。
按菜品名（忽略规格/平台差异）汇总，展示：
  - 总销量
  - 所有出现过的平台
  - 所有出现过的规格
  - 映射到的 SKU（单品 / 加工品拆解）
  - 每份消耗量
"""

import csv
from collections import defaultdict
from pathlib import Path

DATA = Path("data")

# 按菜品名聚合所有映射
by_name = defaultdict(lambda: {
    "platforms": set(),
    "specs": set(),
    "qty": 0,
    "mappings": [],   # [(sku_id, sku_name, base_qty, base_unit, note_kind)]
    "note": "",
})

seen_qty = set()  # (平台, 菜品, 规格) 避免加工品多行重复计 qty

with open(DATA / "sales_map_draft.csv", encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        name = r["item_name"]
        g = by_name[name]
        g["platforms"].add(r["platform"])
        g["specs"].add(f"{r['spec']}/{r['unit']}")
        key = (r["platform"], name, r["spec"], r["unit"])
        if key not in seen_qty:
            g["qty"] += float(r["qty"])
            seen_qty.add(key)
        # 映射列表
        is_recipe = r["note"].startswith("加工品/套餐拆解")
        mapping_key = (r["sku_id"], r["sku_name"], float(r["base_qty"]), r["base_unit"],
                       "加工品" if is_recipe else "单品")
        if mapping_key not in g["mappings"]:
            g["mappings"].append(mapping_key)

# 导出 CSV
out = DATA / "name_sku_mapping_review.csv"
with out.open("w", encoding="utf-8-sig", newline="") as f:
    w = csv.writer(f)
    w.writerow([
        "平台菜品名", "40天总销量", "出现平台",
        "出现规格", "映射类型", "→ SKU编号", "→ SKU名称",
        "每份消耗", "基准单位", "备注"
    ])
    # 按销量降序
    for name, g in sorted(by_name.items(), key=lambda x: -x[1]["qty"]):
        mappings = g["mappings"]
        for i, (sku_id, sku_name, bq, bu, kind) in enumerate(mappings):
            if i == 0:
                # 第一行写完整信息
                w.writerow([
                    name,
                    f"{g['qty']:.0f}",
                    " / ".join(sorted(g["platforms"])),
                    " / ".join(sorted(g["specs"])),
                    kind,
                    sku_id,
                    sku_name,
                    f"{bq:g}",
                    bu,
                    "加工品拆解" if kind == "加工品" and len(mappings) > 1 else "",
                ])
            else:
                # 加工品的附加 SKU 行
                w.writerow(["", "", "", "", kind, sku_id, sku_name, f"{bq:g}", bu, "↑ 同菜品"])

# 也打印一份 markdown 预览
print(f"共 {len(by_name)} 个平台菜品名\n")
print("前 20 个销量最大的：\n")
print(f"{'平台菜品名':<30s} {'销量':>6s}  映射")
print("-" * 100)
for name, g in sorted(by_name.items(), key=lambda x: -x[1]["qty"])[:20]:
    mstr = " + ".join(f"{m[0]}({m[1]}) ×{m[2]:g}{m[3]}" for m in g["mappings"])
    print(f"{name:<30s} {g['qty']:>6.0f}  {mstr}")

print(f"\n✅ 已导出: {out}")
