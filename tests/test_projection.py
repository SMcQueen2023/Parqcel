import pytest

np = pytest.importorskip("numpy")
go = pytest.importorskip("plotly.graph_objects")

import polars as pl  # noqa: E402
from parqcel.core.projection import build_projection  # noqa: E402


def test_projection_samples_before_matrix_and_preserves_category_labels(
    monkeypatch, tmp_path
):
    import ds.dimensionality as dimensionality

    captured = {}
    original_to_numpy = pl.DataFrame.to_numpy

    def to_numpy(frame, *args, **kwargs):
        assert frame.height == 10
        return original_to_numpy(frame, *args, **kwargs)

    def pca(matrix, n_components):
        assert matrix.shape == (10, 2)
        return matrix, np.array([0.5, 0.5])

    monkeypatch.setattr(pl.DataFrame, "to_numpy", to_numpy)
    monkeypatch.setattr(dimensionality, "compute_pca", pca)
    monkeypatch.setattr(
        go.Figure, "write_html", lambda figure, path: captured.update(figure=figure)
    )

    class Files:
        def create(self, **kwargs):
            return str(tmp_path / "plot.html")

    df = pl.DataFrame(
        {"x": list(range(100)), "y": list(range(100)), "category": ["customer"] * 100}
    )
    result = build_projection(
        df,
        ["x", "y"],
        {"method": "PCA", "sample": 10, "n_components": 2, "color_by": "category"},
        Files(),
    )
    assert result["plot_error"] is None
    trace = captured["figure"].data[0]
    assert list(trace.marker.color) == [0] * 10
    assert all(row[1] == "customer" for row in trace.customdata)
