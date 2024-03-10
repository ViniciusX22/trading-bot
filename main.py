from telethon import events
from telegram import get_message_options, run_command, client, CHANNELS
from trading import TradingBot
from debug import log
from utils import Timeout
from os import getenv
from asyncio import get_event_loop


TEST_MODE = getenv('TEST_MODE', 'False') == 'True'
DISCONNECTION_TIMEOUT = int(getenv('DISCONNECTION_TIMEOUT', 60)) * 60


def stop_client():
    client.disconnect()


bot = TradingBot(stop_callback=stop_client, loop=get_event_loop())

target_chat = []
patterns = ['.*']
if TEST_MODE:
    # if test mode, receives signals from "Saved messages" chat
    target_chat = 'me'
else:
    patterns = []
    for chat in CHANNELS:
        target_chat.append(chat['id'])
        patterns.append(chat['pattern'])


# creates a timeout to disconnect the client when no orders are received in the specified interval
disconnect_timeout = Timeout(
    max_interval=DISCONNECTION_TIMEOUT, finish=stop_client, loop=client.loop)


@client.on(events.NewMessage(chats=target_chat, pattern='|'.join(patterns)))
async def new_option_message(event):
    options = get_message_options(event.raw_text)

    if options:
        (pair, action, start_time, timeframe) = options
        disconnect_timeout.reset()
        bot.execute_option(pair, action, start_time, expires_in=timeframe)


# event for receiving commands for the bot through "Saved messages"
# syntax: bot:<command_name>
@client.on(events.NewMessage(chats=['me'], pattern=r'bot:.*'))
async def new_command(event):
    result = run_command(event.raw_text.split('bot:')[1])
    if result == 'STOP':
        await event.reply('Stopped')
        client.disconnect()
    elif result:
        await event.reply(result)


def run():
    if TEST_MODE:
        log('TEST MODE')
    with client:
        client.run_until_disconnected()
    bot.close()
    disconnect_timeout.cancel()


if __name__ == "__main__":
    if DISCONNECTION_TIMEOUT > 0:
        disconnect_timeout.start()
    try:
        run()
    except Exception as e:
        print('Unexpected crash:', e)
        bot.close()
        disconnect_timeout.cancel()
