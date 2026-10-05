"""Projection computation and plot artifacts; no Qt dependencies."""

from __future__ import annotations


def build_projection(df, selected, opts, temp_files):
    import numpy as np
    from ds.dimensionality import compute_pca, compute_umap

    method = opts.get("method", "PCA")
    n_components = opts.get("n_components", 2)
    color_by = opts.get("color_by")
    sample = opts.get("sample", 10000)
    if sample and sample > 0 and df.height > sample:
        rng = np.random.default_rng(0)
        idx = rng.choice(df.height, size=sample, replace=False)
        df = df[idx.tolist()]
    else:
        idx = np.arange(df.height)
    X_vis = df.select(selected).to_numpy()
    color_vals = df[color_by].to_list() if color_by else None
    # compute embedding
    if method.startswith("PCA"):
        emb, _var_ratio = compute_pca(X_vis, n_components=n_components)
    else:
        emb = compute_umap(X_vis, n_components=n_components)
        _var_ratio = None

    try:
        import plotly.graph_objects as go

        # Prepare customdata (index, color value, and up to two feature columns)
        # Use the same sampled row indices when downsampling so hover data aligns with emb
        row_idx = [int(i) for i in idx]

        custom_cols = [row_idx]
        hover_names = ["index"]
        if color_vals is not None:
            custom_cols.append(color_vals)
            hover_names.append("color")
        marker_colors = color_vals
        if color_by and not df[color_by].dtype.is_numeric():
            # Plotly treats string marker colors as CSS colors, not categories.
            # Keep original labels in hover data and encode only the color scale.
            labels = {
                value: index
                for index, value in enumerate(dict.fromkeys(str(v) for v in color_vals))
            }
            marker_colors = [labels[str(value)] for value in color_vals]

        extra_hover_cols = []
        for c in selected:
            if len(extra_hover_cols) >= 2:
                break
            if c == color_by:
                continue
            try:
                vals = df[c].to_list()
                custom_cols.append(vals)
                hover_names.append(c)
                extra_hover_cols.append(c)
            except Exception:
                continue

        try:
            customdata = np.column_stack([np.array(col) for col in custom_cols])
        except Exception:
            customdata = None

        if customdata is not None:
            hover_lines = [
                f"{name}: %{{customdata[{i}]}}" for i, name in enumerate(hover_names)
            ]
            hovertemplate = "<br>".join(hover_lines) + "<extra></extra>"
        else:
            hovertemplate = None

        if n_components == 2:
            trace = go.Scatter(
                x=emb[:, 0],
                y=emb[:, 1],
                mode="markers",
                marker=dict(color=marker_colors),
                customdata=customdata,
                hovertemplate=hovertemplate,
            )
        else:
            trace = go.Scatter3d(
                x=emb[:, 0],
                y=emb[:, 1],
                z=emb[:, 2],
                mode="markers",
                marker=dict(color=marker_colors, size=3),
                customdata=customdata,
                hovertemplate=hovertemplate,
            )

        fig = go.Figure(data=[trace])

        # Create temporary HTML file and close it before writing to avoid Windows locking
        tmp_path = temp_files.create(suffix=".html", prefix="parqcel_plot_")

        fig.write_html(tmp_path)
        return {"html_path": tmp_path, "emb_shape": emb.shape, "plot_error": None}
    except Exception as e:
        return {"html_path": None, "emb_shape": emb.shape, "plot_error": str(e)}
