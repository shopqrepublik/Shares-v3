CREATE TABLE IF NOT EXISTS tickers(
  id SERIAL PRIMARY KEY,
  index_name VARCHAR(100) NOT NULL,
  symbol VARCHAR(100) NOT NULL,
  updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS prices(
  symbol VARCHAR(50) NOT NULL,
  dt DATE NOT NULL,
  open NUMERIC, high NUMERIC, low NUMERIC,
  close NUMERIC, adj_close NUMERIC, volume BIGINT,
  PRIMARY KEY(symbol, dt)
);

CREATE TABLE IF NOT EXISTS portfolio_holdings(
  id SERIAL PRIMARY KEY,
  symbol VARCHAR(20) NOT NULL,
  last_price NUMERIC,
  momentum NUMERIC,
  pattern VARCHAR(50),
  weight NUMERIC,
  updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS forecasts(
  id SERIAL PRIMARY KEY,
  symbol VARCHAR(50) NOT NULL,
  horizon_days INT NOT NULL,
  model VARCHAR(20) NOT NULL,
  pred_price NUMERIC,
  mae NUMERIC, mape NUMERIC,
  updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS user_prefs(
  id SERIAL PRIMARY KEY,
  user_id VARCHAR(64),
  budget NUMERIC,
  risk_level VARCHAR(20),
  goal VARCHAR(20),
  horizon_days INT,
  created_at TIMESTAMP DEFAULT NOW()
);
