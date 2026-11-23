"""Oracle duyarlılık kontrolü için referans; model üretimi/teslimi değildir."""
def normalize_title(value):
    if not isinstance(value,str):
        raise TypeError('TITLE_MUST_BE_STRING')
    result=' '.join(value.split())
    if not result:
        raise ValueError('TITLE_EMPTY')
    if len(result)>120:
        raise ValueError('TITLE_TOO_LONG')
    return result
