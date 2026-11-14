"""Tests for the Chinese broker statement (交割单 / 对账单) parser."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.tools.trade_journal_parsers import (
    detect_format,
    load_dataframe,
    parse_cn_broker,
    parse_file,
)

ZHAOSHANG_DELIVERY = (
    "招商证券股份有限公司交割单\n"
    "资金账号,12345678,客户姓名,张三\n"
    "成交日期,成交时间,证券代码,证券名称,买卖标志,成交数量,成交价格,成交金额,佣金,印花税,过户费\n"
    "20261009,09:35:12,000001,平安银行,买入,1000,11.80,11800.00,5.00,0.00,0.10\n"
    "20261015,14:20:01,000001,平安银行,卖出,1000,12.10,12100.00,5.00,6.05,0.10\n"
    "20261016,10:00:00,,,银行转证券,0,0,-20000.00,0,0,0\n"
)

ZHAOSHANG_STATEMENT = (
    "对账单\n"
    "日期,摘要,证券代码,证券名称,成交数量,成交价格,发生金额,佣金,印花税,过户费\n"
    "2026-10-09,证券买入,600519,贵州茅台,100,1400.00,-140005.00,5.00,0.00,0.10\n"
    "2026-11-03,证券卖出,600519,贵州茅台,100,1450.00,144988.90,5.00,72.50,0.10\n"
    "2026-11-05,红利入账,600519,贵州茅台,0,0,1200.00,0,0,0\n"
)


def _write(tmp_path: Path, name: str, text: str, encoding: str = "utf-8") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding=encoding)
    return path


def test_detects_cn_broker_columns(tmp_path):
    path = _write(tmp_path, "delivery.csv", ZHAOSHANG_DELIVERY, encoding="gbk")
    frame = load_dataframe(path)
    assert detect_format(frame) == "cn_broker"


def test_csv_preamble_rows_do_not_break_loading(tmp_path):
    path = _write(tmp_path, "delivery.csv", ZHAOSHANG_DELIVERY, encoding="gbk")
    frame = load_dataframe(path)

    assert list(frame.columns)[:3] == ["成交日期", "成交时间", "证券代码"]
    assert len(frame) == 3


def test_parses_8_digit_date_time_and_fees(tmp_path):
    path = _write(tmp_path, "delivery.csv", ZHAOSHANG_DELIVERY, encoding="gbk")
    format_name, records = parse_file(path)

    assert format_name == "cn_broker"
    assert [record.side for record in records] == ["buy", "sell"]
    buy, sell = records
    assert buy.datetime == "2026-10-09 09:35:12"
    assert buy.symbol == "000001.SZ"
    assert buy.quantity == 1000
    assert buy.price == 11.8
    assert buy.fee == pytest.approx(5.10)
    assert sell.datetime == "2026-10-15 14:20:01"
    assert sell.fee == pytest.approx(11.15)


def test_transfer_rows_are_skipped(tmp_path):
    path = _write(tmp_path, "delivery.csv", ZHAOSHANG_DELIVERY, encoding="gbk")
    _, records = parse_file(path)

    assert all(record.symbol.startswith("000001") for record in records)


def test_statement_amount_is_absolute_and_dividends_kept(tmp_path):
    path = _write(tmp_path, "statement.csv", ZHAOSHANG_STATEMENT)
    format_name, records = parse_file(path)

    assert format_name == "cn_broker"
    buy, sell, dividend = records
    assert buy.amount == pytest.approx(140005.0)
    assert sell.amount == pytest.approx(144988.9)
    assert dividend.side == "dividend"
    assert dividend.amount == pytest.approx(1200.0)
    assert dividend.symbol == "600519.SH"


def test_price_falls_back_to_amount_over_quantity(tmp_path):
    text = (
        "成交日期,证券代码,证券名称,买卖标志,成交数量,发生金额\n"
        "2026-10-09,000001,平安银行,买入,1000,-11800.00\n"
    )
    path = _write(tmp_path, "no-price.csv", text)
    _, records = parse_file(path)

    assert records[0].price == pytest.approx(11.8)


def test_unknown_direction_rows_are_skipped(tmp_path):
    text = (
        "成交日期,证券代码,证券名称,买卖标志,成交数量,成交价格,成交金额\n"
        "2026-10-09,000001,平安银行,买入,1000,11.80,11800.00\n"
        "2026-10-10,000001,平安银行,担保品划出,1000,11.80,11800.00\n"
    )
    path = _write(tmp_path, "odd.csv", text)
    _, records = parse_file(path)

    assert len(records) == 1


def test_missing_code_column_raises():
    import pandas as pd

    with pytest.raises(ValueError, match="securities-code"):
        parse_cn_broker(pd.DataFrame({"买卖标志": ["买入"], "成交数量": [100]}))
