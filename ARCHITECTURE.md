# kushiage-stock 库存管理系统 · 架构与流程

> 最近一次整理：2026-05-17 by 蜜蜡
> 当前 inventory.json：`last_updated=2026-05-17T18:06:15`，61 个 SKU

---

## 一、核心理念

整个系统的**数据流原则**：

```
一份权威 SKU 字典  +  一份当前库存 (inventory.json)  +  一份销售汇总 (sku_sales_summary.csv)
                              ↓
                   ┌──────────┼──────────┐
                进货       销售扣减      补货建议
              (PURCHASE)  (DEDUCT)     (输出建议)
                              ↓
                       inventory.json
                       inventory_log.json
```

每个动作都遵守：**备份 → dry-run → 用户确认 → 写回 → 记日志**。

---

## 二、数据文件（data/）

### 2.1 主数据（手动维护，权威）

| 文件 | 说明 | 格式 | 谁维护 |
|---|---|---|---|
| **`sku_dictionary.csv`** | SKU 字典 = 系统唯一权威源 | utf-8-sig | 老王手动 |
| `sales_raw.xlsx` | 销售原始流水（外部系统导出）| xlsx | 老王导入 |

**`sku_dictionary.csv` 字段：**

| 字段 | 含义 | 示例 |
|---|---|---|
| `sku_id` | 主键 | SKU001 |
| `sku_name` | 中文名 | 豆干小串 |
| `category` | 油炸品 / 蔬菜 / 调料 / 包材 | 油炸品 |
| `base_unit` | 基准单位 | 串 / g / 个 |
| `pack_size_base` | 1 袋 = 多少 base | 200 |
| `safe_stock_base` | 安全库存（base 量）| 400 |
| `safe_stock_bags` | 安全库存（袋）| 2 |
| `purchase_units` | 多层换算 JSON | `{"箱":{"to":"袋","rate":10},...}` |
| `sale_units` | 销售换算（袋→串）| `{"袋":{"to":"串","rate":200}}` |
| `status` | active / inactive | active |
| `lead_time_days` | 进货周期 | 4 |
| `loss_rate` | 损耗率 | 0.02 |

### 2.2 系统状态（脚本读写）

| 文件 | 用途 | 谁写 |
|---|---|---|
| **`inventory.json`** | 当前各 SKU 库存（base_unit 数）| `inventory_manager.py` 类方法 |
| **`inventory_log.json`** | 所有变更日志（PURCHASE/DEDUCT/ADJUST/INIT）| 同上 |
| `inventory.json.before_*` | 各种备份点（每次写入前）| 写入前自动备份 |

`inventory.json` 顶层结构：
```json
{
  "version": "1.0",
  "last_updated": "2026-05-17T18:06:15",
  "last_sales_deduction":   {"start_date":"2026-05-11","end_date":"2026-05-16","days":6},
  "last_indirect_deduction":{"start_date":"2026-05-11","end_date":"2026-05-16","days":6},
  "skus": {
    "SKU001": {"name":"豆干小串","quantity":1805.0,"unit":"串"}
  }
}
```

### 2.3 销售推导（脚本生成的中间产物）

| 文件 | 来源 |
|---|---|
| **`sku_sales_summary.csv`** | `summarize_by_sku.py` |
| `seasoning_daily.csv` | `seasoning_calc.py` |
| `packaging_daily.csv` | `seasoning_calc.py` |
| `taste_stats.csv` | `taste_stats.py` |
| `sales_map_draft.csv` / `name_sku_mapping_review.csv` / `unmapped.csv` / `ignored.csv` | `build_sales_map.py` |

`sku_sales_summary.csv` 顶部带元数据（关键！）：
```
# start_date,2026-05-11
# end_date,2026-05-16
# days,6
sku_id,sku_name,total_quantity,日均消耗,...
```

### 2.4 流程产物（脚本生成的报表）

