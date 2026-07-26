"""Analyze the reference CSV dataset for verification."""
import csv
import math

CSV_PATH = r"C:\Users\kumar\Downloads\c5c8d485-e827-4cd6-a3f3-631921a2bfd3Autonomous_Choke_Control_Simulated_Dataset (1).csv"

with open(CSV_PATH, "r") as f:
    reader = csv.DictReader(f)
    data = list(reader)

for row in data:
    for k in row:
        row[k] = float(row[k])

n = len(data)
cols = ["Time_hr", "Choke_pct", "OilRate_bbl_hr", "WHP_psi", "FLP_psi", "BHP_psi"]

print("=" * 70)
print("STATISTICAL SUMMARY")
print("=" * 70)
for col in cols:
    vals = [row[col] for row in data]
    mn, mx = min(vals), max(vals)
    avg = sum(vals) / len(vals)
    std = math.sqrt(sum((v - avg) ** 2 for v in vals) / len(vals))
    print(f"  {col:20s}: min={mn:>10.2f}  max={mx:>10.2f}  mean={avg:>10.2f}  std={std:>8.2f}")

# Detect choke changes
choke_vals = [row["Choke_pct"] for row in data]
print()
print("=" * 70)
print("CHOKE CHANGE EVENTS")
print("=" * 70)
for i in range(1, n):
    if choke_vals[i] != choke_vals[i - 1]:
        t = data[i]["Time_hr"]
        c_old = choke_vals[i - 1]
        c_new = choke_vals[i]
        q = data[i]["OilRate_bbl_hr"]
        whp = data[i]["WHP_psi"]
        flp = data[i]["FLP_psi"]
        bhp = data[i]["BHP_psi"]
        print(f"  t={t:>3.0f}h: Choke {c_old:>5.1f}% -> {c_new:>5.1f}% | Q={q:.1f}, WHP={whp:.1f}, FLP={flp:.1f}, BHP={bhp:.1f}")

# Identify operating regimes
print()
print("=" * 70)
print("OPERATING REGIMES")
print("=" * 70)
regimes = []
start = 0
for i in range(1, n):
    if choke_vals[i] != choke_vals[start]:
        regimes.append((start, i - 1, choke_vals[start]))
        start = i
regimes.append((start, n - 1, choke_vals[start]))

for s, e, choke in regimes:
    duration = e - s + 1
    q_final = sum(data[j]["OilRate_bbl_hr"] for j in range(max(s, e - 2), e + 1)) / min(3, e - s + 1)
    whp_final = sum(data[j]["WHP_psi"] for j in range(max(s, e - 2), e + 1)) / min(3, e - s + 1)
    flp_final = sum(data[j]["FLP_psi"] for j in range(max(s, e - 2), e + 1)) / min(3, e - s + 1)
    bhp_final = sum(data[j]["BHP_psi"] for j in range(max(s, e - 2), e + 1)) / min(3, e - s + 1)
    print(f"  Steps {s:>3d}-{e:>3d} ({duration:>3d} steps): Choke={choke:>5.1f}%")
    print(f"    SS: Q={q_final:>7.1f}  WHP={whp_final:>7.1f}  FLP={flp_final:>7.1f}  BHP={bhp_final:>7.1f}")

# Steady-state gains between regimes
print()
print("=" * 70)
print("ESTIMATED STEADY-STATE GAINS (between regime transitions)")
print("=" * 70)
for i in range(1, len(regimes)):
    s1, e1, c1 = regimes[i - 1]
    s2, e2, c2 = regimes[i]
    du = c2 - c1

    def ss_avg(start_idx, end_idx, col):
        idxs = list(range(max(start_idx, end_idx - 2), end_idx + 1))
        return sum(data[j][col] for j in idxs) / len(idxs)

    q1, q2 = ss_avg(s1, e1, "OilRate_bbl_hr"), ss_avg(s2, e2, "OilRate_bbl_hr")
    whp1, whp2 = ss_avg(s1, e1, "WHP_psi"), ss_avg(s2, e2, "WHP_psi")
    flp1, flp2 = ss_avg(s1, e1, "FLP_psi"), ss_avg(s2, e2, "FLP_psi")
    bhp1, bhp2 = ss_avg(s1, e1, "BHP_psi"), ss_avg(s2, e2, "BHP_psi")

    if du != 0:
        kq = (q2 - q1) / du
        kwhp = (whp2 - whp1) / du
        kflp = (flp2 - flp1) / du
        kbhp = (bhp2 - bhp1) / du
        print(f"  Choke {c1:.0f}% -> {c2:.0f}% (du={du:+.0f}%):")
        print(f"    K_Q={kq:+.3f}  K_WHP={kwhp:+.3f}  K_FLP={kflp:+.3f}  K_BHP={kbhp:+.3f}")

# Noise analysis
print()
print("=" * 70)
print("NOISE / VARIABILITY WITHIN STEADY REGIMES")
print("=" * 70)
for s, e, choke in regimes:
    if e - s < 5:
        continue
    # Use last half as steady-state
    mid = s + (e - s) // 2
    for col in ["OilRate_bbl_hr", "WHP_psi", "FLP_psi", "BHP_psi"]:
        vals = [data[j][col] for j in range(mid, e + 1)]
        avg = sum(vals) / len(vals)
        std = math.sqrt(sum((v - avg) ** 2 for v in vals) / len(vals))
        mx_dev = max(abs(v - avg) for v in vals)
        print(f"  Choke={choke:.0f}% {col:20s}: mean={avg:>8.2f}  std={std:>6.2f}  max_dev={mx_dev:>6.2f}")
    print()

# Time constant estimation (63.2% response)
print("=" * 70)
print("DYNAMIC RESPONSE ANALYSIS (Time Constants)")
print("=" * 70)
for i in range(1, len(regimes)):
    s1, e1, c1 = regimes[i - 1]
    s2, e2, c2 = regimes[i]
    
    y_init_q = data[e1]["OilRate_bbl_hr"]
    y_final_q = sum(data[j]["OilRate_bbl_hr"] for j in range(max(s2, e2 - 2), e2 + 1)) / min(3, e2 - s2 + 1)
    delta_q = y_final_q - y_init_q
    
    if abs(delta_q) < 1:
        continue
    
    y_63 = y_init_q + 0.632 * delta_q
    tau_q = None
    for j in range(s2, e2 + 1):
        if (delta_q > 0 and data[j]["OilRate_bbl_hr"] >= y_63) or (delta_q < 0 and data[j]["OilRate_bbl_hr"] <= y_63):
            tau_q = data[j]["Time_hr"] - data[s2]["Time_hr"]
            break
    
    print(f"  Choke {c1:.0f}% -> {c2:.0f}%: Q delta={delta_q:+.1f}, tau_Q={tau_q} hours")

# Constraint proximity
print()
print("=" * 70)
print("CONSTRAINT PROXIMITY CHECK")
print("=" * 70)
print("  (Checking if any measurements approach typical constraint limits)")
print(f"  WHP range: [{min(r['WHP_psi'] for r in data):.1f}, {max(r['WHP_psi'] for r in data):.1f}]")
print(f"  FLP range: [{min(r['FLP_psi'] for r in data):.1f}, {max(r['FLP_psi'] for r in data):.1f}]")
print(f"  BHP range: [{min(r['BHP_psi'] for r in data):.1f}, {max(r['BHP_psi'] for r in data):.1f}]")
print(f"  Q range:   [{min(r['OilRate_bbl_hr'] for r in data):.1f}, {max(r['OilRate_bbl_hr'] for r in data):.1f}]")
