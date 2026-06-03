from __future__ import annotations

from statistics import mean

from .clients import BINANCE_SYMBOL_MAP, OKX_SYMBOL_MAP, fetch_binance_candles, fetch_okx_candles
from .config import AppConfig


TREND_SYMBOLS = ["BTC", "ETH", "SOL", "XAU"]

TIMEFRAME_SPECS = [
    {"key": "5m", "label": "5分钟", "mission": "找入场", "bars": {"okx": "5m", "binance": "5m"}, "lookback": 36},
    {"key": "15m", "label": "15分钟", "mission": "找机会", "bars": {"okx": "15m", "binance": "15m"}, "lookback": 36},
    {"key": "1h", "label": "1小时", "mission": "看日内节奏", "bars": {"okx": "1H", "binance": "1h"}, "lookback": 36},
    {"key": "4h", "label": "4小时", "mission": "看波段节奏", "bars": {"okx": "4H", "binance": "4h"}, "lookback": 36},
    {"key": "1d", "label": "日线", "mission": "看大方向", "bars": {"okx": "1D", "binance": "1d"}, "lookback": 36},
]


def build_trend_learning_payload(config: AppConfig) -> dict:
    exchange = _pick_exchange(config)
    assets: dict[str, dict] = {}

    for symbol in TREND_SYMBOLS:
        pair = _pair_for_symbol(exchange, symbol)
        if not pair:
            continue
        asset_payload = _build_asset_payload(exchange, symbol, pair, config.request_timeout_seconds)
        if asset_payload:
            assets[symbol] = asset_payload

    return {
        "exchange": exchange.upper(),
        "symbols": list(assets.keys()),
        "assets": assets,
        "updated_at": assets.get("BTC", {}).get("updatedAt"),
        "note": "基于公开 K 线和最近价格结构做的简化趋势学习判断，不是投资建议。",
    }


def _pick_exchange(config: AppConfig) -> str:
    return "binance" if config.preferred_exchange.lower().strip() == "binance" else "okx"


def _pair_for_symbol(exchange: str, symbol: str) -> str | None:
    return OKX_SYMBOL_MAP.get(symbol) if exchange == "okx" else BINANCE_SYMBOL_MAP.get(symbol)


def _build_asset_payload(exchange: str, symbol: str, pair: str, timeout: int) -> dict | None:
    candles_by_key: dict[str, list[dict]] = {}
    heatmap: list[dict] = []
    latest_timestamp = None

    for spec in TIMEFRAME_SPECS:
        candles = _fetch_candles(exchange, pair, spec["bars"][exchange], spec["lookback"], timeout)
        if len(candles) < 20:
            return None
        candles_by_key[spec["key"]] = candles
        latest_timestamp = max(latest_timestamp or 0, int(candles[-1]["timestamp"]))
        heatmap.append(_build_heatmap_cell(spec, candles))

    headline = _headline_from_heatmap(heatmap)
    plan = _build_trade_plan(symbol, heatmap, candles_by_key)

    return {
        "name": symbol,
        "trendBias": headline,
        "phase": _build_phase(heatmap),
        "durationHint": _build_duration_hint(heatmap),
        "explanation": _build_explanation(heatmap),
        "aiScript": _build_ai_script(heatmap, headline, plan),
        "warning": _build_conflict_warning(heatmap),
        "plan": plan,
        "heatmap": heatmap,
        "reasonCards": _build_reason_cards(heatmap),
        "updatedAt": latest_timestamp,
    }


def _fetch_candles(exchange: str, pair: str, bar: str, limit: int, timeout: int) -> list[dict]:
    if exchange == "okx":
        return fetch_okx_candles(pair=pair, bar=bar, limit=limit, timeout=timeout)
    return fetch_binance_candles(pair=pair, interval=bar, limit=limit, timeout=timeout)


