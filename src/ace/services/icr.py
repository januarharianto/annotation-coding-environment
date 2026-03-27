"""Inter-coder reliability (ICR) computation service.

Character-level binary agreement with Cohen's kappa per code.
"""

import math
import sqlite3
from dataclasses import dataclass, field


@dataclass
class ICRResult:
    overall_kappa: float = 0.0
    overall_percent_agreement: float = 0.0
    per_code: dict = field(default_factory=dict)
    # per_code maps code_name -> {"kappa": float|None, "percent_agreement": float|None, "n_positions": int}
    overlap_sources: int = 0


def compute_icr(conn: sqlite3.Connection) -> ICRResult:
    """Compute character-level binary ICR across all overlap sources.

    An overlap source is one assigned to at least 2 coders.
    Only the first two coders (by coder_id) are compared per source.
    """
    result = ICRResult()

    # 1. Find overlap sources (assigned to >= 2 coders)
    overlap_rows = conn.execute(
        "SELECT source_id, GROUP_CONCAT(coder_id) AS coder_ids "
        "FROM assignment GROUP BY source_id HAVING COUNT(*) >= 2"
    ).fetchall()

    if not overlap_rows:
        return result

    result.overlap_sources = len(overlap_rows)

    # 2. Get all codes from codebook
    codes = conn.execute(
        "SELECT id, name FROM codebook_code ORDER BY sort_order"
    ).fetchall()

    if not codes:
        return result

    code_ids = [c["id"] for c in codes]
    code_names = {c["id"]: c["name"] for c in codes}

    # Accumulate per-code vectors across all overlap sources
    # Keys: code_id -> {"coder1": list[int], "coder2": list[int]}
    aggregated: dict[str, dict[str, list[int]]] = {
        cid: {"coder1": [], "coder2": []} for cid in code_ids
    }

    for row in overlap_rows:
        source_id = row["source_id"]
        coder_ids_str = row["coder_ids"]
        coder_pair = coder_ids_str.split(",")[:2]
        coder1_id, coder2_id = coder_pair[0], coder_pair[1]

        # a. Get text length
        content_row = conn.execute(
            "SELECT content_text FROM source_content WHERE source_id = ?",
            (source_id,),
        ).fetchone()
        if content_row is None or content_row["content_text"] is None:
            continue
        text_length = len(content_row["content_text"])
        if text_length == 0:
            continue

        # b. Get annotations for each coder (non-deleted only)
        anns_coder1 = conn.execute(
            "SELECT code_id, start_offset, end_offset FROM annotation "
            "WHERE source_id = ? AND coder_id = ? AND deleted_at IS NULL",
            (source_id, coder1_id),
        ).fetchall()

        anns_coder2 = conn.execute(
            "SELECT code_id, start_offset, end_offset FROM annotation "
            "WHERE source_id = ? AND coder_id = ? AND deleted_at IS NULL",
            (source_id, coder2_id),
        ).fetchall()

        # c. For each code, build binary vectors of length text_length
        # Also track which positions have any code applied by any coder
        any_coded = [0] * text_length

        code_vectors: dict[str, dict[str, list[int]]] = {}
        for cid in code_ids:
            vec1 = [0] * text_length
            vec2 = [0] * text_length
            code_vectors[cid] = {"coder1": vec1, "coder2": vec2}

        for ann in anns_coder1:
            cid = ann["code_id"]
            if cid in code_vectors:
                start = ann["start_offset"]
                end = ann["end_offset"]
                vec = code_vectors[cid]["coder1"]
                for i in range(start, min(end, text_length)):
                    vec[i] = 1
                    any_coded[i] = 1

        for ann in anns_coder2:
            cid = ann["code_id"]
            if cid in code_vectors:
                start = ann["start_offset"]
                end = ann["end_offset"]
                vec = code_vectors[cid]["coder2"]
                for i in range(start, min(end, text_length)):
                    vec[i] = 1
                    any_coded[i] = 1

        # d. Filter to positions where at least one coder applied at least one code
        coded_positions = [i for i in range(text_length) if any_coded[i]]

        if not coded_positions:
            continue

        # Append filtered positions to aggregated vectors
        for cid in code_ids:
            vecs = code_vectors[cid]
            for pos in coded_positions:
                aggregated[cid]["coder1"].append(vecs["coder1"][pos])
                aggregated[cid]["coder2"].append(vecs["coder2"][pos])

    # 5. Compute per-code kappa and percent agreement
    kappas = []
    for cid in code_ids:
        name = code_names[cid]
        vec1 = aggregated[cid]["coder1"]
        vec2 = aggregated[cid]["coder2"]
        n_positions = len(vec1)

        if n_positions == 0:
            result.per_code[name] = {
                "kappa": None,
                "percent_agreement": None,
                "n_positions": 0,
            }
            continue

        # Percent agreement
        agree_count = sum(1 for a, b in zip(vec1, vec2) if a == b)
        pct_agreement = agree_count / n_positions

        # Cohen's kappa
        kappa = _safe_kappa(vec1, vec2)

        result.per_code[name] = {
            "kappa": kappa,
            "percent_agreement": pct_agreement,
            "n_positions": n_positions,
        }
        if kappa is not None:
            kappas.append(kappa)

    # 6. Overall kappa = macro-average of per-code kappas
    if kappas:
        result.overall_kappa = sum(kappas) / len(kappas)

    # 7. Overall percent agreement = macro-average of per-code percent agreements
    pcts = [
        v["percent_agreement"]
        for v in result.per_code.values()
        if v["percent_agreement"] is not None
    ]
    if pcts:
        result.overall_percent_agreement = sum(pcts) / len(pcts)

    return result


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
    """Compute Cohen's kappa, handling edge cases.

    If all values are the same for both vectors (perfect agreement),
    _cohens_kappa returns 1.0 when pe == 1.0 and po == 1.0.
    """
    k = _cohens_kappa(vec1, vec2)
    if k is None:
        return 1.0 if vec1 == vec2 else None
    if math.isnan(k):
        return 1.0 if vec1 == vec2 else None
    return k
