"""cronspec 自定义异常。"""


class ScheduleSyntaxError(ValueError):
    """Cron 表达式语法错误。

    属性
    ----
    field:
        出错字段名（``minute`` / ``hour`` / ``day_of_month`` / ``month`` /
        ``day_of_week``）。字段数不对或短写非法时为 ``None``。
    value:
        出错片段原文；字段级错误为片段原文，表达式级错误为去除首尾空白后的
        整个表达式。
    position:
        出错片段在原始表达式中的起始下标（0 基）。
    """

    def __init__(self, field, value, position, reason):
        self.field = field
        self.value = value
        self.position = position
        self.reason = reason
        field_label = field if field is not None else "表达式"
        message = "Cron 表达式语法无效（%s，位置 %d，片段 %r）：%s" % (
            field_label,
            position,
            value,
            reason,
        )
        super().__init__(message)


class NoMatchingTimeError(Exception):
    """在可搜索范围内不存在任何触发时刻。"""
