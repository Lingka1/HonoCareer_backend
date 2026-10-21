import base64
from datetime import datetime, timezone
import hashlib
import hmac
import json
import uuid

class ServiceError(Exception):
    def __init__(self, status, code, message, details=None):
        self.status, self.code, self.message, self.details = status, code, message, details
        super().__init__(message)

def now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")

def uid(prefix):
    return prefix + "_" + uuid.uuid4().hex

def dump(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)

def fingerprint(value):
    return hashlib.sha256(dump(value).encode()).hexdigest()

def owned(db, table, resource_id, user_id):
    assert table in {"profiles", "resumes", "sessions", "weak_points"}
    row = db.execute(f"SELECT * FROM {table} WHERE id=? AND user_id=?", (resource_id, user_id)).fetchone()
    if row is None:
        raise ServiceError(404, "NOT_FOUND", "资源不存在或不可访问")
    return dict(row)

def idem_get(db, user, scope, key, digest):
    if not key:
        return None
    row = db.execute("SELECT * FROM idempotency WHERE user_id=? AND scope=? AND key=?", (user, scope, key)).fetchone()
    if row and row['request_hash'] != digest:
        raise ServiceError(409, "IDEMPOTENCY_CONFLICT", "同一幂等键不能用于不同请求")
    return row['resource_id'] if row else None

def idem_put(db, user, scope, key, digest, resource_id):
    if key:
        db.execute("INSERT INTO idempotency VALUES (?,?,?,?,?)", (user, scope, key, digest, resource_id))

def paginate(rows, limit, cursor, scope, secret, sort_fields=("updatedAt", "id")):
    def sort_key(row):
        return tuple(row[k] for k in sort_fields)
    rows.sort(key=sort_key, reverse=True)
    if cursor:
        try:
            raw, signature = cursor.split(".")
            expected = hmac.new(secret.encode(), raw.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(signature, expected):
                raise ValueError()
            token = json.loads(base64.urlsafe_b64decode(raw + '=' * (-len(raw) % 4)))
            if token['scope'] != scope:
                raise ValueError()
            rows = [row for row in rows if sort_key(row) < tuple(token['key'])]
        except (ValueError, KeyError, TypeError, json.JSONDecodeError):
            raise ServiceError(400, "VALIDATION_ERROR", "游标无效，请重新加载列表") from None
    selected, has_more = rows[:limit], len(rows) > limit
    next_cursor = None
    if has_more:
        raw = base64.urlsafe_b64encode(dump({'scope':scope,'key':sort_key(selected[-1])}).encode()).decode().rstrip('=')
        next_cursor = raw + '.' + hmac.new(secret.encode(), raw.encode(), hashlib.sha256).hexdigest()
    return {'items': selected, 'nextCursor': next_cursor, 'hasMore': has_more}
