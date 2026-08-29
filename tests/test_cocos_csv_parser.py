"""Tests for data/cocos_csv_parser.py.

All scenarios use synthetic in-memory CSVs written to tmp_path.
No network calls, no positions_log.json access.
"""

from __future__ import annotations

import pytest
import pandas as pd
from pathlib import Path

from data.cocos_csv_parser import parse_positions, DerivedPosition, ParseResult


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def mep_series() -> pd.Series:
    """Minimal MEP series covering 2026-01-05 to 2026-01-15."""
    return pd.Series(
        {
            pd.Timestamp("2026-01-05"): 1200.0,
            pd.Timestamp("2026-01-10"): 1250.0,
            pd.Timestamp("2026-01-15"): 1300.0,
        }
    )


_HEADER = (
    "nroTicket;nroComprobante;fechaEjecucion;tipoOperacion;"
    "instrumento;moneda;cantidad;precio;montoBruto;comision;iva;otros;total"
)


def _row(*fields: object) -> str:
    return ";".join(str(f) for f in fields)


# ── Shared row definitions ─────────────────────────────────────────────────────

# AAPL: 2 ARS buys then full sell → fully closed
# Buy 10 @ total=50000, buy 5 @ total=30000, sell 15
# avg = (50000+30000)/15 = 5333.3333...
_AAPL_BUY_10 = _row(1, 1001, "05-01-2026", "Compra",
                    "CEDEAR APPLE INC. (AAPL)", "ARS",
                    10, "5000,00", "50000,00", "0,00", "0,00", "0,00", "50000,00")
_AAPL_BUY_5  = _row(2, 1002, "10-01-2026", "Compra",
                    "CEDEAR APPLE INC. (AAPL)", "ARS",
                    5,  "6000,00", "30000,00", "0,00", "0,00", "0,00", "30000,00")
_AAPL_SELL_15 = _row(3, 1003, "15-01-2026", "Venta",
                     "CEDEAR APPLE INC. (AAPL)", "ARS",
                     -15, "6000,00", "90000,00", "0,00", "0,00", "0,00", "90000,00")

# GGAL: ARS buy only → open position
# Buy 20 @ total=20000 → avg=1000
_GGAL_BUY_20 = _row(4, 1004, "05-01-2026", "Compra",
                    "GRUPO FINANCIERO GALICIA S.A. (GGAL)", "ARS",
                    20, "1000,00", "20000,00", "0,00", "0,00", "0,00", "20000,00")

# MSFT: USD buy → open position (MEP=1200 on 2026-01-05)
# Buy 5 @ total=500 USD → ARS = 500 * 1200 = 600000 → avg=120000
_MSFT_BUY_USD = _row(5, 1005, "05-01-2026", "Compra Dolar Mep",
                     "CEDEAR MICROSOFT CORP. (MSFT)", "USD",
                     5, "100,00", "500,00", "0,00", "0,00", "0,00", "500,00")

# TSLA: sell with no prior buy in window → sells exceed known buys
_TSLA_SELL_ONLY = _row(6, 1006, "05-01-2026", "Venta",
                       "TESLA INC. (TSLA)", "ARS",
                       -10, "10000,00", "100000,00", "0,00", "0,00", "0,00", "100000,00")

# AMZN: USD buy dated 2025-12-31, before MEP series start → skipped
_AMZN_NO_MEP = _row(7, 1007, "31-12-2025", "Compra",
                    "AMAZON.COM INC. (AMZN)", "USD",
                    3, "100,00", "300,00", "0,00", "0,00", "0,00", "300,00")

# Ignored: non-position operation (FCI liquidation)
_FCI_ROW = _row(8, 1008, "05-01-2026", "Liquidacion Rescate Fci",
                "FONDO XYZ (FCI001)", "ARS",
                100, "10,00", "1000,00", "0,00", "0,00", "0,00", "1000,00")


