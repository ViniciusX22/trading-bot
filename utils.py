from time import localtime, time, strftime
from threading import Timer


def fmt_order(pair, action, start_in, timeframe):
    order_time = localtime(time() + start_in)
    return f'{pair};{action};{order_time.tm_hour}:{order_time.tm_min if order_time.tm_min >= 10 else "0" + str(order_time.tm_min)}:{timeframe}'


def get_time(t=None):
    return strftime("%H:%M", localtime(t))


class Timeout():
    finish = None
    max_interval = 1
    finished = False

    def __init__(self, max_interval=1, finish=None):
        self.max_interval = max_interval
        self.finish = finish

    def start(self):
        self.timer = Timer(self.max_interval, lambda: self._stop())
        self.timer.start()

    def _stop(self):
        if self.finish is not None:
            self.finished = True
            self.finish()

    def cancel(self):
        self.timer.cancel()

    def reset(self):
        self.timer.cancel()
        if not self.finished:
            self.start()
