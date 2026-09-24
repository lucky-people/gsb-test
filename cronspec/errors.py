"""cronspec 自定义异常。"""


class ScheduleSyntaxError(ValueError):
    """Cron 表达式语法错误。

    属性
    ----
    field:
        出错字段名（``minute`` / ``hour`` / ``day_of_month`` / ``month`` /
        ``day_of_week``）。字段数不对或短写非法时为 ``None``。
    value:
        最小出错片段的原文；表达式级错误（字段数不对、短写非法）为去除
        首尾空白后的整个表达式。
    position:
        ``value`` 在原始表达式中的起始下标（0 基）。

    定位不变量：对传入的原始表达式 ``expr`` 恒有
    ``expr[position:position + len(value)] == value``，调用方可据此把
    光标精确落在出错片段上。
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
