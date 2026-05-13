# 炸串店补货计算器

## 核心思路

按"**日均消耗 × 覆盖天数 = 目标库存**"反推缺口，按"件→箱"进货规格向上取整，给出一张统一采购单。

```
销售流水 ─→ SKU 日均消耗 ─┐
                          ├─→ 目标库存 ─→ 缺口 ─→ 向上取整到箱 ─→ 采购单
盘货（当前库存，按件）  ──┘
```

覆盖天数根据"今天→下次到货日"动态算：**到货日固定周一 / 周四**，两次到货之间有 3 天或 4 天空档（跨周末会 ×1.15 销量加成）。

## 类别规则

| 类别 | 覆盖天数 | 日均消耗来源 | 周末加成 |
|---|---|---|---|
| 油炸品/蔬菜 | `gap + 0.5天 buffer`（2.5~4.5 天）| `sku_sales_summary.csv`（`summarize_by_sku.py` 生成）| ✅ ×1.15 |
| 调料 | **10 天**（频次低，粒度大）| `seasoning_daily.csv`（`seasoning_calc.py` 按配方+口味统计生成）| ❌ |
| 包材 | 和食材同步 `gap + 0.5天 buffer` | `packaging_daily.csv`（**手填**）| ❌ |

## 目录结构

```
kushiage-stock/
├── data/
│   ├── sales_raw.xlsx            【原始输入】收银系统导出的 40 天品项销售
│   ├── sku_dictionary.csv        【主数据】SKU 字典（含 purchase_units 换算 JSON）
│   ├── packaging_daily.csv       【手填】包材日均消耗
│   │
│   ├── sales_map_draft.csv       菜品名 → SKU 映射（build_sales_map 产出）
│   ├── taste_stats.csv           辣度统计（taste_stats.py 产出）
│   ├── order_count.csv           堂食/外卖单数（order_count.py 产出）
│   ├── sku_sales_summary.csv     SKU 销售汇总（summarize_by_sku.py 产出）
│   ├── seasoning_daily.csv       调料日均（seasoning_calc.py 产出）
│   ├── safe_stock_diff.csv       安全库存变更对照（recalc_safe_stock.py 产出）
│   ├── stock_template.csv/.xlsx  【盘货用】统一模板（食材按袋、包材按件）
│   └── purchase_plan.csv         【最终输出】采购建议
│
├── purchase_plan.py              【主入口】读盘货 + 销售摘要 → 采购单
├── recalc_safe_stock.py          重算安全库存 + 生成盘货模板
├── summarize_by_sku.py           销售 → SKU 日均汇总
├── seasoning_calc.py             调料日均（基于口味配方 + 菜品配方）
├── taste_stats.py                辣度统计
├── order_count.py                堂食/外卖单数（辣度选项反推订单数）
├── build_sales_map.py            菜品名 → SKU 映射生成
├── validate_sku.py               SKU 字典校验
├── export_name_mapping.py        【备用】一次性映射 review 工具（保留，日常不跑）
├── data/name_sku_mapping_review.csv  【备用】上述脚本的产物
├── MAPPING_NOTES.md              菜品映射决策笔记
└── README.md
```

## 日常工作流

```bash
# 1. 收银系统导出最新销售数据 → 覆盖 data/sales_raw.xlsx

# 2. 刷新销售汇总 + 调料日均
python3 summarize_by_sku.py
python3 taste_stats.py
python3 seasoning_calc.py

# 3. 填写 data/packaging_daily.csv 的"日均消耗"列（如有变化）

# 4. 重算安全库存 + 生成盘货模板
python3 recalc_safe_stock.py
#    → 产出 data/stock_template.csv
#    → 产出 data/sku_dictionary_v4.csv（候选新字典，需人工 review 后覆盖 sku_dictionary.csv）

# 5. 打开 stock_template.csv/.xlsx 盘货，填"当前库存_件"列，存成 /tmp/stock_pan.xlsx

# 6. 算采购单
python3 purchase_plan.py
#    → 控制台打印：🛒 需下单 / ✅ 充足 / ❓ 未盘
#    → 明细写入 data/purchase_plan.csv

# 可选参数
python3 purchase_plan.py --gap 3              # 手动指定到下次到货天数
python3 purchase_plan.py --buffer 1           # 安全 buffer 天数（默认 0.5）
python3 purchase_plan.py --weekend-boost 1.2  # 跨周末销量加成（默认 1.15）
python3 purchase_plan.py --stock /path/xlsx   # 指定盘货文件
```

## 订单数口径（`order_count.py`）

按"一个辣度选择 = 一单"的口径，从 `sales_raw.xlsx` 里汇总：
- 店内点餐、美团点评团购、抖音团购 → 堂食
- 美团外卖、淘宝闪购、京东秒送 → 外卖

外卖的辣度在收银系统里是 "【口味】中辣" 或 "微辣（含包装打包费）" 格式，脚本已兼容这三种写法。

## ⚠️ 注意事项

1. **`sku_dictionary_v4.csv` 是 recalc 的候选产物**，人工 review 后手动覆盖到 `sku_dictionary.csv` 再用。不要直接改 v4。
2. **盘货 xlsx 第一行必须是表头**（`sku_id` 开头），如果导出工具在顶部加了标题行，脚本会自动跳过，但别删表头。
3. **包材的"件"是各自的中间单位**（条/捆/提/袋），看 `stock_template.csv` 的"1件=多少基准单位"列。
4. **调料/油炸品的 `pack_size_base` 必须在 sku_dictionary 里填**，否则 `recalc_safe_stock.py` 会把它当"无销量"处理。

## 已废弃（已清理）

以下文件属于早期原型，已在 2026-05-12 清理：
- `stock_calc.py` 及配套的 `sku.csv` / `purchase_map.csv` / `sales_map.csv` / `combo_map.csv` / `stock.csv` / `sales_week.csv`（S001~S004 测试 SKU 架构）
- `packaging_plan.py` / `packaging_stock.csv` / `PACKAGING_TEMPLATE_README.md`（独立包材脚本，已合并进 `purchase_plan.py`）
- 各种 `sku_dictionary.csv.bak*`、`sku_dictionary_v3.csv`

## 迭代路线（后面可以加）

1. **飞书多维表格对接**：用 `feishu-bitable` 把盘货和采购单搬到多维表格
2. **cron 自动跑**：每周一早上自动跑 `summarize_by_sku + recalc_safe_stock`
3. **销售预测**：最近 4 周加权平均代替"40 天平均"
4. **损耗率**：每个 SKU 加一个损耗系数
5. **供应商差异化 lead_time**：区分不同供应商的交付周期
