# 海龟交易法则回测：Python 版

[中文](#中文版) | [English](#english-version)

<a id="中文版"></a>

## 中文版

本目录是海龟交易回测的 Python 实现。核心策略按原 Excel 回测表的公式顺序移植，同时支持：

- 原版单标的回测工作簿；
- 包含多组 OHLC 数据的 `Raw_data` 工作簿；
- 标准 OHLC CSV；
- 单标的或全部标的批量回测；
- 逐日交易明细、绩效汇总；
- Jupyter Notebook 净值和收盘价图表。

### 回测净值总览

下图比较了原始数据中全部 9 个标的应用同一套海龟规则后的实际 NAV：

![9个标的海龟策略NAV对比](charts/turtle_nav_comparison.png)

回测核心仅使用 Python 标准库。绘图 Notebook 额外使用 Jupyter、pandas 和 matplotlib。

## 目录结构

```text
Py_version/
├── run_backtest.py              # 命令行入口
├── turtle_backtest.py           # 数据模型、行情读取、海龟公式、结果输出
├── inspect_workbook.py          # 直接读取 xlsx 内部 XML
├── index_nav_vs_close.ipynb     # 9个标的的 NAV / Close 图表
├── test_multisymbol.py          # 多标的回归测试
├── test_parity.py               # Python 与 Excel 缓存结果对账
└── all_results/                 # 批量回测输出示例
```

当前使用的 Excel 数据位于：

```text
Excel_version/海龟法则_stock_data_2026.xlsx
Excel_version/海龟回测_沪深300_周淞铭.xlsx
```

## 快速开始

所有命令均在项目根目录 `Turtle_Trading` 执行。

### 查看工作簿中的全部标的

```bash
python3 Py_version/run_backtest.py \
  "Excel_version/海龟法则_stock_data_2026.xlsx" \
  --list-symbols
```

当前工作簿包含 9 个标的：

| 代码 | 名称 | 类型 |
|---|---|---|
| `000300.SH` | 沪深300 | 指数 |
| `8841431.WI` | 万得微盘股指数 | 指数 |
| `000905.SH` | 中证500 | 指数 |
| `000852.SH` | 中证1000 | 指数 |
| `932000.CSI` | 中证2000 | 指数 |
| `MSFT.O` | 微软（MICROSOFT） | 股票 |
| `NVDA.O` | 英伟达（NVIDIA） | 股票 |
| `GOOGL.O` | 谷歌（ALPHABET）-A | 股票 |
| `AAPL.O` | 苹果（APPLE） | 股票 |

### 回测单个标的

可以通过代码或名称选择标的：

```bash
python3 Py_version/run_backtest.py \
  "Excel_version/海龟法则_stock_data_2026.xlsx" \
  --symbol 000905.SH \
  -o Py_version/中证500.csv
```

程序会：

1. 在终端打印该标的的 JSON 汇总指标；
2. 将完整逐日回测明细写入 `Py_version/中证500.csv`。

如果不传 `--symbol`，多标的工作簿默认选择 `000300.SH`（沪深300）。

### 批量回测全部标的

```bash
python3 Py_version/run_backtest.py \
  "Excel_version/海龟法则_stock_data_2026.xlsx" \
  --all \
  -o Py_version/all_results
```

批量模式输出：

```text
Py_version/all_results/
├── 000300.SH_沪深300.csv
├── 000905.SH_中证500.csv
├── ...
├── AAPL.O_苹果(APPLE).csv
└── summary.csv
```

每个标的一份逐日明细，`summary.csv` 汇总所有标的的绩效指标。

### 回测原版单标的 Excel

```bash
python3 Py_version/run_backtest.py \
  "Excel_version/海龟回测_沪深300_周淞铭.xlsx" \
  -o Py_version/backtest_result.csv
```

### 回测 CSV

```bash
python3 Py_version/run_backtest.py \
  "path/to/prices.csv" \
  -o Py_version/backtest_result.csv
```

CSV 表头必须包含：

```text
Date,open,high,low,close
```

表头大小写不敏感。日期支持：

- ISO 日期，例如 `2026-07-28`；
- Excel 日期序列值，例如 `46231`。

空白 OHLC 会读取为缺失值；回测过程中，无效或小于等于零的价格使用前一日对应清洗价格向前填充。

## 默认回测参数

| 参数 | 命令行参数 | 默认值 | 含义 |
|---|---|---:|---|
| ATR 周期 | `--atr-period` | 20 | ATR 指数平滑周期 |
| 入场周期 | `--entry-period` | 20 | 前 N 日最高价通道 |
| 退出周期 | `--exit-period` | 10 | 前 N 日最低价通道 |
| 单次风险比例 | `--risk` | 0.02 | NAV 的 2% |
| 买入成本率 | `--buy-cost` | 0.0002 | 0.02% |
| 卖出成本率 | `--sell-cost` | 0.0007 | 0.07% |
| 初始资金 | `--initial-cash` | 1,000,000 | 初始账户 NAV |
| 最小交易单位 | 代码参数 | 100 | 仓位向下取整到整手 |
| 首个信号行 | 代码参数 | Excel 第57行 | 与原回测表保持一致 |

查看完整命令行帮助：

```bash
python3 Py_version/run_backtest.py --help
```

## 数据读取逻辑

### 原版单标的工作簿

`load_reference_xlsx()` 从 `sheet1` 的第 6 行开始读取：

```text
A列 Date
B列 Open
C列 High
D列 Low
E列 Close
```

### Raw_data 多标的工作簿

`load_raw_data_xlsx()` 横向搜索连续的五列数据块：

```text
Date | open | high | low | close
```

表头位于第 5 行，标的名称和代码分别从数据块第二列的第 2、3 行读取。对于上市较晚的标的，从第一条 OHLC 全部有效且大于零的记录开始计算自己的预热期。

Excel 文件通过 `zipfile` 和 XML 直接读取，不需要安装或启动 Microsoft Excel。

## 海龟策略公式

所有核心计算集中在：

```python
Py_version/turtle_backtest.py
run_backtest()
```

逐日计算只引用当日及以前的数据。

### 1. TR

首日：

```text
TR = High - Low
```

之后：

```text
TR(t) = MAX(
    High(t) - Low(t),
    ABS(High(t) - Close(t-1)),
    ABS(Close(t-1) - Low(t))
)
```

### 2. ATR

首日以 TR 初始化，之后使用指数平滑：

```text
ATR(t) =
2 / (N + 1) × TR(t)
+ (N - 1) / (N + 1) × ATR(t-1)
```

默认 `N=20`。这不是简单移动平均，也不同于使用 `1/N` 权重的 Wilder ATR。

### 3. 唐奇安通道

```text
Past High(t) = 当日之前20个交易日的最高价
Past Low(t)  = 当日之前10个交易日的最低价
```

当日不包含在通道窗口中，避免使用未来数据。

为与原 Excel 对齐，第一条行情对应 Excel 第 6 行，第 57 行开始允许产生交易信号。

### 4. 入场与退出

空仓时：

```text
High(t) > Past High(t) → 买入
```

持仓时：

```text
Exit Level(t) = MAX(Past Low(t), Stop Loss(t-1))
Low(t) < Exit Level(t) → 全部卖出
```

判断使用严格不等式。价格刚好等于通道或退出线时，不触发交易。

### 5. 成交价格

```text
买入价 = MAX(Open(t), Past High(t))

退出线 = MAX(Past Low(t), Stop Loss(t-1))
卖出价 = MIN(Open(t), 退出线)
```

这样能够反映突破或退出当天的跳空：

- 跳空高开突破时，按较高的开盘价买入；
- 跳空低开退出时，按较低的开盘价卖出。

### 6. 止损

```text
Stop Loss = 买入成交价 - 前一日 ATR
```

止损在建仓时确定，持仓期间保持不变，平仓后清空。

### 7. 仓位

```text
风险限制股数 = 前一日 NAV × 风险比例 / 前一日 ATR

现金限制股数 =
前一日现金 / [买入价 × (1 + 买入成本率)]

实际仓位 =
MIN(风险限制股数, 现金限制股数)
再向下取整到100股
```

当前策略一次性建仓、一次性清仓，不进行加仓或减仓。

### 8. 现金与净值

```text
仓位变化 = 当日仓位 - 前日仓位

现金 =
前日现金
- 仓位变化 × 成交价
- ABS(仓位变化) × 成交价 × 交易成本率

股票市值 = 当日仓位 × 当日清洗收盘价
NAV = 现金 + 股票市值
```

买入使用买入成本率，卖出使用卖出成本率。

## 当前策略边界

当前实现是原 Excel 的单标的、只做多版本，并非经典海龟组合系统的全部规则：

- 只做多，不做空；
- 一次性建仓和全部平仓；
- 没有每上涨 `0.5N` 加仓；
- 没有最多四个 Unit 的限制；
- 没有 System 1 / System 2 双系统；
- 没有品种相关性和组合风险限制；
- 止损距离为 1 ATR，持仓期间不移动。

准确地说，当前策略是：

> 前20日高点突破入场 + 前10日低点或1 ATR固定止损退出 + 2%风险仓位。

## 输出字段

逐日明细包含：

| 分类 | 字段 |
|---|---|
| 原始价格 | `Date`, `open`, `high`, `low`, `close` |
| 清洗价格 | `Clean Open`, `Clean High`, `Clean Low`, `Clean Close` |
| 波动与通道 | `TR`, `ATR`, `Past High`, `Past Low` |
| 信号与交易 | `Signal`, `Trade Price`, `Stop Loss`, `Trade` |
| 账户 | `Position`, `Cash`, `Stock Value`, `Trading Cost` |
| 绩效 | `Daily P&L`, `NAV`, `Daily Return`, `Drawdown` |
| 对比曲线 | `NAV Index`, `Close Index` |

其中：

```text
NAV Index = NAV / 初始资金 × 100
Close Index = Clean Close / 首日 Clean Close × 100
```

二者单位一致、都从 100 起步，适合直接比较策略与买入持有的累计表现。

## 汇总指标口径

`Summary` 和批量模式的 `summary.csv` 包含：

- `ending_nav`：期末净值；
- `total_return`：总收益率；
- `annualized_return`：复合年化收益率；
- `max_drawdown`：最大回撤；
- `annualized_volatility`：年化波动率；
- `sharpe_ratio`：夏普比率；
- `buys` / `sells`：买入和卖出次数；
- `time_in_market`：信号处于持仓状态的时间比例；
- `ending_position`：期末仓位；
- `total_trading_cost`：累计交易成本；
- `minimum_cash`：历史最低现金；
- `current_signal`：期末持仓状态；
- `nav_check`：检查期末 NAV 是否等于现金加股票市值。

### 年化收益率

年化收益率是复合年化收益率 CAGR，不是各年收益率的算术平均：

```text
年化收益率 =
(期末 NAV / 期初 NAV) ^ (365 / 实际自然日数) - 1
```

### 年化波动率

```text
年化波动率 = 每日收益率样本标准差 × SQRT(252)
```

### 夏普比率

```text
夏普比率 =
平均日收益率 × 252 / 年化波动率
```

当前计算没有扣除无风险利率，相当于无风险利率为 0。

## 图表 Notebook

打开：

```text
Py_version/index_nav_vs_close.ipynb
```

Notebook 默认读取：

```text
Excel_version/海龟法则_stock_data_2026.xlsx
```

并回测原数据中的全部 9 个标的。

Notebook 包含：

1. 工作簿标的清单；
2. 全部标的回测；
3. 每个标的的双纵轴图；
4. 9个标的的实际 NAV 对比图；
5. 回测指标汇总表。

单标的双轴图：

- 左轴：实际 NAV 金额；
- 右轴：标的实际 Close；
- 用于观察走势和时间拐点，不应通过两条线的视觉高度比较收益率。

如果需要严格比较策略与标的收益率，应使用逐日结果中的 `NAV Index` 和 `Close Index`，因为二者都标准化为 100。

所有图表的横轴主刻度固定为每年 4 月 5 日，例如：

```text
2005/4/5, 2006/4/5, ..., 2026/4/5
```

修改 Notebook 中的 `SELECTED_SYMBOLS` 可以增减标的。将：

```python
SAVE_CHARTS = True
```

即可把图表保存到：

```text
Py_version/charts/
```

## 测试

在项目根目录运行：

```bash
python3 -m unittest -v \
  Py_version.test_multisymbol \
  Py_version.test_parity
```

`test_multisymbol` 验证：

- 正确识别全部 9 个标的；
- 所有标的均可完成回测；
- 每个标的的 `nav_check` 均为 `PASS`；
- 沪深300关键回测结果保持稳定。

`test_parity` 用于对比原 Excel 保存的逐日公式缓存：

- 5,152 行；
- 22 个逐日计算字段；
- 14 个汇总指标。

如果当前参考工作簿没有保存公式计算缓存，该项测试会主动跳过；这不代表 Python 回测失败。

## 主要代码入口

| 功能 | 文件 / 函数 |
|---|---|
| 命令行调度 | `run_backtest.py: main()` |
| 核心策略 | `turtle_backtest.py: run_backtest()` |
| CSV 读取 | `turtle_backtest.py: load_csv()` |
| 单标的 Excel | `turtle_backtest.py: load_reference_xlsx()` |
| 多标的 Excel | `turtle_backtest.py: load_raw_data_xlsx()` |
| 标的选择 | `turtle_backtest.py: select_instrument()` |
| 明细 CSV 输出 | `turtle_backtest.py: write_results_csv()` |
| Excel XML 读取 | `inspect_workbook.py: sheet_cells()` |

---

<a id="english-version"></a>

# Turtle Trading Backtest: Python Version

[中文](#中文版) | [English](#english-version)

This directory contains a Python implementation of the Turtle Trading backtest. The core strategy follows the calculation order of the original Excel workbook and supports:

- the original single-instrument workbook;
- multi-instrument `Raw_data` workbooks;
- standard OHLC CSV files;
- single-instrument and batch backtests;
- daily trade details and performance summaries;
- Jupyter charts for NAV and closing prices.

### NAV overview

The chart below compares actual NAV across all 9 source instruments using the same Turtle rules:

![Turtle strategy NAV comparison across 9 instruments](charts/turtle_nav_comparison.png)

The backtest engine uses only the Python standard library. The notebook additionally requires Jupyter, pandas, and matplotlib.

## Project structure

```text
Py_version/
├── run_backtest.py              # Command-line entry point
├── turtle_backtest.py           # Data loaders, strategy, metrics, and output
├── inspect_workbook.py          # Direct xlsx XML reader
├── index_nav_vs_close.ipynb     # NAV and Close charts for 9 instruments
├── test_multisymbol.py          # Multi-instrument regression tests
├── test_parity.py               # Python-to-Excel parity tests
└── all_results/                 # Example batch-backtest output
```

Current source workbooks:

```text
Excel_version/海龟法则_stock_data_2026.xlsx
Excel_version/海龟回测_沪深300_周淞铭.xlsx
```

## Quick start

Run all commands from the `Turtle_Trading` project root.

### List all instruments

```bash
python3 Py_version/run_backtest.py \
  "Excel_version/海龟法则_stock_data_2026.xlsx" \
  --list-symbols
```

The workbook currently contains 9 instruments:

| Symbol | Name | Type |
|---|---|---|
| `000300.SH` | CSI 300 | Index |
| `8841431.WI` | Wind Micro-cap Index | Index |
| `000905.SH` | CSI 500 | Index |
| `000852.SH` | CSI 1000 | Index |
| `932000.CSI` | CSI 2000 | Index |
| `MSFT.O` | Microsoft | Stock |
| `NVDA.O` | NVIDIA | Stock |
| `GOOGL.O` | Alphabet Class A | Stock |
| `AAPL.O` | Apple | Stock |

### Backtest one instrument

Select an instrument by symbol or name:

```bash
python3 Py_version/run_backtest.py \
  "Excel_version/海龟法则_stock_data_2026.xlsx" \
  --symbol 000905.SH \
  -o Py_version/csi500.csv
```

The program prints summary metrics as JSON and writes the complete daily results to the output CSV. If `--symbol` is omitted, a multi-instrument workbook defaults to `000300.SH`.

### Backtest all instruments

```bash
python3 Py_version/run_backtest.py \
  "Excel_version/海龟法则_stock_data_2026.xlsx" \
  --all \
  -o Py_version/all_results
```

Batch mode creates one daily-detail CSV per instrument and a combined `summary.csv`:

```text
Py_version/all_results/
├── 000300.SH_沪深300.csv
├── 000905.SH_中证500.csv
├── ...
├── AAPL.O_苹果(APPLE).csv
└── summary.csv
```

### Backtest the original single-instrument workbook

```bash
python3 Py_version/run_backtest.py \
  "Excel_version/海龟回测_沪深300_周淞铭.xlsx" \
  -o Py_version/backtest_result.csv
```

### Backtest a CSV file

```bash
python3 Py_version/run_backtest.py \
  "path/to/prices.csv" \
  -o Py_version/backtest_result.csv
```

The CSV header must contain:

```text
Date,open,high,low,close
```

Header matching is case-insensitive. Dates may be ISO dates such as `2026-07-28` or Excel serial values such as `46231`. Blank OHLC cells are loaded as missing values. During the backtest, invalid or non-positive prices are forward-filled from the previous cleaned value for the same field.

## Default parameters

| Parameter | CLI option | Default | Meaning |
|---|---|---:|---|
| ATR period | `--atr-period` | 20 | ATR exponential-smoothing period |
| Entry period | `--entry-period` | 20 | Previous N-day high channel |
| Exit period | `--exit-period` | 10 | Previous N-day low channel |
| Risk fraction | `--risk` | 0.02 | 2% of NAV |
| Buy cost rate | `--buy-cost` | 0.0002 | 0.02% |
| Sell cost rate | `--sell-cost` | 0.0007 | 0.07% |
| Initial cash | `--initial-cash` | 1,000,000 | Initial account NAV |
| Lot size | Code parameter | 100 | Position rounded down to whole lots |
| First signal row | Code parameter | Excel row 57 | Matches the original workbook |

Display all CLI options with:

```bash
python3 Py_version/run_backtest.py --help
```

## Data loading

### Original single-instrument workbook

`load_reference_xlsx()` reads from row 6 of `sheet1`:

```text
Column A: Date
Column B: Open
Column C: High
Column D: Low
Column E: Close
```

### Multi-instrument Raw_data workbook

`load_raw_data_xlsx()` scans horizontally for consecutive blocks:

```text
Date | open | high | low | close
```

Headers are on row 5. The instrument name and symbol are read from rows 2 and 3 of the block's second column. A later-listed instrument starts at its first row where all OHLC values are valid and positive, followed by its own warm-up period.

Excel files are read directly through `zipfile` and XML parsing. Microsoft Excel does not need to be installed or running.

## Turtle strategy formulas

All core calculations are implemented in `turtle_backtest.py: run_backtest()`. Daily calculations only use information available on or before the current date.

### 1. True Range

First day:

```text
TR = High - Low
```

Thereafter:

```text
TR(t) = MAX(
    High(t) - Low(t),
    ABS(High(t) - Close(t-1)),
    ABS(Close(t-1) - Low(t))
)
```

### 2. ATR

ATR is initialized with the first TR and then exponentially smoothed:

```text
ATR(t) =
2 / (N + 1) × TR(t)
+ (N - 1) / (N + 1) × ATR(t-1)
```

The default is `N=20`. This is not a simple moving average or Wilder's `1/N` smoothing formula.

### 3. Donchian channels

```text
Past High(t) = highest price over the 20 trading days before t
Past Low(t)  = lowest price over the 10 trading days before t
```

The current day is excluded, preventing look-ahead bias. To match the original workbook, the first observation corresponds to Excel row 6 and signals begin on row 57.

### 4. Entry and exit

While flat:

```text
High(t) > Past High(t) → Buy
```

While long:

```text
Exit Level(t) = MAX(Past Low(t), Stop Loss(t-1))
Low(t) < Exit Level(t) → Sell the entire position
```

Both use strict inequalities. Equality does not trigger a trade.

### 5. Execution prices

```text
Buy Price = MAX(Open(t), Past High(t))

Exit Level = MAX(Past Low(t), Stop Loss(t-1))
Sell Price = MIN(Open(t), Exit Level)
```

An upside opening gap is bought at the higher open. A downside opening gap is sold at the lower open.

### 6. Stop loss

```text
Stop Loss = Buy Price - Previous-day ATR
```

The stop is fixed when the position opens, remains unchanged while holding, and is cleared after exit.

### 7. Position sizing

```text
Risk-limited Shares =
Previous-day NAV × Risk Fraction / Previous-day ATR

Cash-limited Shares =
Previous-day Cash / [Buy Price × (1 + Buy Cost Rate)]

Actual Position =
MIN(Risk-limited Shares, Cash-limited Shares)
rounded down to the nearest 100 shares
```

The strategy enters once and exits the full position. It does not pyramid or scale out.

### 8. Cash and NAV

```text
Position Change = Current Position - Previous Position

Cash =
Previous Cash
- Position Change × Trade Price
- ABS(Position Change) × Trade Price × Trading Cost Rate

Stock Value = Current Position × Current Clean Close
NAV = Cash + Stock Value
```

Purchases use the buy cost rate and sales use the sell cost rate.

## Strategy scope

This is the long-only, single-instrument system from the original Excel model, not the complete classic Turtle portfolio system:

- long only;
- one entry and one full exit;
- no additional unit every `0.5N`;
- no four-unit maximum;
- no separate System 1 and System 2;
- no portfolio correlation or aggregate risk limits;
- a fixed 1-ATR stop with no trailing adjustment.

In concise terms:

> Enter above the previous 20-day high; exit below the previous 10-day low or a fixed 1-ATR stop; size the position with a 2% NAV risk budget.

## Daily output

| Category | Fields |
|---|---|
| Raw prices | `Date`, `open`, `high`, `low`, `close` |
| Cleaned prices | `Clean Open`, `Clean High`, `Clean Low`, `Clean Close` |
| Volatility and channels | `TR`, `ATR`, `Past High`, `Past Low` |
| Signals and trades | `Signal`, `Trade Price`, `Stop Loss`, `Trade` |
| Account | `Position`, `Cash`, `Stock Value`, `Trading Cost` |
| Performance | `Daily P&L`, `NAV`, `Daily Return`, `Drawdown` |
| Comparison series | `NAV Index`, `Close Index` |

The comparison series are:

```text
NAV Index = NAV / Initial Cash × 100
Close Index = Clean Close / First Clean Close × 100
```

Both start at 100 and use the same unit, so they can be directly compared as cumulative performance series.

## Summary metrics

The summary includes ending NAV, cumulative return, annualized return, maximum drawdown, annualized volatility, Sharpe ratio, trade counts, time in market, ending position, total transaction cost, minimum cash, current signal, and a NAV balance check.

### Annualized return

Annualized return is CAGR, not the arithmetic average of yearly returns:

```text
Annualized Return =
(Ending NAV / Starting NAV) ^ (365 / Elapsed Calendar Days) - 1
```

### Annualized volatility

```text
Annualized Volatility =
Sample Standard Deviation of Daily Returns × SQRT(252)
```

### Sharpe ratio

```text
Sharpe Ratio =
Mean Daily Return × 252 / Annualized Volatility
```

No risk-free rate is deducted, which is equivalent to assuming a zero risk-free rate.

## Charting notebook

Open:

```text
Py_version/index_nav_vs_close.ipynb
```

The notebook reads `Excel_version/海龟法则_stock_data_2026.xlsx` by default and backtests all 9 instruments. It contains:

1. the workbook instrument list;
2. backtests for all selected instruments;
3. one dual-axis chart per instrument;
4. an actual-NAV comparison chart for all 9 instruments;
5. a performance summary table.

For each dual-axis chart:

- the left axis shows actual NAV;
- the right axis shows the actual closing price;
- the chart is useful for timing and turning points, but the visual heights of the two lines are not comparable returns.

For a rigorous strategy-versus-underlying comparison, use `NAV Index` and `Close Index`, since both are normalized to 100.

Major x-axis ticks are fixed at April 5 of each year:

```text
2005/4/5, 2006/4/5, ..., 2026/4/5
```

Edit `SELECTED_SYMBOLS` to include or exclude instruments. Set:

```python
SAVE_CHARTS = True
```

to save charts under `Py_version/charts/`.

## Tests

Run from the project root:

```bash
python3 -m unittest -v \
  Py_version.test_multisymbol \
  Py_version.test_parity
```

`test_multisymbol` verifies discovery of all 9 instruments, successful backtests, passing NAV balance checks, and stable key CSI 300 results.

`test_parity` compares Python with formula values cached by the original workbook:

- 5,152 rows;
- 22 daily calculated fields;
- 14 summary metrics.

If the reference workbook does not contain cached formula results, the parity test is intentionally skipped. This does not indicate a Python backtest failure.

## Main code entry points

| Functionality | File / function |
|---|---|
| Command-line orchestration | `run_backtest.py: main()` |
| Core strategy | `turtle_backtest.py: run_backtest()` |
| CSV loader | `turtle_backtest.py: load_csv()` |
| Single-instrument Excel loader | `turtle_backtest.py: load_reference_xlsx()` |
| Multi-instrument Excel loader | `turtle_backtest.py: load_raw_data_xlsx()` |
| Instrument selection | `turtle_backtest.py: select_instrument()` |
| Daily CSV output | `turtle_backtest.py: write_results_csv()` |
| Excel XML reader | `inspect_workbook.py: sheet_cells()` |
