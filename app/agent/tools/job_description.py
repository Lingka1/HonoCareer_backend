"""Extract explicitly supplied JD text; does not claim to fetch external jobs."""
import re

def retrieve(text):
    terms=re.findall(r'[A-Za-z][A-Za-z0-9+#.-]{1,30}|[\u4e00-\u9fff]{2,12}',text)
    return {'source':'user_supplied_jd','keywords':list(dict.fromkeys(terms))[:30],
            'requirements':[x.strip() for x in re.split(r'[\n；;]',text) if x.strip()][:20]}
