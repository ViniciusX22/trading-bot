from telethon import TelegramClient
from dotenv import load_dotenv
from os import getenv
import re
from datetime import timedelta
from time import localtime
from debug import log

load_dotenv()

api_id = getenv('TELEGRAM_API_ID')
api_hash = getenv('TELEGRAM_API_HASH')
client = TelegramClient('iqbot', api_id, api_hash)

CHANNELS = [
    {'name': 'CANAL - Trader Equipe Brasil',
        'pattern': '.*FREE - Trader Equipe Brasil.*'},
    {'name': '📊 Trader Milionário Oficial | Sharkão',
        'pattern': '.*SINALZINHO GRATUITO.*'}
]


def get_message_options(message):
    action_map = {'COMPRA': 'call', 'VENDA': 'put'}
    start_time = None
    duration = None
    pair = None
    action = None
    timeframe = None

    try:
        start_time = re.search('⏰ (\d):(\d)h 🇧🇷', message)
        if start_time:
            duration = timedelta(hours=int(start_time.group(0)), minutes=int(start_time.group(
                1))) - timedelta(hours=localtime().tm_hour, minutes=localtime().tm_min, seconds=localtime().tm_sec)
        else:
            start_time = re.search('(\d{2}):(\d{2})', message)
            duration = timedelta(hours=int(start_time.group(1)), minutes=int(start_time.group(
                2))) - timedelta(hours=localtime().tm_hour, minutes=localtime().tm_min, seconds=localtime().tm_sec)

        pair = re.search('Moeda: (\w{6}|\w{3}/\w{3})\n', message)
        if not pair:
            pair = re.search('(\w{6});', message)

        if not pair:
            pair = re.search('(\w{3}/\w{3})\s?', message)

        pair = pair.group(1).replace('/', '')

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
            timeframe = re.search('Expiração M(\d)', message)
        if timeframe:
            timeframe = int(timeframe.group(1))
        else:
            timeframe = 5

    except Exception as e:
        log(f'Error while parsing message: {e}', False)
        return None

    if duration.seconds / 3600 > 9:
        return None

    log(
        f'Parsed pair, action, start time and timeframe: {(pair, action, duration.seconds, timeframe)}', False)

    return (pair, action, duration.seconds, timeframe)


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