def _build_heatmap_cell(spec: dict, candles: list[dict]) -> dict:
    closes = [float(item["close"]) for item in candles]
    highs = [float(item["high"]) for item in candles]
    lows = [float(item["low"]) for item in candles]

    last_price = closes[-1]
    fast_ma = mean(closes[-5:])
    slow_ma = mean(closes[-20:])
    short_return = _pct_change(closes[-6], closes[-1])
    swing_return = _pct_change(closes[-12], closes[-1])
    range_pct = _pct_change(min(lows[-12:]), max(highs[-12:]))
    ma_gap_pct = _pct_change(slow_ma, fast_ma)
    momentum_bias = short_return + swing_return * 0.6 + ma_gap_pct * 0.8

    direction = "震荡"
    score = 50
    tone = "range"

    if last_price > fast_ma > slow_ma and swing_return > 0.25:
        direction = "上涨"
        score = min(96, 55 + int(abs(swing_return) * 8 + abs(ma_gap_pct) * 10))
        tone = "strong-bull" if score >= 76 else "weak-bull"
    elif last_price < fast_ma < slow_ma and swing_return < -0.25:
        direction = "下跌"
        score = min(96, 55 + int(abs(swing_return) * 8 + abs(ma_gap_pct) * 10))
        tone = "strong-bear" if score >= 76 else "weak-bear"
    else:
        score = max(38, min(62, 50 + int(momentum_bias * 2)))

    return {
        "timeframe": spec["label"],
        "mission": spec["mission"],
        "tone": tone,
        "direction": direction,
        "score": score,
        "summary": _cell_summary(direction, tone, short_return, range_pct),
        "probabilityWindow": _probability_window(spec["key"], score),
        "miniCandles": _build_mini_candles(candles[-18:]),
        "reasons": _build_reasons(direction, last_price, fast_ma, slow_ma, short_return, swing_return, range_pct),
        "metrics": {
            "lastPrice": last_price,
            "fastMa": fast_ma,
            "slowMa": slow_ma,
            "shortReturn": round(short_return, 2),
            "swingReturn": round(swing_return, 2),
            "rangePct": round(range_pct, 2),
        },
    }


def _headline_from_heatmap(heatmap: list[dict]) -> str:
    daily = _find_cell(heatmap, "日线")
    four_hour = _find_cell(heatmap, "4小时")
    short_term = _find_cell(heatmap, "15分钟")

    if daily["direction"] == "上涨" and four_hour["direction"] == "上涨":
        return "大方向偏多"
    if daily["direction"] == "下跌" and four_hour["direction"] == "下跌":
        return "大方向偏空"
    if daily["direction"] != short_term["direction"]:
        return "长短周期有分歧"
    return "当前以震荡观察为主"


def _build_phase(heatmap: list[dict]) -> str:
    five_min = _find_cell(heatmap, "5分钟")
    fifteen_min = _find_cell(heatmap, "15分钟")
    four_hour = _find_cell(heatmap, "4小时")

    if four_hour["direction"] == "上涨" and fifteen_min["direction"] == "震荡":
        return "适合等回踩后的观察入场"
    if four_hour["direction"] == "上涨" and five_min["direction"] == "上涨":
        return "短线转强，但别离安全带太远"
    if four_hour["direction"] == "下跌" and five_min["direction"] == "上涨":
        return "更像下跌里的反弹，先别急着追"
    if four_hour["direction"] == "下跌":
        return "偏弱阶段，适合先观察风险"
    return "震荡阶段，等方向更清楚再出手"


def _build_explanation(heatmap: list[dict]) -> str:
    daily = _find_cell(heatmap, "日线")
    four_hour = _find_cell(heatmap, "4小时")
    fifteen_min = _find_cell(heatmap, "15分钟")
    five_min = _find_cell(heatmap, "5分钟")
    return (
        f"日线像潮汐，目前{_plain_dir(daily['direction'])}；"
        f"4小时像海浪，目前{_plain_dir(four_hour['direction'])}；"
        f"15分钟是上车机会区，现在{_plain_dir(fifteen_min['direction'])}；"
        f"5分钟是脚下台阶，现在{_plain_dir(five_min['direction'])}。"
    )


