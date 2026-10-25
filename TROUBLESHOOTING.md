# MAVIS Troubleshooting and Issue Log

This log records significant errors, root causes, attempted solutions, and resolved outcomes encountered during development.

---

### Issue 1: DuckDB CSV Auto-Detection Date Format Mismatch
- **Date**: 2026-10-21
- **Symptoms**: `Conversion Error: CSV Error on Line: 25363. Could not convert string "11/30/2019" to 'DATE'`.
- **Root Cause**: DuckDB auto-detector sampled initial rows where day <= 12 and tentatively inferred `%d/%m/%Y`. When encountering day `30` in the second month position (`11/30/2019`), conversion failed because the dataset uses `%m/%d/%Y` (or mixed formats).
- **Fix**: As designed in MAVIS Specification Section 8.2 and Rule CL-02, ingest raw date as VARCHAR in Bronze, run format ambiguity analysis in the Ingestion Agent, and parse to ISO 8601 (`%Y-%m-%d`) explicitly during Silver cleaning.
- **Verification**: Verified using `types={'Date': 'VARCHAR', ...}`, successfully loading all 536,350 rows in DuckDB in ~0.5 seconds.

---

### Issue 2: YAML Multi-line Triple Quotes Syntax Error
- **Date**: 2026-10-21
- **Symptoms**: `yaml.parser.ParserError: while parsing a block mapping ... expected <block end>, but found '<scalar>'`.
- **Root Cause**: Python-style triple quotes (`"""`) were used in `metrics.yaml` for multi-line SQL definitions instead of YAML block scalar syntax (`|`).
- **Fix**: Replaced triple quotes with standard YAML literal block scalar `|`.

---

### Issue 3: Market Basket Analysis Pair Combinatorial Explosion (OOM)
- **Date**: 2026-10-21
- **Symptoms**: `_duckdb.OutOfMemoryException: Out of Memory Error: Allocation failure` during basket pairs calculation.
- **Root Cause**: Joining all 500k+ basket rows against themselves (`a.order_id = b.order_id AND a.sku < b.sku`) produced an unfiltered Cartesian product across thousands of infrequent SKUs.
- **Fix**: Following Section 20 of the specification, pre-filter items to candidate SKUs with minimum order support (`HAVING COUNT(*) >= 25`) prior to the self-join, keeping memory usage constant and computation under 1 second.

