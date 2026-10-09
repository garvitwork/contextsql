"""Business question -> SQL templates (verified by execution at build time)."""

VALID = "LOWER(o.status) NOT IN ('cancelled','canceled','returned')"
REV = "SUM(oi.quantity * oi.unit_price * (1 - COALESCE(oi.discount_pct,0)/100))"
J_OI = "FROM order_items oi JOIN orders o ON o.order_id = oi.order_id"
J_OC = J_OI + " JOIN customers c ON c.customer_id = o.customer_id"
J_OP = J_OI + " JOIN products p ON p.product_id = oi.product_id"
LAST = "o.order_date >= DATE_SUB(CURDATE(), INTERVAL {days} DAY)"

NOTES = {
    "status": "orders.status has inconsistent spelling/case (Shipped, Delivered, Pending, Returned, canceled, Cancelled); compare with LOWER() and treat canceled/cancelled as the same.",
    "discount": "order_items.discount_pct is NULL when there is no discount; use COALESCE(discount_pct,0).",
    "channel": "orders.channel can be NULL (unknown channel).",
    "contact": "customers.city and customers.email can be NULL.",
    "payments": "Not every valid order has a payment row; cancelled and pending orders have none.",
}

TEMPLATES = []

def add(tid, questions, sql, tables, terms=(), notes=(), req=()):
    TEMPLATES.append(dict(id=tid, questions=questions, sql=sql, tables=list(tables),
                          terms=list(terms), notes=list(notes), req=list(req)))

RT = ["valid order", "revenue"]
OO = ["orders", "order_items"]

add("rev_total", ["What is our total revenue?", "Total revenue?", "How much revenue have we made so far?"],
    f"SELECT ROUND({REV},2) AS revenue {J_OI} WHERE {VALID}", OO, RT, ["status", "discount"])
add("rev_last_days", ["Revenue in the last {days} days", "How much did we earn in the past {days} days?", "Show total revenue for the last {days} days"],
    f"SELECT ROUND({REV},2) AS revenue {J_OI} WHERE {VALID} AND {LAST}", OO, RT, ["status", "discount"])
add("rev_by_country", ["Revenue by country", "Which countries bring the most revenue?", "Show revenue per country"],
    f"SELECT c.country, ROUND({REV},2) AS revenue {J_OC} WHERE {VALID} GROUP BY c.country ORDER BY revenue DESC",
    ["customers"] + OO, RT, ["status"])
add("rev_by_category", ["Revenue by product category", "Which category earns the most?", "Show revenue per category"],
    f"SELECT p.category, ROUND({REV},2) AS revenue {J_OP} WHERE {VALID} GROUP BY p.category ORDER BY revenue DESC",
    ["products"] + OO, RT, ["status"])
add("top_customers", ["Top {n} customers by revenue", "Who are our {n} biggest customers?", "List the {n} highest spending customers"],
    f"SELECT c.customer_id, c.name, ROUND({REV},2) AS revenue {J_OC} WHERE {VALID} GROUP BY c.customer_id, c.name ORDER BY revenue DESC LIMIT {{n}}",
    ["customers"] + OO, RT, ["status"])
add("top_products", ["Top {n} products by revenue", "What are our {n} best selling products by revenue?", "Show the {n} products that earn the most"],
    f"SELECT p.product_id, p.name, ROUND({REV},2) AS revenue {J_OP} WHERE {VALID} GROUP BY p.product_id, p.name ORDER BY revenue DESC LIMIT {{n}}",
    ["products"] + OO, RT, ["status"])
add("rev_by_month", ["Monthly revenue", "Show revenue by month", "How does revenue trend month over month?"],
    f"SELECT DATE_FORMAT(o.order_date,'%Y-%m') AS month, ROUND({REV},2) AS revenue {J_OI} WHERE {VALID} GROUP BY month ORDER BY month",
    OO, RT, ["status"])
add("best_month", ["Which month had the highest revenue?", "What was our best month for revenue?", "Find the top revenue month"],
    f"SELECT DATE_FORMAT(o.order_date,'%Y-%m') AS month, ROUND({REV},2) AS revenue {J_OI} WHERE {VALID} GROUP BY month ORDER BY revenue DESC LIMIT 1",
    OO, RT, ["status"])
