import json

with open('out/f203_regime_report.json', 'r', encoding='utf-8') as f:
    rep = json.load(f)

matrix = rep['regime_matrix']
print(f"Total evaluated cells: {len(matrix)}")
sign_flips = [c for c in matrix if c['sign_flip']]
print(f"Total sign-flip cells: {len(sign_flips)} ({len(sign_flips)/len(matrix)*100:.1f}%)")

hose_cells = [c for c in matrix if c['exchange'] == 'HOSE']
print(f"HOSE sign-flip cells: {sum(1 for c in hose_cells if c['sign_flip'])} / {len(hose_cells)}")

print("\nKey Regimes Breakdown on HOSE:")
for c in hose_cells:
    sf = 'SIGN-FLIP (-)' if c['sign_flip'] else 'REVERSION (+)'
    print(f"{c['regime_id']:<20} | n={c['n_events']:>5} | Mean={c['mean_diff']:>7.2%} | Med={c['median_diff']:>7.2%} | Win={c['win_rate']:>6.1%} | {sf}")

print("\nSummary Across All Exchanges:")
for ex in ["ALL", "HOSE", "HNX", "UPCOM"]:
    cells = [c for c in matrix if c['exchange'] == ex]
    sf_count = sum(1 for c in cells if c['sign_flip'])
    print(f"{ex:<6}: {sf_count:>2} / {len(cells):>2} sign-flips ({sf_count/len(cells)*100:.1f}%)")