def _build_ai_script(heatmap: list[dict], headline: str, plan: dict) -> str:
    daily = _find_cell(heatmap, "日线")
    four_hour = _find_cell(heatmap, "4小时")
    fifteen_min = _find_cell(heatmap, "15分钟")
    five_min = _find_cell(heatmap, "5分钟")
    return (
        f"当前日线{_bias_word(daily['direction'])}，4小时{_bias_word(four_hour['direction'])}，"
        f"15分钟{_action_word(fifteen_min['direction'])}，5分钟{_action_word(five_min['direction'])}。"
        f"整体来看，{headline}。如果要做计划，更适合等价格走到 {plan['entryZone']} 再观察，"
        f"并把安全带放在 {plan['stopLoss']} 附近。"
    )


def _build_conflict_warning(heatmap: list[dict]) -> str:
    daily = _find_cell(heatmap, "日线")
    five_min = _find_cell(heatmap, "5分钟")
    if daily["direction"] != five_min["direction"]:
        return (
            f"日线{daily['direction']}，但5分钟{five_min['direction']}，"
            "这通常只是大级别趋势里的短线反向波动，不适合只看一根小K线就追。"
        )
    return "长短周期目前没有明显打架，但入场前仍要先看价格有没有站稳关键位置。"


def _build_duration_hint(heatmap: list[dict]) -> str:
    four_hour = _find_cell(heatmap, "4小时")
    daily = _find_cell(heatmap, "日线")
    if daily["direction"] == four_hour["direction"] == "上涨":
        return "如果 4 小时结构不破，当前上升节奏继续维持 1 到 3 天的概率偏高。"
    if daily["direction"] == four_hour["direction"] == "下跌":
        return "如果 4 小时弱势不收回，当前偏弱节奏继续延续 1 到 3 天的概率偏高。"
    return "当前更像整理和切换阶段，未来 6 到 24 小时继续拉扯后再选方向的概率更高。"


