from threading import Timer, enumerate, main_thread
from termcolor import colored
from utils import get_time


def watch_threads(interval=300):
    log(f'Currently running threads: {enumerate()}', False)
    if main_thread().is_alive():
      t = Timer(interval, lambda: watch_threads(interval))
      t.name = 'Watcher'
      t.daemon = True
      t.start()


def log(message, live=True):
    timestamp = get_time()
    raw_text = f'{timestamp}: {message}'

    if live:
        print_text = raw_text
        if 'WIN' in print_text:
            print_text = print_text.replace(
                'WIN', colored(' WIN ', 'grey', 'on_green'))
        elif 'LOSS' in print_text:
            print_text = print_text.replace(
                'LOSS', colored(' LOSS ', 'white', 'on_red'))

        print_text = print_text.replace(
            timestamp + ':', colored(f' {timestamp} ', 'grey', 'on_cyan'))
        print(print_text)

    with open('./log.txt', 'a') as f:
        f.write(raw_text + '\n')