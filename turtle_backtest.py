"""Turtle Trading formulas and backtest flow."""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable, Sequence


# ---------------------------------------------------------------------------
# Parameters and result models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Parameters:
    atr_period: int = 20
    entry_period: int = 20
    exit_period: int = 10
    risk_fraction: float = 0.02
    buy_cost_rate: float = 0.0002
    sell_cost_rate: float = 0.0007
    initial_cash: float = 1_000_000.0
    lot_size: int = 100
    warmup_bars: int | None = None

    @property
    def required_history(self) -> int:
        """Completed bars required before the first signal is evaluated."""
        if self.warmup_bars is not None:
            return self.warmup_bars
        return max(self.atr_period, self.entry_period, self.exit_period)


@dataclass(frozen=True)
class PriceBar:
    date: object
    open: float | None
    high: float | None
    low: float | None
    close: float | None


@dataclass(frozen=True)
class CleanPrices:
    open: float | None
    high: float | None
    low: float | None
    close: float | None


@dataclass
class BacktestRow:
    date: object
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    clean_open: float | None
    clean_high: float | None
    clean_low: float | None
    clean_close: float | None
    tr: float | None
    atr: float | None
    past_high: float | None
    past_low: float | None
    signal: int
    trade_price: float | None
    stop_loss: float | None
    position: int
    cash: float
    stock_value: float
    trading_cost: float
    daily_pnl: float
    nav: float
    daily_return: float
    drawdown: float
    nav_index: float
    close_index: float | None
    trade: str


@dataclass(frozen=True)
class Summary:
    start: object
    end: object
    ending_nav: float
    total_return: float
    annualized_return: float
    max_drawdown: float
    annualized_volatility: float
    sharpe_ratio: float
    buys: int
    sells: int
    time_in_market: float
    ending_position: int
    total_trading_cost: float
    nav_check: str
    minimum_cash: float
    current_signal: str


# ---------------------------------------------------------------------------
# Price cleaning and indicators
# ---------------------------------------------------------------------------


def validate_parameters(parameters: Parameters) -> None:
    if parameters.atr_period <= 0 or parameters.entry_period <= 0:
        raise ValueError("ATR周期和入场周期必须大于0")
    if parameters.exit_period <= 0 or parameters.lot_size <= 0:
        raise ValueError("退出周期和最小交易单位必须大于0")
    if parameters.risk_fraction <= 0:
        raise ValueError("风险比例必须大于0")
    if parameters.buy_cost_rate < 0 or parameters.sell_cost_rate < 0:
        raise ValueError("交易成本率不能小于0")
    if parameters.initial_cash <= 0:
        raise ValueError("初始资金必须大于0")
    if parameters.warmup_bars is not None:
        minimum_history = max(
            parameters.entry_period, parameters.exit_period
        )
        if parameters.warmup_bars < minimum_history:
            raise ValueError(
                "自定义预热期不能小于入场周期和退出周期中的较大值"
            )