add("rev_by_channel", ["Revenue by sales channel", "Which channel brings the most revenue?", "Show revenue per channel"],
    f"SELECT COALESCE(o.channel,'unknown') AS channel, ROUND({REV},2) AS revenue {J_OI} WHERE {VALID} GROUP BY COALESCE(o.channel,'unknown') ORDER BY revenue DESC",
    OO, RT, ["status", "channel"])
add("aov_total", ["What is the average order value?", "Average order value", "How much does a typical order bring in?"],
    f"SELECT ROUND({REV} / COUNT(DISTINCT o.order_id),2) AS average_order_value {J_OI} WHERE {VALID}",
    OO, ["valid order", "average order value"], ["status", "discount"])
add("aov_by_country", ["Average order value by country", "Which country has the highest average order value?", "Show AOV per country"],
    f"SELECT c.country, ROUND({REV} / COUNT(DISTINCT o.order_id),2) AS average_order_value {J_OC} WHERE {VALID} GROUP BY c.country ORDER BY average_order_value DESC",
    ["customers"] + OO, ["valid order", "average order value"], ["status"])
add("margin_total", ["What is our gross margin?", "Total gross margin", "How much gross profit have we made?"],
    f"SELECT ROUND({REV} - SUM(oi.quantity * p.cost_price),2) AS gross_margin {J_OP} WHERE {VALID}",
    ["products"] + OO, ["valid order", "gross margin"], ["status", "discount"])
add("margin_by_category", ["Gross margin by category", "Which category has the best margin?", "Show gross margin per product category"],
    f"SELECT p.category, ROUND({REV} - SUM(oi.quantity * p.cost_price),2) AS gross_margin {J_OP} WHERE {VALID} GROUP BY p.category ORDER BY gross_margin DESC",
    ["products"] + OO, ["valid order", "gross margin"], ["status"])
add("return_rate", ["What is our return rate?", "Return rate overall", "What share of orders get returned?"],
    "SELECT ROUND(SUM(LOWER(o.status) = 'returned') / COUNT(*),4) AS return_rate FROM orders o",
    ["orders"], ["return rate"], ["status"])
add("return_rate_country", ["Return rate by country", "Which country has the highest return rate?", "Show returns share per country"],
    "SELECT c.country, ROUND(SUM(LOWER(o.status) = 'returned') / COUNT(*),4) AS return_rate FROM orders o JOIN customers c ON c.customer_id = o.customer_id GROUP BY c.country ORDER BY return_rate DESC",
    ["customers", "orders"], ["return rate"], ["status"])
add("cancel_rate", ["What is the cancellation rate?", "Cancellation rate overall", "What share of orders are cancelled?"],
    "SELECT ROUND(SUM(LOWER(o.status) IN ('cancelled','canceled')) / COUNT(*),4) AS cancellation_rate FROM orders o",
    ["orders"], ["valid order"], ["status"])
add("orders_by_status", ["How many orders per status?", "Order count by status", "Break down orders by status"],
    "SELECT CASE WHEN LOWER(o.status) IN ('cancelled','canceled') THEN 'cancelled' ELSE LOWER(o.status) END AS status, COUNT(*) AS orders FROM orders o GROUP BY 1 ORDER BY orders DESC",
    ["orders"], ["valid order"], ["status"])
add("cancelled_count", ["How many orders were cancelled?", "Number of cancelled orders", "Count cancelled orders"],
    "SELECT COUNT(*) AS cancelled_orders FROM orders o WHERE LOWER(o.status) IN ('cancelled','canceled')",
    ["orders"], ["valid order"], ["status"])
add("valid_orders_days", ["How many valid orders in the last {days} days?", "Count of orders in the past {days} days, excluding cancelled and returned", "Number of successful orders over the last {days} days"],
    f"SELECT COUNT(*) AS orders FROM orders o WHERE {VALID} AND {LAST}",
    ["orders"], ["valid order"], ["status"])