def _build_trade_plan(symbol: str, heatmap: list[dict], candles_by_key: dict[str, list[dict]]) -> dict:
    fifteen = candles_by_key["15m"]
    hourly = candles_by_key["1h"]
    four_hour = candles_by_key["4h"]

    current = float(hourly[-1]["close"])
    support = min(float(item["low"]) for item in hourly[-12:])
    resistance = max(float(item["high"]) for item in hourly[-12:])
    entry_support = min(float(item["low"]) for item in fifteen[-8:])
    entry_resistance = max(float(item["high"]) for item in fifteen[-8:])
    daily_direction = _find_cell(heatmap, "日线")["direction"]
    daily_cell = _find_cell(heatmap, "日线")
    four_hour_cell = _find_cell(heatmap, "4小时")
    trend_direction = four_hour_cell["direction"]
    short_direction = _find_cell(heatmap, "15分钟")["direction"]

    range_size = max(0.0001, resistance - support)
    long_entry_low = support + range_size * 0.10
    long_entry_high = support + range_size * 0.28
    long_stop = support - range_size * 0.10
    long_target1 = resistance - range_size * 0.08
    long_target2 = resistance + range_size * 0.22

    short_entry_low = resistance - range_size * 0.28
    short_entry_high = resistance - range_size * 0.10
    short_stop = resistance + range_size * 0.10
    short_target1 = support + range_size * 0.08
    short_target2 = support - range_size * 0.22

    entry_low = long_entry_low
    entry_high = long_entry_high
    stop_loss = long_stop
    target1 = long_target1
    target2 = long_target2
    stance = "顺大方向等回踩"
    action = "价格回到支撑附近，再等 5 分钟企稳确认。"

    if trend_direction == "下跌":
        entry_low = short_entry_low
        entry_high = short_entry_high
        stop_loss = short_stop
        target1 = short_target1
        target2 = short_target2
        stance = "弱势里等反弹"
        action = "先等反弹靠近压力，再看 5 分钟是否重新转弱。"
    elif trend_direction == "震荡" or short_direction == "震荡":
        entry_low = entry_support
        entry_high = entry_resistance
        stop_loss = support - range_size * 0.08
        target1 = resistance - range_size * 0.12
        target2 = resistance
        stance = "震荡里等边界"
        action = "不要在中间区域追单，等靠近上下边界再观察。"

    entry_mid = (entry_low + entry_high) / 2
    reward = abs(target1 - entry_mid)
    risk = abs(entry_mid - stop_loss)
    risk_reward = reward / max(0.0001, risk)

    long_plan = _scenario_plan(
        symbol=symbol,
        title="做多观察方案",
        setup="站稳再进",
        entry_low=long_entry_low,
        entry_high=long_entry_high,
        stop_loss=long_stop,
        target1=long_target1,
        target2=long_target2,
        when_to_use=_long_when_to_use(daily_direction, trend_direction, short_direction),
        trigger_rule=_long_trigger_rule(trend_direction, short_direction),
        invalidation_rule="跌回支撑下方，且 5 分钟继续出低点，就先当做多思路失效。",
    )
    short_plan = _scenario_plan(
        symbol=symbol,
        title="做空观察方案",
        setup="反抽失败再进",
        entry_low=short_entry_low,
        entry_high=short_entry_high,
        stop_loss=short_stop,
        target1=short_target1,
        target2=short_target2,
        when_to_use=_short_when_to_use(daily_direction, trend_direction, short_direction),
        trigger_rule=_short_trigger_rule(trend_direction, short_direction),
        invalidation_rule="重新站稳压力上方，且 5 分钟低点抬高，就先把做空计划取消。",
    )

    return {
        "stance": stance,
        "action": action,
        "current": _format_price(symbol, current),
        "support": _format_price(symbol, support),
        "resistance": _format_price(symbol, resistance),
        "entryZone": f"{_format_price(symbol, entry_low)} - {_format_price(symbol, entry_high)}",
        "stopLoss": _format_price(symbol, stop_loss),
        "target1": _format_price(symbol, target1),
        "target2": _format_price(symbol, target2),
        "riskReward": f"1 : {risk_reward:.1f}",
        "planSummary": _plan_summary(trend_direction, stance),
        "entryRule": _entry_rule(trend_direction),
        "stopRule": _stop_rule(trend_direction),
        "targetRule": _target_rule(trend_direction),
        "recommendedPlan": "做多观察方案" if trend_direction == "上涨" else "做空观察方案" if trend_direction == "下跌" else "区间两边都观察",
        "headlineSignal": _headline_signal(trend_direction, short_direction),
        "headlineTone": _headline_tone(trend_direction, short_direction),
        "headlineStrength": _headline_strength(daily_cell, four_hour_cell, short_direction),
        "headlineConclusion": _headline_conclusion(trend_direction, short_direction),
        "simpleConclusion": _simple_conclusion(trend_direction, short_direction),
        "watchFirst": _watch_first(trend_direction, short_direction),
        "avoidWhen": _avoid_when(trend_direction, short_direction),
        "longPlan": long_plan,
        "shortPlan": short_plan,
        "updatedAt": int(four_hour[-1]["timestamp"]),
    }


def _build_reason_cards(heatmap: list[dict]) -> list[dict]:
    cards: list[dict] = []
    for cell in heatmap:
        metrics = cell["metrics"]
        cards.append(
            {
                "timeframe": cell["timeframe"],
                "direction": cell["direction"],
                "score": cell["score"],
                "reasons": cell["reasons"],
                "facts": [
                    f"最近一段变化 {metrics['shortReturn']}%",
                    f"波段变化 {metrics['swingReturn']}%",
                    f"快线/慢线位置 {metrics['fastMa']:.2f} / {metrics['slowMa']:.2f}",
                ],
            }
        )
    return cards


def _find_cell(heatmap: list[dict], label: str) -> dict:
    return next(item for item in heatmap if item["timeframe"] == label)


