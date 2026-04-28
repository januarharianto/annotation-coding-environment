# ACE Agreement Verdict Methodology

This document explains how ACE classifies inter-coder agreement results into diagnostic verdicts.

## Why Gwet's AC1

ACE uses Gwet's AC1 as the primary metric for verdict classification rather than Krippendorff's alpha or Cohen's kappa. The reason is empirical: Zhao et al. (2022) tested seven agreement indices against known true reliabilities via simulation and found that Krippendorff's alpha, Cohen's kappa, and Scott's pi underestimated true reliability by approximately 31 percentage points with the worst correlation to actual reliability (r² = 0.31). Gwet's AC1 was the best approximator (r² = 0.72).

The root cause is how each metric models chance agreement. Alpha and kappa compute expected agreement from observed marginal distributions. In character-level span annotation — where most positions are uncoded for any given code — these marginals are extreme, inflating the chance baseline and suppressing the metric even when coders genuinely agree. AC1 uses an "occasional guessing" model that caps chance agreement at 0.5 for binary data, preventing this inflation.

ACE still computes and displays all seven metrics (percent agreement, Krippendorff's alpha, Cohen's/Fleiss' kappa, Conger's kappa, Gwet's AC1, Brennan-Prediger). The divergence pattern across metrics is itself informative — when metrics disagree, ACE flags the prevalence paradox automatically.

## Verdict Thresholds

Per-code status is determined by the code's AC1 value:

| AC1 Range | Status | Colour | Rationale |
|-----------|--------|--------|-----------|
| ≥ 0.80 | Reliable | Green | AC1 ≥ 0.80 corresponded to true reliability ≥ 0.75 in Zhao et al.'s simulation. |
| 0.60–0.79 | Tentative | Amber | Moderate true reliability. Tentative conclusions only. |
| < 0.60 | Unreliable | Red | True reliability likely below acceptable thresholds. |
| < 50 coded positions | Insufficient data | Grey | Too few observations for any metric to be meaningful. |

These thresholds are calibrated to AC1's empirical behaviour, not the Landis & Koch (1977) scale, which was designed for kappa and would be misleading if applied to AC1 (AC1 produces systematically higher values than kappa).

The overall verdict uses the pooled overall AC1 value — computed across all codes simultaneously, not the average of per-code AC1 values — with the same thresholds.

## Prevalence Paradox Detection

ACE detects the prevalence paradox (Feinstein & Cicchetti, 1990) when all three conditions hold for a given code:

1. Percent agreement ≥ 85%
2. Krippendorff's alpha < 0.60
3. Gwet's AC1 ≥ 0.70

When detected, this means alpha is misleadingly low due to extreme base rates — the code was applied to a small fraction of the text, which inflates the chance-agreement baseline that alpha uses. The actual agreement (reflected by AC1 and percent agreement) is strong.

ACE flags the paradox with a "paradox" badge in the status column and provides an explanatory callout in the expanded row guidance, directing the user to focus revision efforts on genuinely problematic codes instead.

## Overall Verdict

The overall verdict card colour is determined by the pooled overall AC1. The guidance text adapts based on the distribution of per-code statuses:

- **Green (all reliable):** Codebook is working well, proceed with coding.
- **Green (some tentative):** Strong overall but some codes need boundary refinement.
- **Amber (no unreliable):** Tentative range, review definitions before proceeding.
- **Amber (some unreliable):** Moderate overall, specific codes need revision.
- **Red:** Codebook needs significant revision, with a concrete 3-step recommendation.
- **Grey:** Insufficient data to assess.

## Insufficient Data Threshold

A code with fewer than 50 coded character positions is classified as "insufficient data" regardless of its metric values. At low sample sizes, all agreement metrics become unstable and unreliable — reporting a verdict would be misleading.

## References

1. Gwet, K. L. (2008). Computing inter-rater reliability and its variance in the presence of high agreement. *British Journal of Mathematical and Statistical Psychology*, 61(1), 29–48.
2. Krippendorff, K. (2018). *Content Analysis: An Introduction to Its Methodology* (4th ed.). SAGE.
3. Cohen, J. (1960). A coefficient of agreement for nominal scales. *Educational and Psychological Measurement*, 20(1), 37–46.
4. Fleiss, J. L. (1971). Measuring nominal scale agreement among many raters. *Psychological Bulletin*, 76(5), 378–382.
5. Conger, A. J. (1980). Integration and generalization of kappas for multiple raters. *Psychological Bulletin*, 88(2), 322–328.
6. Brennan, R. L. & Prediger, D. J. (1981). Coefficient kappa: Some uses, misuses, and alternatives. *Educational and Psychological Measurement*, 41(3), 687–699.
7. Landis, J. R. & Koch, G. G. (1977). The measurement of observer agreement for categorical data. *Biometrics*, 33(1), 159–174.
8. Holsti, O. R. (1969). *Content Analysis for the Social Sciences and Humanities*. Addison-Wesley.
9. Feinstein, A. R. & Cicchetti, D. V. (1990). High agreement but low kappa: I. The problems of two paradoxes. *Journal of Clinical Epidemiology*, 43(6), 543–549.
10. Cicchetti, D. V. & Feinstein, A. R. (1990). High agreement but low kappa: II. Resolving the paradoxes. *Journal of Clinical Epidemiology*, 43(6), 551–558.
11. Zhao, X., Feng, G. C., Ao, S. H., & Liu, P. L. (2022). Interrater reliability estimators tested against true interrater reliabilities. *BMC Medical Research Methodology*, 22, 232.
12. Krippendorff, K. (2011). Computing Krippendorff's alpha-reliability. University of Pennsylvania Scholarly Commons.
