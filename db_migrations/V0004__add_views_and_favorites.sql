ALTER TABLE t_p38250381_mc_server_bot.servers ADD COLUMN IF NOT EXISTS views integer NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS t_p38250381_mc_server_bot.favorites (
    id serial PRIMARY KEY,
    user_id bigint NOT NULL,
    server_id integer NOT NULL,
    added_at timestamp NOT NULL DEFAULT now(),
    UNIQUE(user_id, server_id)
);