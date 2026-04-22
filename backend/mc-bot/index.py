import json
import os
import socket
import random
import struct
import datetime
import psycopg2
import urllib.request

SCHEMA = os.environ.get('MAIN_DB_SCHEMA', 't_p38250381_mc_server_bot')
PAGE_SIZE = 5

user_states = {}

LAUNCH_PHRASES = [
    "🚀 Твой сервер теперь в космосе! Полетели искать игроков!",
    "⛏️ Добавлено в каталог. Пусть алмазы сами идут к тебе!",
    "🌍 Сервер на орбите! Скоро к тебе придут первые игроки.",
    "🎮 Готово! Ещё один сервер покорит просторы блочного мира.",
    "✨ Принято! Надеюсь, на твоём сервере нет гриферов 😄",
    "🏆 Запись добавлена. Может именно твой сервер станет топ-1?",
]

SCORE_LABELS = {1: "😡 Ужасно", 2: "😕 Плохо", 3: "😐 Норм", 4: "😊 Хорошо", 5: "🤩 Огонь!"}

# ─── Telegram ─────────────────────────────────────────────────────────────────

def send_message(token, chat_id, text, reply_markup=None):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req)

def answer_callback(token, callback_query_id, text=None):
    url = f"https://api.telegram.org/bot{token}/answerCallbackQuery"
    payload = {"callback_query_id": callback_query_id}
    if text:
        payload["text"] = text
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req)

def get_main_keyboard():
    return json.dumps({
        "keyboard": [
            [{"text": "➕ ДОБАВИТЬ СЕРВЕР"}, {"text": "🌐 СЕРВЕРЫ"}],
            [{"text": "🏆 ТОП СЕРВЕРОВ"}, {"text": "⭐ ИЗБРАННОЕ"}],
            [{"text": "📋 МОИ СЕРВЕРЫ"}, {"text": "✏️ ИЗМЕНИТЬ ОПИСАНИЕ"}],
            [{"text": "📊 МОЯ СТАТИСТИКА"}]
        ],
        "resize_keyboard": True
    })

# ─── DB ───────────────────────────────────────────────────────────────────────

def get_db_conn():
    return psycopg2.connect(os.environ['DATABASE_URL'])

def add_server(user_id, username, hosting, ip, version, description=None):
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute(
        f"INSERT INTO {SCHEMA}.servers (user_id, username, hosting, ip, version, description) VALUES (%s, %s, %s, %s, %s, %s)",
        (user_id, username, hosting, ip, version, description)
    )
    conn.commit()
    cur.close(); conn.close()

def get_servers_page(page):
    conn = get_db_conn()
    cur = conn.cursor()
    offset = page * PAGE_SIZE
    cur.execute(
        f"""SELECT ip, version, username, added_at, description, hosting, views,
                   CASE WHEN rating_count > 0 THEN ROUND(rating_sum::numeric / rating_count, 1) ELSE NULL END
            FROM {SCHEMA}.servers ORDER BY added_at DESC LIMIT %s OFFSET %s""",
        (PAGE_SIZE, offset)
    )
    rows = cur.fetchall()
    cur.execute(f"SELECT COUNT(*) FROM {SCHEMA}.servers")
    total = cur.fetchone()[0]
    cur.close(); conn.close()
    return rows, total

def get_top_servers():
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute(
        f"""SELECT id, ip, version, username, description, hosting, views,
                   CASE WHEN rating_count > 0 THEN ROUND(rating_sum::numeric / rating_count, 1) ELSE NULL END,
                   rating_count
            FROM {SCHEMA}.servers ORDER BY views DESC LIMIT 10"""
    )
    rows = cur.fetchall()
    cur.close(); conn.close()
    return rows

def get_user_servers(user_id):
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute(
        f"""SELECT id, ip, version, description, hosting,
                   CASE WHEN rating_count > 0 THEN ROUND(rating_sum::numeric / rating_count, 1) ELSE NULL END,
                   rating_count
            FROM {SCHEMA}.servers WHERE user_id = %s ORDER BY added_at DESC""",
        (user_id,)
    )
    rows = cur.fetchall()
    cur.close(); conn.close()
    return rows

