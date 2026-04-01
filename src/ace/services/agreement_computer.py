"""Computes inter-coder agreement metrics from an AgreementDataset."""

import math
from collections import defaultdict

import krippendorff
import numpy as np
import pandas as pd
from irrCAC.raw import CAC

from ace.services.agreement_types import (
    AgreementDataset,
    AgreementResult,
    CodeMetrics,
)


def compute_agreement(dataset: AgreementDataset) -> AgreementResult:
    """Compute all agreement metrics from a matched dataset."""
    if not dataset.annotations or not dataset.sources or not dataset.codes:
        empty = CodeMetrics(percent_agreement=0.0, n_positions=0)
        return AgreementResult(
            overall=empty,
            per_code={},
            per_source={},
            pairwise={},
            n_coders=len(dataset.coders),
            n_sources=0,
            n_codes=0,
        )

    coder_ids = [c.id for c in dataset.coders]
    code_names = [c.name for c in dataset.codes]

    # Group annotations by (source_hash, coder_id, code_name)
    ann_index = defaultdict(list)
    for ann in dataset.annotations:
        ann_index[(ann.source_hash, ann.coder_id, ann.code_name)].append(ann)

    # Build character-level vectors per code, aggregated across sources
    per_code_vectors: dict[str, dict[str, list[int]]] = {
        cn: {cid: [] for cid in coder_ids} for cn in code_names
    }

    # Also per source
    per_source_vectors: dict[str, dict[str, list[int]]] = {}

    for source in dataset.sources:
        text_len = len(source.content_text)
        if text_len == 0:
            continue

        # Track which positions have any code applied by any coder
        any_coded = [0] * text_len

        # Build vectors per code per coder for this source
        source_code_vecs: dict[str, dict[str, list[int]]] = {}
        for cn in code_names:
            vecs = {}
            for cid in coder_ids:
                vec = [0] * text_len
                for ann in ann_index.get((source.content_hash, cid, cn), []):
                    for i in range(ann.start_offset, min(ann.end_offset, text_len)):
                        vec[i] = 1
                        any_coded[i] = 1
                vecs[cid] = vec
            source_code_vecs[cn] = vecs

        # Filter to positions where at least one coder applied at least one code
        coded_positions = [i for i in range(text_len) if any_coded[i]]
        if not coded_positions:
            continue

        # Aggregate into per-code vectors
        for cn in code_names:
            for cid in coder_ids:
                vec = source_code_vecs[cn][cid]
                for pos in coded_positions:
                    per_code_vectors[cn][cid].append(vec[pos])

        # Aggregate into per-source vectors (all codes flattened)
        source_key = source.display_id
        if source_key not in per_source_vectors:
            per_source_vectors[source_key] = {cid: [] for cid in coder_ids}
        for cn in code_names:
            for cid in coder_ids:
                vec = source_code_vecs[cn][cid]
                for pos in coded_positions:
                    per_source_vectors[source_key][cid].append(vec[pos])

    # Count distinct sources per code (from annotations)
    code_source_sets: dict[str, set[str]] = {cn: set() for cn in code_names}
    for ann in dataset.annotations:
        if ann.code_name in code_source_sets:
            code_source_sets[ann.code_name].add(ann.source_hash)

    # Compute per-code metrics
    per_code_results: dict[str, CodeMetrics] = {}
    for cn in code_names:
        vectors = per_code_vectors[cn]
        metrics = _compute_metrics(vectors, coder_ids)
        metrics.n_sources = len(code_source_sets[cn])
        per_code_results[cn] = metrics

    # Compute per-source metrics
    per_source_results: dict[str, CodeMetrics] = {}
    for src_key, vectors in per_source_vectors.items():
        per_source_results[src_key] = _compute_metrics(vectors, coder_ids)

    # Compute overall (pooled across all codes)
    pooled_vectors: dict[str, list[int]] = {cid: [] for cid in coder_ids}
    for cn in code_names:
        for cid in coder_ids:
            pooled_vectors[cid].extend(per_code_vectors[cn][cid])
    overall = _compute_metrics(pooled_vectors, coder_ids)
    overall.n_sources = len(dataset.sources)

    # Compute pairwise alpha
    pairwise = _compute_pairwise(per_code_vectors, coder_ids)

    return AgreementResult(
        overall=overall,
        per_code=per_code_results,
        per_source=per_source_results,
        pairwise=pairwise,
        n_coders=len(dataset.coders),
        n_sources=len(per_source_vectors),
        n_codes=len(code_names),
    )


def _compute_metrics(vectors: dict[str, list[int]], coder_ids: list[str]) -> CodeMetrics:
    """Compute all metrics from coder vectors."""
    vec_len = len(vectors[coder_ids[0]]) if coder_ids else 0
    if vec_len == 0:
        return CodeMetrics(percent_agreement=0.0, n_positions=0)

    n_coders = len(coder_ids)

    # Percent agreement (pairwise average)
    pair_agrees = []
    for i in range(n_coders):
        for j in range(i + 1, n_coders):
            v1 = vectors[coder_ids[i]]
            v2 = vectors[coder_ids[j]]
            agree = sum(1 for a, b in zip(v1, v2) if a == b) / vec_len
            pair_agrees.append(agree)
    pct_agree = sum(pair_agrees) / len(pair_agrees) if pair_agrees else 0.0

    # Cohen's kappa (only for 2 coders)
    cohens_k = None
    if n_coders == 2:
        cohens_k = _safe_kappa(vectors[coder_ids[0]], vectors[coder_ids[1]])

    # Krippendorff's alpha
    k_alpha = _safe_krippendorff(vectors, coder_ids)

    # irrCAC metrics (Fleiss, Conger, Gwet, Brennan-Prediger)
    fleiss_k, congers_k, gwets, bp = _compute_irrcac(vectors, coder_ids)

    return CodeMetrics(
        percent_agreement=pct_agree,
        n_positions=vec_len,
        cohens_kappa=cohens_k,
        krippendorffs_alpha=k_alpha,
        fleiss_kappa=fleiss_k,
        congers_kappa=congers_k,
        gwets_ac1=gwets,
        brennan_prediger=bp,
    )


