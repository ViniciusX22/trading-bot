from time import time, strftime
from datetime import tzinfo, timedelta, datetime
from threading import Timer
from asyncio import set_event_loop


class CustomTZ(tzinfo):
    """ Update this to the desired timezone """

    def utcoffset(self, dt):
        return timedelta(hours=-3)

    def dst(self, dt):
        return timedelta(0)

    def tzname(self, dt):
        return "-03:00"

    def __repr__(self):
        return f"{self.__class__.__name__}()"


def fmt_order(pair, action, start_time, timeframe):
    if type(start_time) == int:
        order_time = datetime.fromtimestamp(time() + start_time, CustomTZ())
        return f'{pair};{action};{order_time.hour}:{order_time.minute if order_time.minute >= 10 else "0" + str(order_time.minute)}:{timeframe}'
    return f'{pair};{action};{start_time}:{timeframe}'


def get_time(t=None):
    if t:
        dt = datetime.fromtimestamp(t, CustomTZ())
    else:
        dt = datetime.now(CustomTZ())
    return strftime("%H:%M", (1, 0, 0, dt.hour, dt.minute, 0, 0, 0, 0))


def normalize_amount(amount):
    return min(max(round(amount, 2), 1), 1000)


def time_until(start_time):
    hour, min = start_time.split(':')
    dt = datetime.now(CustomTZ())
    time_is_equal = int(hour) == dt.hour and int(min) == dt.minute
    duration = timedelta(hours=int(hour), minutes=int(min)) - timedelta(
        hours=dt.hour, minutes=dt.minute, seconds=dt.second) if not time_is_equal else timedelta()
    return duration.seconds


class Timeout():
    finish = None
    max_interval = 1
    finished = False
    timer = None
    loop = None

    def __init__(self, max_interval=1, finish=None, loop=None):
        self.max_interval = max_interval
        self.finish = finish
        self.loop = loop

    def start(self):
        self.timer = Timer(self.max_interval, lambda: self._stop())
        self.timer.name = 'Disconnection Timeout'
        self.timer.start()

    def _stop(self):
        if self.finish is not None:
            self.finished = True
            if self.loop:
                set_event_loop(self.loop)
            self.finish()

    def cancel(self):
        if self.timer:
            self.timer.cancel()

    def reset(self):
        if self.timer:
            self.timer.cancel()
        if not self.finished:
            self.start()
