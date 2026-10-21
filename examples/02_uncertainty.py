"""A food plant under uncertainty: one year of demand per sample.

Follows docs/uncertainty.md. Needs `pip install loadcast scipy`.

Four inputs are sampled, each uniformly over its range:

    heat_to_cold          11.5 - 32.3   food, beverages and tobacco: the two datasets
                                        of Rehfeldt et al. (loadcast.reference)
    elec_share            0.14 - 0.28   a third either side of the industry-wide
                                        0.213 of JERICHO-E-usage (loadcast.reference)
    carrier_correlation   0.45 - 0.90   from just above the class's floor, 0.434,
                                        to tight coupling
    cold lag              0 - 12 h      from none to half a day, in whole hours

The seed is the same in every sample, so the spread across samples comes from
the inputs alone. Each sample becomes a year of demand, and the script reports
the spread of three outputs. Feed the profiles to your own design model instead,
and fit a polynomial chaos expansion to its outputs to rank the inputs.
"""

import pandas as pd
from scipy.stats import qmc

import loadcast

names = ["heat_to_cold", "elec_share", "carrier_correlation", "cold lag (h)"]
low, high = [11.5, 0.14, 0.45, 0.0], [32.3, 0.28, 0.90, 12.0]
samples = pd.DataFrame(qmc.scale(qmc.Sobol(d=4, seed=1).random(32), low, high),
                       columns=names)

rows = []
for heat_to_cold, elec_share, correlation, lag in samples.to_numpy():
    profiles = loadcast.generate(
        annual_mwh=10_000,
        heat_to_cold=heat_to_cold,
        elec_share=elec_share,
        process_class="semi_continuous",    # weekday shifts, as in brewing
        carrier_correlation=correlation,
        carrier_lag_h={"cold": int(round(lag))},
        seed=1,
    )
    heat, cold = profiles["heat_kw"], profiles["cold_kw"]
    rows.append({"heat peak (kW)": heat.max(),
                 "cold peak (kW)": cold.max(),
                 "24 h drift (h)": loadcast.integrated_drift(heat, cold, window_h=24)})

outputs = pd.DataFrame(rows)
print(f"{len(samples)} years of demand for a semi-continuous food plant\n")
print(outputs.quantile([0.05, 0.5, 0.95]).T.round(2)
      .rename(columns={0.05: "P05", 0.5: "median", 0.95: "P95"}))
