# Other released versions of the engines

Conformance of a released version other than the one pinned in `versions.env`, measured with
the harness of `main` and the published rule, the version pointed at for one run
(`KGC_BENCH_PIN_<KEY>`; a Python engine installed apart, visible by `PYTHONPATH`). These
rows are not in `results/conformance.csv`.

## `sdm-rdfizer-4.7.5.14/`

SDM-RDFizer 4.7.5.14 (2026-04-21), the version of the CG's implementation report and the best
total of the versions measured on the seven suites (fiche bench/203 of the audit), on the SQL
tracks of rml-test-cases (suite `rml-test-cases-sql`) and RMLSTC0006a, measured 2026-11-27:

```sh
pip install --no-deps --target ~/.cache/kgc-bench-versions/sdm-rdfizer-4.7.5.14 rdfizer==4.7.5.14
PYTHONPATH=~/.cache/kgc-bench-versions/sdm-rdfizer-4.7.5.14 KGC_BENCH_PIN_SDM_RDFIZER_VERSION=4.7.5.14 \
KGC_BENCH_RESULTS=results/versions/sdm-rdfizer-4.7.5.14 \
  python -m harness.conformance --modes rml --engines sdm-rdfizer --suites rml-test-cases-sql
# and: --suites rml-io --only RMLSTC0006a --update
```

| track | 4.7.5.14 | 4.7.5.15.4.1 (pinned) |
|---|---|---|
| PostgreSQL | 15/60 | 30/60 |
| MySQL | 32/60 | 32/60 |
| SQL Server | 15/60 | 15/60 |
| RMLSTC0006a (rml-io, PostgreSQL) | PASS | PASS |

On PostgreSQL and SQL Server, 4.7.5.14 stops at a typo of its own (`rdfizer/functions.py`,
line 941: `onfig["datasets"]["dbType"]`, a `NameError` on every database but MySQL, where the
`or` is not evaluated). 4.7.5.15.4.1 has `config` there; on SQL Server it stops further,
at a `pyodbc.ProgrammingError` (42000). On those tracks, 10 of the 15 PASS of each version
are cases that expect an error.
