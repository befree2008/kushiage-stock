#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 sales_raw.xlsx 统计 5 种标准口味（不辣/微微辣/微辣/中辣/特辣）的份数。
- 各平台名称花样很多：'微辣' / '【口味】微辣' / '微辣（含包装打包费）' / '炸串口味...'
- 先做名称归一化 → 标准口味
- 分平台打印 + 合计
- 老王已确认忽略的模糊行（IGNORED_TASTE_NAMES）不算入任何口味

输出：data/taste_stats.csv  —— 标准口味 × 总份数 / 日均
"""
import re
from collections import defaultdict
from pathlib import Path

import openpyxl

DATA = Path(__file__).parent / "data"
SRC = DATA / "sales_raw.xlsx"

# 标准口味列表（顺序即展示顺序）
STANDARD_TASTES = ["不辣", "微微辣", "微辣", "中辣", "特辣"]

# 统计窗口天数（sales_raw.xlsx 当前 = 2026-04-01 ~ 2026-05-10 = 40 天）
WINDOW_DAYS = 40

# 老王 2026-05-12 确认：这些模糊行直接忽略，不算入任何口味
IGNORED_TASTE_NAMES = {
    "套餐口味辣度自选",
    "炸串口味（辣椒有点辣）",
    "炸串口味及打包费（辣椒有点辣）",
}


def normalize_taste(name: str) -> str | None:
    """
    把任意平台的口味行名字映射到 5 种标准口味之一。
    返回值：
      - "不辣" / "微微辣" / "微辣" / "中辣" / "特辣"：匹配成功
      - None：不是口味行
      - "IGNORED"：老王已确认忽略的模糊行
    """
    # 1. 先挡掉已确认忽略的行
    if name.strip() in IGNORED_TASTE_NAMES:
        return "IGNORED"

    # 2. 剥掉平台噪音字样
    s = name
    for noise in [
        "【口味】", "（含包装打包费）", "(含包装打包费)",
        "含包装打包费", "及打包费", "（标准）", "(标准)",
    ]:
        s = s.replace(noise, "")
    s = s.strip()

    # 3. 顺序匹配：微微辣 > 特辣 > 中辣 > 微辣 > 不辣，避免噪音误匹配
    if "微微辣" in s:
        return "微微辣"
    if "特辣" in s:
        return "特辣"
    if "中辣" in s:
        return "中辣"
    if "微辣" in s:
        return "微辣"
    if "不辣" in s:
        return "不辣"

    # 4. 口味相关但无法归类——回退为忽略（安全做法）
    if any(kw in name for kw in [
        "口味", "辣度", "辣椒有点辣", "炸串口味",
    ]):
        return "IGNORED"
    return None


def is_taste_row(name: str, spec: str, unit: str) -> bool:
    """
    快速判断：是否可能是口味行。
    口味行的典型特征：名字含上面关键词，且规格是 '标准/1人份/1克/--'，单位是'份'
    """
    if not name:
        return False
    txt = name
    return any(k in txt for k in [
        "辣", "口味", "辣度",
    ])


def main():
    wb = openpyxl.load_workbook(SRC, data_only=True)
    ws = wb["品项销售统计"]
    rows = list(ws.iter_rows(values_only=True))

    # by_platform[platform][taste] = 份数
    by_platform = defaultdict(lambda: defaultdict(float))
    total_by_taste = defaultdict(float)
    ignored = []     # [(platform, name, spec, qty), ...]
    skipped = []

    for r in rows[3:]:
        if not r[3]:
            continue
        platform = str(r[0]) if r[0] else "未知平台"
        name = str(r[3])
        spec = str(r[4]) if r[4] else ""
        unit = str(r[5]) if r[5] else ""
        qty = r[7] or 0

        if not is_taste_row(name, spec, unit):
            continue

        taste = normalize_taste(name)
        if taste is None:
            skipped.append((platform, name, spec, qty))
            continue
        if taste == "IGNORED":
            ignored.append((platform, name, spec, qty))
            continue

        by_platform[platform][taste] += float(qty)
        total_by_taste[taste] += float(qty)

    # ========== 输出 ==========
    platforms = sorted(by_platform.keys(),
                       key=lambda p: -sum(by_platform[p].values()))

    # 分平台表格
    print("=" * 88)
    print("📊 各平台 × 标准口味  份数统计（40 天：2026-04-01 ~ 2026-05-10）")
    print("=" * 88)

    header = f"{'平台':<14}" + "".join(f"{t:>9}" for t in STANDARD_TASTES) + f"{'合计':>9}"
    print(header)
    print("-" * 88)
    for p in platforms:
        row = f"{p:<14}"
        for t in STANDARD_TASTES:
            v = by_platform[p].get(t, 0)
            row += f"{int(v) if v else '-':>9}"
        total = sum(by_platform[p].values())
        row += f"{int(total):>9}"
        print(row)
    print("-" * 88)
    # 合计行
    total_row = f"{'🔥 总计':<14}"
    grand = 0
    for t in STANDARD_TASTES:
        v = total_by_taste.get(t, 0)
        total_row += f"{int(v):>9}"
        grand += v
    total_row += f"{int(grand):>9}"
    print(total_row)

    # 占比
    print()
    print(f"{'占比':<14}", end="")
    for t in STANDARD_TASTES:
        v = total_by_taste.get(t, 0)
        pct = v / grand * 100 if grand else 0
        print(f"{pct:>8.1f}%", end="")
    print(f"{'100%':>9}")

    # 日均
    print(f"{'日均份数':<14}", end="")
    for t in STANDARD_TASTES:
        v = total_by_taste.get(t, 0)
        print(f"{v/40:>9.1f}", end="")
    print(f"{grand/40:>9.1f}")

    # 忽略行（老王 2026-05-12 确认）
    if ignored:
        print()
        print("🗑️  已忽略的模糊口味行（老王确认，不算入调料消耗）")
        print("-" * 88)
        print(f"{'平台':<14}{'名称':<30}{'规格':<12}{'份数':>8}")
        total_ignored = 0
        for p, n, s, q in sorted(ignored, key=lambda x: -x[3]):
            print(f"{p:<14}{n:<30}{s:<12}{int(q):>8}")
            total_ignored += q
        print(f"{'  小计':<56}{int(total_ignored):>8}")

    if skipped:
        print()
        print("ℹ️ 匹配上'辣'字但未归类的行（可能是菜品名里带辣，已自动跳过）")
        for p, n, s, q in skipped[:5]:
            print(f"  [{p}] {n} ({s}) × {q}")
        if len(skipped) > 5:
            print(f"  ...还有 {len(skipped)-5} 行")

    # ========== 输出给后续脚本用的 CSV ==========
    out = DATA / "taste_stats.csv"
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        import csv
        w = csv.writer(f)
        w.writerow(["标准口味", "总份数", "日均份数", "占比"])
        for t in STANDARD_TASTES:
            v = total_by_taste.get(t, 0)
            w.writerow([
                t, int(v), round(v/WINDOW_DAYS, 2),
                f"{v/grand*100:.1f}%" if grand else "0%"
            ])
        w.writerow(["合计", int(grand), round(grand/WINDOW_DAYS, 2), "100%"])
    print(f"\n📄 统计结果已写入: {out}")


if __name__ == "__main__":
    main()