def delete_server(server_id, user_id):
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute(f"DELETE FROM {SCHEMA}.servers WHERE id = %s AND user_id = %s", (server_id, user_id))
    deleted = cur.rowcount
    conn.commit()
    cur.close(); conn.close()
    return deleted > 0

def update_description(server_id, user_id, description):
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute(
        f"UPDATE {SCHEMA}.servers SET description = %s WHERE id = %s AND user_id = %s",
        (description, server_id, user_id)
    )
    updated = cur.rowcount
    conn.commit()
    cur.close(); conn.close()
    return updated > 0

def increment_views(server_id):
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute(f"UPDATE {SCHEMA}.servers SET views = views + 1 WHERE id = %s", (server_id,))
    conn.commit()
    cur.close(); conn.close()

def toggle_favorite(user_id, server_id):
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute(f"SELECT id FROM {SCHEMA}.favorites WHERE user_id = %s AND server_id = %s", (user_id, server_id))
    existing = cur.fetchone()
    if existing:
        cur.execute(f"DELETE FROM {SCHEMA}.favorites WHERE user_id = %s AND server_id = %s", (user_id, server_id))
        added = False
    else:
        cur.execute(f"INSERT INTO {SCHEMA}.favorites (user_id, server_id) VALUES (%s, %s)", (user_id, server_id))
        added = True
    conn.commit()
    cur.close(); conn.close()
    return added

def get_favorites(user_id):
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute(
        f"""SELECT s.id, s.ip, s.version, s.description, s.hosting, s.views,
                   CASE WHEN s.rating_count > 0 THEN ROUND(s.rating_sum::numeric / s.rating_count, 1) ELSE NULL END
            FROM {SCHEMA}.favorites f
            JOIN {SCHEMA}.servers s ON s.id = f.server_id
            WHERE f.user_id = %s ORDER BY f.added_at DESC""",
        (user_id,)
    )
    rows = cur.fetchall()
    cur.close(); conn.close()
    return rows

def get_user_favorite_ids(user_id):
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute(f"SELECT server_id FROM {SCHEMA}.favorites WHERE user_id = %s", (user_id,))
    ids = {row[0] for row in cur.fetchall()}
    cur.close(); conn.close()
    return ids

def cast_vote(user_id, server_id, score):
    """Голосует за сервер. Обновляет если уже голосовал на этой неделе. Возвращает (is_new, old_score)."""
    now = datetime.datetime.utcnow()
    week = int(now.strftime('%V'))
    year = now.year
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute(
        f"SELECT id, score FROM {SCHEMA}.votes WHERE user_id = %s AND server_id = %s AND week_number = %s AND year_number = %s",
        (user_id, server_id, week, year)
    )
    existing = cur.fetchone()
    if existing:
        old_score = existing[1]
        cur.execute(
            f"UPDATE {SCHEMA}.votes SET score = %s, voted_at = now() WHERE id = %s",
            (score, existing[0])
        )
        cur.execute(
            f"UPDATE {SCHEMA}.servers SET rating_sum = rating_sum - %s + %s WHERE id = %s",
            (old_score, score, server_id)
        )
        conn.commit()
        cur.close(); conn.close()
        return False, old_score
    else:
        cur.execute(
            f"INSERT INTO {SCHEMA}.votes (user_id, server_id, score, week_number, year_number) VALUES (%s, %s, %s, %s, %s)",
            (user_id, server_id, score, week, year)
        )
        cur.execute(
            f"UPDATE {SCHEMA}.servers SET rating_sum = rating_sum + %s, rating_count = rating_count + 1 WHERE id = %s",
            (score, server_id)
        )
        conn.commit()
        cur.close(); conn.close()
        return True, None

def get_user_vote_this_week(user_id, server_id):
    now = datetime.datetime.utcnow()
    week = int(now.strftime('%V'))
    year = now.year
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute(
        f"SELECT score FROM {SCHEMA}.votes WHERE user_id = %s AND server_id = %s AND week_number = %s AND year_number = %s",
        (user_id, server_id, week, year)
    )
    row = cur.fetchone()
    cur.close(); conn.close()
    return row[0] if row else None

