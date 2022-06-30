from iqoptionapi.stable_api import IQ_Option
import time
from dotenv import load_dotenv
from os import getenv
from threading import Thread
from debug import log
from utils import fmt_order, get_time

load_dotenv()
EMAIL = getenv('IQOPTION_EMAIL')
PASSWORD = getenv('IQOPTION_PASSWORD')

BASE_ORDER = 0.01    # percentage of balance used by order
GALE_RATE = 2.2      # how much of order amount will be used for the gale
MAX_GALES = 1        # max amount of gales per order
SOROS_HOLDING = 0.1  # percentage of payout + base_order that will be kept in the balance
MAX_SOROS = 3        # max amount of soros per successful order
STOP_WIN = None      # profit needed to stop orders for the day
STOP_LOSS = None     # loss needed to stop orders for the day


class IQBot():
    positions = []
    next_soros_amount = None
    current_soros_count = 0
    pending_soros = False
    order_queue = []
    pending_orders = []
    stopped = False

    def __init__(self, stop_callback=None):
        print("Conecting...")
        self.api = IQ_Option(EMAIL, PASSWORD)
        _, reason = self.api.connect()

        if reason == "2FA":
            print('##### 2FA enabled #####')
            print("An sms has been sent with a code to your number")

            code_sms = input("Enter the code received: ")
            _, reason = self.api.connect_2fa(code_sms)

        self.initial_balance = self.api.get_balance()
        self.stop_callback = stop_callback

        print("Balance:", self.initial_balance)
        print("##############################")

    def execute_option(self, pair, action, amount=None, gale=False, pos_index=None, expires_in=5):
        if self.stopped:
            return False
        # filter pending orders which are 93% of the expiration time in
        # (e.g. 4m40s if expires in 5min)
        pending_orders = list(filter(lambda pos: not pos['closed'] and time.time(
        ) - pos["time"] >= pos["expires_in"] * 60 * 0.93, self.positions))

        if len(pending_orders) > 0 and not gale:
            log(f'Order queued: {pair}/{action.upper()}', False)
            # delay order excution to wait possible SOROS use
            def order(): return self.buy(
                amount, pair, action, gale, pos_index, expires_in)
            self.order_queue.append(order)
            return order
        else:
            id = self.buy(amount, pair, action, gale, pos_index, expires_in)
            return id

    def buy(self, amount, pair, action, gale=False, pos_index=None, expires_in=5):
        if not gale and self.next_soros_amount:
            amount = self.next_soros_amount
        else:
            amount = self.api.get_balance() * BASE_ORDER if not gale else amount

        check, id = self.api.buy(amount, pair, action, expires_in)
        if check:
            if not gale:
                self.positions.append({'id': id, 'pair': pair, 'action': action, 'gales': 0,
                                       'amount': amount, 'time': time.time(), 'expires_in': expires_in, 'closed': False})
            else:
                self.positions[pos_index]['amount'] = amount

            msg = ''
            if gale:
                msg += f'GALE {self.positions[pos_index]["gales"]}: '
            elif self.next_soros_amount:
                msg += f'SOROS {self.current_soros_count}: '
                self.pending_soros = False

            msg += f'{action.upper()} of ${"{:.2f}".format(amount)} {pair}'
            log(msg)

            index = len(self.positions) - 1 if not gale else pos_index

            Thread(target=lambda: self.check_gale_for(
                id, index), name=f'Gale Check ({fmt_order(pair, action, 0, expires_in)})').start()

            return id
        else:
            log(
                f'Failed to enter position: {pair}')

    def check_gale_for(self, id, index):
        order = self.api.check_binary_order(id)
        position = self.positions[index]
        queued_order_gale = None

        if order['result'] != 'win':
            if not position['closed'] and MAX_GALES >= 1 and (self.current_soros_count == 0 or self.pending_soros):
                position['gales'] += 1
                if position['gales'] == MAX_GALES:
                    position['closed'] = True

                if not self.pending_soros:
                    self.reset_soros()

                queued_order_gale = self.execute_option(
                    order['active'], order['direction'], position['amount'] * GALE_RATE, True, index, position["expires_in"])
            else:
                position['closed'] = True
                gales_time = position["expires_in"] * 60 * \
                    MAX_GALES if self.current_soros_count == 0 or self.pending_soros else 0
                log(f'LOSS for {order["active"]} from {get_time(time.time() - position["expires_in"] * 60 - gales_time)}')

                if not self.pending_soros:
                    self.reset_soros()
        else:
            position['closed'] = True
            log(f'WIN for {order["active"]} from {get_time(time.time() - position["expires_in"] * 60)}')
            if not self.pending_soros:
                # enables SOROS if direct WIN
                if position['gales'] == 0 and self.current_soros_count < MAX_SOROS:
                    self.next_soros_amount = order['profit_amount'] * \
                        (1 - SOROS_HOLDING)
                    self.current_soros_count += 1
                    self.pending_soros = True
                elif self.current_soros_count >= MAX_SOROS:
                    self.reset_soros()

        if not self.check_stop():
            for queued_order in self.order_queue:
                if queued_order == queued_order_gale:
                    continue
                log(f'Running queued order: {self.order_queue.index(queued_order)}', False)
                queued_order()
            self.order_queue = []

    def reset_soros(self):
        self.current_soros_count = 0
        self.next_soros_amount = None
        self.pending_soros = False

    def check_stop(self):
        current_balance = self.api.get_balance()
        stop = False
        if STOP_WIN is not None and current_balance - self.initial_balance >= self.initial_balance * STOP_WIN:
            stop = 'WIN'

        if STOP_LOSS is not None and current_balance - self.initial_balance <= self.initial_balance * STOP_LOSS:
            stop = 'LOSS'

        if stop:
            log(f"STOP {stop} reached\nFinal balance: {current_balance}")
            self.stop_orders(current_balance)
            return True

    def stop_orders(self, balance):
        if callable(self.stop_callback):
            self.stop_callback(balance)

    def get_current_value(self, pair, candle_time=5):
        return self.api.get_candles(pair, candle_time * 60, 1, time.time())[0]['close']


if __name__ == '__main__':
    iq = IQBot()
    id = iq.execute_option('GBPUSD', 'put', 100)
