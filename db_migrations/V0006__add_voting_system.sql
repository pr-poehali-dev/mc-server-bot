CREATE TABLE IF NOT EXISTS t_p38250381_mc_server_bot.votes (
    id serial PRIMARY KEY,
    user_id bigint NOT NULL,
    server_id integer NOT NULL,
    score smallint NOT NULL CHECK (score BETWEEN 1 AND 5),
    voted_at timestamp NOT NULL DEFAULT now(),
    week_number integer NOT NULL DEFAULT EXTRACT(WEEK FROM now())::integer,
    year_number integer NOT NULL DEFAULT EXTRACT(YEAR FROM now())::integer,
    UNIQUE(user_id, server_id, week_number, year_number)
);

ALTER TABLE t_p38250381_mc_server_bot.servers
    ADD COLUMN IF NOT EXISTS rating_sum integer NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS rating_count integer NOT NULL DEFAULT 0;