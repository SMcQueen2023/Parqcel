from __future__ import annotations

import argparse
import json
import os

import polars as pl


def run_featurize(input_path: str, output_path: str) -> None:
    from ds.featurize import add_features_to_df, generate_feature_matrix

    df = (
        pl.read_parquet(input_path)
        if input_path.endswith(".parquet")
        else pl.read_csv(input_path)
    )
    X, names = generate_feature_matrix(df)
    out = add_features_to_df(df, X, names)
    out.write_parquet(output_path)


def run_pca(input_path: str, output_path: str, components: int = 2) -> None:
    from ds.dimensionality import compute_pca
    from ds.featurize import generate_feature_matrix

    df = (
        pl.read_parquet(input_path)
        if input_path.endswith(".parquet")
        else pl.read_csv(input_path)
    )
    X, _ = generate_feature_matrix(df)
    emb, _ = compute_pca(X, n_components=components)
    out = pl.DataFrame({f"pca_{i + 1}": emb[:, i] for i in range(emb.shape[1])})
    out.write_csv(output_path)


def _run_from_payload(payload: dict) -> None:
    op = payload.get("operation")
    if op == "featurize":
        run_featurize(payload["input_path"], payload["output_path"])
    elif op == "pca":
        run_pca(
            payload["input_path"],
            payload["output_path"],
            int(payload.get("components", 2)),
        )
    else:
        raise ValueError(f"Unsupported operation: {op}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="parqcel-worker")
    parser.add_argument("--payload", type=str, help="Inline JSON payload")
    parser.add_argument("--payload-file", type=str, help="Path to JSON payload file")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    payload_json = args.payload or os.getenv("PARQCEL_JOB_PAYLOAD")
    payload_file = args.payload_file or os.getenv("PARQCEL_JOB_FILE")

    if payload_json:
        payload = json.loads(payload_json)
    elif payload_file:
        with open(payload_file, "r", encoding="utf-8") as f:
            payload = json.load(f)
    else:
        raise SystemExit(
            "No payload supplied. Use --payload/--payload-file or PARQCEL_JOB_PAYLOAD/PARQCEL_JOB_FILE"
        )

    _run_from_payload(payload)


if __name__ == "__main__":
    main()
