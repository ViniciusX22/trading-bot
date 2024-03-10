from os import getenv
from dotenv import load_dotenv

load_dotenv()

color = False
try:
    from termcolor import colored
    color = True
except Exception:
    pass

""" 
Reads a signal history from a file and simulates the end
balance after every trade, taking into consideration possible
SOROS and GALE strategies
"""


BASE_ORDER = float(getenv('BASE_ORDER', 0.02))
GALE_RATE = float(getenv('GALE_RATE', 2.2))
PAYOUT = float(getenv('PAYOUT', 0.8))
MAX_GALES = int(getenv('MAX_GALES', 1))
SOROS_HOLDING = float(getenv('SOROS_HOLDING', 0.1))
MAX_SOROS = int(getenv('MAX_SOROS', 3))

balance = float(input("Balance ($1000): ") or 1000)
signals = input("Signals file (signals.txt): ") or "signals.txt"
orders = []
initial_balance = balance
soros_count = 0
soros_amount = None
soros_enabled = False


def parse_order(text):
    pair = text[:6]
    time = text[7:12]
    action = "CALL" if "COMPRA" in text else "PUT"
    result = "WIN" if "WIN" in text else "LOSS"
    gales = text[-2:].count('G')

    return (pair, time, action, result, gales)


with open("data/" + signals, "r") as f:
    grouped_signals = {}
    for line in f.readlines():
        line = line[:-1]
        (pair, time, action, result, gales) = parse_order(line)

        if time not in grouped_signals:
            grouped_signals[time] = []

        grouped_signals[time].append((pair, action, result, gales))

    for time in grouped_signals:
        signals_in_time = grouped_signals[time]
        last_soros_status = False
        amount = balance * BASE_ORDER if not soros_enabled else soros_amount

        for signal in signals_in_time:
            (pair, action, result, gales) = signal

            balance_now = balance

            if result == 'WIN':
                if gales == 0:
                    if soros_count < MAX_SOROS:
                        soros_enabled = True
                    else:
                        soros_enabled = False

                    balance += amount * PAYOUT
                elif gales == 1 and MAX_GALES >= 1 and not soros_enabled:
                    balance += -amount + amount * GALE_RATE * PAYOUT
                    soros_enabled = False if not last_soros_status else True
                elif gales == 2 and MAX_GALES >= 2 and not soros_enabled:
                    balance += -amount - amount * GALE_RATE + \
                        (amount * GALE_RATE ** 2) * PAYOUT
                    soros_enabled = False if not last_soros_status else True
                else:
                    result = 'LOSS'

            if result == 'LOSS':
                balance -= amount
                if gales == 0:
                    gales = 2
                if not soros_enabled:
                    if MAX_GALES >= 1:
                        balance -= amount * GALE_RATE
                    if MAX_GALES == 2:
                        balance -= amount * GALE_RATE ** 2
                else:
                    gales = 0
                soros_enabled = False if not last_soros_status else True

            orders.append({'pair': pair, 'time': time,
                           'action': action, 'result': result, 'amount': balance - balance_now, 'gales': min(gales, MAX_GALES)})
            last_soros_status = soros_enabled

        if soros_enabled:
            soros_amount = (amount + amount * PAYOUT) * (1 - SOROS_HOLDING)
            soros_count += 1
        else:
            soros_amount = None
            soros_count = 0

output = ""

for order in orders:
    output += f'{order["time"]}: {order["pair"]} - {order["action"]} ${"{:.2f}".format(order["amount"])} {order["result"]} {"G" * order["gales"]}\n'

output += "\nWINS: " + str(output.count('WIN'))
output += "\nLOSSES: " + str(output.count('LOSS'))

output += "\nInitial balance: {:.2f}".format(initial_balance)
output += "\nFinal balance: {:.2f}".format(balance)

with open('output.txt', 'w') as f:
    f.write(output)

if color:
    output = output.replace(
        ' WIN', ' ' + colored(f' WIN ', "grey", 'on_green'))
    output = output.replace(
        ' LOSS', ' ' + colored(f' LOSS ', "grey", 'on_red'))

print(output)
