USE contextsql;

CREATE TABLE IF NOT EXISTS customers (
  customer_id INT PRIMARY KEY AUTO_INCREMENT,
  name        VARCHAR(100) NOT NULL,
  email       VARCHAR(120),
  country     VARCHAR(50),
  city        VARCHAR(60),
  segment     VARCHAR(20),          -- consumer / smb / enterprise
  created_at  DATE NOT NULL
);

CREATE TABLE IF NOT EXISTS products (
  product_id  INT PRIMARY KEY AUTO_INCREMENT,
  name        VARCHAR(100) NOT NULL,
  category    VARCHAR(50) NOT NULL,
  unit_price  DECIMAL(10,2) NOT NULL,
  cost_price  DECIMAL(10,2) NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
  order_id    INT PRIMARY KEY AUTO_INCREMENT,
  customer_id INT NOT NULL,
  order_date  DATE NOT NULL,
  status      VARCHAR(20) NOT NULL,  -- messy: 'Shipped','shipped','SHIPPED','canceled','Cancelled',...
  channel     VARCHAR(20),           -- web / app / store / partner
  FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
);

CREATE TABLE IF NOT EXISTS order_items (
  item_id      INT PRIMARY KEY AUTO_INCREMENT,
  order_id     INT NOT NULL,
  product_id   INT NOT NULL,
  quantity     INT NOT NULL,
  unit_price   DECIMAL(10,2) NOT NULL,
  discount_pct DECIMAL(5,2),         -- NULL means no discount
  FOREIGN KEY (order_id) REFERENCES orders(order_id),
  FOREIGN KEY (product_id) REFERENCES products(product_id)
);

CREATE TABLE IF NOT EXISTS payments (
  payment_id   INT PRIMARY KEY AUTO_INCREMENT,
  order_id     INT NOT NULL,
  amount       DECIMAL(12,2) NOT NULL,
  payment_date DATE NOT NULL,
  method       VARCHAR(20),
  FOREIGN KEY (order_id) REFERENCES orders(order_id)
);

CREATE TABLE IF NOT EXISTS business_glossary (
  term        VARCHAR(60) PRIMARY KEY,
  definition  TEXT NOT NULL,
  sql_snippet TEXT NOT NULL,
  tables_used VARCHAR(200)
);

CREATE TABLE IF NOT EXISTS query_log (
  id            INT PRIMARY KEY AUTO_INCREMENT,
  question      TEXT NOT NULL,
  generated_sql TEXT,
  success       BOOLEAN,
  error         TEXT,
  attempts      INT DEFAULT 1,
  latency_ms    INT,
  model_version VARCHAR(60),
  created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