def _build_reasons(
    direction: str,
    last_price: float,
    fast_ma: float,
    slow_ma: float,
    short_return: float,
    swing_return: float,
    range_pct: float,
) -> list[str]:
    ma_text = f"现价 {last_price:.2f}，快线 {fast_ma:.2f}，慢线 {slow_ma:.2f}"
    move_text = f"近段变化 {short_return:.2f}% ，波段变化 {swing_return:.2f}%"
    range_text = f"最近波动带宽约 {range_pct:.2f}%"

    if direction == "上涨":
        return [ma_text, move_text, f"{range_text}，价格结构仍在抬高"]
    if direction == "下跌":
        return [ma_text, move_text, f"{range_text}，价格结构仍在走低"]
    return [ma_text, move_text, f"{range_text}，方向还没有形成一致推进"]


def _build_mini_candles(candles: list[dict]) -> list[dict]:
    if not candles:
        return []
    width = 100.0
    height = 36.0
    highs = [float(item["high"]) for item in candles]
    lows = [float(item["low"]) for item in candles]
    high = max(highs)
    low = min(lows)
    spread = max(high - low, 0.0001)
    step = width / max(1, len(candles))
    body_width = max(2.0, step * 0.5)
    chart: list[dict] = []

    def scale(value: float) -> float:
        return height - (((value - low) / spread) * height)

    for index, candle in enumerate(candles):
        open_price = float(candle["open"])
        close_price = float(candle["close"])
        high_price = float(candle["high"])
        low_price = float(candle["low"])
        spread_value = max(high_price - low_price, 0.0001)
        body_value = abs(close_price - open_price)
        x = step * index + step / 2
        body_top = min(scale(open_price), scale(close_price))
        body_bottom = max(scale(open_price), scale(close_price))
        chart.append(
            {
                "x": round(x, 2),
                "width": round(body_width, 2),
                "wickTop": round(scale(high_price), 2),
                "wickBottom": round(scale(low_price), 2),
                "bodyTop": round(body_top, 2),
                "bodyHeight": round(max(1.4, body_bottom - body_top), 2),
                "openY": round(scale(open_price), 2),
                "closeY": round(scale(close_price), 2),
                "closeValue": round(close_price, 4),
                "biasLabel": _candle_bias_label(open_price, close_price, body_value, spread_value),
                "shapeLabel": _candle_shape_label(open_price, close_price, body_value, spread_value),
                "direction": "up" if close_price >= open_price else "down",
            }
        )
    return chart


def _scenario_plan(
    *,
    symbol: str,
    title: str,
    setup: str,
    entry_low: float,
    entry_high: float,
    stop_loss: float,
    target1: float,
    target2: float,
    when_to_use: str,
    trigger_rule: str,
    invalidation_rule: str,
) -> dict:
    entry_mid = (entry_low + entry_high) / 2
    reward = abs(target1 - entry_mid)
    risk = abs(entry_mid - stop_loss)
    return {
        "title": title,
        "setup": setup,
        "entryZone": f"{_format_price(symbol, entry_low)} - {_format_price(symbol, entry_high)}",
        "stopLoss": _format_price(symbol, stop_loss),
        "target1": _format_price(symbol, target1),
        "target2": _format_price(symbol, target2),
        "riskReward": f"1 : {reward / max(0.0001, risk):.1f}",
        "whenToUse": when_to_use,
        "triggerRule": trigger_rule,
        "invalidationRule": invalidation_rule,
    }


def _long_when_to_use(daily_direction: str, trend_direction: str, short_direction: str) -> str:
    if daily_direction == "上涨" and trend_direction == "上涨":
        return "更适合日线和 4 小时都偏多时，用回踩后的企稳去接。"
    if trend_direction == "上涨" and short_direction != "下跌":
        return "适合大级别仍偏多，但短线正在整理的时候观察。"
    return "只有当价格重新收回关键位，且 5 分钟低点抬高时，才值得看一眼。"


