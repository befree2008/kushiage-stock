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

---

## 📦 库存管理系统（2026-05-13 新增）

### 核心文件

| 文件 | 功能 |
|------|------|
| `inventory_manager.py` | **库存管理核心模块**（扣减、入库、调账、日志、持久化存储） |
| `import_inventory_from_template.py` | 从 `stock_template.csv` 批量导入初始库存 |
| `weekly_run_all.py` | **一键运行脚本**（每周只需要运行这一个！） |
| `inventory_integration.py` | 库存系统与销售脚本集成示例 |

### 生成的数据文件

| 文件 | 说明 | ⚠️ 注意 |
|------|------|--------|
| `data/inventory.json` | **库存数据文件**（永久保存每个 SKU 的当前库存） | ❌ 不要手动删除！ |
| `data/inventory_log.json` | **库存变动日志**（所有操作永久记录，方便追溯） | ❌ 不要手动删除！ |

---

### 🚀 使用流程

#### 第一步：初始化库存（只需要做一次！）

从现有的 `stock_template.csv` 批量导入：

```bash
python3 import_inventory_from_template.py
```

脚本会自动：
- 读取所有 SKU 信息
- 换算成基准单位（自动处理 TBD 待定项）
- 生成 `data/inventory.json` 和 `data/inventory_log.json`

---

#### 第二步：每周一键运行（最重要！）

以后每周**只需要运行这一个脚本**，剩下的全自动：

```bash
python3 weekly_run_all.py
```

**自动完成以下流程：**
1. ✅ 汇总销售数据（summarize_by_sku）
2. ✅ 计算调料消耗（seasoning_calc）
3. 📉 **自动扣减库存**
4. ✅ 重算安全库存 + 生成盘货模板
5. 🛒 生成补货建议
6. 📦 显示当前库存清单
7. 🎮 交互式入库/调账菜单

---

#### 第三步：独立库存管理工具

平时想单独管理库存，直接运行：

```bash
python3 inventory_manager.py
```

**交互式菜单功能：**
```
1. 查看当前库存
2. 手动入库（补货到货）
3. 手动扣减（损耗/赠送）
4. 调账（每月实际库存对账）← 你每月用这个
5. 查看操作日志
6. 初始化新 SKU
0. 退出
```

---

### 📜 操作日志示例

所有操作永久记录，方便追溯：

```
时间                类型    SKU           数量     原因
---------------------------------------------------------------------
2026-05-13 15:30  入库    SKU001       +20.00  补货入库
2026-05-13 15:25  扣减    SKU001       -15.50  40天销售消耗
2026-05-12 10:00  调账    SKU002        +3.50  每月对账调账
2026-05-10 09:30  扣减    SKU003        -2.00  赠送客户
2026-05-08 14:15  初始化 SKU001       100.00  初始化库存
```

---

### 💡 每月对账流程

1. 盘完实际库存
2. 运行 `python3 inventory_manager.py`
3. 选择 `4. 调账`
4. 逐个输入 SKU 的实际库存数量
5. 系统自动计算差异并永久记录

---

### 🔧 代码调用示例

在其他脚本中调用库存管理：

```python
from inventory_manager import InventoryManager

inv = InventoryManager()

# 扣减库存
inv.deduct_sales("SKU001", 15.5, "销售消耗")

# 补货入库
inv.add_restock("SKU001", 20, "新货到了")

# 调账
inv.adjust_inventory("SKU001", 100, "每月对账")

# 查看库存
inv.print_inventory()

# 查看日志
inv.print_logs(10)
```

---

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
