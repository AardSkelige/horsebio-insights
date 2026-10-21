def normalize(article):
    return ''.join(str(article or '').split()).upper()