def _short_when_to_use(daily_direction: str, trend_direction: str, short_direction: str) -> str:
    if daily_direction == "下跌" and trend_direction == "下跌":
        return "更适合日线和 4 小时都偏空时，用反抽后的转弱去跟。"
    if trend_direction == "下跌" and short_direction != "上涨":
        return "适合大级别偏弱，但短线刚好反抽到压力带附近的时候观察。"
    return "只有当价格冲高站不稳，且 5 分钟重新出低点时，才值得看空。"


def _long_trigger_rule(trend_direction: str, short_direction: str) -> str:
    if trend_direction == "上涨":
        return "先等价格回到支撑带，再等 5 分钟收回前一根高点，属于站稳再进。"
    if short_direction == "上涨":
        return "若 15 分钟先转强，再等 5 分钟二次回踩不破低点后观察。"
    return "没有重新站稳前，不要急着在下跌途中抄底。"


def _short_trigger_rule(trend_direction: str, short_direction: str) -> str:
    if trend_direction == "下跌":
        return "先等价格反抽到压力带，再等 5 分钟跌回前一根低点下方，属于反抽失败再进。"
    if short_direction == "下跌":
        return "若 15 分钟先转弱，再等 5 分钟冲高不过前高后观察。"
    return "没有明显转弱前，不要在上涨途中硬做空。"


def _watch_first(trend_direction: str, short_direction: str) -> str:
    if trend_direction == "上涨":
        return "先看 15 分钟有没有回踩，再看 5 分钟能不能站回去。"
    if trend_direction == "下跌":
        return "先看价格有没有反抽到压力区，再看 5 分钟会不会重新转弱。"
    if short_direction == "上涨":
        return "先看能不能站上区间上沿，不然先别当成真突破。"
    if short_direction == "下跌":
        return "先看会不会跌破区间下沿，不然先别当成真下跌。"
    return "先看价格是不是靠近区间边缘，中间地带先别急。"


def _avoid_when(trend_direction: str, short_direction: str) -> str:
    if trend_direction == "上涨":
        return "如果价格已经离支撑太远，或者 5 分钟连续冲高后放量回落，就别追。"
    if trend_direction == "下跌":
        return "如果价格还没反抽到压力区，或者突然一根大阳直接站回去，就别硬空。"
    if short_direction == "上涨":
        return "如果只是区间中间的小反弹，没有站稳关键位，就别误以为趋势翻多。"
    if short_direction == "下跌":
        return "如果只是区间中间的小回落，没有跌破关键位，就别误以为趋势翻空。"
    return "如果位置卡在区间中间、盈亏比又不划算，就先看不做。"


def _simple_conclusion(trend_direction: str, short_direction: str) -> str:
    if trend_direction == "上涨":
        return "今天先等回踩站稳，再考虑顺着多头节奏看机会。"
    if trend_direction == "下跌":
        return "今天先等反抽，不要急着硬空，等转弱确认再看。"
    if short_direction == "上涨":
        return "今天先看区间上沿，没站稳前先别当成真突破。"
    if short_direction == "下跌":
        return "今天先看区间下沿，没跌破前先别当成真下跌。"
    return "今天先等价格靠近边界，中间位置先观察不出手。"


def _headline_conclusion(trend_direction: str, short_direction: str) -> str:
    if trend_direction == "上涨":
        return "今天先等回踩，不追高，不猜顶。"
    if trend_direction == "下跌":
        return "今天先等，不追，不猜底。"
    if short_direction == "上涨":
        return "今天先看站稳，再决定追不追。"
    if short_direction == "下跌":
        return "今天先看跌破，再决定跟不跟。"
    return "今天先看边界，先别在中间乱出手。"


def _headline_signal(trend_direction: str, short_direction: str) -> str:
    if trend_direction == "上涨":
        return "多头节奏"
    if trend_direction == "下跌":
        return "空头节奏"
    if short_direction == "上涨":
        return "突破观察"
    if short_direction == "下跌":
        return "跌破观察"
    return "震荡观察"


def _headline_tone(trend_direction: str, short_direction: str) -> str:
    if trend_direction == "上涨":
        return "bull"
    if trend_direction == "下跌":
        return "bear"
    if short_direction in {"上涨", "下跌"}:
        return "watch"
    return "range"