def get_user_stats(user_id):
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute(f"SELECT COUNT(*) FROM {SCHEMA}.servers WHERE user_id = %s", (user_id,))
    servers_count = cur.fetchone()[0]
    cur.execute(f"SELECT COUNT(*) FROM {SCHEMA}.favorites WHERE user_id = %s", (user_id,))
    fav_count = cur.fetchone()[0]
    cur.execute(f"SELECT COUNT(*) FROM {SCHEMA}.votes WHERE user_id = %s", (user_id,))
    votes_given = cur.fetchone()[0]
    cur.execute(
        f"""SELECT COALESCE(SUM(s.views), 0), COALESCE(SUM(s.rating_count), 0)
            FROM {SCHEMA}.servers s WHERE s.user_id = %s""",
        (user_id,)
    )
    row = cur.fetchone()
    total_views = row[0] if row else 0
    total_votes_received = row[1] if row else 0
    cur.execute(
        f"""SELECT s.ip, ROUND(s.rating_sum::numeric / s.rating_count, 1), s.rating_count
            FROM {SCHEMA}.servers s
            WHERE s.user_id = %s AND s.rating_count > 0
            ORDER BY ROUND(s.rating_sum::numeric / s.rating_count, 1) DESC LIMIT 1""",
        (user_id,)
    )
    best = cur.fetchone()
    cur.close(); conn.close()
    return servers_count, fav_count, votes_given, total_views, total_votes_received, best

def get_server_for_vote(server_id):
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute(
        f"""SELECT id, ip, version, description, hosting,
                   CASE WHEN rating_count > 0 THEN ROUND(rating_sum::numeric / rating_count, 1) ELSE NULL END,
                   rating_count
            FROM {SCHEMA}.servers WHERE id = %s""",
        (server_id,)
    )
    row = cur.fetchone()
    cur.close(); conn.close()
    return row

# ─── Minecraft Server List Ping ───────────────────────────────────────────────

def get_mc_status(ip_port: str):
    """Получает онлайн-статус и количество игроков через протокол Minecraft 1.7+."""
    try:
        if ':' in ip_port:
            host, port = ip_port.rsplit(':', 1)
            port = int(port)
        else:
            host, port = ip_port, 25565

        sock = socket.create_connection((host, port), timeout=3)

        def pack_varint(val):
            result = b''
            while True:
                part = val & 0x7F
                val >>= 7
                if val:
                    part |= 0x80
                result += bytes([part])
                if not val:
                    break
            return result

        def read_varint(s):
            result, shift = 0, 0
            while True:
                b = s.recv(1)
                if not b:
                    return 0
                val = b[0]
                result |= (val & 0x7F) << shift
                if not (val & 0x80):
                    return result
                shift += 7

        host_encoded = host.encode('utf-8')
        handshake = (
            pack_varint(0x00) +
            pack_varint(47) +
            pack_varint(len(host_encoded)) +
            host_encoded +
            struct.pack('>H', port) +
            pack_varint(1)
        )
        sock.sendall(pack_varint(len(handshake)) + handshake)
        sock.sendall(pack_varint(1) + pack_varint(0x00))

        read_varint(sock)
        read_varint(sock)
        length = read_varint(sock)
        data = b''
        while len(data) < length:
            chunk = sock.recv(length - len(data))
            if not chunk:
                break
            data += chunk
        sock.close()

        response = json.loads(data)
        players = response.get('players', {})
        return True, players.get('online', 0), players.get('max', 0)
    except Exception:
        return False, 0, 0

# ─── Helpers ──────────────────────────────────────────────────────────────────

def stars_bar(rating):
    """Визуальная полоска рейтинга: ★★★☆☆ 4.2"""
    if rating is None:
        return "☆ нет оценок"
    filled = round(float(rating))
    bar = "★" * filled + "☆" * (5 - filled)
    return f"{bar} {rating}"

def days_until_monday():
    today = datetime.datetime.utcnow().weekday()
    return 7 - today

