from pocketoption import PocketOption
from time import time
from datetime import datetime
from dotenv import load_dotenv
from os import getenv
from threading import Thread, Timer, enumerate
from debug import log
from utils import fmt_order, get_time, normalize_amount, time_until
from asyncio import set_event_loop
from typing import Dict, List

load_dotenv()

POCKET_SSID = getenv('POCKETOPTION_SESSION')

# only stop orders for the day if True
SOFT_TOP = getenv('SOFT_TOP', 'False') == 'True'

DEMO_MODE = getenv('DEMO_MODE', 'True') == 'True'

# percentage of balance used by orders
BASE_ORDER = float(getenv('BASE_ORDER', 0.02))
# how much of order amount will be used for the gale
GALE_RATE = float(getenv('GALE_RATE', 2.2))
# max amount of gales per order
MAX_GALES = int(getenv('MAX_GALES', 1))
# percentage of payout + base_order that will be kept in the balance
SOROS_HOLDING = float(getenv('SOROS_HOLDING', 0.1))
# max amount of soros per successful order
MAX_SOROS = int(getenv('MAX_SOROS', 3))
# profit needed to stop orders for the day
STOP_WIN = float(getenv('STOP_WIN', 0.1)) or None
# wheather to enter next order with previous total loss
CYCLE_LOSS = getenv('CYCLE_LOSS', 'True') == 'True'
# loss needed to stop orders for the day
STOP_LOSS = float(getenv('STOP_LOSS', 0.12)) or None


