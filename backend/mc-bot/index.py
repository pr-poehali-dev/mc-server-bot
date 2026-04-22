import json
import os
import socket
import psycopg2
import urllib.request

SCHEMA = os.environ.get('MAIN_DB_SCHEMA', 't_p38250381_mc_server_bot')
PAGE_SIZE = 5
user_states = {}

# ─── Telegram helpers ────────────────────────────────────────────────────────

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
            [{"text": "📋 МОИ СЕРВЕРЫ"}, {"text": "✏️ ИЗМЕНИТЬ ОПИСАНИЕ"}]
        ],
        "resize_keyboard": True
    })

# ─── DB helpers ───────────────────────────────────────────────────────────────

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
        f"SELECT ip, version, username, added_at, description, hosting FROM {SCHEMA}.servers ORDER BY added_at DESC LIMIT %s OFFSET %s",
        (PAGE_SIZE, offset)
    )
    rows = cur.fetchall()
    cur.execute(f"SELECT COUNT(*) FROM {SCHEMA}.servers")
    total = cur.fetchone()[0]
    cur.close(); conn.close()
    return rows, total

def get_user_servers(user_id):
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute(
        f"SELECT id, ip, version, description, hosting FROM {SCHEMA}.servers WHERE user_id = %s ORDER BY added_at DESC",
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

# ─── Ping ─────────────────────────────────────────────────────────────────────

def ping_server(ip_port: str) -> bool:
    """Проверяет доступность сервера по TCP (порт 25565 по умолчанию)."""
    try:
        if ':' in ip_port:
            host, port = ip_port.rsplit(':', 1)
            port = int(port)
        else:
            host, port = ip_port, 25565
        sock = socket.create_connection((host, port), timeout=3)
        sock.close()
        return True
    except Exception:
        return False

# ─── UI builders ──────────────────────────────────────────────────────────────

def build_servers_page(servers, page, total):
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    lines = [f"<b>🌐 Список серверов</b> (стр. {page + 1}/{total_pages}):\n"]
    for i, (ip, version, uname, added_at, description, hosting) in enumerate(servers, page * PAGE_SIZE + 1):
        date_str = added_at.strftime('%d.%m.%Y') if added_at else ''
        status = "🟢" if ping_server(ip) else "🔴"
        line = f"{status} {i}. <code>{ip}</code>"
        if hosting:
            line += f" [{hosting}]"
        line += f"\nВерсия: {version} | @{uname} | {date_str}"
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

def build_my_servers(servers):
    lines = ["<b>📋 Мои серверы:</b>\n"]
    buttons = []
    for i, (sid, ip, version, description, hosting) in enumerate(servers, 1):
        line = f"{i}. <code>{ip}</code>"
        if hosting:
            line += f" [{hosting}]"
        line += f"\nВерсия: {version}"
        if description:
            line += f"\n💬 {description}"
        lines.append(line)
        buttons.append([{"text": f"❌ Удалить {ip}", "callback_data": f"delete_{sid}"}])
    markup = json.dumps({"inline_keyboard": buttons})
    return "\n".join(lines), markup

def build_edit_picker(servers):
    lines = ["<b>✏️ Выберите сервер для изменения описания:</b>\n"]
    buttons = []
    for i, (sid, ip, version, description, hosting) in enumerate(servers, 1):
        lines.append(f"{i}. <code>{ip}</code>")
        buttons.append([{"text": f"✏️ {ip}", "callback_data": f"edit_{sid}"}])
    markup = json.dumps({"inline_keyboard": buttons})
    return "\n".join(lines), markup

# ─── Handler ──────────────────────────────────────────────────────────────────

def handler(event: dict, context) -> dict:
    """Telegram-бот для пиара серверов Minecraft с пагинацией, хостингом, пингом и редактированием."""
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
            send_message(token, cb_chat_id, "Введите новое описание для сервера (или <b>-</b> чтобы убрать описание):")

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
            "Здесь ты можешь добавить свой сервер или найти новый.\n"
            "Выбери действие:",
            get_main_keyboard()
        )

    elif text == '➕ ДОБАВИТЬ СЕРВЕР':
        user_states[user_id] = {'step': 'await_hosting'}
        send_message(token, chat_id,
            "🖥️ На каком хостинге держится твой сервер?\n\n"
            "<i>Например: Aternos, Minehut, своя VPS, домашний ПК и т.д.</i>"
        )

    elif text == '🌐 СЕРВЕРЫ':
        servers, total = get_servers_page(0)
        if not servers:
            send_message(token, chat_id, "Серверов пока нет. Будьте первым — нажмите «➕ ДОБАВИТЬ СЕРВЕР».", get_main_keyboard())
        else:
            msg, markup = build_servers_page(servers, 0, total)
            send_message(token, chat_id, msg, markup)

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

    # ── Шаги добавления сервера ───────────────────────────────────────────────
    elif state and state.get('step') == 'await_hosting':
        user_states[user_id] = {'step': 'await_ip', 'hosting': text}
        send_message(token, chat_id, f"Хостинг: <b>{text}</b> ✅\n\nТеперь введите <b>IP-адрес</b> сервера:")

    elif state and state.get('step') == 'await_ip':
        user_states[user_id] = {**state, 'step': 'await_version', 'ip': text}
        send_message(token, chat_id, f"IP принят: <code>{text}</code>\n\nВведите <b>версию</b> сервера (например: 1.20.4):")

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
        online = "🟢 Онлайн" if ping_server(ip) else "🔴 Недоступен"
        desc_line = f"\n💬 <b>Описание:</b> {description}" if description else ""
        hosting_line = f"\n🖥️ <b>Хостинг:</b> {hosting}" if hosting else ""
        send_message(token, chat_id,
            f"✅ Сервер успешно добавлен!\n\n"
            f"<b>IP:</b> <code>{ip}</code>\n"
            f"<b>Версия:</b> {version}"
            f"{hosting_line}{desc_line}\n"
            f"<b>Статус:</b> {online}",
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
