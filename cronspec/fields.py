"""字段取值集合、匹配语义以及 :class:`Schedule` 类型。"""

from bisect import bisect_right
from dataclasses import dataclass


MINUTE = "minute"
HOUR = "hour"
DAY_OF_MONTH = "day_of_month"
MONTH = "month"
DAY_OF_WEEK = "day_of_week"

FIELD_NAMES = (MINUTE, HOUR, DAY_OF_MONTH, MONTH, DAY_OF_WEEK)

# 各字段允许的最小值与最大值。星期字段的 7 在解析阶段归一化为 0（周日）。
FIELD_RANGES = {
    MINUTE: (0, 59),
    HOUR: (0, 23),
    DAY_OF_MONTH: (1, 31),
    MONTH: (1, 12),
    DAY_OF_WEEK: (0, 7),
}

MONTH_NAMES = {
    "JAN": 1,
    "FEB": 2,
    "MAR": 3,
    "APR": 4,
    "MAY": 5,
    "JUN": 6,
    "JUL": 7,
    "AUG": 8,
    "SEP": 9,
    "OCT": 10,
    "NOV": 11,
    "DEC": 12,
}

WEEKDAY_NAMES = {
    "SUN": 0,
    "MON": 1,
    "TUE": 2,
    "WED": 3,
    "THU": 4,
    "FRI": 5,
    "SAT": 6,
}


class CronField:
    """单个字段解析后的取值集合。

    ``values`` 为升序去重后的整数元组；``is_star`` 表示原字段是否以 ``*``
    开头（``*``、``*/n`` 都算）。DOM/DOW 的 POSIX 并集规则依赖该标记：
    在 vixie cron 中，只要字段词法上是星号，就不参与“两者都限定”的分支。
    """

    __slots__ = ("values", "is_star")

    def __init__(self, values, is_star):
        self.values = tuple(values)
        self.is_star = is_star

    def contains(self, value):
        return value in self.values

    def next_value_at_or_above(self, value):
        """返回集合中 >= value 的最小值，不存在则返回 None。"""
        idx = bisect_right(self.values, value - 1)
        if idx < len(self.values):
            return self.values[idx]
        return None

    @property
    def minimum(self):
        return self.values[0]

    def __eq__(self, other):
        if not isinstance(other, CronField):
            return NotImplemented
        return self.values == other.values and self.is_star == other.is_star

    def __repr__(self):
        return "CronField(values=%r, is_star=%r)" % (self.values, self.is_star)


@dataclass(frozen=True)
class Schedule:
    """解析后的 Cron 计划。

    通过 :func:`cronspec.parser.parse` 创建；匹配与触发时间计算方法定义在
    :mod:`cronspec.engine` 中，并以方法形式挂到本类上。
    """

    raw: str
    minute: CronField
    hour: CronField
    day_of_month: CronField
    month: CronField
    day_of_week: CronField

    def day_matches(self, year, month, day, cron_weekday):
        """按 POSIX/vixie cron 语义判断某日是否参与触发。

        ``cron_weekday`` 为 0（周日）到 6（周六）。

        * DOM 与 DOW 都被显式限定（词法上都不是 ``*``）时取并集；
        * 只有一个被限定时按限定的那个判断；
        * 两个都是 ``*`` 时每天参与。
        """
        dom_restricted = not self.day_of_month.is_star
        dow_restricted = not self.day_of_week.is_star
        if dom_restricted and dow_restricted:
            return (
                self.day_of_month.contains(day)
                and self.day_of_week.contains(cron_weekday)
            )
        if dom_restricted:
            return self.day_of_month.contains(day)
        if dow_restricted:
            return self.day_of_week.contains(cron_weekday)
        return True

    def matches(self, dt):
        # 延迟导入，避免 fields -> engine 的循环导入。
        from .engine import matches

        return matches(self, dt)

    def next_after(self, dt):
        from .engine import next_after

        return next_after(self, dt)

    def next_n(self, dt, n):
        from .engine import next_n

        return next_n(self, dt, n)