def _headline_strength(daily_cell: dict, four_hour_cell: dict, short_direction: str) -> str:
    if daily_cell["direction"] == four_hour_cell["direction"] and four_hour_cell["direction"] in {"上涨", "下跌"}:
        if daily_cell["score"] >= 72 and four_hour_cell["score"] >= 76:
            return "strong"
        return "soft"
    if short_direction in {"上涨", "下跌"} and four_hour_cell["score"] >= 58:
        return "soft"
    return "quiet"


def _candle_bias_label(open_price: float, close_price: float, body_value: float, spread_value: float) -> str:
    if (body_value / spread_value) < 0.22:
        return "震荡"
    if close_price >= open_price:
        return "偏强"
    return "偏弱"


def _candle_shape_label(open_price: float, close_price: float, body_value: float, spread_value: float) -> str:
    if (body_value / spread_value) < 0.22:
        return "十字犹豫"
    if close_price >= open_price:
        return "上涨实体"
    return "下跌实体"


def _plain_dir(direction: str) -> str:
    if direction == "上涨":
        return "偏上走"
    if direction == "下跌":
        return "偏下走"
    return "来回拉扯"


def _bias_word(direction: str) -> str:
    if direction == "上涨":
        return "偏多"
    if direction == "下跌":
        return "偏空"
    return "震荡"


def _action_word(direction: str) -> str:
    if direction == "上涨":
        return "在试着转强"
    if direction == "下跌":
        return "还在回落"
    return "还在整理"


def _cell_summary(direction: str, tone: str, short_return: float, range_pct: float) -> str:
    if direction == "上涨":
        return "趋势推进较顺，强势明显" if tone == "strong-bull" else "偏多但还要看确认"
    if direction == "下跌":
        return "弱势延续，压力较大" if tone == "strong-bear" else "偏弱运行，注意支撑"
    if abs(short_return) < 0.15 and abs(range_pct) < 1.2:
        return "短线来回拉扯"
    return "方向还不够一致"


def _probability_window(timeframe_key: str, score: int) -> str:
    if timeframe_key == "5m":
        return "30-90分钟"
    if timeframe_key == "15m":
        return "2-6小时"
    if timeframe_key == "1h":
        return "6-12小时" if score >= 60 else "4-8小时"
    if timeframe_key == "4h":
        return "1-3天"
    return "3-7天"


def _plan_summary(direction: str, stance: str) -> str:
    if direction == "上涨":
        return f"大级别偏多，计划以 {stance} 为主。"
    if direction == "下跌":
        return f"大级别偏弱，计划以 {stance} 为主。"
    return f"当前偏震荡，计划以 {stance} 为主。"


def _entry_rule(direction: str) -> str:
    if direction == "上涨":
        return "等价格回到支撑带，再看 5 分钟是否止跌企稳。"
    if direction == "下跌":
        return "等价格反弹到压力带，再看 5 分钟是否重新转弱。"
    return "只在上下边界附近观察，不在中间区域随意进。"


def _stop_rule(direction: str) -> str:
    if direction == "上涨":
        return "跌破支撑带且 5 分钟继续走弱，就当计划失效。"
    if direction == "下跌":
        return "反弹站稳压力带上方，就当计划失效。"
    return "边界失守就先退，不要把震荡单拿成长线。"


def _target_rule(direction: str) -> str:
    if direction == "上涨":
        return "先看前高附近，再看突破后的延伸空间。"
    if direction == "下跌":
        return "先看前低附近，再看跌破后的延伸空间。"
    return "先看到区间另一侧，再看是否需要全部离场。"


def _pct_change(base: float, current: float) -> float:
    if base == 0:
        return 0.0
    return ((current - base) / base) * 100.0


def _format_price(symbol: str, value: float) -> str:
    digits = 2
    if symbol in {"DOGE", "SUI"}:
        digits = 4
    return f"${value:,.{digits}f}"