| 文件 | 来源 | 用途 |
|---|---|---|
| **`purchase_plan.csv`** | `purchase_plan.py` | 补货详细报表（每次覆盖）|
| **`inventory_pieces_YYYYMMDD.csv`** | 同上 | 当前库存折件，老王盘点用（每次跟日期）|
| `purchase_order_template.csv` | 手动维护 | 进货单填写模板 |

备注：以下产物需要时重跑对应脚本生成（不作为長期保留文件）：
- `safe_stock_diff.csv`、`stock_template.csv/xlsx` ← `recalc_safe_stock.py`
- `order_OCK*.csv` ← OCR 识别后走 `purchase_order_import.py` 入库，然后可删

---

## 三、脚本清单（共 13 个）

### 3.1 核心引擎（依赖，不直接跑）

| 脚本 | 行数 | 职责 |
|---|---:|---|
| **`inventory_manager.py`** | 398 | `InventoryManager` 类：读写 inventory.json / 日志 / `deduct_sales` / `add_restock` / `adjust_inventory` / 销售期校验 |

### 3.2 主流程脚本（日常使用）

| 脚本 | 行数 | 输入 | 输出 | 时机 |
|---|---:|---|---|---|
| **`summarize_by_sku.py`** | 174 | `sales_raw.xlsx` 等 | `sku_sales_summary.csv` | 拿到销售流水后 |
| **`seasoning_calc.py`** | 228 | 销售映射 + summary | `seasoning_daily.csv`<br>`packaging_daily.csv` | 跟随 summarize 跑 |
| **`weekly_deduct.py`** ⭐ | 331 | 三份汇总 + `inventory.json` | 写回 `inventory.json` | 销售扣减（销售+调料+包材一次扣完）|
| **`purchase_order_import.py`** | 327 | 进货单 CSV（OCR）+ 字典 | 写回 `inventory.json` | 进货到货时 |
| **`purchase_plan.py`** ⭐ | 545 | `inventory.json` + `sku_sales_summary.csv` | `purchase_plan.csv`<br>`inventory_pieces_YYYYMMDD.csv` | 决定下单前 |

### 3.3 数据加工 / 一次性工具

| 脚本 | 用途 | 频率 |
|---|---|---|
| `build_sales_map.py` | 销售名称模糊匹配到 SKU | 销售映射不完整时 |
| `taste_stats.py` | 口味销量统计 | 分析时 |
| `validate_sku.py` | 校验 sku_dictionary 的 JSON / 字段一致性 | 改字典后 |
| `recalc_safe_stock.py` | 根据销售重算安全库存阈值 | 月度审视 |
| `import_inventory_from_template.py` | 从盘点模板导入 inventory.json | 大盘点时 |
| `export_name_mapping.py` | 导出销售名映射用于人工审核 | 销售映射不全时 |
| `order_count.py` | 进货单 CSV 行数清点 | 偶尔 |

---

## 四、标准工作流（每周节奏）

### 进货日（周一 / 周四）

```
1. 老王拍进货单照片 → 发给蜜蜡
2. 蜜蜡：image 工具 OCR → 列识别表 → 老王确认
3. 蜜蜡：python3 purchase_order_import.py
   ├─ 备份 inventory.json
   ├─ 写入 PURCHASE 日志
   └─ inventory.json 各 SKU 数量 +
```

### 销售日报到（每周固定）

```
1. 老王导出销售流水 → data/sales_raw.xlsx
2. 蜜蜡：python3 summarize_by_sku.py
   ├─ 生成 sku_sales_summary.csv（含起止日期元数据）
   └─ 生成 seasoning_daily.csv / packaging_daily.csv
3. 蜜蜡：python3 weekly_deduct.py
   ├─ 校验 last_sales_deduction 不重叠
   ├─ 备份 inventory.json
   ├─ 一次性扣减：销售 + 调料 + 包材
   ├─ 蔬菜 skip
   └─ 记录 last_sales_deduction + last_indirect_deduction
```

### 决定下单（每次进货前）

