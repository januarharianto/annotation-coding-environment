import pytest
from pathlib import Path

@pytest.fixture
def tmp_db(tmp_path):
    """Create a temporary .ace SQLite file path."""
    return tmp_path / "test.ace"

@pytest.fixture
def sample_csv(tmp_path):
    """Create a sample CSV for import testing."""
    csv_path = tmp_path / "sample.csv"
    csv_path.write_text(
        "participant_id,reflection,age\n"
        'P001,"I enjoyed the group work sessions.",22\n'
        'P002,"The lectures were too fast-paced.",25\n'
        'P003,"Overall a good experience with some challenges.",23\n'
    )
    return csv_path
