"""Simple CLI entrypoints for headless workflows used by Parqcel.

Commands:
- featurize: run the featurizer and optionally write out a parquet
- pca: compute PCA and save embedding CSV/HTML
- assistant: run assistant query (uses dummy or configured backend)
"""

from __future__ import annotations

import argparse
from parqcel.core.io import read_dataset, write_dataset_atomic


def cmd_featurize(args):
    try:
        from parqcel.core.operations import featurize_dataset

        df = read_dataset(args.input, csv_types=args.csv_types)
        new_df = featurize_dataset(df)
    except ImportError as exc:  # pragma: no cover - optional extra
        raise SystemExit(
            "Install with 'pip install parqcel[ml]' to use featurize"
        ) from exc

    if args.output:
        write_dataset_atomic(new_df, args.output)
    else:
        print(new_df)


def cmd_pca(args):
    try:
        from parqcel.core.operations import pca_dataset

        df = read_dataset(args.input, csv_types=args.csv_types)
        out = pca_dataset(df, args.components)
    except ImportError as exc:  # pragma: no cover - optional extra
        raise SystemExit("Install with 'pip install parqcel[ml]' to use pca") from exc

    if args.output:
        write_dataset_atomic(out, args.output, format="csv")
    else:
        print(out)


def cmd_assistant(args):
    from ai.assistant import assistant_from_config

    a = assistant_from_config()
    resp = a.suggest_transformation(args.query)
    print(resp)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="parqcel")
    sub = parser.add_subparsers(dest="cmd")

    p = sub.add_parser("featurize")
    p.add_argument("input")
    p.add_argument("--output", "-o")
    p.add_argument("--csv-types", choices=("strings", "infer"), default="strings")

    p2 = sub.add_parser("pca")
    p2.add_argument("input")
    p2.add_argument("--components", "-k", type=int, default=2)
    p2.add_argument("--output", "-o")
    p2.add_argument("--csv-types", choices=("strings", "infer"), default="strings")

    p3 = sub.add_parser("assistant")
    p3.add_argument("query")

    ns = parser.parse_args(argv)
    if ns.cmd == "featurize":
        cmd_featurize(ns)
    elif ns.cmd == "pca":
        cmd_pca(ns)
    elif ns.cmd == "assistant":
        cmd_assistant(ns)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