add("active_customers", ["How many active customers do we have?", "Count of active customers", "Number of customers who ordered recently"],
    f"SELECT COUNT(DISTINCT c.customer_id) AS active_customers FROM customers c JOIN orders o ON o.customer_id = c.customer_id WHERE o.order_date >= DATE_SUB(CURDATE(), INTERVAL 90 DAY) AND {VALID}",
    ["customers", "orders"], ["active customer", "valid order"], ["status"])
add("active_by_country", ["Active customers by country", "Which countries have the most active customers?", "Show active customer count per country"],
    f"SELECT c.country, COUNT(DISTINCT c.customer_id) AS active_customers FROM customers c JOIN orders o ON o.customer_id = c.customer_id WHERE o.order_date >= DATE_SUB(CURDATE(), INTERVAL 90 DAY) AND {VALID} GROUP BY c.country ORDER BY active_customers DESC",
    ["customers", "orders"], ["active customer"], ["status"])
add("churned_count", ["How many customers have churned?", "Count churned customers", "Number of customers we lost"],
    f"SELECT COUNT(*) AS churned_customers FROM (SELECT c.customer_id FROM customers c JOIN orders o ON o.customer_id = c.customer_id WHERE {VALID} GROUP BY c.customer_id HAVING MAX(o.order_date) < DATE_SUB(CURDATE(), INTERVAL 180 DAY)) t",
    ["customers", "orders"], ["churned customer", "valid order"], ["status"])
add("unpaid_count", ["How many orders are unpaid?", "Number of valid orders without a payment", "Count unpaid orders"],
    f"SELECT COUNT(*) AS unpaid_orders FROM orders o WHERE {VALID} AND NOT EXISTS (SELECT 1 FROM payments pay WHERE pay.order_id = o.order_id)",
    ["orders", "payments"], ["unpaid order", "valid order"], ["status", "payments"])
add("unpaid_list", ["Show the {n} most recent unpaid orders", "List {n} latest orders that have no payment", "Latest {n} unpaid orders"],
    f"SELECT o.order_id, o.order_date FROM orders o WHERE {VALID} AND NOT EXISTS (SELECT 1 FROM payments pay WHERE pay.order_id = o.order_id) ORDER BY o.order_date DESC LIMIT {{n}}",
    ["orders", "payments"], ["unpaid order", "valid order"], ["status", "payments"])
add("cust_by_country", ["How many customers per country?", "Customer count by country", "Show number of customers in each country"],
    "SELECT country, COUNT(*) AS customers FROM customers GROUP BY country ORDER BY customers DESC",
    ["customers"], [], ["contact"])
add("cust_in_country", ["How many customers are in {country}?", "Customer count in {country}", "Number of customers from {country}"],
    "SELECT COUNT(*) AS customers FROM customers WHERE country = '{country}'",
    ["customers"], [], [])
add("cust_no_email", ["How many customers have no email?", "Count customers missing an email address", "Number of customers without email"],
    "SELECT COUNT(*) AS customers_without_email FROM customers WHERE email IS NULL",
    ["customers"], [], ["contact"])
add("products_in_cat", ["Top {n} most expensive products in {category}", "Show the {n} priciest {category} products", "List {n} {category} products by price, highest first"],
    "SELECT name, unit_price FROM products WHERE category = '{category}' ORDER BY unit_price DESC LIMIT {n}",
    ["products"], [], [])
add("priciest_products", ["What are the {n} most expensive products?", "Show the {n} priciest products", "List the {n} highest priced products"],
    "SELECT name, category, unit_price FROM products ORDER BY unit_price DESC LIMIT {n}",
    ["products"], [], [])
add("rev_by_segment", ["Revenue by customer segment", "Which segment brings the most revenue?", "Show revenue per segment"],
    f"SELECT c.segment, ROUND({REV},2) AS revenue {J_OC} WHERE {VALID} GROUP BY c.segment ORDER BY revenue DESC",
    ["customers"] + OO, RT, ["status"])
add("rev_segment", ["How much revenue comes from {segment} customers?", "Revenue from the {segment} segment", "Total revenue of {segment} customers"],
    f"SELECT ROUND({REV},2) AS revenue {J_OC} WHERE {VALID} AND c.segment = '{{segment}}'",
    ["customers"] + OO, RT, ["status"])
