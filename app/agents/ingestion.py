"""Ingestion Agent: File parsing, schema mapping, profiling, and capability evaluation."""
import csv
import io
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
import duckdb
from app.data.bronze import BronzeManager


CANONICAL_FIELDS = {
    "order_id": ["transactionno", "invoiceno", "order_id", "orderid", "transaction_id", "invoice_no"],
    "order_date": ["date", "invoicedate", "order_date", "transaction_date", "orderdate", "timestamp"],
    "sku": ["productno", "stockcode", "sku", "product_id", "item_code", "product_code", "productno."],
    "product_name": ["productname", "description", "product_name", "item_name", "title", "product_description"],
    "unit_price": ["price", "unitprice", "unit_price", "rate", "price_per_unit"],
    "quantity": ["quantity", "qty", "units", "quantity_ordered"],
    "customer_id": ["customerno", "customerid", "customer_id", "user_id", "client_id", "customer_no"],
    "country": ["country", "location", "region", "nation", "country_name"],
}


class IngestionAgent:
    """Agent responsible for inspecting raw input files, inferring schema, profiling data,
    and evaluating the Data Capability Matrix."""

    def __init__(self, duckdb_conn: Optional[duckdb.DuckDBPyConnection] = None):
        self.bronze_manager = BronzeManager(duckdb_conn)
        self.con = self.bronze_manager.con

    @staticmethod
    def detect_file_properties(file_path: str) -> Dict[str, Any]:
        """Detect encoding, delimiter, and header from sample bytes."""
        encoding = "utf-8"
        sample_bytes = b""
        with open(file_path, "rb") as f:
            sample_bytes = f.read(65536)

        try:
            sample_text = sample_bytes.decode("utf-8")
        except UnicodeDecodeError:
            try:
                sample_text = sample_bytes.decode("latin-1")
                encoding = "latin-1"
            except UnicodeDecodeError:
                sample_text = sample_bytes.decode("utf-8", errors="replace")
                encoding = "utf-8-sig"

        # Detect delimiter using csv Sniffer
        sniffer = csv.Sniffer()
        try:
            dialect = sniffer.sniff(sample_text[:8192], delimiters=[",", "\t", ";", "|"])
            delimiter = dialect.delimiter
            has_header = sniffer.has_header(sample_text[:8192])
        except Exception:
            delimiter = ","
            has_header = True

        first_line = sample_text.splitlines()[0] if sample_text.splitlines() else ""
        raw_headers = [h.strip().strip('"').strip("'") for h in first_line.split(delimiter)]

        return {
            "encoding": encoding,
            "delimiter": delimiter,
            "has_header": has_header,
            "raw_headers": raw_headers,
        }

    def map_columns(self, raw_headers: List[str], overrides: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """Map raw headers to canonical fields with confidence scoring."""
        mapping = {}
        confidence_scores = {}
        overrides = overrides or {}

        # Normalize raw headers
        norm_to_raw = {re.sub(r"[^a-z0-9]", "", h.lower()): h for h in raw_headers}

        for canonical, aliases in CANONICAL_FIELDS.items():
            if canonical in overrides:
                source_col = overrides[canonical]
                mapping[canonical] = source_col
                confidence_scores[canonical] = 1.0
                continue

            matched = False
            # Check exact match with canonical name
            clean_canonical = re.sub(r"[^a-z0-9]", "", canonical.lower())
            if clean_canonical in norm_to_raw:
                mapping[canonical] = norm_to_raw[clean_canonical]
                confidence_scores[canonical] = 1.0
                matched = True

            if not matched:
                # Check aliases
                for alias in aliases:
                    clean_alias = re.sub(r"[^a-z0-9]", "", alias.lower())
                    if clean_alias in norm_to_raw:
                        mapping[canonical] = norm_to_raw[clean_alias]
                        confidence_scores[canonical] = 0.95
                        matched = True
                        break

            if not matched:
                # Substring match
                for clean_norm, orig in norm_to_raw.items():
                    if any(clean_norm in a or a in clean_norm for a in [clean_canonical] + aliases):
                        mapping[canonical] = orig
                        confidence_scores[canonical] = 0.75
                        matched = True
                        break

            if not matched:
                mapping[canonical] = None
                confidence_scores[canonical] = 0.0

        return {
            "mapping": mapping,
            "confidence_scores": confidence_scores,
            "all_mapped": all(mapping[k] is not None for k in ["order_id", "order_date", "sku", "unit_price", "quantity"]),
        }

    def detect_date_format(self, table_name: str, date_col: str) -> Dict[str, Any]:
        """Analyze date string values to determine whether %m/%d/%Y or %d/%m/%Y is used."""
        query = f"""
            SELECT "{date_col}" AS sample_date 
            FROM {table_name} 
            WHERE "{date_col}" IS NOT NULL AND trim("{date_col}") != ''
            LIMIT 5000
        """
        sample_rows = self.con.execute(query).fetchall()
        
        m_first_confirms = 0  # first token > 12 -> impossible for month -> d/m/y
        d_first_confirms = 0  # second token > 12 -> impossible for month -> m/d/y
        separator = "/"

        for (val,) in sample_rows:
            if not val:
                continue
            parts = re.split(r"[/.-]", str(val).split()[0])
            if len(parts) >= 3:
                try:
                    p1, p2, _ = int(parts[0]), int(parts[1]), parts[2]
                    if p1 > 12 >= p2:
                        m_first_confirms += 1  # part 1 is day -> d/m/y
                    elif p2 > 12 >= p1:
                        d_first_confirms += 1  # part 2 is day -> m/d/y
                except ValueError:
                    continue

        if d_first_confirms > m_first_confirms:
            inferred_format = "%m/%d/%Y"
            confidence = 0.98
        elif m_first_confirms > d_first_confirms:
            inferred_format = "%d/%m/%Y"
            confidence = 0.98
        else:
            inferred_format = "%m/%d/%Y"  # fallback default
            confidence = 0.60

        return {
            "inferred_format": inferred_format,
            "d_first_confirms": d_first_confirms,
            "m_first_confirms": m_first_confirms,
            "confidence": confidence,
        }

    def profile_dataset(self, file_path: str, dataset_id: str = "ds_reference", overrides: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """Execute full profiling checks (Section 8.7 & Section 10.1) on the input file."""
        t0 = datetime.now()
        # Ingest to bronze layer
        bronze_info = self.bronze_manager.load_raw_csv_to_bronze(file_path, dataset_id)
        raw_table = bronze_info["raw_table"]

        file_props = self.detect_file_properties(file_path)
        mapping_info = self.map_columns(file_props["raw_headers"], overrides)
        mapping = mapping_info["mapping"]

        # Date format detection
        date_col = mapping.get("order_date")
        date_format_info = self.detect_date_format(raw_table, date_col) if date_col else {}

        # First checks from Section 8.7
        order_col = mapping.get("order_id") or "TransactionNo"
        product_col = mapping.get("sku") or "ProductNo"
        desc_col = mapping.get("product_name") or "ProductName"
        price_col = mapping.get("unit_price") or "Price"
        qty_col = mapping.get("quantity") or "Quantity"
        customer_col = mapping.get("customer_id") or "CustomerNo"
        country_col = mapping.get("country") or "Country"

        # Summary query
        summary_sql = f"""
            SELECT 
                COUNT(*) as total_rows,
                COUNT(DISTINCT "{order_col}") as unique_orders,
                COUNT(DISTINCT "{product_col}") as unique_products,
                COUNT(DISTINCT "{customer_col}") as unique_customers,
                COUNT(DISTINCT "{country_col}") as unique_countries,
                COUNT(*) FILTER (WHERE "{customer_col}" IS NULL OR trim("{customer_col}") = '') as null_customers,
                COUNT(*) FILTER (WHERE TRY_CAST("{price_col}" AS DOUBLE) <= 0) as zero_or_neg_prices,
                COUNT(*) FILTER (WHERE TRY_CAST("{qty_col}" AS BIGINT) < 0) as neg_quantities,
                COUNT(*) FILTER (WHERE "{order_col}" LIKE 'C%' OR "{order_col}" LIKE 'c%') as c_prefix_orders
            FROM {raw_table}
        """
        summary_row = self.con.execute(summary_sql).fetchone()

        total_rows = summary_row[0]
        unique_orders = summary_row[1]
        unique_products = summary_row[2]
        unique_customers = summary_row[3]
        unique_countries = summary_row[4]
        null_customers = summary_row[5]
        zero_or_neg_prices = summary_row[6]
        neg_quantities = summary_row[7]
        c_prefix_orders = summary_row[8]

        # Duplicate rows check (Section 8.7 query 4)
        dup_sql = f"""
            SELECT COUNT(*) - COUNT(DISTINCT ("{order_col}", "{product_col}", "{qty_col}", "{date_col}", "{customer_col}"))
            FROM {raw_table}
        """
        dup_rows = self.con.execute(dup_sql).fetchone()[0]

        # Date range detection
        date_min_max = self.con.execute(f"""
            SELECT MIN("{date_col}"), MAX("{date_col}") FROM {raw_table} WHERE "{date_col}" IS NOT NULL
        """).fetchone()

        # Capability matrix evaluation
        capability_matrix = self.evaluate_capabilities(mapping)

        duration_sec = (datetime.now() - t0).total_seconds()

        return {
            "dataset_id": dataset_id,
            "file_properties": file_props,
            "column_mapping": mapping,
            "mapping_confidence": mapping_info["confidence_scores"],
            "date_format_analysis": date_format_info,
            "profile": {
                "total_rows": total_rows,
                "unique_orders": unique_orders,
                "unique_products": unique_products,
                "unique_customers": unique_customers,
                "unique_countries": unique_countries,
                "null_customers": null_customers,
                "null_customer_pct": round(null_customers / total_rows * 100, 2) if total_rows else 0.0,
                "zero_or_neg_prices": zero_or_neg_prices,
                "neg_quantities": neg_quantities,
                "c_prefix_orders": c_prefix_orders,
                "duplicate_rows": dup_rows,
                "duplicate_row_pct": round(dup_rows / total_rows * 100, 2) if total_rows else 0.0,
                "raw_date_min": date_min_max[0],
                "raw_date_max": date_min_max[1],
            },
            "capability_matrix": capability_matrix,
            "bronze_meta": bronze_info,
            "profiling_duration_sec": round(duration_sec, 2),
        }

    @staticmethod
    def evaluate_capabilities(mapping: Dict[str, str]) -> List[Dict[str, Any]]:
        """Evaluate business analytical capabilities per Section 8.5."""
        has_id = bool(mapping.get("order_id"))
        has_date = bool(mapping.get("order_date"))
        has_sku = bool(mapping.get("sku"))
        has_price = bool(mapping.get("unit_price"))
        has_qty = bool(mapping.get("quantity"))
        has_cust = bool(mapping.get("customer_id"))
        has_country = bool(mapping.get("country"))

        return [
            {
                "feature": "Revenue, orders, units, AOV trends",
                "needs": "date, price, quantity, order id",
                "status": "Available" if (has_date and has_price and has_qty and has_id) else "Unavailable",
                "unlock_reason": "" if (has_date and has_price and has_qty and has_id) else "Missing core transaction fields"
            },
            {
                "feature": "Top and bottom products, ABC, long tail",
                "needs": "product, price, quantity",
                "status": "Available" if (has_sku and has_price and has_qty) else "Unavailable",
                "unlock_reason": "" if (has_sku and has_price and has_qty) else "Requires product identifier, price and quantity"
            },
            {
                "feature": "Country analysis",
                "needs": "country",
                "status": "Available" if has_country else "Unavailable",
                "unlock_reason": "" if has_country else "Missing country column"
            },
            {
                "feature": "Repeat rate, RFM, customer lifetime proxies",
                "needs": "customer id, date, value",
                "status": "Available for rows with a customer id" if (has_cust and has_date and has_price and has_qty) else "Unavailable",
                "unlock_reason": "Missing customer identifier" if not has_cust else ""
            },
            {
                "feature": "Product affinity (baskets)",
                "needs": "order id, product",
                "status": "Available" if (has_id and has_sku) else "Unavailable",
                "unlock_reason": "Missing order ID or product ID" if not (has_id and has_sku) else ""
            },
            {
                "feature": "Cancellation analysis",
                "needs": "negative quantity or cancel code",
                "status": "Available" if (has_qty or has_id) else "Unavailable",
                "unlock_reason": ""
            },
            {
                "feature": "Revenue forecast",
                "needs": "daily history",
                "status": "Available; one year limits annual seasonality (see Section 18)",
                "unlock_reason": "" if has_date else "Requires date history"
            },
            {
                "feature": "Price elasticity",
                "needs": "price variation over time",
                "status": "Partial; observational only; wide ranges",
                "unlock_reason": "Observational data without randomized pricing experiments"
            },
            {
                "feature": "Profit and margin",
                "needs": "unit cost",
                "status": "Not available; optional user-entered or simulated cost (flagged)",
                "unlock_reason": "Unit cost data missing from dataset. Provide cost column or category margin assumption."
            },
            {
                "feature": "Stock-out prediction",
                "needs": "stock levels",
                "status": "Not available; MAVIS reports demand velocity instead",
                "unlock_reason": "Stock levels missing from dataset. MAVIS computes velocity (units/30d) as proxy."
            },
            {
                "feature": "Channel and device funnel",
                "needs": "channel, device, sessions",
                "status": "Not available",
                "unlock_reason": "Channel, device and session web analytics not present in transactional export."
            },
            {
                "feature": "Ad ROI and CAC",
                "needs": "ad spend by channel",
                "status": "Not available; add a marketing file to unlock",
                "unlock_reason": "Ad spend file required to compute ROI and CAC."
            }
        ]