def _write_csv(tmp_path: Path, rows: list[str], filename: str = "movimientos.csv") -> Path:
    path = tmp_path / filename
    path.write_text("\n".join([_HEADER] + rows), encoding="utf-8")
    return path


# ── Helpers ────────────────────────────────────────────────────────────────────

def _by_ticker(positions: list[DerivedPosition], ticker: str) -> DerivedPosition:
    matches = [p for p in positions if p.ticker == ticker]
    assert len(matches) == 1, f"expected exactly one {ticker}, got {len(matches)}"
    return matches[0]


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestFullyClosedPosition:
    def test_aapl_lands_in_closed_bucket(self, tmp_path, mep_series):
        csv = _write_csv(tmp_path, [_AAPL_BUY_10, _AAPL_BUY_5, _AAPL_SELL_15])
        result = parse_positions([csv], mep_series)

        assert any(p.ticker == "AAPL" for p in result.closed_positions)
        assert not any(p.ticker == "AAPL" for p in result.open_positions)

    def test_aapl_net_qty_is_zero(self, tmp_path, mep_series):
        csv = _write_csv(tmp_path, [_AAPL_BUY_10, _AAPL_BUY_5, _AAPL_SELL_15])
        result = parse_positions([csv], mep_series)

        pos = _by_ticker(result.closed_positions, "AAPL")
        assert pos.net_qty == pytest.approx(0.0, abs=1e-6)
        assert pos.fully_closed is True

    def test_aapl_avg_cost_is_weighted_average(self, tmp_path, mep_series):
        # Buy 10 @ 50000 total + buy 5 @ 30000 total → total_cost=80000, qty=15
        # avg = 80000 / 15 = 5333.3333...
        csv = _write_csv(tmp_path, [_AAPL_BUY_10, _AAPL_BUY_5, _AAPL_SELL_15])
        result = parse_positions([csv], mep_series)

        pos = _by_ticker(result.closed_positions, "AAPL")
        expected_avg = 80_000.0 / 15.0
        assert pos.avg_cost_ars == pytest.approx(expected_avg, rel=1e-5)

    def test_aapl_total_cost_is_zero_when_closed(self, tmp_path, mep_series):
        csv = _write_csv(tmp_path, [_AAPL_BUY_10, _AAPL_BUY_5, _AAPL_SELL_15])
        result = parse_positions([csv], mep_series)

        pos = _by_ticker(result.closed_positions, "AAPL")
        assert pos.total_cost_ars == pytest.approx(0.0, abs=1e-4)

    def test_aapl_dates(self, tmp_path, mep_series):
        csv = _write_csv(tmp_path, [_AAPL_BUY_10, _AAPL_BUY_5, _AAPL_SELL_15])
        result = parse_positions([csv], mep_series)

        pos = _by_ticker(result.closed_positions, "AAPL")
        assert pos.first_buy_date == "2026-01-05"
        assert pos.last_trade_date == "2026-01-15"


class TestOpenArsPosition:
    def test_ggal_lands_in_open_bucket(self, tmp_path, mep_series):
        csv = _write_csv(tmp_path, [_GGAL_BUY_20])
        result = parse_positions([csv], mep_series)

        assert any(p.ticker == "GGAL" for p in result.open_positions)

    def test_ggal_net_qty_and_avg_cost(self, tmp_path, mep_series):
        csv = _write_csv(tmp_path, [_GGAL_BUY_20])
        result = parse_positions([csv], mep_series)

        pos = _by_ticker(result.open_positions, "GGAL")
        assert pos.net_qty == pytest.approx(20.0, rel=1e-6)
        assert pos.avg_cost_ars == pytest.approx(1_000.0, rel=1e-6)
        assert pos.total_cost_ars == pytest.approx(20_000.0, rel=1e-6)
        assert pos.fully_closed is False


