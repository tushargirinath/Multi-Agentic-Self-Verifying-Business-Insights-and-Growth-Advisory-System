"""Semantic Metric Compiler: Translates registered metrics and dimension requests into validated SQL."""
from pathlib import Path
from typing import Dict, Any, List, Optional
import yaml


class SemanticCompiler:
    """Compiles registered business metrics into deterministic SQL."""

    def __init__(self, metrics_path: Optional[str] = None):
        if metrics_path is None:
            metrics_path = str(Path(__file__).parent / "metrics.yaml")
        with open(metrics_path, "r", encoding="utf-8") as f:
            self.catalog = yaml.safe_load(f).get("metrics", {})

    def get_registered_metrics(self) -> List[str]:
        """List all registered metric identifiers."""
        return list(self.catalog.keys())

    def get_metric_meta(self, metric_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve metadata for a specific registered metric."""
        return self.catalog.get(metric_id)

    def compile(
        self,
        metric_id: str,
        dimensions: Optional[List[str]] = None,
        filters: Optional[List[str]] = None,
        order_by: Optional[str] = None,
        limit: Optional[int] = None,
        dataset_id: str = "ds_reference",
    ) -> Dict[str, Any]:
        """Compile a registered metric into a complete DuckDB SQL query."""
        if metric_id not in self.catalog:
            raise ValueError(f"Unregistered metric '{metric_id}'. Must be one of {list(self.catalog.keys())}")

        metric = self.catalog[metric_id]
        dimensions = dimensions or []
        filter_clauses = [f"dataset_id = '{dataset_id}'"]
        if filters:
            filter_clauses.extend(filters)

        where_stmt = " AND ".join(filter_clauses)

        # Standalone CTE metrics (e.g. repeat_rate, concentration_top10)
        if "WITH" in metric["sql"].upper():
            sql = metric["sql"].strip()
            return {
                "metric_id": metric_id,
                "name": metric["name"],
                "sql": sql,
                "currency": metric.get("currency"),
                "assumptions": metric.get("assumptions", []),
            }

        select_cols = []
        group_by_cols = []

        for dim in dimensions:
            if dim == "month":
                select_cols.append("date_trunc('month', order_date) AS month")
                group_by_cols.append("1")
            elif dim == "day":
                select_cols.append("order_date AS day")
                group_by_cols.append("1")
            elif dim in ["country", "sku", "product_name", "customer_token"]:
                select_cols.append(f"{dim}")
                group_by_cols.append(dim)
            else:
                select_cols.append(dim)
                group_by_cols.append(dim)

        agg_expr = f"{metric['sql']} AS {metric_id}"
        select_clause = ", ".join(select_cols + [agg_expr]) if select_cols else agg_expr

        sql = f"SELECT {select_clause} FROM fact_order_lines WHERE {where_stmt}"

        if group_by_cols:
            sql += f" GROUP BY {', '.join(group_by_cols)}"

        if order_by:
            sql += f" ORDER BY {order_by}"
        elif select_cols:
            sql += f" ORDER BY {metric_id} DESC"

        if limit:
            sql += f" LIMIT {limit}"

        sql += ";"

        return {
            "metric_id": metric_id,
            "name": metric["name"],
            "sql": sql,
            "dimensions": dimensions,
            "currency": metric.get("currency"),
            "assumptions": metric.get("assumptions", []),
        }