add("rev_country_days", ["Revenue from {country} in the last {days} days", "How much did customers in {country} spend in the past {days} days?", "Show {country} revenue for the last {days} days"],
    f"SELECT ROUND({REV},2) AS revenue {J_OC} WHERE {VALID} AND c.country = '{{country}}' AND {LAST}",
    ["customers"] + OO, RT, ["status"])
add("top_cust_country", ["Top {n} customers in {country} by revenue", "Who are the {n} biggest customers from {country}?", "List the {n} highest spending customers in {country}"],
    f"SELECT c.customer_id, c.name, ROUND({REV},2) AS revenue {J_OC} WHERE {VALID} AND c.country = '{{country}}' GROUP BY c.customer_id, c.name ORDER BY revenue DESC LIMIT {{n}}",
    ["customers"] + OO, RT, ["status"])
add("top_products_cat", ["Top {n} {category} products by revenue", "Best {n} products in {category} by revenue", "Which {n} {category} products earn the most?"],
    f"SELECT p.product_id, p.name, ROUND({REV},2) AS revenue {J_OP} WHERE {VALID} AND p.category = '{{category}}' GROUP BY p.product_id, p.name ORDER BY revenue DESC LIMIT {{n}}",
    ["products"] + OO, RT, ["status"])
add("pay_by_method", ["Total payments by method", "How much was paid through each payment method?", "Show payment totals per method"],
    "SELECT method, ROUND(SUM(amount),2) AS total_paid FROM payments GROUP BY method ORDER BY total_paid DESC",
    ["payments"], [], [])
add("pay_last_days", ["How much payment did we receive in the last {days} days?", "Total payments in the past {days} days", "Payments received over the last {days} days"],
    "SELECT ROUND(SUM(amount),2) AS total_paid FROM payments WHERE payment_date >= DATE_SUB(CURDATE(), INTERVAL {days} DAY)",
    ["payments"], [], [])
add("avg_discount", ["What is the average discount?", "Average discount percentage across all order lines", "How big is our typical discount?"],
    "SELECT ROUND(AVG(COALESCE(discount_pct,0)),2) AS avg_discount_pct FROM order_items",
    ["order_items"], [], ["discount"])
add("discounted_orders", ["How many orders had a discount?", "Number of orders with a discounted item", "Count orders that used a discount"],
    "SELECT COUNT(DISTINCT order_id) AS discounted_orders FROM order_items WHERE discount_pct IS NOT NULL",
    ["order_items"], [], ["discount"])
add("orders_per_channel", ["How many orders per channel?", "Order count by sales channel", "Show number of orders for each channel"],
    "SELECT COALESCE(channel,'unknown') AS channel, COUNT(*) AS orders FROM orders GROUP BY COALESCE(channel,'unknown') ORDER BY orders DESC",
    ["orders"], [], ["channel"])


# ---- "with extra columns" requests (customers) ----
for _cols in [("country", "email"), ("city", "country"), ("segment", "email"), ("segment", "country", "city"), ("email", "city")]:
    _nl = ", ".join(_cols[:-1]) + " and " + _cols[-1]
    _cs = ", ".join(f"c.{x}" for x in _cols)
    add("top_cust_with_" + "_".join(_cols),
        [f"Top {{n}} customers by revenue with their {_nl}", f"give top {{n}} customers with highest revenue with {_nl}",
         f"List the {{n}} biggest customers by revenue including {_nl}"],
        f"SELECT c.customer_id, c.name, {_cs}, ROUND({REV},2) AS revenue {J_OC} WHERE {VALID} GROUP BY c.customer_id, c.name, {_cs} ORDER BY revenue DESC LIMIT {{n}}",
        ["customers"] + OO, RT, ["status", "contact"], list(_cols))
add("top1_customer_loc",
    ["Which customer has the highest revenue and in which city and country?", "which customer has highest revenue in which city and country",
     "Who is our best customer by revenue, and where are they from (city and country)?"],
    f"SELECT c.customer_id, c.name, c.city, c.country, ROUND({REV},2) AS revenue {J_OC} WHERE {VALID} GROUP BY c.customer_id, c.name, c.city, c.country ORDER BY revenue DESC LIMIT 1",
    ["customers"] + OO, RT, ["status", "contact"], ["city", "country"])
