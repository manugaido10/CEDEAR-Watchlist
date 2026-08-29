from pathlib import Path
from data.cocos_csv_parser import parse_positions
from data.mep import fetch_mep
from data.cache import Cache

mep = fetch_mep(Cache()).data
paths = sorted(Path("data/transactions_report").glob("report_2026*.csv"))
result = parse_positions(paths, mep)

for p in result.open_positions:
    print(f"{p.ticker:8} qty={p.net_qty:>10,.0f}  avg_cost_ars={p.avg_cost_ars:>10,.2f}")
print("\nWarnings:", result.warnings)
print("Skipped:", result.skipped_usd_no_mep)