def _positive(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def clean_prices(
    bar: PriceBar, previous: BacktestRow | None
) -> CleanPrices:
    """Convert invalid prices to missing and forward-fill after the first bar."""
    clean = CleanPrices(
        open=_positive(bar.open),
        high=_positive(bar.high),
        low=_positive(bar.low),
        close=_positive(bar.close),
    )
    if previous is None:
        return clean
    return CleanPrices(
        open=clean.open if clean.open is not None else previous.clean_open,
        high=clean.high if clean.high is not None else previous.clean_high,
        low=clean.low if clean.low is not None else previous.clean_low,
        close=clean.close if clean.close is not None else previous.clean_close,
    )


def calculate_tr(
    prices: CleanPrices,
    previous_close: float | None,
) -> float | None:
    """Calculate True Range from current prices and the previous close."""
    if prices.high is None or prices.low is None:
        return None
    if previous_close is None:
        return prices.high - prices.low
    return max(
        prices.high - prices.low,
        abs(prices.high - previous_close),
        abs(previous_close - prices.low),
    )


def calculate_atr(
    tr: float | None,
    previous_atr: float | None,
    period: int,
) -> float | None:
    """Initialize ATR with TR, then apply the validated EMA formula."""
    if previous_atr is None:
        return tr
    if tr is None:
        return None
    return 2 / (period + 1) * tr + (period - 1) / (period + 1) * previous_atr


def calculate_channels(
    rows: Sequence[BacktestRow],
    parameters: Parameters,
    record_number: int,
) -> tuple[float | None, float | None]:
    """Use completed bars only to form entry and exit channels."""
    if len(rows) < parameters.required_history:
        return None, None

    high_window = [
        row.clean_high for row in rows[-parameters.entry_period :]
    ]
    low_window = [
        row.clean_low for row in rows[-parameters.exit_period :]
    ]
    if len(high_window) < parameters.entry_period or any(
        value is None for value in high_window
    ):
        raise ValueError(f"第 {record_number} 条行情无法形成入场通道")
    if len(low_window) < parameters.exit_period or any(
        value is None for value in low_window
    ):
        raise ValueError(f"第 {record_number} 条行情无法形成退出通道")

    return (
        max(value for value in high_window if value is not None),
        min(value for value in low_window if value is not None),
    )


# ---------------------------------------------------------------------------
# Turtle entry, exit, stop, and position rules
# ---------------------------------------------------------------------------


def calculate_signal(
    prices: CleanPrices,
    past_high: float | None,
    past_low: float | None,
    previous_signal: int,
    previous_stop: float | None,
) -> int:
    if past_high is None or past_low is None:
        return 0
    if previous_signal == 0:
        return int(prices.high is not None and prices.high > past_high)
    if previous_stop is None:
        raise ValueError("持仓状态缺少止损价")
    exit_level = max(past_low, previous_stop)
    return int(not (prices.low is not None and prices.low < exit_level))


def calculate_trade_price(
    prices: CleanPrices,
    past_high: float | None,
    past_low: float | None,
    previous_stop: float | None,
    is_buy: bool,
    is_sell: bool,
) -> float | None:
    if not is_buy and not is_sell:
        return None
    if prices.open is None:
        raise ValueError("交易日缺少可用开盘价")
    if is_buy:
        if past_high is None:
            raise ValueError("买入信号缺少入场通道")
        return max(prices.open, past_high)
    if past_low is None or previous_stop is None:
        raise ValueError("卖出信号缺少退出通道或止损价")
    return min(prices.open, max(past_low, previous_stop))
def calculate_stop_loss(
    previous_atr: float | None,
    previous_stop: float | None,
    trade_price: float | None,
    signal: int,
    is_buy: bool,
    record_number: int,
) -> float | None:
    if is_buy:
        if previous_atr is None or trade_price is None:
            raise ValueError(f"第 {record_number} 条行情缺少前一日 ATR")
        return trade_price - previous_atr
    return previous_stop if signal == 1 else None


def calculate_position(
    previous: BacktestRow,
    signal: int,
    is_buy: bool,
    trade_price: float | None,
    parameters: Parameters,
) -> int:
    if signal == 0:
        return 0
    if not is_buy:
        return previous.position
    if (
        previous.atr is None
        or previous.atr <= 0
        or trade_price is None
        or trade_price <= 0
    ):
        return 0

    risk_position = (
        previous.nav * parameters.risk_fraction / previous.atr
    )
    cash_position = previous.cash / (
        trade_price * (1 + parameters.buy_cost_rate)
    )
    raw_position = min(risk_position, cash_position)
    return math.floor(raw_position / parameters.lot_size) * parameters.lot_size


# ---------------------------------------------------------------------------
# Account and performance calculations
# ---------------------------------------------------------------------------


def update_cash(
    previous_cash: float,
    previous_position: int,
    position: int,
    trade_price: float | None,
    parameters: Parameters,
) -> float:
    delta = position - previous_position
    if delta == 0:
        return previous_cash
    if trade_price is None:
        raise ValueError("仓位发生变化但缺少成交价")
    cost_rate = (
        parameters.buy_cost_rate
        if delta > 0
        else parameters.sell_cost_rate
    )
    return (
        previous_cash
        - delta * trade_price
        - abs(delta) * trade_price * cost_rate
    )


def calculate_trading_cost(
    previous_position: int,
    position: int,
    trade_price: float | None,
    parameters: Parameters,
) -> float:
    delta = position - previous_position
    if delta == 0:
        return 0.0
    if trade_price is None:
        raise ValueError("仓位发生变化但缺少成交价")
    rate = (
        parameters.buy_cost_rate
        if delta > 0
        else parameters.sell_cost_rate
    )
    return abs(delta) * trade_price * rate


def _day_number(value: object) -> float:
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        return float((value - date(1899, 12, 30)).days)
    return float(value)


def calculate_summary(
    rows: Sequence[BacktestRow],
) -> Summary:
    returns = [row.daily_return for row in rows[1:]]
    annualized_volatility = (
        statistics.stdev(returns) * math.sqrt(252)
        if len(returns) >= 2
        else 0.0
    )
    average_return = statistics.mean(returns) if returns else 0.0
    elapsed_days = _day_number(rows[-1].date) - _day_number(rows[0].date)
    annualized_return = (
        (rows[-1].nav / rows[0].nav) ** (365 / elapsed_days) - 1
        if elapsed_days
        else 0.0
    )
    return Summary(
        start=rows[0].date,
        end=rows[-1].date,
        ending_nav=rows[-1].nav,
        total_return=rows[-1].nav / rows[0].nav - 1,
        annualized_return=annualized_return,
        max_drawdown=min(row.drawdown for row in rows),
        annualized_volatility=annualized_volatility,
        sharpe_ratio=(
            average_return * 252 / annualized_volatility
            if annualized_volatility
            else 0.0
        ),
        buys=sum(row.trade == "BUY" for row in rows),
        sells=sum(row.trade == "SELL" for row in rows),
        time_in_market=statistics.mean(row.signal for row in rows),
        ending_position=rows[-1].position,
        total_trading_cost=sum(row.trading_cost for row in rows),
        nav_check=(
            "PASS"
            if abs(rows[-1].nav - (rows[-1].cash + rows[-1].stock_value))
            < 0.01
            else "FAIL"
        ),
        minimum_cash=min(row.cash for row in rows),
        current_signal="持仓" if rows[-1].signal == 1 else "空仓",
    )


# ---------------------------------------------------------------------------
# Backtest orchestration
# ---------------------------------------------------------------------------


def run_backtest(
    bars: Iterable[PriceBar],
    parameters: Parameters = Parameters(),
) -> tuple[list[BacktestRow], Summary]:
    source = list(bars)
    if not source:
        raise ValueError("至少需要一行 OHLC 数据")
    validate_parameters(parameters)

    rows: list[BacktestRow] = []
    running_nav_high = parameters.initial_cash

    for index, bar in enumerate(source):
        previous = rows[-1] if rows else None
        record_number = index + 1

        prices = clean_prices(bar, previous)
        tr = calculate_tr(
            prices,
            previous.clean_close if previous else None,
        )
        atr = calculate_atr(
            tr,
            previous.atr if previous else None,
            parameters.atr_period,
        )
        past_high, past_low = calculate_channels(
            rows, parameters, record_number
        )

        previous_signal = previous.signal if previous else 0
        previous_stop = previous.stop_loss if previous else None
        signal = calculate_signal(
            prices,
            past_high,
            past_low,
            previous_signal,
            previous_stop,
        )
        is_buy = previous_signal == 0 and signal == 1
        is_sell = previous_signal == 1 and signal == 0
        trade_price = calculate_trade_price(
            prices,
            past_high,
            past_low,
            previous_stop,
            is_buy,
            is_sell,
        )
        stop_loss = calculate_stop_loss(
            previous.atr if previous else None,
            previous_stop,
            trade_price,
            signal,
            is_buy,
            record_number,
        )

        if previous is None:
            position = 0
            cash = parameters.initial_cash
            trading_cost = 0.0
        else:
            position = calculate_position(
                previous, signal, is_buy, trade_price, parameters
            )
            cash = update_cash(
                previous.cash,
                previous.position,
                position,
                trade_price,
                parameters,
            )
            trading_cost = calculate_trading_cost(
                previous.position,
                position,
                trade_price,
                parameters,
            )

        stock_value = (
            position * prices.close if prices.close is not None else 0.0
        )
        nav = cash + stock_value
        daily_pnl = 0.0 if previous is None else nav - previous.nav
        daily_return = (
            0.0
            if previous is None or previous.nav == 0
            else nav / previous.nav - 1
        )
        running_nav_high = max(running_nav_high, nav)
        drawdown = 0.0 if nav == 0 else nav / running_nav_high - 1
        nav_index = nav / parameters.initial_cash * 100
        initial_close = (
            prices.close if previous is None else rows[0].clean_close
        )
        close_index = (
            prices.close / initial_close * 100
            if prices.close is not None and initial_close not in (None, 0)
            else None
        )
        trade = "BUY" if is_buy and position > 0 else "SELL" if is_sell else ""

        rows.append(
            BacktestRow(
                date=bar.date,
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                clean_open=prices.open,
                clean_high=prices.high,
                clean_low=prices.low,
                clean_close=prices.close,
                tr=tr,
                atr=atr,
                past_high=past_high,
                past_low=past_low,
                signal=signal,
                trade_price=trade_price,
                stop_loss=stop_loss,
                position=position,
                cash=cash,
                stock_value=stock_value,
                trading_cost=trading_cost,
                daily_pnl=daily_pnl,
                nav=nav,
                daily_return=daily_return,
                drawdown=drawdown,
                nav_index=nav_index,
                close_index=close_index,
                trade=trade,
            )
        )

    return rows, calculate_summary(rows)
