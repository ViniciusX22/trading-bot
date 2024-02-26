from telethon.tl.types import PeerChannel
from telethon import TelegramClient
from dotenv import load_dotenv
from os import getenv
import re
from datetime import timedelta, datetime
from time import localtime
from debug import log

load_dotenv()

api_id = getenv('TELEGRAM_API_ID')
api_hash = getenv('TELEGRAM_API_HASH')
phone = getenv('TELEGRAM_PHONE')
password = getenv('TELEGRAM_PASSWORD')
client = TelegramClient('iqbot', api_id, api_hash).start(
    phone=phone,  password=password)

CHANNELS = [
    {'name': PeerChannel(channel_id=1756002871),  # Sinais VIP
        'pattern': '.*SINAL VIP.*'},
    {'name': PeerChannel(channel_id=1221176746),  # Sinais Blacklist
     'pattern': '.*SINAL BLACKLIST.*'},
    {'name': PeerChannel(channel_id=1366197983),  # Sinais Grátis
     'pattern': '.*SINALZINHO GRATUITO.*'}
]


def get_message_options(message):
    action_map = {'COMPRA': 'call', 'VENDA': 'put'}
    start_time = None
    pair = None
    action = None
    timeframe = None

    log(f'Message received: {message}', False)

    try:
        start_time = re.search('(\d{2}):(\d{2})', message)
        if start_time:
            start_time = f'{start_time.group(1)}:{start_time.group(2)}'

        pair = re.search('Moeda: (\w{6}|\w{3}/\w{3})\n', message)
        if not pair:
            pair = re.search('(\w{6});', message)

        if not pair:
            pair = re.search('(\w{3}/\w{3})\s?', message)

        if not pair:
            pair = re.search('\s(\w{6})-', message)

        if not pair:
            pair = re.search('\s(\w{6})\(', message)

        if not pair:
            pair = re.search('\s(\w{6})\s', message)

        pair = pair.group(1).replace('/', '')

        otc = re.search('(OTC)', message)
        otc = otc or re.search('-OTC', message)

        if otc:
            pair += '-OTC'

        action = re.search(';(COMPRA|VENDA)', message)
        if not action:
            action = re.search('Sinal - .(COMPRA|VENDA).\n', message)
        else:
            action = action_map[action.group(1)]

        if not action:
            action = re.search('PUT|CALL', message)
            action = action.group(0).lower()

        timeframe = re.search('Timeframe M(\d)', message)
        if not timeframe:
            timeframe = re.search('Expiração(?: M|: )(\d)', message)
        if timeframe:
            timeframe = int(timeframe.group(1))
        else:
            timeframe = 5

    except Exception as e:
        log(f'Error while parsing message: {e}', False)
        return None

    log(
        f'Parsed pair, action, start time and timeframe: {(pair, action, start_time, timeframe)}', False)

    return (pair, action, start_time, timeframe)


def get_message_options_list(message):
    options_list = []
    for line in message.split('\n'):
        start_time = None
        duration = None
        pair = None
        action = None

        try:
            start_time = re.search('(\d{2}):(\d{2})', line)
            duration = timedelta(hours=int(start_time.group(1)), minutes=int(start_time.group(
                2))) - timedelta(hours=localtime().tm_hour, minutes=localtime().tm_min, seconds=localtime().tm_sec)

            pair = re.search('(\w{6}|\w{3}/\w{3})', line)
            pair = pair.group(1).replace('/', '')

            action = re.search('(PUT|CALL)', line)
            action = action.group(1).lower()
        except Exception as e:
            continue

        if duration and duration.seconds / 3600 > 9:
            continue

        log(
            f'Parsed pair, action and start time: {(pair, action, duration.seconds)}', False)

        options_list.append((pair, action, duration.seconds))

    return options_list if len(options_list) > 0 else None


def run_command(command):
    commands = {
        'logs': logs,
        'stop': stop
    }

    args = command.split(' ')
    command = args[0]
    args = args[1:]

    return commands[command](*args) if command in commands else None


def logs(page=None):
    limit = 4096
    page = int(page) if page else 1
    with open(f'./log-{datetime.today().strftime("%d-%m-%Y")}.txt', 'r', encoding='utf-8') as f:
        content = f.read()
        if len(content) > limit:
            content = content[0 + limit * (page - 1):limit * page]
            if len(content) == limit:
                return content[:-3] + '...'
            else:
                return content
        else:
            return content


def stop():
    print('Stop command received')
    return 'STOP'