def _cohens_kappa(y1: list, y2: list) -> float | None:
    """Cohen's kappa for two binary raters."""
    n = len(y1)
    if n == 0:
        return None
    a11 = a10 = a01 = a00 = 0
    for i in range(n):
        if y1[i] and y2[i]:
            a11 += 1
        elif y1[i] and not y2[i]:
            a10 += 1
        elif not y1[i] and y2[i]:
            a01 += 1
        else:
            a00 += 1
    po = (a11 + a00) / n
    pe = ((a11 + a10) * (a11 + a01) + (a01 + a00) * (a10 + a00)) / (n * n)
    if pe == 1.0:
        return 1.0 if po == 1.0 else 0.0
    return (po - pe) / (1 - pe)


def _safe_kappa(vec1: list[int], vec2: list[int]) -> float | None:
    """Cohen's kappa with edge case handling."""
    k = _cohens_kappa(vec1, vec2)
    if k is None:
        return 1.0 if vec1 == vec2 else None
    if math.isnan(k):
        return 1.0 if vec1 == vec2 else None
    return k


def _safe_krippendorff(vectors: dict[str, list[int]], coder_ids: list[str]) -> float | None:
    """Krippendorff's alpha with edge case handling."""
    try:
        matrix = np.array([vectors[cid] for cid in coder_ids])
        # If all raters agree on every unit, alpha is undefined but agreement
        # is perfect — return 1.0 by convention.
        if np.all(matrix == matrix[0]):
            return 1.0
        alpha = krippendorff.alpha(
            reliability_data=matrix, level_of_measurement="nominal"
        )
        if math.isnan(alpha):
            return None
        return float(alpha)
    except Exception:
        return None


def _compute_irrcac(
    vectors: dict[str, list[int]], coder_ids: list[str]
) -> tuple[float | None, float | None, float | None, float | None]:
    """Compute Fleiss, Conger, Gwet AC1, Brennan-Prediger via irrCAC."""
    try:
        df = pd.DataFrame({cid: vectors[cid] for cid in coder_ids})
        cac = CAC(df)
    except Exception:
        return None, None, None, None

    # Compute each metric independently so one failure doesn't prevent others
    fleiss = _safe_irrcac(cac.fleiss)
    conger = _safe_irrcac(cac.conger)
    gwet = _safe_irrcac(cac.gwet)
    bp = _safe_irrcac(cac.bp)

    return fleiss, conger, gwet, bp


def _safe_irrcac(method) -> float | None:
    """Safely call an irrCAC method and extract its coefficient."""
    try:
        return _extract_coeff(method())
    except Exception:
        return None


def _extract_coeff(result) -> float | None:
    """Extract coefficient value from an irrCAC result."""
    try:
        coeff = result["est"]["coefficient_value"]
        if isinstance(coeff, pd.Series):
            coeff = coeff.iloc[0]
        if math.isnan(float(coeff)):
            return None
        return float(coeff)
    except (KeyError, TypeError, IndexError):
        return None


def _macro_average(metrics_list: list[CodeMetrics]) -> CodeMetrics:
    """Macro-average across a list of CodeMetrics."""
    if not metrics_list:
        return CodeMetrics(percent_agreement=0.0, n_positions=0)

    def avg(vals: list[float | None]) -> float | None:
        nums = [v for v in vals if v is not None]
        return sum(nums) / len(nums) if nums else None

    total_positions = sum(m.n_positions for m in metrics_list)
    pct = avg([m.percent_agreement for m in metrics_list if m.n_positions > 0])

    return CodeMetrics(
        percent_agreement=pct or 0.0,
        n_positions=total_positions,
        cohens_kappa=avg([m.cohens_kappa for m in metrics_list]),
        krippendorffs_alpha=avg([m.krippendorffs_alpha for m in metrics_list]),
        fleiss_kappa=avg([m.fleiss_kappa for m in metrics_list]),
        congers_kappa=avg([m.congers_kappa for m in metrics_list]),
        gwets_ac1=avg([m.gwets_ac1 for m in metrics_list]),
        brennan_prediger=avg([m.brennan_prediger for m in metrics_list]),
    )


def _compute_pairwise(
    per_code_vectors: dict[str, dict[str, list[int]]],
    coder_ids: list[str],
) -> dict[tuple[str, str], float]:
    """Compute pairwise Krippendorff's alpha between each coder pair."""
    pairwise: dict[tuple[str, str], float] = {}

    for i in range(len(coder_ids)):
        for j in range(i + 1, len(coder_ids)):
            cid_i, cid_j = coder_ids[i], coder_ids[j]
            pair_vecs = {cid_i: [], cid_j: []}
            for cn in per_code_vectors:
                pair_vecs[cid_i].extend(per_code_vectors[cn][cid_i])
                pair_vecs[cid_j].extend(per_code_vectors[cn][cid_j])

            alpha = _safe_krippendorff(pair_vecs, [cid_i, cid_j])
            if alpha is not None:
                pairwise[(cid_i, cid_j)] = alpha

    return pairwise
