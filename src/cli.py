"""Simple CLI entrypoints for headless workflows used by Parqcel.

Commands:
- featurize: run the featurizer and optionally write out a parquet
- pca: compute PCA and save embedding CSV/HTML
- assistant: run assistant query (uses dummy or configured backend)
"""
from __future__ import annotations

import argparse
import polars as pl

from ds.featurize import generate_feature_matrix, add_features_to_df
from ds.dimensionality import compute_pca


def cmd_featurize(args):
    df = pl.read_parquet(args.input) if args.input.endswith('.parquet') else pl.read_csv(args.input)
    X, names = generate_feature_matrix(df)
    new_df = add_features_to_df(df, X, names)
    if args.output:
        new_df.write_parquet(args.output)
    else:
        print(new_df)


def cmd_pca(args):
    df = pl.read_parquet(args.input) if args.input.endswith('.parquet') else pl.read_csv(args.input)
    X, names = generate_feature_matrix(df)
    emb, var = compute_pca(X, n_components=args.components)
    out = pl.DataFrame({f'pca_{i+1}': emb[:, i] for i in range(emb.shape[1])})
    if args.output:
        out.write_csv(args.output)
    else:
        print(out)


def cmd_assistant(args):
    from ai.assistant import assistant_from_config
    a = assistant_from_config()
    resp = a.suggest_transformation(args.query)
    print(resp)


def main(argv=None):
    parser = argparse.ArgumentParser(prog='parqcel')
    sub = parser.add_subparsers(dest='cmd')

    p = sub.add_parser('featurize')
    p.add_argument('input')
    p.add_argument('--output', '-o')

    p2 = sub.add_parser('pca')
    p2.add_argument('input')
    p2.add_argument('--components', '-k', type=int, default=2)
    p2.add_argument('--output', '-o')

    p3 = sub.add_parser('assistant')
    p3.add_argument('query')

    ns = parser.parse_args(argv)
    if ns.cmd == 'featurize':
        cmd_featurize(ns)
    elif ns.cmd == 'pca':
        cmd_pca(ns)
    elif ns.cmd == 'assistant':
        cmd_assistant(ns)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