class TestUsdBuyWithMep:
    def test_msft_cost_converted_to_ars(self, tmp_path, mep_series):
        # Buy 5 @ total=500 USD, MEP=1200 → ARS = 500*1200 = 600000, avg=120000
        csv = _write_csv(tmp_path, [_MSFT_BUY_USD])
        result = parse_positions([csv], mep_series)

        pos = _by_ticker(result.open_positions, "MSFT")
        assert pos.net_qty == pytest.approx(5.0, rel=1e-6)
        assert pos.avg_cost_ars == pytest.approx(120_000.0, rel=1e-5)
        assert pos.total_cost_ars == pytest.approx(600_000.0, rel=1e-5)

    def test_msft_mep_ffill_for_intervening_date(self, tmp_path):
        # MEP series has values on 2026-01-05 and 2026-01-10.
        # Trade on 2026-01-07 (between the two) should ffill to 2026-01-05 rate=1200.
        series = pd.Series(
            {pd.Timestamp("2026-01-05"): 1200.0, pd.Timestamp("2026-01-10"): 1250.0}
        )
        row = _row(10, 2001, "07-01-2026", "Compra Dolar Mep",
                   "CEDEAR MICROSOFT CORP. (MSFT)", "USD",
                   5, "100,00", "500,00", "0,00", "0,00", "0,00", "500,00")
        csv = _write_csv(tmp_path, [row])
        result = parse_positions([csv], series)

        pos = _by_ticker(result.open_positions, "MSFT")
        assert pos.avg_cost_ars == pytest.approx(120_000.0, rel=1e-5)  # 600000/5


class TestSellsExceedKnownBuys:
    def test_tsla_not_in_any_position_bucket(self, tmp_path, mep_series):
        csv = _write_csv(tmp_path, [_TSLA_SELL_ONLY])
        result = parse_positions([csv], mep_series)

        tickers_in_result = (
            {p.ticker for p in result.open_positions}
            | {p.ticker for p in result.closed_positions}
        )
        assert "TSLA" not in tickers_in_result

    def test_tsla_warning_emitted(self, tmp_path, mep_series):
        csv = _write_csv(tmp_path, [_TSLA_SELL_ONLY])
        result = parse_positions([csv], mep_series)

        assert any("TSLA" in w and "sells exceed" in w for w in result.warnings)


class TestUsdWithNoMep:
    def test_amzn_in_skipped_bucket(self, tmp_path, mep_series):
        # Date 2025-12-31 is before the MEP series start (2026-01-05) → no MEP rate.
        csv = _write_csv(tmp_path, [_AMZN_NO_MEP])
        result = parse_positions([csv], mep_series)

        assert "AMZN" in result.skipped_usd_no_mep

    def test_amzn_not_in_position_buckets(self, tmp_path, mep_series):
        csv = _write_csv(tmp_path, [_AMZN_NO_MEP])
        result = parse_positions([csv], mep_series)

        tickers_in_result = (
            {p.ticker for p in result.open_positions}
            | {p.ticker for p in result.closed_positions}
        )
        assert "AMZN" not in tickers_in_result

    def test_amzn_warning_emitted(self, tmp_path, mep_series):
        csv = _write_csv(tmp_path, [_AMZN_NO_MEP])
        result = parse_positions([csv], mep_series)

        assert any("AMZN" in w and "MEP unavailable" in w for w in result.warnings)


# Rows that reproduce the real-world crash: non-trade rows with empty numeric cells.
_DIVIDENDOS_EMPTY = _row(20, 2001, "05-01-2026", "Dividendos",
                         "CEDEAR APPLE INC. (AAPL)", "ARS",
                         "", "", "", "", "", "", "")
_NOTA_CREDITO_EMPTY = _row(21, 2002, "05-01-2026", "Nota De Credito",
                           "CEDEAR GGAL INC. (GGAL)", "ARS",
                           "", "", "", "", "", "", "")
# Trade row with an empty `cantidad` — should drop with warning, not crash.
_NVDA_BAD_CANTIDAD = _row(22, 2003, "05-01-2026", "Compra",
                          "CEDEAR NVIDIA CORP. (NVDA)", "ARS",
                          "", "500,00", "", "0,00", "0,00", "0,00", "5000,00")


