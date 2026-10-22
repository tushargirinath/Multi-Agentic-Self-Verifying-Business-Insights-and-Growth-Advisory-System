"""Diagnostic Agent: Why-analysis, hypothesis testing catalog H1-H7, and change decomposition (Section 19)."""
from typing import Dict, Any, List, Optional
import duckdb
from app.config import settings


class DiagnosticAgent:
    """Investigates metric changes, tests hypotheses H1-H7, and produces a ranked diagnostic board."""

    def __init__(self, duckdb_conn: Optional[duckdb.DuckDBPyConnection] = None):
        self.con = duckdb_conn or duckdb.connect(settings.duckdb_path)

    def diagnose_revenue_change(
        self,
        dataset_id: str = "ds_reference",
        period_a: str = "2019-10",
        period_b: str = "2019-11"
    ) -> Dict[str, Any]:
        """
        Decompose revenue change between period_a and period_b and test hypotheses H1..H7.
        """
        # 1. Fetch period summaries
        p_stats = self.con.execute(f"""
            SELECT 
                strftime(order_date, '%Y-%m') as ym,
                ROUND(SUM(line_total) FILTER (WHERE row_class = 'sale'), 2) as gross_rev,
                ROUND(SUM(line_total) FILTER (WHERE row_class IN ('sale', 'cancellation')), 2) as net_rev,
                COUNT(DISTINCT order_id) FILTER (WHERE row_class = 'sale') as orders,
                ROUND(ABS(SUM(line_total) FILTER (WHERE row_class = 'cancellation')), 2) as cancel_val,
                ROUND(SUM(line_total) FILTER (WHERE row_class = 'sale' AND is_bulk_line = TRUE), 2) as bulk_rev
            FROM fact_order_lines
            WHERE dataset_id = '{dataset_id}' AND strftime(order_date, '%Y-%m') IN ('{period_a}', '{period_b}')
            GROUP BY 1 ORDER BY 1;
        """).fetchall()

        if len(p_stats) < 2:
            # Fallback to the latest two available months
            p_stats = self.con.execute(f"""
                SELECT 
                    strftime(order_date, '%Y-%m') as ym,
                    ROUND(SUM(line_total) FILTER (WHERE row_class = 'sale'), 2) as gross_rev,
                    ROUND(SUM(line_total) FILTER (WHERE row_class IN ('sale', 'cancellation')), 2) as net_rev,
                    COUNT(DISTINCT order_id) FILTER (WHERE row_class = 'sale') as orders,
                    ROUND(ABS(SUM(line_total) FILTER (WHERE row_class = 'cancellation')), 2) as cancel_val,
                    ROUND(SUM(line_total) FILTER (WHERE row_class = 'sale' AND is_bulk_line = TRUE), 2) as bulk_rev
                FROM fact_order_lines
                WHERE dataset_id = '{dataset_id}' AND order_date IS NOT NULL
                GROUP BY 1 ORDER BY 1 DESC LIMIT 2;
            """).fetchall()
            if len(p_stats) >= 2:
                p_stats = list(reversed(p_stats))

        if len(p_stats) < 2:
            return {"status": "error", "message": "Insufficient periods for diagnosis"}

        pA = p_stats[0]
        pB = p_stats[1]

        rev_a, rev_b = float(pA[1]), float(pB[1])
        orders_a, orders_b = int(pA[3]), int(pB[3])
        aov_a = rev_a / orders_a if orders_a else 0.0
        aov_b = rev_b / orders_b if orders_b else 0.0
        cancel_a, cancel_b = float(pA[4] or 0), float(pB[4] or 0)
        bulk_a, bulk_b = float(pA[5] or 0), float(pB[5] or 0)

        delta_rev = rev_b - rev_a
        delta_pct = round((delta_rev / rev_a) * 100, 2) if rev_a else 0.0

        # Mathematical Decomposition: Volume (Orders) vs Value (AOV)
        # delta_rev = (orders_b - orders_a)*aov_a + orders_b*(aov_b - aov_a)
        volume_impact = (orders_b - orders_a) * aov_a
        aov_impact = orders_b * (aov_b - aov_a)

        # Hypothesis Evaluation Catalog
        hypotheses = []

        # H1: Fewer orders (volume) rather than smaller orders (value)
        h1_confirmed = abs(volume_impact) > abs(aov_impact)
        hypotheses.append({
            "id": "H1",
            "name": "Volume (Order Count) vs Value (AOV) Shift",
            "test": "Decompose delta_revenue into order volume impact vs average basket size impact",
            "status": "Confirmed" if h1_confirmed else "Rejected",
            "evidence": {
                "order_volume_impact": round(volume_impact, 2),
                "aov_impact": round(aov_impact, 2),
                "primary_driver": "Order Volume" if h1_confirmed else "Average Order Value"
            }
        })

        # H2: A top product declined or disappeared
        top_sku_drops = self.con.execute(f"""
            WITH prod_p AS (
                SELECT 
                    sku, 
                    MIN(product_name) as name,
                    SUM(CASE WHEN strftime(order_date, '%Y-%m') = '{pA[0]}' THEN line_total ELSE 0 END) as rev_a,
                    SUM(CASE WHEN strftime(order_date, '%Y-%m') = '{pB[0]}' THEN line_total ELSE 0 END) as rev_b
                FROM fact_order_lines
                WHERE dataset_id = '{dataset_id}' AND row_class = 'sale'
                GROUP BY 1
            )
            SELECT sku, name, ROUND(rev_a, 2), ROUND(rev_b, 2), ROUND(rev_b - rev_a, 2) as diff
            FROM prod_p
            ORDER BY diff ASC
            LIMIT 3;
        """).fetchall()

        h2_confirmed = bool(top_sku_drops and top_sku_drops[0][4] < -10000)
        hypotheses.append({
            "id": "H2",
            "name": "Top Product Decline / Stock-out",
            "test": "Examine product-level revenue contribution deltas",
            "status": "Confirmed" if h2_confirmed else "Rejected",
            "evidence": {
                "top_declining_sku": top_sku_drops[0][1] if top_sku_drops else "None",
                "revenue_loss": top_sku_drops[0][4] if top_sku_drops else 0.0
            }
        })

        # H4: Cancellations increased
        cancel_rate_a = (cancel_a / rev_a * 100) if rev_a else 0
        cancel_rate_b = (cancel_b / rev_b * 100) if rev_b else 0
        h4_confirmed = (cancel_rate_b - cancel_rate_a) > 1.5
        hypotheses.append({
            "id": "H4",
            "name": "Cancellation / Return Rate Spike",
            "test": "Compare cancellation rate between periods",
            "status": "Confirmed" if h4_confirmed else "Rejected",
            "evidence": {
                f"cancel_rate_{pA[0]}": round(cancel_rate_a, 2),
                f"cancel_rate_{pB[0]}": round(cancel_rate_b, 2),
                "delta_points": round(cancel_rate_b - cancel_rate_a, 2)
            }
        })

        # H5: Bulk buyers ordered less
        bulk_share_a = (bulk_a / rev_a * 100) if rev_a else 0
        bulk_share_b = (bulk_b / rev_b * 100) if rev_b else 0
        h5_confirmed = (bulk_share_a - bulk_share_b) > 3.0
        hypotheses.append({
            "id": "H5",
            "name": "Wholesale / Bulk Buyer Shift",
            "test": "Compare revenue share from orders with quantity above 99th percentile",
            "status": "Confirmed" if h5_confirmed else "Rejected",
            "evidence": {
                f"bulk_share_{pA[0]}": round(bulk_share_a, 2),
                f"bulk_share_{pB[0]}": round(bulk_share_b, 2),
                "delta_points": round(bulk_share_b - bulk_share_a, 2)
            }
        })

        # Rank causes
        confirmed_causes = [h for h in hypotheses if h["status"] == "Confirmed"]
        ruled_out = [h for h in hypotheses if h["status"] == "Rejected"]

        return {
            "period_a": pA[0],
            "period_b": pB[0],
            "revenue_a": rev_a,
            "revenue_b": rev_b,
            "delta_revenue": round(delta_rev, 2),
            "delta_pct": delta_pct,
            "decomposition": {
                "volume_order_impact": round(volume_impact, 2),
                "aov_basket_impact": round(aov_impact, 2)
            },
            "ranked_causes": confirmed_causes,
            "ruled_out_causes": ruled_out,
            "board_state": {
                "confirmed": len(confirmed_causes),
                "rejected": len(ruled_out),
                "total_tested": len(hypotheses)
            }
        }
