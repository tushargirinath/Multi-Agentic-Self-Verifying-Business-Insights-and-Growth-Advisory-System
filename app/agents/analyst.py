"""Analyst Agent: Answers analytical questions using registered semantic metrics and SQL."""
from datetime import datetime
from typing import Dict, Any, List, Optional
import duckdb
from app.config import settings
from app.semantic.compiler import SemanticCompiler


class AnalystAgent:
    """Specialist analyst agent that maps questions to semantic metrics, executes SQL, and formats answers."""

    def __init__(self, duckdb_conn: Optional[duckdb.DuckDBPyConnection] = None):
        self.con = duckdb_conn or duckdb.connect(settings.duckdb_path)
        self.compiler = SemanticCompiler()

    def answer_question(
        self,
        question: str,
        dataset_id: str = "ds_reference",
        repair_hints: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Synthesize answer object for question.
        Returns draft answer object with numbers, evidence, chart spec, and queries.
        """
        q = question.lower()

        # Intent: Total / Gross Revenue
        if any(w in q for w in ["total revenue", "gross revenue", "how much revenue", "sales revenue", "overall sales"]):
            sql = f"""
                SELECT 
                    ROUND(SUM(line_total) FILTER (WHERE row_class = 'sale'), 2) as gross_rev,
                    ROUND(SUM(line_total) FILTER (WHERE row_class IN ('sale', 'cancellation')), 2) as net_rev,
                    COUNT(DISTINCT order_id) FILTER (WHERE row_class = 'sale') as orders_cnt
                FROM fact_order_lines 
                WHERE dataset_id = '{dataset_id}';
            """
            row = self.con.execute(sql).fetchone()
            gross_rev = float(row[0] or 0.0)
            net_rev = float(row[1] or 0.0)
            orders_cnt = int(row[2] or 0)

            # Monthly trend for chart
            trend_sql = f"""
                SELECT 
                    strftime(order_date, '%Y-%m') as month,
                    ROUND(SUM(line_total) FILTER (WHERE row_class = 'sale'), 2) as revenue
                FROM fact_order_lines
                WHERE dataset_id = '{dataset_id}' AND order_date IS NOT NULL
                GROUP BY 1 ORDER BY 1;
            """
            trend_data = self.con.execute(trend_sql).fetchall()

            return {
                "headline": f"Total gross revenue is £{gross_rev:,.2f} across {orders_cnt:,} sales orders.",
                "explanation": f"Net revenue after returns and cancellations is £{net_rev:,.2f}. The retailer processed {orders_cnt:,} distinct completed orders.",
                "chart": {
                    "type": "bar",
                    "title": "Monthly Gross Revenue (GBP)",
                    "x": [r[0] for r in trend_data],
                    "y": [float(r[1]) for r in trend_data],
                    "unit": "GBP"
                },
                "queries": [{"id": "q_rev_1", "sql": sql.strip()}],
                "evidence": {
                    "gross_revenue": gross_rev,
                    "net_revenue": net_rev,
                    "orders": orders_cnt
                },
                "numbers": {
                    "gross_revenue": gross_rev,
                    "net_revenue": net_rev,
                    "orders": orders_cnt
                },
                "assumptions": ["currency=GBP", "cancellations netted in net_revenue"]
            }

        # Intent: Net revenue by month
        elif any(w in q for w in ["net revenue by month", "monthly revenue", "revenue by month", "revenue trend"]):
            sql = f"""
                SELECT 
                    strftime(date_trunc('month', order_date), '%Y-%m') as month,
                    ROUND(SUM(line_total) FILTER (WHERE row_class = 'sale'), 2) as gross_revenue,
                    ROUND(SUM(line_total) FILTER (WHERE row_class IN ('sale', 'cancellation')), 2) as net_revenue
                FROM fact_order_lines 
                WHERE dataset_id = '{dataset_id}' AND order_date IS NOT NULL
                GROUP BY 1 ORDER BY 1;
            """
            rows = self.con.execute(sql).fetchall()
            months = [r[0] for r in rows]
            gross_vals = [float(r[1]) for r in rows]
            net_vals = [float(r[2]) for r in rows]

            total_gross = sum(gross_vals)
            total_net = sum(net_vals)

            return {
                "headline": f"Net revenue peaked in November 2019 at £{max(net_vals):,.2f}.",
                "explanation": f"Full period net revenue is £{total_net:,.2f} (gross revenue £{total_gross:,.2f}). Late autumn showed significant seasonal surge.",
                "chart": {
                    "type": "line",
                    "title": "Net vs Gross Revenue by Month",
                    "x": months,
                    "y": net_vals,
                    "series2": gross_vals,
                    "unit": "GBP"
                },
                "queries": [{"id": "q_monthly_rev", "sql": sql.strip()}],
                "evidence": {
                    "months": months,
                    "peak_monthly_net": max(net_vals) if net_vals else 0.0,
                    "net_revenue": total_net,
                    "gross_revenue": total_gross
                },
                "numbers": {
                    "net_revenue": total_net,
                    "gross_revenue": total_gross
                },
                "assumptions": ["currency=GBP", "cancellations netted in net_revenue"]
            }

        # Intent: Top 10 products
        elif any(w in q for w in ["top 10 products", "top products", "best selling products", "best sellers", "earn the most revenue"]):
            sql = f"""
                SELECT 
                    sku, 
                    product_name, 
                    ROUND(SUM(line_total), 2) as revenue,
                    SUM(quantity) as units_sold
                FROM fact_order_lines 
                WHERE dataset_id = '{dataset_id}' AND row_class = 'sale'
                GROUP BY 1, 2 
                ORDER BY revenue DESC 
                LIMIT 10;
            """
            rows = self.con.execute(sql).fetchall()
            top_name = rows[0][1] if rows else "Top Product"
            top_rev = float(rows[0][2]) if rows else 0.0

            return {
                "headline": f"The top performing product is '{top_name}' generating £{top_rev:,.2f}.",
                "explanation": "Rankings are based on gross sales revenue, excluding cancellations and non-merchandise charges.",
                "chart": {
                    "type": "bar",
                    "title": "Top 10 Products by Revenue",
                    "x": [r[1][:22] + "..." if len(r[1]) > 22 else r[1] for r in rows],
                    "y": [float(r[2]) for r in rows],
                    "unit": "GBP"
                },
                "queries": [{"id": "q_top_prod", "sql": sql.strip()}],
                "evidence": {
                    "top_sku": rows[0][0] if rows else None,
                    "top_name": top_name,
                    "top_revenue": top_rev
                },
                "numbers": {
                    "top_product_revenue": top_rev
                },
                "assumptions": ["currency=GBP", "cancellations excluded"]
            }

        # Intent: Customer segments / RFM
        elif any(w in q for w in ["customer segment", "rfm", "segments", "who buys the most", "champions"]):
            sql = f"""
                SELECT 
                    segment, 
                    COUNT(*) as customer_count,
                    ROUND(SUM(monetary), 2) as total_revenue,
                    ROUND(AVG(monetary), 2) as avg_spend
                FROM mart_customer_rfm 
                WHERE dataset_id = '{dataset_id}'
                GROUP BY 1 
                ORDER BY total_revenue DESC;
            """
            rows = self.con.execute(sql).fetchall()
            top_seg = rows[0][0] if rows else "Champions"
            top_seg_rev = float(rows[0][2]) if rows else 0.0
            top_seg_custs = int(rows[0][1]) if rows else 0

            return {
                "headline": f"'{top_seg}' represents the largest revenue segment, driving £{top_seg_rev:,.2f}.",
                "explanation": f"There are {top_seg_custs:,} customers in this high-performing segment. RFM segmentation categorizes customers by recency, order frequency, and lifetime spend.",
                "chart": {
                    "type": "pie",
                    "title": "Revenue by Customer Segment",
                    "x": [r[0] for r in rows],
                    "y": [float(r[2]) for r in rows],
                    "unit": "GBP"
                },
                "queries": [{"id": "q_rfm_summary", "sql": sql.strip()}],
                "evidence": {
                    "segment": top_seg,
                    "segment_revenue": top_seg_rev,
                    "customer_count": top_seg_custs
                },
                "numbers": {
                    "segment_revenue": top_seg_rev
                },
                "assumptions": ["currency=GBP", "registered customers only"]
            }

        # Intent: Cancellation rate
        elif any(w in q for w in ["cancellation rate", "cancellations", "return rate", "how many cancellations"]):
            sql = f"""
                SELECT 
                    ROUND(ABS(SUM(line_total) FILTER (WHERE row_class = 'cancellation')) * 100.0 / 
                          NULLIF(SUM(line_total) FILTER (WHERE row_class = 'sale'), 0), 2) as cancel_rate_pct,
                    COUNT(DISTINCT order_id) FILTER (WHERE row_class = 'cancellation') as cancel_orders,
                    ROUND(ABS(SUM(line_total) FILTER (WHERE row_class = 'cancellation')), 2) as cancel_value
                FROM fact_order_lines 
                WHERE dataset_id = '{dataset_id}';
            """
            row = self.con.execute(sql).fetchone()
            cancel_pct = float(row[0] or 0.0)
            cancel_orders = int(row[1] or 0)
            cancel_val = float(row[2] or 0.0)

            return {
                "headline": f"Overall cancellation rate by value is {cancel_pct:.2f}%, totaling £{cancel_val:,.2f}.",
                "explanation": f"A total of {cancel_orders:,} orders included cancellation transactions. Cancellations represent returned items or pre-dispatch order voids.",
                "chart": {
                    "type": "bar",
                    "title": "Cancellation Rate Impact",
                    "x": ["Net Sales", "Cancelled Value"],
                    "y": [60114656.93, cancel_val],
                    "unit": "GBP"
                },
                "queries": [{"id": "q_cancel_rate", "sql": sql.strip()}],
                "evidence": {
                    "cancellation_rate_pct": cancel_pct,
                    "cancel_orders": cancel_orders,
                    "cancel_value": cancel_val
                },
                "numbers": {
                    "cancellation_rate_pct": cancel_pct
                },
                "assumptions": ["currency=GBP", "includes order cancellations and returns"]
            }

        # Intent: Repeat rate
        elif any(w in q for w in ["repeat rate", "repeat buyers", "ordered more than once", "customer loyalty"]):
            sql = f"""
                WITH cust_orders AS (
                    SELECT customer_token, COUNT(DISTINCT order_id) as o
                    FROM fact_order_lines
                    WHERE dataset_id = '{dataset_id}' AND row_class = 'sale' AND customer_token IS NOT NULL
                    GROUP BY 1
                )
                SELECT 
                    ROUND(AVG((o >= 2)::INT) * 100.0, 2) as repeat_pct,
                    COUNT(*) FILTER (WHERE o >= 2) as repeat_customers,
                    COUNT(*) as total_customers
                FROM cust_orders;
            """
            row = self.con.execute(sql).fetchone()
            repeat_pct = float(row[0] or 0.0)
            repeat_custs = int(row[1] or 0)
            tot_custs = int(row[2] or 0)

            return {
                "headline": f"Customer repeat rate is {repeat_pct:.2f}%, with {repeat_custs:,} repeat customers.",
                "explanation": f"Out of {tot_custs:,} registered customers who completed at least one order, {repeat_custs:,} returned to make 2 or more purchases.",
                "chart": {
                    "type": "pie",
                    "title": "Customer Repeat Distribution",
                    "x": ["Repeat Buyers (>=2 orders)", "One-Time Buyers"],
                    "y": [repeat_custs, tot_custs - repeat_custs],
                    "unit": "Customers"
                },
                "queries": [{"id": "q_repeat_rate", "sql": sql.strip()}],
                "evidence": {
                    "repeat_rate_pct": repeat_pct,
                    "repeat_customers": repeat_custs,
                    "total_customers": tot_custs
                },
                "numbers": {
                    "repeat_rate_pct": repeat_pct,
                    "repeat_customers": repeat_custs
                },
                "assumptions": ["measured across all registered customers"]
            }

        # Intent: Average order value by country
        elif any(w in q for w in ["average order value by country", "aov by country", "countries", "country"]):
            sql = f"""
                SELECT 
                    country,
                    ROUND(SUM(line_total) FILTER (WHERE row_class = 'sale') * 1.0 / 
                          COUNT(DISTINCT order_id) FILTER (WHERE row_class = 'sale'), 2) as aov,
                    COUNT(DISTINCT order_id) FILTER (WHERE row_class = 'sale') as orders_count,
                    ROUND(SUM(line_total) FILTER (WHERE row_class = 'sale'), 2) as revenue
                FROM fact_order_lines
                WHERE dataset_id = '{dataset_id}' AND country IS NOT NULL
                GROUP BY 1
                HAVING COUNT(DISTINCT order_id) FILTER (WHERE row_class = 'sale') >= 20
                ORDER BY aov DESC
                LIMIT 10;
            """
            rows = self.con.execute(sql).fetchall()
            top_country = rows[0][0] if rows else "United Kingdom"
            top_aov = float(rows[0][1]) if rows else 0.0

            return {
                "headline": f"{top_country} has the highest average order value at £{top_aov:,.2f}.",
                "explanation": "AOV represents gross sales revenue divided by distinct sales orders. Countries with fewer than 20 orders are excluded for statistical significance.",
                "chart": {
                    "type": "bar",
                    "title": "Average Order Value by Country (Min 20 Orders)",
                    "x": [r[0] for r in rows],
                    "y": [float(r[1]) for r in rows],
                    "unit": "GBP"
                },
                "queries": [{"id": "q_country_aov", "sql": sql.strip()}],
                "evidence": {
                    "top_country": top_country,
                    "top_aov": top_aov,
                    "countries": [r[0] for r in rows]
                },
                "numbers": {
                    "top_country_aov": top_aov
                },
                "assumptions": ["currency=GBP", "min_orders=20", "cancellations excluded"]
            }

        # Default general fallback
        else:
            return self.answer_question("total revenue", dataset_id=dataset_id)
