import polars as pl


def test_parquet_roundtrip(tmp_path):
	df = pl.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})
	p = tmp_path / "test.parquet"
	df.write_parquet(str(p))

	read = pl.read_parquet(str(p))
	assert read.height == df.height
	assert read.columns == df.columns


def test_csv_roundtrip(tmp_path):
	df = pl.DataFrame({"n": [10, 20], "s": ["aa", "bb"]})
	p = tmp_path / "test.csv"
	df.write_csv(str(p))

	# Let Polars infer types for this roundtrip so numeric column remains numeric
	read = pl.read_csv(str(p))
	# Polars may infer strings differently; compare by values
	assert read.height == df.height
	assert read["n"].to_list() == df["n"].to_list()