class TradingBot():
    positions = []
    order_queue = []
    orders_received: Dict[str, List] = {}
    parsed_orders = {}

    next_soros_amount = None
    soros_start_balance = None
    current_soros_count = 0
    pending_soros = False
    cycle_loss_amount = None

    loop = None
    stop_day = None
    last_order_day = None

    def __init__(self, stop_callback=None, loop=None):
        print("Conecting...")

        self.api = PocketOption(POCKET_SSID, DEMO_MODE)

        self.initial_balance = self.api.get_balance()
        self.stop_callback = stop_callback
        self.loop = loop

        print("Balance:", self.initial_balance)
        print("##############################")

    def execute_option(self, pair, action, start_time=None, amount=None, gale=False, pos_index=None, expires_in=5):
        order_format = fmt_order(pair, action, start_time, expires_in)
        if not order_format in self.parsed_orders:
            self.parsed_orders[order_format] = True
        else:
            log(f'Order {order_format} already queued', False)
            return
        if start_time is not None:
            start_in = time_until(start_time)
            if start_in / 3600 > 9:
                log(f'Order too late or too soon to be executed', False)
                return
            order_fmt = fmt_order(pair, action, start_time, expires_in)
            if start_time not in self.orders_received:
                self.orders_received[start_time] = []
            self.orders_received[start_time].append(order_fmt)
            t = Timer(start_in, lambda: self.execute_option(
                pair, action, amount=amount, gale=gale, pos_index=pos_index, expires_in=expires_in))
            t.name = 'Order ' + order_fmt
            t.start()
            return

        try:
            del self.parsed_orders[fmt_order(
                pair, action, start_time, expires_in)]
        except:
            pass

        if self.stopped:
            log(f'Ignoring order due to soft stop', False)
            return
        elif self.stop_day or self.last_order_day is not None and self.last_order_day != datetime.now().day:
            self.reset()
        self.last_order_day = datetime.now().day
        log(f'Executing order: {pair}/{action.upper()}', False)

        # filter pending orders which are 93% of the expiration time in
        # (e.g. 4m40s if expires in 5min)
        pending_orders = list(filter(lambda pos: not pos['closed'] and time(
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
        is_soros = False
        is_cycle_loss = False
        if self.next_soros_amount:
            amount = self.next_soros_amount
            self.next_soros_amount = None
            is_soros = True
        elif self.cycle_loss_amount and not gale:
            amount = self.cycle_loss_amount
            self.cycle_loss_amount = None
            is_cycle_loss = True
        else:
            balance = self.api.get_balance()
            if balance is None:
                log(
                    f'Failed to enter position: {pair}')
                return

            now = get_time()
            log(f'{now} | {self.orders_received}', False)

            # split amount equally for all orders schedule for the same time
            amount = normalize_amount(
                balance * BASE_ORDER / len(self.orders_received[now]) if not gale else amount)

        log(f'Raw amount: {amount}', False)

        check, id = self.api.buy(amount, pair, action, expires_in)
        if check:
            if not gale:
                self.positions.append({'id': id, 'pair': pair, 'action': action, 'gales': 0,
                                       'amount': amount, 'time': time(), 'expires_in': expires_in, 'cycle_loss': is_cycle_loss, 'closed': False})
            else:
                self.positions[pos_index]['amount'] = amount

            msg = ''
            if gale:
                msg += f'GALE {self.positions[pos_index]["gales"]}: '
            elif is_soros:
                msg += f'SOROS {self.current_soros_count}: '
                self.pending_soros = False
            elif is_cycle_loss:
                msg += f'CYCLE: '

            msg += f'{action.upper()} of ${"{:.2f}".format(amount)} {pair}'
            log(msg)

            index = len(self.positions) - 1 if not gale else pos_index

            Thread(target=lambda: self.check_gale_for(
                id, index, order_info=fmt_order(pair, action, 0, expires_in)), name=f'Gale Check ({fmt_order(pair, action, 0, expires_in)})').start()

            return id
        else:
            log(
                f'Failed to enter position: {pair}')

    def check_gale_for(self, id, index, order_info='Unknown'):
        order = self.api.check_binary_order(id)
        position = self.positions[index]

        if not order:
            log(f'Failed to verify result for order: {order_info}')
            position['closed'] = True
            self.reset_soros()
        elif order['result'] != 'win':
            if position['gales'] != MAX_GALES and MAX_GALES >= 1 and (self.current_soros_count == 0 or self.pending_soros):
                position['gales'] += 1

                if not self.pending_soros:
                    self.reset_soros()

                now = get_time()

                if now not in self.orders_received:
                    self.orders_received[now] = []
                self.orders_received[now].append(
                    fmt_order(order['active'], order['direction'], now, position["expires_in"]))

                self.execute_option(
                    order['active'], order['direction'], amount=position['amount'] * GALE_RATE, gale=True, pos_index=index, expires_in=position["expires_in"])
            else:
                position['closed'] = True
                gales_time = position["expires_in"] * 60 * \
                    MAX_GALES if self.current_soros_count == 0 or self.pending_soros else 0
                log(f'LOSS for {order["active"]} from {get_time(time() - position["expires_in"] * 60 - gales_time)}')

                self.enable_cycle_loss(position)

                if not self.pending_soros:
                    self.reset_soros()
        else:
            position['closed'] = True
            log(f'WIN for {order["active"]} from {get_time(time() - position["expires_in"] * 60)}')
            log(
                f"SOROS check: Pending = {self.pending_soros} | Gales = {position['gales']} | Cycle loss = {position['cycle_loss']} | Current SOROS = {self.current_soros_count} | Max SOROS = {MAX_SOROS}", False)
            if not self.pending_soros:
                # enables SOROS if direct WIN
                if position['gales'] == 0 and not position['cycle_loss'] and self.current_soros_count < MAX_SOROS:
                    self.next_soros_amount = normalize_amount(
                        order['profit_amount'] * (1 - SOROS_HOLDING))
                    self.current_soros_count += 1
                    self.pending_soros = True
                    self.soros_start_balance = self.api.get_balance(
                    ) - (order['profit_amount'] - order['amount'])
                    log(
                        f'SOROS config: Start balance = {self.soros_start_balance} | Amount  = {self.next_soros_amount}', False)
                elif self.current_soros_count >= MAX_SOROS:
                    self.reset_soros()

        if not self.check_stop():
            for queued_order in self.order_queue:
                log(
                    f'Running queued order: {self.order_queue.index(queued_order)}', False)
                queued_order()
            self.order_queue = []

    def enable_cycle_loss(self, position):
        if self.cycle_loss_amount is not None or not CYCLE_LOSS:
            return

        if self.soros_start_balance is not None:
            self.cycle_loss_amount = normalize_amount(
                self.soros_start_balance - self.api.get_balance())
        else:
            self.cycle_loss_amount = 0
            for i in range(MAX_GALES + 1):
                self.cycle_loss_amount += position['amount'] / \
                    GALE_RATE ** (MAX_GALES - i)
            self.cycle_loss_amount = normalize_amount(self.cycle_loss_amount)

        log(f'CYCLE LOSS amount: {self.cycle_loss_amount}', False)

    def reset_soros(self):
        self.current_soros_count = 0
        self.next_soros_amount = None
        self.pending_soros = False
        self.soros_start_balance = None

    def check_stop(self):
        current_balance = self.api.get_balance()
        if current_balance is None:
            return False
        stop = False
        if STOP_WIN is not None and current_balance - self.initial_balance >= self.initial_balance * STOP_WIN:
            stop = 'WIN'

        if STOP_LOSS is not None and self.initial_balance - current_balance >= self.initial_balance * STOP_LOSS:
            stop = 'LOSS'

        log(self.positions, False)
        pending_orders = list(
            filter(lambda pos: not pos['closed'], self.positions))
        log(pending_orders, False)
        if stop:
            if len(pending_orders) == 0:
                log(f"STOP {stop} reached\nFinal balance: {current_balance}")
                self.stop_orders(soft=SOFT_TOP)
            else:
                self.stop_day = datetime.now().day
            return True

    def stop_orders(self, soft=False, cb=True):
        if soft:
            self.stop_day = datetime.now().day
        # cancel all scheduled orders
        for thread in enumerate():
            if 'Order' in thread.name:
                thread.cancel()
        self.api.quit()
        if callable(self.stop_callback) and cb and not soft:
            set_event_loop(self.loop)
            self.stop_callback()

    def close(self):
        if not self.stop_day:
            log('Closing...')
            self.stop_orders(False)

    def reset(self):
        self.reset_soros()
        self.stop_day = None
        self.order_queue = []
        self.api.restart()
        self.initial_balance = self.api.get_balance()
        print("Balance:", self.initial_balance)
        print("##############################")

    @property
    def stopped(self):
        return self.stop_day is not None and datetime.now().day == self.stop_day


# if __name__ == '__main__':
#     iq = TradingBot()
#     id = iq.execute_option('GBPUSD', 'put', 100)