class TestRobustnessAgainstRealWorldNoise:
    def test_non_trade_rows_with_empty_numerics_do_not_crash(self, tmp_path, mep_series):
        """Regression: dividend and credit-note rows have blank numeric cells.
        Before the fix, numeric conversion ran before filtering and raised ValueError.
        """
        csv = _write_csv(tmp_path, [_GGAL_BUY_20, _DIVIDENDOS_EMPTY, _NOTA_CREDITO_EMPTY])
        result = parse_positions([csv], mep_series)  # must not raise

        # Non-trade rows silently discarded; GGAL still processed correctly.
        pos = _by_ticker(result.open_positions, "GGAL")
        assert pos.net_qty == pytest.approx(20.0)
        assert result.warnings == []

    def test_malformed_trade_row_is_dropped_with_warning(self, tmp_path, mep_series):
        """A trade row with empty `cantidad` is dropped and a warning is emitted."""
        csv = _write_csv(tmp_path, [_GGAL_BUY_20, _NVDA_BAD_CANTIDAD])
        result = parse_positions([csv], mep_series)

        all_tickers = {p.ticker for p in result.open_positions + result.closed_positions}
        assert "NVDA" not in all_tickers
        assert any("NVDA" in w and "nroTicket" in w for w in result.warnings)

        # GGAL unaffected by the bad NVDA row.
        pos = _by_ticker(result.open_positions, "GGAL")
        assert pos.net_qty == pytest.approx(20.0)


class TestNonPositionOpsIgnored:
    def test_fci_row_does_not_create_position(self, tmp_path, mep_series):
        csv = _write_csv(tmp_path, [_FCI_ROW])
        result = parse_positions([csv], mep_series)

        assert result.open_positions == []
        assert result.closed_positions == []
        assert result.warnings == []


class TestDedupAcrossMultipleCsvs:
    def test_duplicate_row_in_second_csv_does_not_double_count(
        self, tmp_path, mep_series
    ):
        # Main CSV: buy 10, buy 5, sell 15 → AAPL net=0.
        # Second CSV repeats the buy-10 row (same nroTicket+nroComprobante).
        # Without dedup: net = 10+10+5-15 = 10 (open, wrong).
        # With dedup:    net = 10+5-15 = 0 (closed, correct).
        main = _write_csv(tmp_path, [_AAPL_BUY_10, _AAPL_BUY_5, _AAPL_SELL_15],
                          filename="jan.csv")
        dup = _write_csv(tmp_path, [_AAPL_BUY_10], filename="feb.csv")  # duplicate

        result = parse_positions([main, dup], mep_series)

        assert any(p.ticker == "AAPL" for p in result.closed_positions)
        assert not any(p.ticker == "AAPL" for p in result.open_positions)


class TestAllScenariosComposite:
    def test_composite_csv_buckets(self, tmp_path, mep_series):
        """Integration: single CSV with all scenarios produces correct buckets."""
        all_rows = [
            _AAPL_BUY_10, _AAPL_BUY_5, _AAPL_SELL_15,
            _GGAL_BUY_20,
            _MSFT_BUY_USD,
            _TSLA_SELL_ONLY,
            _AMZN_NO_MEP,
            _FCI_ROW,
        ]
        csv = _write_csv(tmp_path, all_rows)
        result = parse_positions([csv], mep_series)

        open_tickers = {p.ticker for p in result.open_positions}
        closed_tickers = {p.ticker for p in result.closed_positions}

        assert "AAPL" in closed_tickers
        assert "GGAL" in open_tickers
        assert "MSFT" in open_tickers
        assert "TSLA" not in open_tickers and "TSLA" not in closed_tickers
        assert "AMZN" in result.skipped_usd_no_mep
        assert "FCI001" not in open_tickers and "FCI001" not in closed_tickers
