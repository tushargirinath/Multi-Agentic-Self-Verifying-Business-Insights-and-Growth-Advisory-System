"""Gold Data Layer: Materialized marts, RFM customer segmentation, and market basket analysis."""
from typing import Dict, Any, Optional
import duckdb
from app.config import settings


class GoldManager:
    """Manages the creation and materialization of Gold analytical marts."""

    def __init__(self, duckdb_conn: Optional[duckdb.DuckDBPyConnection] = None):
        self.con = duckdb_conn or duckdb.connect(settings.duckdb_path)
        self._init_tables()

    def _init_tables(self):
        """Create Gold mart tables."""
        self.con.execute("""
            CREATE TABLE IF NOT EXISTS gold_daily (
                dataset_id VARCHAR,
                order_date DATE,
                gross_revenue DECIMAL(14,4),
                net_revenue DECIMAL(14,4),
                orders INTEGER,
                units INTEGER,
                customers INTEGER,
                cancellations INTEGER,
                PRIMARY KEY (dataset_id, order_date)
            );
        """)
        self.con.execute("""
            CREATE TABLE IF NOT EXISTS mart_product_month (
                dataset_id VARCHAR,
                sku VARCHAR,
                product_name VARCHAR,
                order_month DATE,
                revenue DECIMAL(14,4),
                units INTEGER,
                orders INTEGER,
                cancel_units INTEGER
            );
        """)
        self.con.execute("""
            CREATE TABLE IF NOT EXISTS mart_customer_rfm (
                dataset_id VARCHAR,
                customer_token VARCHAR,
                recency_days INTEGER,
                frequency INTEGER,
                monetary DECIMAL(14,4),
                r_score INTEGER,
                f_score INTEGER,
                m_score INTEGER,
                segment VARCHAR,
                PRIMARY KEY (dataset_id, customer_token)
            );
        """)
        self.con.execute("""
            CREATE TABLE IF NOT EXISTS mart_basket_pairs (
                dataset_id VARCHAR,
                a_sku VARCHAR,
                a_name VARCHAR,
                b_sku VARCHAR,
                b_name VARCHAR,
                pair_count INTEGER,
                support DOUBLE,
                confidence DOUBLE,
                lift DOUBLE
            );
        """)

    def build_gold_marts(self, dataset_id: str = "ds_reference") -> Dict[str, Any]:
        """Build all Gold data marts from fact_order_lines."""
        # 1. gold_daily
        self.con.execute(f"DELETE FROM gold_daily WHERE dataset_id = '{dataset_id}';")
        self.con.execute(f"""
            INSERT INTO gold_daily
            SELECT 
                '{dataset_id}' AS dataset_id,
                order_date,
                COALESCE(SUM(line_total) FILTER (WHERE row_class = 'sale'), 0) AS gross_revenue,
                COALESCE(SUM(line_total) FILTER (WHERE row_class IN ('sale', 'cancellation')), 0) AS net_revenue,
                COUNT(DISTINCT order_id) FILTER (WHERE row_class = 'sale') AS orders,
                COALESCE(SUM(quantity) FILTER (WHERE row_class = 'sale'), 0) AS units,
                COUNT(DISTINCT customer_token) FILTER (WHERE row_class = 'sale' AND customer_token IS NOT NULL) AS customers,
                COUNT(DISTINCT order_id) FILTER (WHERE row_class = 'cancellation') AS cancellations
            FROM fact_order_lines
            WHERE dataset_id = '{dataset_id}' AND order_date IS NOT NULL
            GROUP BY order_date
            ORDER BY order_date ASC;
        """)

        # 2. mart_product_month
        self.con.execute(f"DELETE FROM mart_product_month WHERE dataset_id = '{dataset_id}';")
        self.con.execute(f"""
            INSERT INTO mart_product_month
            SELECT 
                '{dataset_id}' AS dataset_id,
                sku,
                MIN(product_name) AS product_name,
                date_trunc('month', order_date)::DATE AS order_month,
                COALESCE(SUM(line_total) FILTER (WHERE row_class = 'sale'), 0) AS revenue,
                COALESCE(SUM(quantity) FILTER (WHERE row_class = 'sale'), 0) AS units,
                COUNT(DISTINCT order_id) FILTER (WHERE row_class = 'sale') AS orders,
                COALESCE(ABS(SUM(quantity) FILTER (WHERE row_class = 'cancellation')), 0) AS cancel_units
            FROM fact_order_lines
            WHERE dataset_id = '{dataset_id}' AND order_date IS NOT NULL
            GROUP BY sku, date_trunc('month', order_date)
            ORDER BY order_month ASC, revenue DESC;
        """)

        # 3. mart_customer_rfm (Section 12.1)
        self.con.execute(f"DELETE FROM mart_customer_rfm WHERE dataset_id = '{dataset_id}';")
        max_date = self.con.execute(f"""
            SELECT MAX(order_date) FROM fact_order_lines WHERE dataset_id = '{dataset_id}'
        """).fetchone()[0]

        self.con.execute(f"""
            CREATE OR REPLACE TEMP TABLE tmp_rfm_raw AS
            SELECT 
                customer_token,
                DATE_DIFF('day', MAX(order_date), DATE '{max_date}') AS recency_days,
                COUNT(DISTINCT order_id) AS frequency,
                COALESCE(SUM(line_total), 0) AS monetary
            FROM fact_order_lines
            WHERE dataset_id = '{dataset_id}' AND row_class = 'sale' AND customer_token IS NOT NULL
            GROUP BY customer_token;
        """)

        self.con.execute(f"""
            CREATE OR REPLACE TEMP TABLE tmp_rfm_scored AS
            SELECT 
                customer_token,
                recency_days,
                frequency,
                monetary,
                NTILE(5) OVER (ORDER BY recency_days DESC) AS r_score,
                NTILE(5) OVER (ORDER BY frequency ASC) AS f_score,
                NTILE(5) OVER (ORDER BY monetary ASC) AS m_score
            FROM tmp_rfm_raw;
        """)

        # Segment mapping per Section 12.1
        self.con.execute(f"""
            INSERT INTO mart_customer_rfm
            SELECT 
                '{dataset_id}' AS dataset_id,
                customer_token,
                recency_days,
                frequency,
                monetary,
                r_score,
                f_score,
                m_score,
                CASE 
                    WHEN r_score >= 4 AND f_score >= 4 AND m_score >= 4 THEN 'Champions'
                    WHEN r_score >= 3 AND f_score >= 3 THEN 'Loyal'
                    WHEN r_score >= 4 AND f_score BETWEEN 2 AND 3 THEN 'Potential Loyalists'
                    WHEN r_score <= 2 AND f_score >= 3 THEN 'At Risk'
                    WHEN r_score <= 2 AND f_score <= 2 THEN 'Hibernating'
                    WHEN r_score = 5 AND f_score = 1 THEN 'New'
                    ELSE 'Promising'
                END AS segment
            FROM tmp_rfm_scored;
        """)

        # 4. mart_basket_pairs (Product Affinity / Market Basket Analysis per Section 12.2 & 20)
        self.con.execute(f"DELETE FROM mart_basket_pairs WHERE dataset_id = '{dataset_id}';")
        self.con.execute(f"""
            CREATE OR REPLACE TEMP TABLE tmp_baskets AS
            SELECT order_id, sku, MIN(product_name) AS product_name
            FROM fact_order_lines
            WHERE dataset_id = '{dataset_id}' AND row_class = 'sale'
            GROUP BY order_id, sku;
        """)

        total_orders = self.con.execute("SELECT COUNT(DISTINCT order_id) FROM tmp_baskets").fetchone()[0] or 1

        # Pre-filter to candidate frequent SKUs to optimize performance
        self.con.execute(f"""
            CREATE OR REPLACE TEMP TABLE tmp_frequent_items AS
            SELECT sku, product_name, COUNT(*) AS item_orders
            FROM tmp_baskets
            GROUP BY 1, 2
            ORDER BY item_orders DESC
            LIMIT 200;
        """)

        # Calculate pairs on candidate frequent products with minimum support of 15 co-orders
        self.con.execute(f"""
            INSERT INTO mart_basket_pairs
            WITH frequent_baskets AS (
                SELECT b.order_id, b.sku, b.product_name
                FROM tmp_baskets b
                JOIN tmp_frequent_items f ON b.sku = f.sku
            ),
            pair_counts AS (
                SELECT 
                    a.sku AS a_sku,
                    a.product_name AS a_name,
                    b.sku AS b_sku,
                    b.product_name AS b_name,
                    COUNT(*) AS pair_count
                FROM frequent_baskets a
                JOIN frequent_baskets b ON a.order_id = b.order_id AND a.sku < b.sku
                GROUP BY 1, 2, 3, 4
                HAVING COUNT(*) >= 15
            )
            SELECT 
                '{dataset_id}' AS dataset_id,
                p.a_sku,
                p.a_name,
                p.b_sku,
                p.b_name,
                p.pair_count,
                ROUND(p.pair_count * 1.0 / {total_orders}, 5) AS support,
                ROUND(p.pair_count * 1.0 / ia.item_orders, 4) AS confidence,
                ROUND((p.pair_count * 1.0 / ia.item_orders) / (ib.item_orders * 1.0 / {total_orders}), 3) AS lift
            FROM pair_counts p
            JOIN tmp_frequent_items ia ON p.a_sku = ia.sku
            JOIN tmp_frequent_items ib ON p.b_sku = ib.sku
            ORDER BY lift DESC;
        """)

        daily_rows = self.con.execute(f"SELECT COUNT(*) FROM gold_daily WHERE dataset_id = '{dataset_id}'").fetchone()[0]
        rfm_rows = self.con.execute(f"SELECT COUNT(*) FROM mart_customer_rfm WHERE dataset_id = '{dataset_id}'").fetchone()[0]
        basket_rows = self.con.execute(f"SELECT COUNT(*) FROM mart_basket_pairs WHERE dataset_id = '{dataset_id}'").fetchone()[0]

        return {
            "dataset_id": dataset_id,
            "daily_records": daily_rows,
            "rfm_customers": rfm_rows,
            "basket_pairs": basket_rows,
            "status": "materialized"
        }