# ─── UI builders ──────────────────────────────────────────────────────────────

def build_servers_page(servers, page, total):
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    lines = [f"<b>🌐 Список серверов</b> (стр. {page + 1}/{total_pages}):\n"]
    for i, (ip, version, uname, added_at, description, hosting, views, rating) in enumerate(servers, page * PAGE_SIZE + 1):
        online, pl_on, pl_max = get_mc_status(ip)
        date_str = added_at.strftime('%d.%m.%Y') if added_at else ''
        status = f"🟢 {pl_on}/{pl_max}" if online else "🔴"
        line = f"{i}. <code>{ip}</code>"
        if hosting:
            line += f" <i>[{hosting}]</i>"
        line += f"\nВерсия: {version} | {status} | 👁 {views}"
        line += f"\n{stars_bar(rating)} | @{uname} {date_str}"
        if description:
            line += f"\n💬 {description}"
        lines.append(line)

    nav_buttons = []
    if page > 0:
        nav_buttons.append({"text": "◀️ Назад", "callback_data": f"page_{page - 1}"})
    if (page + 1) * PAGE_SIZE < total:
        nav_buttons.append({"text": "Вперёд ▶️", "callback_data": f"page_{page + 1}"})

    markup = json.dumps({"inline_keyboard": [nav_buttons]}) if nav_buttons else None
    return "\n".join(lines), markup

def build_top_servers(servers, user_id):
    fav_ids = get_user_favorite_ids(user_id)
    lines = ["<b>🏆 Топ серверов по просмотрам:</b>\n"]
    medals = ["🥇", "🥈", "🥉"]
    inline_buttons = []
    for i, (sid, ip, version, uname, description, hosting, views, rating, r_count) in enumerate(servers):
        online, pl_on, pl_max = get_mc_status(ip)
        medal = medals[i] if i < 3 else f"{i+1}."
        status = f"🟢 {pl_on}/{pl_max}" if online else "🔴"
        star = "⭐" if sid in fav_ids else ""
        line = f"{medal} {star}<code>{ip}</code>"
        if hosting:
            line += f" <i>[{hosting}]</i>"
        line += f"\nВерсия: {version} | {status} | 👁 {views}"
        line += f"\n{stars_bar(rating)}"
        if description:
            line += f"\n💬 {description}"
        lines.append(line)

        row = []
        fav_label = "★ Убрать" if sid in fav_ids else "☆ В избранное"
        row.append({"text": fav_label, "callback_data": f"fav_{sid}"})
        row.append({"text": "🗳️ Оценить", "callback_data": f"vote_{sid}"})
        inline_buttons.append(row)

    markup = json.dumps({"inline_keyboard": inline_buttons})
    return "\n".join(lines), markup

def build_vote_keyboard(server_id):
    buttons = [[
        {"text": f"{score} {'⭐' * score}", "callback_data": f"score_{server_id}_{score}"}
        for score in range(1, 6)
    ]]
    return json.dumps({"inline_keyboard": buttons})

def build_favorites(servers, user_id):
    if not servers:
        return "У вас нет избранных серверов.\nДобавляйте серверы из раздела 🏆 Топ!", None
    lines = ["<b>⭐ Избранные серверы:</b>\n"]
    inline_buttons = []
    for sid, ip, version, description, hosting, views, rating in servers:
        online, pl_on, pl_max = get_mc_status(ip)
        status = f"🟢 {pl_on}/{pl_max}" if online else "🔴"
        line = f"⭐ <code>{ip}</code>"
        if hosting:
            line += f" <i>[{hosting}]</i>"
        line += f"\nВерсия: {version} | {status} | 👁 {views}"
        line += f"\n{stars_bar(rating)}"
        if description:
            line += f"\n💬 {description}"
        lines.append(line)
        inline_buttons.append([
            {"text": "★ Убрать из избранного", "callback_data": f"fav_{sid}"},
            {"text": "🗳️ Оценить", "callback_data": f"vote_{sid}"}
        ])
    markup = json.dumps({"inline_keyboard": inline_buttons})
    return "\n".join(lines), markup

