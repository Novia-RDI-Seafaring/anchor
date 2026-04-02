"""Example centrifugal pump curve plot.

Based on https://github.com/fpoposki/Mechanical-Engineering-Based-Code-Python/blob/master/Centrifugal%20pump%20curve.py
Simplified to be self-contained with hardcoded realistic pump data.
"""
import numpy as np
import matplotlib.pyplot as plt
from scipy.interpolate import interp1d

# ── Manufacturer data (Goulds 3196 style) ─────────────────────────────────
# Flow [m³/h] and Head [m] from datasheet
flow_mfr = np.array([0, 5, 10, 15, 20, 25, 30, 35])
head_mfr = np.array([52, 51, 49, 45, 40, 33, 24, 12])

# Experimental measurements (adjusted to rated RPM via similarity laws)
flow_exp = np.array([3, 8, 14, 20, 26, 32])
head_exp = np.array([51.5, 50.0, 46.2, 39.5, 31.8, 22.0])

# ── Smooth interpolation ──────────────────────────────────────────────────
flow_smooth = np.linspace(flow_mfr.min(), flow_mfr.max(), 200)
f_mfr = interp1d(flow_mfr, head_mfr, kind='quadratic')
head_smooth = f_mfr(flow_smooth)

flow_exp_smooth = np.linspace(flow_exp.min(), flow_exp.max(), 200)
f_exp = interp1d(flow_exp, head_exp, kind='quadratic')
head_exp_smooth = f_exp(flow_exp_smooth)

# ── Efficiency curve (bell-shaped, typical for centrifugal pump) ──────────
bep_flow = 22  # Best Efficiency Point at ~22 m³/h
eff_max = 72   # Peak efficiency %
eff_width = 12
efficiency = eff_max * np.exp(-((flow_smooth - bep_flow) / eff_width)**2)

# ── Power curve: P = ρgQH/η (simplified) ─────────────────────────────────
rho = 1000  # kg/m³
g = 9.81    # m/s²
# Avoid division by zero for very low efficiency
eff_safe = np.clip(efficiency, 5, 100)
power = rho * g * (flow_smooth / 3600) * head_smooth / (eff_safe / 100) / 1000  # kW

# ── Plot ──────────────────────────────────────────────────────────────────
import matplotlib as mpl
mpl.rcParams['font.family'] = 'serif'
mpl.rcParams['font.size'] = 11
mpl.rcParams['axes.linewidth'] = 0.8
mpl.rcParams['xtick.direction'] = 'in'
mpl.rcParams['ytick.direction'] = 'in'
mpl.rcParams['xtick.top'] = True
mpl.rcParams['ytick.right'] = True
mpl.rcParams['xtick.minor.visible'] = True
mpl.rcParams['ytick.minor.visible'] = True

fig, ax1 = plt.subplots(figsize=(10, 7))

# H-Q curves
ax1.plot(flow_smooth, head_smooth, 'b-', linewidth=2, label='Manufacturer H-Q')
ax1.scatter(flow_mfr, head_mfr, color='blue', marker='s', s=40, zorder=5)

ax1.plot(flow_exp_smooth, head_exp_smooth, color='#CC3300', linestyle='--',
         linewidth=1.8, label='Experimental H-Q')
ax1.scatter(flow_exp, head_exp, color='#CC3300', marker='o', s=40, zorder=5)

# BEP marker
bep_head = float(f_mfr(bep_flow))
ax1.plot(bep_flow, bep_head, 'k*', markersize=15, zorder=6, label=f'BEP ({bep_flow} m³/h)')

ax1.set_xlabel('Flow Rate Q [m³/h]')
ax1.set_ylabel('Head H [m]')
ax1.set_xlim(0, 38)
ax1.set_ylim(0, 58)
ax1.grid(True, linestyle='--', alpha=0.4)

# Efficiency on secondary axis
ax2 = ax1.twinx()
ax2.plot(flow_smooth, efficiency, color='green', linestyle='-.', linewidth=1.5,
         label='Efficiency η')
ax2.set_ylabel('Efficiency η [%]')
ax2.set_ylim(0, 100)

# Power on secondary axis (share with efficiency)
ax3 = ax1.twinx()
ax3.spines['right'].set_position(('outward', 60))
ax3.plot(flow_smooth, power, color='darkred', linestyle=':', linewidth=1.5,
         label='Power P')
ax3.set_ylabel('Power P [kW]')
ax3.set_ylim(0, max(power) * 1.3)

# Combined legend
lines1, labels1 = ax1.get_legend_handles_labels()
lines2, labels2 = ax2.get_legend_handles_labels()
lines3, labels3 = ax3.get_legend_handles_labels()
ax1.legend(lines1 + lines2 + lines3, labels1 + labels2 + labels3,
           loc='upper right', fontsize=9, framealpha=1.0, edgecolor='black')

ax1.set_title('Centrifugal Pump Performance Curve\nManufacturer vs Experimental @ 2850 RPM',
              fontsize=13, pad=12)

plt.tight_layout()
plt.savefig('OUTPUT_PATH', dpi=150, bbox_inches='tight')
plt.close()