add("top_products_with_cat", ["Top {n} products by revenue with their category", "give top {n} products with highest revenue with category"],
    f"SELECT p.product_id, p.name, p.category, ROUND({REV},2) AS revenue {J_OP} WHERE {VALID} GROUP BY p.product_id, p.name, p.category ORDER BY revenue DESC LIMIT {{n}}",
    ["products"] + OO, RT, ["status"], ["category"])


# ---- more glossary-driven business questions ----
V = ["valid order"]
add("units_total", ["How many units have we sold?", "Total units sold", "Number of items sold so far"],
    f"SELECT SUM(oi.quantity) AS units_sold {J_OI} WHERE {VALID}", OO, V + ["units sold"], ["status"])
add("units_by_category", ["Units sold by category", "How many units did each category sell?", "Show units sold per product category"],
    f"SELECT p.category, SUM(oi.quantity) AS units_sold {J_OP} WHERE {VALID} GROUP BY p.category ORDER BY units_sold DESC",
    ["products"] + OO, V + ["units sold"], ["status"])
add("discount_total", ["How much discount have we given?", "Total discount given", "What is the total discount amount?"],
    f"SELECT ROUND(SUM(oi.quantity * oi.unit_price * COALESCE(oi.discount_pct,0) / 100),2) AS discount_given {J_OI} WHERE {VALID}",
    OO, V + ["discount given"], ["status", "discount"])
add("discount_by_category", ["Discount given by category", "How much discount did each category get?"],
    f"SELECT p.category, ROUND(SUM(oi.quantity * oi.unit_price * COALESCE(oi.discount_pct,0) / 100),2) AS discount_given {J_OP} WHERE {VALID} GROUP BY p.category ORDER BY discount_given DESC",
    ["products"] + OO, V + ["discount given"], ["status", "discount"])
add("gross_total", ["What is our gross revenue?", "Gross revenue before discounts", "Total revenue before discount"],
    f"SELECT ROUND(SUM(oi.quantity * oi.unit_price),2) AS gross_revenue {J_OI} WHERE {VALID}", OO, V + ["gross revenue"], ["status"])
add("gross_by_country", ["Gross revenue by country", "Which countries have the highest gross revenue?"],
    f"SELECT c.country, ROUND(SUM(oi.quantity * oi.unit_price),2) AS gross_revenue {J_OC} WHERE {VALID} GROUP BY c.country ORDER BY gross_revenue DESC",
    ["customers"] + OO, V + ["gross revenue"], ["status"])
add("repeat_count", ["How many repeat customers do we have?", "Number of repeat customers", "Count customers who ordered more than once"],
    f"SELECT COUNT(*) AS repeat_customers FROM (SELECT o.customer_id FROM orders o WHERE {VALID} GROUP BY o.customer_id HAVING COUNT(DISTINCT o.order_id) >= 2) t",
    ["orders"], V + ["repeat customer"], ["status"])
add("repeat_list", ["Top {n} repeat customers by number of orders", "Which {n} customers have ordered the most times?", "List {n} repeat customers with the most orders"],
    f"SELECT c.customer_id, c.name, COUNT(DISTINCT o.order_id) AS orders FROM customers c JOIN orders o ON o.customer_id = c.customer_id WHERE {VALID} GROUP BY c.customer_id, c.name HAVING COUNT(DISTINCT o.order_id) >= 2 ORDER BY orders DESC LIMIT {{n}}",
    ["customers", "orders"], V + ["repeat customer"], ["status"])
add("new_customers", ["How many new customers did we get recently?", "Number of new customers", "Count new customers"],
    f"SELECT COUNT(*) AS new_customers FROM (SELECT o.customer_id FROM orders o WHERE {VALID} GROUP BY o.customer_id HAVING MIN(o.order_date) >= DATE_SUB(CURDATE(), INTERVAL 90 DAY)) t",
    ["orders"], V + ["new customer"], ["status"])
add("items_per_order", ["What is the average number of items per order?", "Items per order", "How many items does a typical order have?"],
    f"SELECT ROUND(SUM(oi.quantity) / COUNT(DISTINCT o.order_id),2) AS items_per_order {J_OI} WHERE {VALID}",
    OO, V + ["items per order"], ["status"])
