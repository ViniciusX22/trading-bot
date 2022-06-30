from telethon import events
from telegram import get_message_options, get_message_options_list, client, CHANNELS
from iqoption import IQBot
from threading import Timer
from debug import watch_threads, log
from utils import fmt_order, Timeout
from os import getenv
from termcolor import colored


TEST_MODE = getenv('TEST_MODE', 'False') == 'True'
DISCONNECTION_TIMEOUT = int(getenv('DISCONNECTION_TIMEOUT', 60)) * 60

bot = IQBot(stop_callback=lambda _: client.disconnect())
parsed_orders = {}

target_chat = []
patterns = ['.*']
if TEST_MODE:
    target_chat = 'me'
else:
    patterns = []
    for chat in CHANNELS:
        target_chat.append(chat['name'])
        patterns.append(chat['pattern'])


def stop_client():
    client.disconnect()


# creates a timeout to disconnect the client when no orders are received in the specified interval
disconnect_timeout = Timeout(
    max_interval=DISCONNECTION_TIMEOUT, finish=stop_client)


# @client.on(events.NewMessage(chats=target_chat, pattern='.*ATENÇÃO.*'))
@client.on(events.NewMessage(chats=target_chat, pattern='|'.join(patterns)))
async def new_option_message(event):
    def run_order(pair, action, timeframe):
        try:
            del parsed_orders[fmt_order(pair, action, 0, timeframe)]
        except:
            pass
        bot.execute_option(pair, action, expires_in=timeframe)

    options = get_message_options(event.raw_text)

    if options:
        (pair, action, start_in, timeframe) = options
        order_format = fmt_order(pair, action, start_in, timeframe)
        if not order_format in parsed_orders:
            parsed_orders[order_format] = True
            # disconnect_timeout.reset()
            t = Timer(start_in, lambda: run_order(pair, action, timeframe))
            t.name = 'Order ' + order_format
            t.start()
        else:
            log(f'Order {order_format} already queued', False)


@client.on(events.NewMessage(chats=target_chat, pattern=r'OTC - \d{2}/(\w{3}|\d{2})/\d{4}'))
async def new_otc_message(event):
    options_list = get_message_options_list(event.raw_text)

    if options_list:
        for options in options_list:
            (pair, action, start_in) = options
            Timer(start_in, lambda: bot.execute_option(pair, action)).start()


def run():
    if TEST_MODE:
        log(colored(' TEST MODE ', 'grey', 'on_yellow'))
    with client:
        client.run_until_disconnected()


if __name__ == "__main__":
    watch_threads()
    # disconnect_timeout.start()
    # try:
    run()
    # except Exception:
    # disconnect_timeout.cancel()
