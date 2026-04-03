"""Computes inter-coder agreement metrics from an AgreementDataset.

Pure Python — no numpy, scipy, or pandas required.
"""

import math
from collections import defaultdict

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

    # Compute pairwise
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
    k_alpha = _krippendorffs_alpha(vectors, coder_ids)

    # Fleiss, Conger, Gwet, Brennan-Prediger
    fleiss_k = _fleiss_kappa(vectors, coder_ids)
    congers_k = _congers_kappa(vectors, coder_ids)
    gwets = _gwets_ac1(vectors, coder_ids)
    bp = _brennan_prediger(vectors, coder_ids)

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


# ---------------------------------------------------------------------------
# Cohen's kappa (2 raters)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Krippendorff's alpha (any number of raters, nominal)
# ---------------------------------------------------------------------------


def _krippendorffs_alpha(vectors: dict[str, list[int]], coder_ids: list[str]) -> float | None:
    """Krippendorff's alpha for nominal data via coincidence matrix."""
    n_units = len(vectors[coder_ids[0]]) if coder_ids else 0
    if n_units == 0:
        return None

    # Check if all raters agree on every unit
    first = vectors[coder_ids[0]]
    if all(vectors[cid] == first for cid in coder_ids[1:]):
        return 1.0

    # Collect all distinct categories
    categories = set()
    for cid in coder_ids:
        categories.update(vectors[cid])
    cats = sorted(categories)
    cat_idx = {c: i for i, c in enumerate(cats)}
    q = len(cats)

    # Build coincidence matrix
    coincidence = [[0.0] * q for _ in range(q)]

    for u in range(n_units):
        # Collect ratings for this unit (no missing data in our use case)
        ratings = [vectors[cid][u] for cid in coder_ids]
        n_r = len(ratings)
        if n_r < 2:
            continue
        for i in range(n_r):
            for j in range(n_r):
                if i != j:
                    ci = cat_idx[ratings[i]]
                    cj = cat_idx[ratings[j]]
                    coincidence[ci][cj] += 1.0 / (n_r - 1)

    # Marginals
    n_total = sum(sum(row) for row in coincidence)
    if n_total == 0:
        return None
    marginals = [sum(coincidence[c]) for c in range(q)]

    # Observed disagreement
    do = 0.0
    for c in range(q):
        for k in range(q):
            if c != k:
                do += coincidence[c][k]
    do /= n_total

    # Expected disagreement
    de = 0.0
    for c in range(q):
        for k in range(q):
            if c != k:
                de += marginals[c] * marginals[k]
    de /= (n_total * (n_total - 1))

    if de == 0:
        return 1.0
    alpha = 1.0 - do / de
    return None if math.isnan(alpha) else alpha


# ---------------------------------------------------------------------------
# Fleiss' kappa (any number of raters)
# ---------------------------------------------------------------------------


def _fleiss_kappa(vectors: dict[str, list[int]], coder_ids: list[str]) -> float | None:
    """Fleiss' kappa for multiple raters."""
    n_units = len(vectors[coder_ids[0]]) if coder_ids else 0
    n_coders = len(coder_ids)
    if n_units == 0 or n_coders < 2:
        return None

    categories = set()
    for cid in coder_ids:
        categories.update(vectors[cid])
    cats = sorted(categories)
    q = len(cats)

    # Count how many raters assigned each category per unit
    counts = [[0] * q for _ in range(n_units)]
    for cid in coder_ids:
        for u in range(n_units):
            c_idx = cats.index(vectors[cid][u])
            counts[u][c_idx] += 1

    # Observed agreement per unit
    po_sum = 0.0
    for u in range(n_units):
        s = sum(counts[u][j] * (counts[u][j] - 1) for j in range(q))
        po_sum += s / (n_coders * (n_coders - 1))
    po = po_sum / n_units

    # Expected agreement (marginal proportions)
    pe = 0.0
    for j in range(q):
        pj = sum(counts[u][j] for u in range(n_units)) / (n_units * n_coders)
        pe += pj * pj

    if pe == 1.0:
        return 1.0 if po == 1.0 else 0.0
    return (po - pe) / (1 - pe)


# ---------------------------------------------------------------------------
# Conger's kappa (any number of raters)
# ---------------------------------------------------------------------------


