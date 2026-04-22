import json
import os
import psycopg2
import urllib.request
import urllib.parse

SCHEMA = os.environ.get('MAIN_DB_SCHEMA', 't_p38250381_mc_server_bot')
user_states = {}

def send_message(token, chat_id, text, reply_markup=None):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    }
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
            [{"text": "ДОБАВИТЬ СЕРВЕР"}, {"text": "СЕРВЕРЫ"}],
            [{"text": "МОИ СЕРВЕРЫ"}]
        ],
        "resize_keyboard": True
    })

def get_db_conn():
    return psycopg2.connect(os.environ['DATABASE_URL'])

def add_server(user_id, username, ip, version):
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute(
        f"INSERT INTO {SCHEMA}.servers (user_id, username, ip, version) VALUES (%s, %s, %s, %s)",
        (user_id, username, ip, version)
    )
    conn.commit()
    cur.close()
    conn.close()

def get_servers():
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute(f"SELECT ip, version, username, added_at FROM {SCHEMA}.servers ORDER BY added_at DESC LIMIT 50")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows

def get_user_servers(user_id):
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute(f"SELECT id, ip, version FROM {SCHEMA}.servers WHERE user_id = %s ORDER BY added_at DESC", (user_id,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows

def delete_server(server_id, user_id):
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute(f"DELETE FROM {SCHEMA}.servers WHERE id = %s AND user_id = %s", (server_id, user_id))
    deleted = cur.rowcount
    conn.commit()
    cur.close()
    conn.close()
    return deleted > 0

def handler(event: dict, context) -> dict:
    """Telegram-бот для пиара серверов Minecraft."""
    if event.get('httpMethod') == 'OPTIONS':
        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type'
            },
            'body': ''
        }

    token = os.environ.get('TG_BOT_TOKEN')
    if not token:
        return {'statusCode': 500, 'headers': {'Access-Control-Allow-Origin': '*'}, 'body': json.dumps({'error': 'Token not set'})}

    body = json.loads(event.get('body', '{}'))

    # Обработка нажатия инлайн-кнопки удаления
    callback_query = body.get('callback_query')
    if callback_query:
        cb_id = callback_query['id']
        cb_data = callback_query.get('data', '')
        cb_chat_id = callback_query['message']['chat']['id']
        cb_user_id = callback_query['from']['id']

        if cb_data.startswith('delete_'):
            server_id = int(cb_data.split('_')[1])
            ok = delete_server(server_id, cb_user_id)
            if ok:
                answer_callback(token, cb_id, "Сервер удалён")
                # Показываем обновлённый список
                servers = get_user_servers(cb_user_id)
                if not servers:
                    send_message(token, cb_chat_id, "У вас больше нет добавленных серверов.", get_main_keyboard())
                else:
                    inline_buttons = []
                    lines = ["<b>Мои серверы:</b>\n"]
                    for i, (sid, ip, version) in enumerate(servers, 1):
                        lines.append(f"{i}. <code>{ip}</code>\nВерсия: {version}")
                        inline_buttons.append([{"text": f"❌ Удалить {ip}", "callback_data": f"delete_{sid}"}])
                    markup = json.dumps({"inline_keyboard": inline_buttons})
                    send_message(token, cb_chat_id, "\n".join(lines), markup)
            else:
                answer_callback(token, cb_id, "Не удалось удалить")

        return {'statusCode': 200, 'headers': {'Access-Control-Allow-Origin': '*'}, 'body': ''}

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
            "<b>Добро пожаловать в каталог Minecraft-серверов.</b>\n\nВыберите действие:",
            get_main_keyboard()
        )

    elif text == 'ДОБАВИТЬ СЕРВЕР':
        user_states[user_id] = {'step': 'await_ip'}
        send_message(token, chat_id, "Введите IP-адрес сервера:")

    elif text == 'СЕРВЕРЫ':
        servers = get_servers()
        if not servers:
            send_message(token, chat_id, "Серверов пока нет. Будьте первым — нажмите «ДОБАВИТЬ СЕРВЕР».", get_main_keyboard())
        else:
            lines = ["<b>Список серверов:</b>\n"]
            for i, (ip, version, uname, added_at) in enumerate(servers, 1):
                date_str = added_at.strftime('%d.%m.%Y') if added_at else ''
                lines.append(f"{i}. <code>{ip}</code>\nВерсия: {version} | Добавил: @{uname} | {date_str}")
            send_message(token, chat_id, "\n".join(lines), get_main_keyboard())

    elif text == 'МОИ СЕРВЕРЫ':
        servers = get_user_servers(user_id)
        if not servers:
            send_message(token, chat_id, "Вы ещё не добавляли серверов.", get_main_keyboard())
        else:
            inline_buttons = []
            lines = ["<b>Мои серверы:</b>\n"]
            for i, (sid, ip, version) in enumerate(servers, 1):
                lines.append(f"{i}. <code>{ip}</code>\nВерсия: {version}")
                inline_buttons.append([{"text": f"❌ Удалить {ip}", "callback_data": f"delete_{sid}"}])
            markup = json.dumps({"inline_keyboard": inline_buttons})
            send_message(token, chat_id, "\n".join(lines), markup)

    elif state and state.get('step') == 'await_ip':
        user_states[user_id] = {'step': 'await_version', 'ip': text}
        send_message(token, chat_id, f"IP принят: <code>{text}</code>\n\nТеперь введите версию сервера (например: 1.20.4):")

    elif state and state.get('step') == 'await_version':
        ip = state['ip']
        version = text
        add_server(user_id, username, ip, version)
        user_states.pop(user_id, None)
        send_message(token, chat_id,
            f"Сервер успешно добавлен.\n\n<b>IP:</b> <code>{ip}</code>\n<b>Версия:</b> {version}",
            get_main_keyboard()
        )

    else:
        send_message(token, chat_id, "Используйте кнопки меню.", get_main_keyboard())

    return {'statusCode': 200, 'headers': {'Access-Control-Allow-Origin': '*'}, 'body': ''}
