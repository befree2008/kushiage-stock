#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
按 SKU 汇总指定日期范围的销量报表。
✅ 自动从 sales_raw.xlsx 提取日期范围，无需手动设置！

输出:
  sku_sales_summary.csv（包含日期元数据）
  控制台打印排行榜
"""
import csv
import re
import zipfile
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

DATA = Path("data")


def extract_dates_from_excel(xlsx_path: str = None) -> dict:
    """
    自动从 sales_raw.xlsx 提取营业日期范围
    返回: {start_date: '2026-04-01', end_date: '2026-05-10', days: 40}
    """
    if xlsx_path is None:
        xlsx_path = DATA / "sales_raw.xlsx"

    # 直接读取 xlsx 内部 XML，不需要 openpyxl
    with zipfile.ZipFile(xlsx_path) as zf:
        with zf.open('xl/worksheets/sheet1.xml') as f:
            content = f.read().decode('utf-8')

    # 查找 A2 单元格的日期格式: 营业日期【2026/04/01-2026/05/10】
    # 用正则匹配日期范围
    date_pattern = r'营业日期【(\d{4})/(\d{2})/(\d{2})[-~至](\d{4})/(\d{2})/(\d{2})】'
    match = re.search(date_pattern, content)

    if not match:
        # 尝试匹配其他格式
        alt_pattern = r'(\d{4})/(\d{2})/(\d{2})[-~至](\d{4})/(\d{2})/(\d{2})'
        match = re.search(alt_pattern, content)

    if not match:
        raise ValueError(
            "❌ 无法从 Excel 提取日期！\n"
            "请确认 sales_raw.xlsx 的 A2 单元格应该包含类似格式：\n"
            "   营业日期【2026/04/01-2026/05/10】"
        )

    y1, m1, d1, y2, m2, d2 = match.groups()
    start_date = f"{y1}-{m1}-{d1}"
    end_date = f"{y2}-{m2}-{d2}"

    # 计算天数
    from datetime import datetime
    d_start = datetime.strptime(start_date, "%Y-%m-%d")
    d_end = datetime.strptime(end_date, "%Y-%m-%d")
    days = (d_end - d_start).days + 1

    return {
        "start_date": start_date,
        "end_date": end_date,
        "days": days
    }


# ✅ 自动提取日期，无需手动设置！
try:
    DATE_INFO = extract_dates_from_excel()
    SALES_START_DATE = DATE_INFO["start_date"]
    SALES_END_DATE = DATE_INFO["end_date"]
    DAYS = DATE_INFO["days"]
    print(f"✅ 自动提取日期成功: {SALES_START_DATE} ~ {SALES_END_DATE} ({DAYS} 天)")
except Exception as e:
    print(f"❌ 日期提取失败: {e}")
    exit(1)

# 加载 SKU 字典，保证没卖过的 SKU 也出现在报表里（销量=0）
skus = {}
with (DATA / "sku_dictionary.csv").open(encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        if r["status"] != "active":
            continue
        skus[r["sku_id"]] = {
            "name": r["sku_name"],
            "category": r["category"],
            "base_unit": r["base_unit"],
        }

# 聚合销售：按 SKU 汇总 "被点单次数" 和 "基准单位消耗量"
agg = defaultdict(lambda: {"orders": 0, "consumption": 0.0, "platforms": defaultdict(float)})

# 先把"被点单次数"按 (平台, 菜名, 规格) 去重统计
# 因为一个套餐/加工品会拆成多行写入，但 qty 是同一份数不应重复加
seen_orders = {}  # key=(platform,item,spec,unit) → qty

with (DATA / "sales_map_draft.csv").open(encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        sku_id = r["sku_id"]
        qty = float(r["qty"])
        consumption = float(r["total_consumption"])
        platform = r["platform"]
        key = (platform, r["item_name"], r["spec"], r["unit"])

        # 消耗量直接累加（一个套餐拆多行，每行消耗不同 SKU）
        agg[sku_id]["consumption"] += consumption
        agg[sku_id]["platforms"][platform] += consumption

        # 点单次数只在第一次看到该 key 时算（按 SKU 维度一样避免重复）
        order_key = (sku_id, platform, r["item_name"], r["spec"], r["unit"])
        if order_key not in seen_orders:
            seen_orders[order_key] = qty
            agg[sku_id]["orders"] += qty

# 合成完整报表
rows = []
for sku_id, info in skus.items():
    a = agg.get(sku_id, {"orders": 0, "consumption": 0, "platforms": {}})
    cons = a["consumption"]
    daily = cons / DAYS
    weekly = daily * 7
    rows.append({
        "sku_id": sku_id,
        "sku_name": info["name"],
        "category": info["category"],
        "base_unit": info["base_unit"],
        "40天订单数": round(a["orders"], 1),
        "40天消耗": round(cons, 2),
        "日均消耗": round(daily, 2),
        "周均消耗": round(weekly, 1),
        "Top平台": max(a["platforms"].items(), key=lambda x: x[1])[0] if a["platforms"] else "",
        "平台数": len(a["platforms"]),
    })

# 按周均消耗降序
rows.sort(key=lambda r: -r["周均消耗"])

# 导出 CSV（先写元数据，再写表头和数据）
out = DATA / "sku_sales_summary.csv"
with out.open("w", encoding="utf-8-sig", newline="") as f:
    w = csv.writer(f)
    # 元数据行（# 开头，方便解析）
    w.writerow(["# sales_start_date", SALES_START_DATE])
    w.writerow(["# sales_end_date", SALES_END_DATE])
    w.writerow(["# sales_days", DAYS])
    w.writerow(["# generated_at", __import__("datetime").datetime.now().isoformat()])
    # 数据表头和数据
    w.writerow(list(rows[0].keys()))
    for r in rows:
        w.writerow(list(r.values()))

# ==== 打印报表 ====
print("=" * 92)
print(f"{'排名':<4}{'SKU':<8}{'名称':<16}{'分类':<6}{'40天订单':>9}{'40天消耗':>10}{'日均':>8}{'周均':>9} 单位")
print("=" * 92)

cat_totals = defaultdict(lambda: {"weekly": 0, "sku_count": 0, "sold_count": 0})
for i, r in enumerate(rows, 1):
    mark = "  " if r["周均消耗"] > 0 else "💤"
    print(f"{i:<4}{r['sku_id']:<8}{r['sku_name']:<16}{r['category']:<6}"
          f"{r['40天订单数']:>9.0f}{r['40天消耗']:>10.1f}{r['日均消耗']:>8.1f}{r['周均消耗']:>9.1f} {r['base_unit']} {mark}")
    cat_totals[r["category"]]["weekly"] += r["周均消耗"] if r["base_unit"] == "串" else 0
    cat_totals[r["category"]]["sku_count"] += 1
    if r["周均消耗"] > 0:
        cat_totals[r["category"]]["sold_count"] += 1

print("\n" + "=" * 60)
print("📊 分类统计")
print("=" * 60)
for cat, t in cat_totals.items():
    print(f"  {cat:<6}  SKU数: {t['sku_count']:>3} (在售 {t['sold_count']})   周消耗合计: {t['weekly']:>7.0f} 串")

print(f"\n📄 详细报表: {out}")