def build_my_servers(servers):
    lines = ["<b>📋 Мои серверы:</b>\n"]
    buttons = []
    for i, (sid, ip, version, description, hosting, rating, r_count) in enumerate(servers, 1):
        line = f"{i}. <code>{ip}</code>"
        if hosting:
            line += f" <i>[{hosting}]</i>"
        line += f"\nВерсия: {version} | {stars_bar(rating)} ({r_count} голосов)"
        if description:
            line += f"\n💬 {description}"
        lines.append(line)
        buttons.append([{"text": f"❌ Удалить {ip}", "callback_data": f"delete_{sid}"}])
    markup = json.dumps({"inline_keyboard": buttons})
    return "\n".join(lines), markup

def build_edit_picker(servers):
    lines = ["<b>✏️ Выберите сервер для изменения описания:</b>\n"]
    buttons = []
    for i, (sid, ip, version, description, hosting, rating, r_count) in enumerate(servers, 1):
        lines.append(f"{i}. <code>{ip}</code>")
        buttons.append([{"text": f"✏️ {ip}", "callback_data": f"edit_{sid}"}])
    markup = json.dumps({"inline_keyboard": buttons})
    return "\n".join(lines), markup

def build_stats(user_id):
    servers_count, fav_count, votes_given, total_views, total_votes_received, best = get_user_stats(user_id)
    lines = ["<b>📊 Твоя статистика:</b>\n"]
    lines.append(f"🖥️ Добавлено серверов: <b>{servers_count}</b>")
    lines.append(f"⭐ В избранном (у тебя): <b>{fav_count}</b>")
    lines.append(f"🗳️ Оценок отдано: <b>{votes_given}</b>")
    lines.append(f"👁️ Просмотров твоих серверов: <b>{total_views}</b>")
    lines.append(f"📥 Оценок получено твоими серверами: <b>{total_votes_received}</b>")
    if best:
        lines.append(f"\n🏅 Лучший сервер: <code>{best[0]}</code>\n   {stars_bar(best[1])} ({best[2]} голосов)")
    lines.append(f"\n<i>Голоса обновляются каждую неделю. До следующего сброса: {days_until_monday()} дн.</i>")
    return "\n".join(lines)

# ─── Handler ──────────────────────────────────────────────────────────────────