def _congers_kappa(vectors: dict[str, list[int]], coder_ids: list[str]) -> float | None:
    """Conger's kappa — like Fleiss but uses per-rater marginals."""
    n_units = len(vectors[coder_ids[0]]) if coder_ids else 0
    n_coders = len(coder_ids)
    if n_units == 0 or n_coders < 2:
        return None

    categories = set()
    for cid in coder_ids:
        categories.update(vectors[cid])
    cats = sorted(categories)
    q = len(cats)

    # Count per unit per category
    counts = [[0] * q for _ in range(n_units)]
    for cid in coder_ids:
        for u in range(n_units):
            c_idx = cats.index(vectors[cid][u])
            counts[u][c_idx] += 1

    # Observed agreement (same as Fleiss)
    po_sum = 0.0
    for u in range(n_units):
        s = sum(counts[u][j] * (counts[u][j] - 1) for j in range(q))
        po_sum += s / (n_coders * (n_coders - 1))
    po = po_sum / n_units

    # Per-rater marginal proportions
    rater_props = []
    for cid in coder_ids:
        props = [0.0] * q
        for u in range(n_units):
            c_idx = cats.index(vectors[cid][u])
            props[c_idx] += 1.0 / n_units
        rater_props.append(props)

    # Expected agreement: average of per-rater-pair pe
    pe = 0.0
    for j in range(q):
        s = sum(rater_props[r][j] for r in range(n_coders))
        pe += (s * s - sum(rater_props[r][j] ** 2 for r in range(n_coders)))
    pe /= (n_coders * (n_coders - 1))

    if pe == 1.0:
        return 1.0 if po == 1.0 else 0.0
    return (po - pe) / (1 - pe)


# ---------------------------------------------------------------------------
# Gwet's AC1 (any number of raters)
# ---------------------------------------------------------------------------


def _gwets_ac1(vectors: dict[str, list[int]], coder_ids: list[str]) -> float | None:
    """Gwet's AC1 for multiple raters."""
    n_units = len(vectors[coder_ids[0]]) if coder_ids else 0
    n_coders = len(coder_ids)
    if n_units == 0 or n_coders < 2:
        return None

    categories = set()
    for cid in coder_ids:
        categories.update(vectors[cid])
    cats = sorted(categories)
    q = len(cats)

    # Count per unit per category
    counts = [[0] * q for _ in range(n_units)]
    for cid in coder_ids:
        for u in range(n_units):
            c_idx = cats.index(vectors[cid][u])
            counts[u][c_idx] += 1

    # Observed agreement (same as Fleiss)
    po_sum = 0.0
    for u in range(n_units):
        s = sum(counts[u][j] * (counts[u][j] - 1) for j in range(q))
        po_sum += s / (n_coders * (n_coders - 1))
    po = po_sum / n_units

    # Gwet's chance agreement: based on marginal proportions with
    # propensity adjustment
    marginals = [0.0] * q
    for j in range(q):
        marginals[j] = sum(counts[u][j] for u in range(n_units)) / (n_units * n_coders)

    pe = sum(p * (1 - p) for p in marginals) / (q - 1) if q > 1 else 0.0

    if pe == 1.0:
        return 1.0 if po == 1.0 else 0.0
    return (po - pe) / (1 - pe)


# ---------------------------------------------------------------------------
# Brennan-Prediger (any number of raters)
# ---------------------------------------------------------------------------


def _brennan_prediger(vectors: dict[str, list[int]], coder_ids: list[str]) -> float | None:
    """Brennan-Prediger coefficient — chance = 1/q (uniform)."""
    n_units = len(vectors[coder_ids[0]]) if coder_ids else 0
    n_coders = len(coder_ids)
    if n_units == 0 or n_coders < 2:
        return None

    categories = set()
    for cid in coder_ids:
        categories.update(vectors[cid])
    cats = sorted(categories)
    q = len(cats)

    # Count per unit per category
    counts = [[0] * q for _ in range(n_units)]
    for cid in coder_ids:
        for u in range(n_units):
            c_idx = cats.index(vectors[cid][u])
            counts[u][c_idx] += 1

    # Observed agreement
    po_sum = 0.0
    for u in range(n_units):
        s = sum(counts[u][j] * (counts[u][j] - 1) for j in range(q))
        po_sum += s / (n_coders * (n_coders - 1))
    po = po_sum / n_units

    pe = 1.0 / q
    if pe == 1.0:
        return 1.0 if po == 1.0 else 0.0
    return (po - pe) / (1 - pe)


# ---------------------------------------------------------------------------
# Pairwise
# ---------------------------------------------------------------------------


def _compute_pairwise(
    per_code_vectors: dict[str, dict[str, list[int]]],
    coder_ids: list[str],
) -> dict[tuple[str, str], "CodeMetrics"]:
    """Compute full CodeMetrics for each coder pair."""
    pairwise: dict[tuple[str, str], CodeMetrics] = {}

    for i in range(len(coder_ids)):
        for j in range(i + 1, len(coder_ids)):
            cid_i, cid_j = coder_ids[i], coder_ids[j]
            pair_vecs: dict[str, list[int]] = {cid_i: [], cid_j: []}
            for cn in per_code_vectors:
                pair_vecs[cid_i].extend(per_code_vectors[cn][cid_i])
                pair_vecs[cid_j].extend(per_code_vectors[cn][cid_j])

            pairwise[(cid_i, cid_j)] = _compute_metrics(pair_vecs, [cid_i, cid_j])

    return pairwise
