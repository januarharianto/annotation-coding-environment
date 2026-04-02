"""Data structures for inter-coder agreement computation."""

from dataclasses import dataclass, field


@dataclass
class MatchedSource:
    content_hash: str
    display_id: str
    content_text: str


@dataclass
class CoderInfo:
    id: str  # unique across the comparison
    label: str  # display name (coder name or "Coder N")
    source_file: str  # path to the .ace file


@dataclass
class MatchedCode:
    name: str
    present_in: set[str] = field(default_factory=set)  # set of coder IDs


@dataclass
class MatchedAnnotation:
    source_hash: str  # content_hash of the source
    coder_id: str  # CoderInfo.id
    code_name: str  # MatchedCode.name
    start_offset: int
    end_offset: int


@dataclass
class AgreementDataset:
    sources: list[MatchedSource]
    coders: list[CoderInfo]
    codes: list[MatchedCode]
    annotations: list[MatchedAnnotation]
    warnings: list[str]


@dataclass
class CodeMetrics:
    percent_agreement: float
    n_positions: int
    n_sources: int = 0
    cohens_kappa: float | None = None
    krippendorffs_alpha: float | None = None
    fleiss_kappa: float | None = None
    congers_kappa: float | None = None
    gwets_ac1: float | None = None
    brennan_prediger: float | None = None


@dataclass
class AgreementResult:
    overall: CodeMetrics
    per_code: dict[str, CodeMetrics]  # code_name -> metrics
    per_source: dict[str, CodeMetrics]  # display_id -> metrics
    pairwise: dict[tuple[str, str], CodeMetrics]  # (coder_id, coder_id) -> metrics
    n_coders: int
    n_sources: int
    n_codes: int
