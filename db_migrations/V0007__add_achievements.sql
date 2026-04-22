CREATE TABLE IF NOT EXISTS t_p38250381_mc_server_bot.achievements (
    id serial PRIMARY KEY,
    user_id bigint NOT NULL,
    code text NOT NULL,
    unlocked_at timestamp NOT NULL DEFAULT now(),
    UNIQUE(user_id, code)
);