def handler(event: dict, context) -> dict:
    """Telegram-бот каталог Minecraft-серверов: пинг, онлайн игроков, топ, избранное, пагинация, еженедельные оценки."""
    if event.get('httpMethod') == 'OPTIONS':
        return {'statusCode': 200, 'headers': {'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Methods': 'GET, POST, OPTIONS', 'Access-Control-Allow-Headers': 'Content-Type'}, 'body': ''}

    token = os.environ.get('TG_BOT_TOKEN')
    if not token:
        return {'statusCode': 500, 'headers': {'Access-Control-Allow-Origin': '*'}, 'body': json.dumps({'error': 'Token not set'})}

    body = json.loads(event.get('body', '{}'))

    # ── Callback-кнопки ───────────────────────────────────────────────────────
    callback_query = body.get('callback_query')
    if callback_query:
        cb_id = callback_query['id']
        cb_data = callback_query.get('data', '')
        cb_chat_id = callback_query['message']['chat']['id']
        cb_user_id = callback_query['from']['id']

        if cb_data.startswith('page_'):
            page = int(cb_data.split('_')[1])
            servers, total = get_servers_page(page)
            text, markup = build_servers_page(servers, page, total)
            answer_callback(token, cb_id)
            send_message(token, cb_chat_id, text, markup)

        elif cb_data.startswith('delete_'):
            server_id = int(cb_data.split('_')[1])
            ok = delete_server(server_id, cb_user_id)
            if ok:
                answer_callback(token, cb_id, "Сервер удалён ✅")
                servers = get_user_servers(cb_user_id)
                if not servers:
                    send_message(token, cb_chat_id, "У вас больше нет добавленных серверов.", get_main_keyboard())
                else:
                    text, markup = build_my_servers(servers)
                    send_message(token, cb_chat_id, text, markup)
            else:
                answer_callback(token, cb_id, "Не удалось удалить")

        elif cb_data.startswith('edit_'):
            server_id = int(cb_data.split('_')[1])
            answer_callback(token, cb_id)
            user_states[cb_user_id] = {'step': 'await_new_desc', 'server_id': server_id}
            send_message(token, cb_chat_id, "Введите новое описание (или <b>-</b> чтобы убрать):")

        elif cb_data.startswith('fav_'):
            server_id = int(cb_data.split('_')[1])
            increment_views(server_id)
            added = toggle_favorite(cb_user_id, server_id)
            label = "⭐ Добавлено в избранное!" if added else "Убрано из избранного"
            answer_callback(token, cb_id, label)

        elif cb_data.startswith('vote_'):
            server_id = int(cb_data.split('_')[1])
            answer_callback(token, cb_id)
            srv = get_server_for_vote(server_id)
            if not srv:
                send_message(token, cb_chat_id, "Сервер не найден.")
            else:
                sid, ip, version, description, hosting, rating, r_count = srv
                existing_score = get_user_vote_this_week(cb_user_id, server_id)
                note = f"\nТвоя текущая оценка: {'⭐' * existing_score} ({existing_score})" if existing_score else ""
                send_message(
                    token, cb_chat_id,
                    f"<b>Оцени сервер</b> <code>{ip}</code>\n"
                    f"{stars_bar(rating)} ({r_count} голосов){note}\n\n"
                    f"Выбери оценку (голос действует 1 неделю):",
                    build_vote_keyboard(server_id)
                )

        elif cb_data.startswith('score_'):
            parts = cb_data.split('_')
            server_id = int(parts[1])
            score = int(parts[2])
            srv = get_server_for_vote(server_id)
            if srv and srv[0] == cb_user_id:
                answer_callback(token, cb_id, "Нельзя голосовать за свой сервер 😏")
            else:
                is_new, old_score = cast_vote(cb_user_id, server_id, score)
                label_score = SCORE_LABELS.get(score, str(score))
                if is_new:
                    answer_callback(token, cb_id, f"{label_score} — голос принят!")
                    msg = f"✅ Ты оценил сервер на {'⭐' * score} ({score}/5)\n<i>Можешь изменить оценку до конца недели.</i>"
                else:
                    answer_callback(token, cb_id, f"Оценка обновлена: {score}/5")
                    msg = f"🔄 Оценка обновлена: {'⭐' * score} ({score}/5)"
                send_message(token, cb_chat_id, msg)

        return {'statusCode': 200, 'headers': {'Access-Control-Allow-Origin': '*'}, 'body': ''}

    # ── Обычные сообщения ─────────────────────────────────────────────────────
    message = body.get('message', {})
    if not message:
        return {'statusCode': 200, 'headers': {'Access-Control-Allow-Origin': '*'}, 'body': ''}

    chat_id = message['chat']['id']
    user_id = message['from']['id']
    username = message['from'].get('username') or message['from'].get('first_name', '')
    text = message.get('text', '').strip()
    state = user_states.get(user_id)

    if text == '/start':
        user_states.pop(user_id, None)
        send_message(token, chat_id,
            "⛏️ <b>Добро пожаловать в каталог Minecraft-серверов!</b>\n\n"
            "Добавляй свой сервер, ищи новый, сохраняй в избранное и голосуй за лучшие!\n\n"
            "Выбери действие:",
            get_main_keyboard()
        )

    elif text == '➕ ДОБАВИТЬ СЕРВЕР':
        user_states[user_id] = {'step': 'await_hosting'}
        send_message(token, chat_id,
            "🖥️ <b>На каком хостинге держится твой сервер?</b>\n\n"
            "<i>Например: Aternos, Minehut, своя VPS, домашний ПК...</i>"
        )

    elif text == '🌐 СЕРВЕРЫ':
        servers, total = get_servers_page(0)
        if not servers:
            send_message(token, chat_id, "Серверов пока нет. Будьте первым — нажмите «➕ ДОБАВИТЬ СЕРВЕР».", get_main_keyboard())
        else:
            msg, markup = build_servers_page(servers, 0, total)
            send_message(token, chat_id, msg, markup)

    elif text == '🏆 ТОП СЕРВЕРОВ':
        servers = get_top_servers()
        if not servers:
            send_message(token, chat_id, "Серверов пока нет.", get_main_keyboard())
        else:
            msg, markup = build_top_servers(servers, user_id)
            send_message(token, chat_id, msg, markup)

    elif text == '⭐ ИЗБРАННОЕ':
        servers = get_favorites(user_id)
        msg, markup = build_favorites(servers, user_id)
        send_message(token, chat_id, msg, markup if markup else get_main_keyboard())

    elif text == '📋 МОИ СЕРВЕРЫ':
        servers = get_user_servers(user_id)
        if not servers:
            send_message(token, chat_id, "Вы ещё не добавляли серверов.", get_main_keyboard())
        else:
            msg, markup = build_my_servers(servers)
            send_message(token, chat_id, msg, markup)

    elif text == '✏️ ИЗМЕНИТЬ ОПИСАНИЕ':
        servers = get_user_servers(user_id)
        if not servers:
            send_message(token, chat_id, "У вас нет добавленных серверов.", get_main_keyboard())
        else:
            msg, markup = build_edit_picker(servers)
            send_message(token, chat_id, msg, markup)

    elif text == '📊 МОЯ СТАТИСТИКА':
        msg = build_stats(user_id)
        send_message(token, chat_id, msg, get_main_keyboard())

    # ── Шаги добавления ───────────────────────────────────────────────────────
    elif state and state.get('step') == 'await_hosting':
        user_states[user_id] = {'step': 'await_ip', 'hosting': text}
        send_message(token, chat_id, f"Хостинг: <b>{text}</b> ✅\n\nТеперь введите <b>IP-адрес</b> сервера:")

    elif state and state.get('step') == 'await_ip':
        user_states[user_id] = {**state, 'step': 'await_version', 'ip': text}
        send_message(token, chat_id, f"IP принят: <code>{text}</code> ✅\n\nВведите <b>версию</b> сервера (например: 1.20.4):")

    elif state and state.get('step') == 'await_version':
        user_states[user_id] = {**state, 'step': 'await_description', 'version': text}
        send_message(token, chat_id, f"Версия: <b>{text}</b> ✅\n\nВведите <b>описание</b> сервера (или <b>-</b> чтобы пропустить):")

    elif state and state.get('step') == 'await_description':
        ip = state['ip']
        version = state['version']
        hosting = state.get('hosting')
        description = None if text == '-' else text
        add_server(user_id, username, hosting, ip, version, description)
        user_states.pop(user_id, None)
        online, pl_on, pl_max = get_mc_status(ip)
        status_line = f"🟢 Онлайн ({pl_on}/{pl_max} игроков)" if online else "🔴 Сейчас недоступен"
        desc_line = f"\n💬 <b>Описание:</b> {description}" if description else ""
        hosting_line = f"\n🖥️ <b>Хостинг:</b> {hosting}" if hosting else ""
        phrase = random.choice(LAUNCH_PHRASES)
        send_message(token, chat_id,
            f"{phrase}\n\n"
            f"<b>IP:</b> <code>{ip}</code>\n"
            f"<b>Версия:</b> {version}"
            f"{hosting_line}{desc_line}\n"
            f"<b>Статус:</b> {status_line}",
            get_main_keyboard()
        )

    # ── Редактирование описания ────────────────────────────────────────────────
    elif state and state.get('step') == 'await_new_desc':
        server_id = state['server_id']
        new_desc = None if text == '-' else text
        ok = update_description(server_id, user_id, new_desc)
        user_states.pop(user_id, None)
        if ok:
            send_message(token, chat_id, "✅ Описание обновлено!", get_main_keyboard())
        else:
            send_message(token, chat_id, "Не удалось обновить — возможно, сервер не ваш.", get_main_keyboard())

    else:
        send_message(token, chat_id, "Используйте кнопки меню.", get_main_keyboard())

    return {'statusCode': 200, 'headers': {'Access-Control-Allow-Origin': '*'}, 'body': ''}
