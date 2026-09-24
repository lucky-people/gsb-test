"""cronspec 自定义异常。"""


class ScheduleSyntaxError(ValueError):
    """Cron 表达式语法错误。

    属性
    ----
    field:
        出错字段名（``minute`` / ``hour`` / ``day_of_month`` / ``month`` /
        ``day_of_week``）。字段数不对或短写非法时为 ``None``。
    value:
        最小出错片段原文（字段级错误定位到出错的数字、名字、步进值或
        子片段；空片段等「缺失」类错误为空字符串）；表达式级错误（字段数
        不对、短写非法）为去除首尾空白后的整个表达式。
    position:
        ``value`` 在原始表达式中的起始下标（0 基）。

    不变量：对字符串输入 ``expr`` 恒有
    ``expr[position:position + len(value)] == value``。
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
