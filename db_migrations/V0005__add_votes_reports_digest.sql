CREATE TABLE IF NOT EXISTS t_p38250381_mc_server_bot.votes (
    id serial PRIMARY KEY,
    user_id bigint NOT NULL,
    server_id integer NOT NULL,
    value smallint NOT NULL CHECK (value IN (1, -1)),
    voted_at timestamp NOT NULL DEFAULT now(),
    UNIQUE(user_id, server_id)
);

CREATE TABLE IF NOT EXISTS t_p38250381_mc_server_bot.reports (
    id serial PRIMARY KEY,
    user_id bigint NOT NULL,
    server_id integer NOT NULL,
    reason text,
    reported_at timestamp NOT NULL DEFAULT now(),
    UNIQUE(user_id, server_id)
);

ALTER TABLE t_p38250381_mc_server_bot.servers
    ADD COLUMN IF NOT EXISTS likes integer NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS dislikes integer NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS reports_count integer NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS digest_subscribers bigint[] NOT NULL DEFAULT '{}';

CREATE TABLE IF NOT EXISTS t_p38250381_mc_server_bot.digest_subs (
    user_id bigint PRIMARY KEY,
    subscribed_at timestamp NOT NULL DEFAULT now()
);