```
1. 蜜蜡：python3 purchase_plan.py
   ├─ 默认 buffer=1 天，min-cover=5 天
   ├─ 油炸/蔬菜目标 = max(gap+buffer, min_cover) 天
   ├─ 调料目标 = 10 天
   ├─ 输出 data/purchase_plan.csv（详细报表）
   └─ 输出 data/inventory_pieces_YYYYMMDD.csv（折件库存表）
2. 老王看建议 → 决定下单
3. 同时可在 inventory_pieces_YYYYMMDD.csv 上加列「实际盘点_件」
   蜜蜡读回 → adjust_inventory 写回 ADJUST 日志
```

---

## 五、调用关系图

```
┌──────────────────────────────────────────────────────────────┐
│                    sku_dictionary.csv                         │  权威字典
└───┬───────────────┬─────────────────┬────────────────────────┘
    │               │                 │
    ▼               ▼                 ▼
┌────────┐   ┌────────────────┐  ┌──────────────────────┐
│ build_ │   │ summarize_     │  │ purchase_order_      │
│ sales_ │   │ by_sku.py      │  │ import.py            │
│ map.py │   │ ↓              │  │ ↓ PURCHASE           │
└────────┘   │ seasoning_     │  └──────────┬───────────┘
             │ calc.py        │             │
             │ ↓              │             │
             │ sku_sales_     │             │
             │ summary.csv    │             │
             │ seasoning_     │             │
             │ daily.csv      │             │
             │ packaging_     │             │
             │ daily.csv      │             │
             └────────┬───────┘             │
                      ▼                     │
              ┌─────────────────┐           │
              │ weekly_deduct.py│◄──────────┘
              │ ↓ DEDUCT        │
              └────────┬────────┘
                       ▼
            ┌────────────────────┐
            │  inventory.json    │◄──── adjust_inventory（盘点校对）
            │  inventory_log     │      ADJUST
            └────────┬───────────┘
                     ▼
            ┌────────────────────┐
            │ purchase_plan.py   │
            │ ↓ 输出建议（不写库存） │
            └────┬───────┬───────┘
                 ▼       ▼
        purchase_plan.csv   inventory_pieces_YYYYMMDD.csv
```

---

## 六、单位与换算约定

```
基准单位 (base_unit)：串 / g / 个
   │
   ↑ ×pack_size_base
   │
件 (袋/条/捆/提/把)：进货/盘点最常用粒度
   │
   ↑ ×bags_per_box（来自 purchase_units）
   │
箱：采购最大粒度
```

**换算规则**：所有脚本读 `purchase_units` JSON 递归解析（`box_size_of()` / `_piece_size_for_sku()`），不硬编码。

**盘点界面**统一用「件」（袋/条/提/捆/把）这一层；写回时自动换算成 base 量。

---

## 七、约定与红线

1. **所有写 inventory.json 之前必须先备份**（`cp data/inventory.json data/inventory.json.before_xxx_TIMESTAMP`）
   　　注意：`data/` 在 .gitignore 中，本地备份不进 git。完成一个流程后可手动清理过期备份。
2. **CSV 顶部 `#` 开头是元数据行**（如销售期）—— 解析时跳过
3. **CSV 编码统一 utf-8-sig**（兼容 Excel BOM）
4. **蔬菜在销售扣减中 skip**（base_unit 缺、purchase_units TBD）
5. **dry-run 模式不卡 input、不写文件**
6. **OCR 必须走 `image` 工具**（按 `TOOLS.md` 老王硬性要求）
7. **去重扣减**：通过 `last_sales_deduction` / `last_indirect_deduction` 区间防重复

---

## 八、待办

- [ ] `inventory_log.json` 时间戳排序错乱（查 `_log()`）
- [ ] `print_inventory()` 显示 SKU ID 而非中文名
- [ ] 蔬菜分类的「日均消耗」接入（5 个蔬菜 SKU 现在都是 TBD）
