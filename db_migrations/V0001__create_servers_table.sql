CREATE TABLE IF NOT EXISTS t_p38250381_mc_server_bot.servers (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    username TEXT,
    ip TEXT NOT NULL,
    version TEXT NOT NULL,
    added_at TIMESTAMP DEFAULT NOW()
);