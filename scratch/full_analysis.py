"""
Comprehensive engineering analysis of the Honeywell reference dataset.
Produces all numbers needed for the 11-task validation gate.
"""
import csv
import math
import sys

CSV = r"C:\Users\kumar\Downloads\c5c8d485-e827-4cd6-a3f3-631921a2bfd3Autonomous_Choke_Control_Simulated_Dataset (1).csv"

with open(CSV, "r") as f:
    reader = csv.DictReader(f)
    raw = list(reader)

data = []
for row in raw:
    data.append({k: float(v) for k, v in row.items()})

N = len(data)
VARS = ["OilRate_bbl_hr", "WHP_psi", "FLP_psi", "BHP_psi"]

def col(name):
    return [r[name] for r in data]

def stats(vals):
    n = len(vals)
    mn, mx = min(vals), max(vals)
    avg = sum(vals) / n
    var = sum((v - avg)**2 for v in vals) / n
    std = math.sqrt(var)
    s = sorted(vals)
    med = s[n//2] if n%2 else (s[n//2-1] + s[n//2])/2
    q1 = s[n//4]
    q3 = s[3*n//4]
    skew = sum((v - avg)**3 for v in vals) / (n * std**3) if std > 0 else 0
    return {"min": mn, "max": mx, "mean": avg, "std": std, "median": med,
            "q1": q1, "q3": q3, "iqr": q3-q1, "skew": skew, "n": n}

# ====== SECTION 1: STATISTICAL SUMMARY ======
print("=" * 80)
print("SECTION 1: STATISTICAL SUMMARY")
print("=" * 80)
for c in ["Time_hr", "Choke_pct"] + VARS:
    s = stats(col(c))
    print(f"\n  {c}:")
    for k, v in s.items():
        print(f"    {k:>8s}: {v:>12.4f}")

# ====== DATA QUALITY ======
print("\n" + "=" * 80)
print("SECTION 1b: DATA QUALITY")
print("=" * 80)
print(f"  Total rows: {N}")
print(f"  Columns: {list(data[0].keys())}")

# Check for NaN, inf
nan_count = sum(1 for r in data for v in r.values() if math.isnan(v) or math.isinf(v))
print(f"  NaN/Inf values: {nan_count}")

# Duplicates
dup = 0
for i in range(N):
    for j in range(i+1, N):
        if all(data[i][k] == data[j][k] for k in data[0].keys()):
            dup += 1
print(f"  Duplicate rows: {dup}")

# Negative values
neg = {c: sum(1 for r in data if r[c] < 0) for c in VARS}
print(f"  Negative values: {neg}")

# Monotonicity of time
time_gaps = [data[i+1]["Time_hr"] - data[i]["Time_hr"] for i in range(N-1)]
print(f"  Time step: min={min(time_gaps)}, max={max(time_gaps)}, all=1.0: {all(g == 1.0 for g in time_gaps)}")

# ====== SECTION 2: OPERATING REGIMES ======
print("\n" + "=" * 80)
print("SECTION 2: OPERATING REGIMES")
print("=" * 80)

chokes = col("Choke_pct")
regimes = []
start = 0
for i in range(1, N):
    if chokes[i] != chokes[start]:
        regimes.append((start, i-1, chokes[start]))
        start = i
regimes.append((start, N-1, chokes[start]))

for idx, (s, e, ck) in enumerate(regimes):
    dur = e - s + 1
    print(f"\n  Regime {idx+1}: Steps {s}-{e} ({dur} steps), Choke={ck:.0f}%")
    
    # Steady-state: last 5 points
    ss_start = max(s, e - 4)
    for var in VARS:
        vals = [data[j][var] for j in range(ss_start, e+1)]
        ss_mean = sum(vals) / len(vals)
        ss_std = math.sqrt(sum((v - ss_mean)**2 for v in vals) / len(vals))
        
        # Full regime stats
        all_vals = [data[j][var] for j in range(s, e+1)]
        pk_max = max(all_vals)
        pk_min = min(all_vals)
        
        print(f"    {var:20s}: SS_mean={ss_mean:>10.2f}  SS_std={ss_std:>6.2f}  peak=[{pk_min:.2f}, {pk_max:.2f}]")

# ====== SECTION 3: TRANSITION ANALYSIS ======
print("\n" + "=" * 80)
print("SECTION 3: TRANSITION ANALYSIS (Gains, Time Constants, Dead Times)")
print("=" * 80)

for i in range(1, len(regimes)):
    s1, e1, c1 = regimes[i-1]
    s2, e2, c2 = regimes[i]
    du = c2 - c1
    t_step = data[s2]["Time_hr"]
    
    print(f"\n  Transition {i}: Choke {c1:.0f}% -> {c2:.0f}% at t={t_step:.0f}h (du={du:+.0f}%)")
    
    # SS values (last 5 of each regime)
    for var in VARS:
        y_before = [data[j][var] for j in range(max(s1, e1-4), e1+1)]
        y_after = [data[j][var] for j in range(max(s2, e2-4), e2+1)]
        
        y_init = sum(y_before) / len(y_before)
        y_final = sum(y_after) / len(y_after)
        dy = y_final - y_init
        K = dy / du if du != 0 else 0
        
        # Time constant (63.2% method)
        y_63 = y_init + 0.632 * dy
        tau = None
        for j in range(s2, e2+1):
            if dy > 0 and data[j][var] >= y_63:
                tau = data[j]["Time_hr"] - t_step
                break
            elif dy < 0 and data[j][var] <= y_63:
                tau = data[j]["Time_hr"] - t_step
                break
        
        # Dead time (first measurable response > 2*noise)
        noise_std = math.sqrt(sum((v - y_init)**2 for v in y_before) / len(y_before))
        threshold = max(2.0 * noise_std, 0.5)
        dead_time = 0
        for j in range(s2, min(s2+10, e2+1)):
            if abs(data[j][var] - y_init) > threshold:
                dead_time = data[j]["Time_hr"] - t_step
                break
        
        # Settling time (within 2% of final value)
        settle_band = 0.02 * abs(dy) if abs(dy) > 0.1 else 0.5
        settling = None
        for j in range(e2, s2-1, -1):
            if abs(data[j][var] - y_final) > settle_band:
                settling = data[j+1]["Time_hr"] - t_step if j+1 <= e2 else None
                break
        
        # Overshoot
        if dy > 0:
            overshoot = (max(data[j][var] for j in range(s2, e2+1)) - y_final) / abs(dy) * 100
        else:
            overshoot = (y_final - min(data[j][var] for j in range(s2, e2+1))) / abs(dy) * 100 if abs(dy) > 0.1 else 0
        
        print(f"    {var:20s}: K={K:>+8.3f}  tau={tau}h  dead_t={dead_time}h  settle={settling}  overshoot={overshoot:.1f}%")

# ====== SECTION 4: NONLINEARITY ASSESSMENT ======
print("\n" + "=" * 80)
print("SECTION 4: GAIN VARIATION ACROSS TRANSITIONS (Nonlinearity)")
print("=" * 80)

gains = {var: [] for var in VARS}
for i in range(1, len(regimes)):
    s1, e1, c1 = regimes[i-1]
    s2, e2, c2 = regimes[i]
    du = c2 - c1
    if du == 0:
        continue
    for var in VARS:
        y1 = sum(data[j][var] for j in range(max(s1, e1-4), e1+1)) / min(5, e1-s1+1)
        y2 = sum(data[j][var] for j in range(max(s2, e2-4), e2+1)) / min(5, e2-s2+1)
        K = (y2 - y1) / du
        gains[var].append((c1, c2, du, K))

for var in VARS:
    print(f"\n  {var}:")
    k_vals = [g[3] for g in gains[var]]
    k_avg = sum(k_vals) / len(k_vals)
    k_std = math.sqrt(sum((k - k_avg)**2 for k in k_vals) / len(k_vals))
    k_cv = k_std / abs(k_avg) * 100 if abs(k_avg) > 1e-6 else 0
    for c1, c2, du, K in gains[var]:
        print(f"    {c1:.0f}%->{c2:.0f}%: K={K:+.4f}")
    print(f"    Average K={k_avg:+.4f}, Std={k_std:.4f}, CV={k_cv:.1f}%")

# ====== SECTION 5: NOISE ANALYSIS PER REGIME ======
print("\n" + "=" * 80)
print("SECTION 5: NOISE ANALYSIS (Steady-State Portion Only)")
print("=" * 80)

for idx, (s, e, ck) in enumerate(regimes):
    if e - s < 8:
        continue
    mid = s + (e - s) // 2  # Use second half as steady state
    print(f"\n  Regime {idx+1} (Choke={ck:.0f}%):")
    for var in VARS:
        vals = [data[j][var] for j in range(mid, e+1)]
        avg = sum(vals) / len(vals)
        std = math.sqrt(sum((v - avg)**2 for v in vals) / len(vals))
        pk2pk = max(vals) - min(vals)
        snr = abs(avg) / std if std > 0 else float("inf")
        print(f"    {var:20s}: mean={avg:>10.2f}  noise_std={std:>6.3f}  pk2pk={pk2pk:>6.2f}  SNR={snr:>8.1f}")

# ====== SECTION 6: CROSS-CORRELATION ======
print("\n" + "=" * 80)
print("SECTION 6: CROSS-CORRELATION (Pearson)")
print("=" * 80)

def pearson(x, y):
    n = len(x)
    mx, my = sum(x)/n, sum(y)/n
    num = sum((xi-mx)*(yi-my) for xi, yi in zip(x, y))
    dx = math.sqrt(sum((xi-mx)**2 for xi in x))
    dy = math.sqrt(sum((yi-my)**2 for yi in y))
    return num / (dx * dy) if dx * dy > 0 else 0

all_vars = ["Choke_pct"] + VARS
for i, v1 in enumerate(all_vars):
    for j, v2 in enumerate(all_vars):
        if j > i:
            r = pearson(col(v1), col(v2))
            print(f"  corr({v1}, {v2}) = {r:+.4f}")

# ====== SECTION 7: STEADY-STATE MAPPING ======
print("\n" + "=" * 80)
print("SECTION 7: STEADY-STATE INPUT-OUTPUT MAPPING")
print("=" * 80)
print("  Choke% -> Q_ss, WHP_ss, FLP_ss, BHP_ss")
for idx, (s, e, ck) in enumerate(regimes):
    ss = {}
    for var in VARS:
        vals = [data[j][var] for j in range(max(s, e-4), e+1)]
        ss[var] = sum(vals) / len(vals)
    print(f"  {ck:>5.0f}%: Q={ss['OilRate_bbl_hr']:>8.2f}  WHP={ss['WHP_psi']:>8.2f}  FLP={ss['FLP_psi']:>8.2f}  BHP={ss['BHP_psi']:>8.2f}")

# Linear regression: y = a*choke + b for each output
print("\n  Linear regression (y = a*choke + b):")
choke_ss = []
output_ss = {v: [] for v in VARS}
for idx, (s, e, ck) in enumerate(regimes):
    choke_ss.append(ck)
    for var in VARS:
        vals = [data[j][var] for j in range(max(s, e-4), e+1)]
        output_ss[var].append(sum(vals) / len(vals))

for var in VARS:
    x = choke_ss
    y = output_ss[var]
    n = len(x)
    mx = sum(x) / n
    my = sum(y) / n
    sxy = sum((xi-mx)*(yi-my) for xi, yi in zip(x, y))
    sxx = sum((xi-mx)**2 for xi in x)
    a = sxy / sxx if sxx > 0 else 0
    b = my - a * mx
    # R-squared
    ss_res = sum((yi - (a*xi+b))**2 for xi, yi in zip(x, y))
    ss_tot = sum((yi - my)**2 for yi in y)
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0
    print(f"    {var:20s}: slope={a:+.4f}/%, intercept={b:>10.2f}, R2={r2:.4f}")

print("\n  Residuals from linear fit:")
for var in VARS:
    x = choke_ss
    y = output_ss[var]
    n = len(x)
    mx = sum(x) / n
    my = sum(y) / n
    sxy = sum((xi-mx)*(yi-my) for xi, yi in zip(x, y))
    sxx = sum((xi-mx)**2 for xi in x)
    a = sxy / sxx if sxx > 0 else 0
    b = my - a * mx
    for i, (xi, yi) in enumerate(zip(x, y)):
        pred = a * xi + b
        resid = yi - pred
        print(f"    {var:20s} at {xi:.0f}%: actual={yi:.2f}, predicted={pred:.2f}, residual={resid:+.2f}")
