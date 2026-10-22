import asyncio
import copy
import json
import operator
import os
import re
import time
import uuid
import weakref
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from psycopg import OperationalError
from psycopg.errors import UniqueViolation
from psycopg.rows import dict_row
from psycopg.types.json import set_json_loads
from psycopg_pool import AsyncConnectionPool



def _raw_json(b):
    return b if isinstance(b, str) else bytes(b).decode()


async def _configure(conn):
    set_json_loads(_raw_json, conn)
_PH = re.compile(r"\$(\d+)")


class _Con:
    def __init__(self, conn):
        self.conn = conn

    async def _run(self, sql, args):
        return await self.conn.execute(_PH.sub(r"%(p\1)s", sql), {f"p{i + 1}": a for i, a in enumerate(args)})

    async def fetch(self, sql, *args):
        return await (await self._run(sql, args)).fetchall()

    async def fetchrow(self, sql, *args):
        return await (await self._run(sql, args)).fetchone()

    async def fetchval(self, sql, *args):
        row = await self.fetchrow(sql, *args)
        return next(iter(row.values())) if row else None

    async def execute(self, sql, *args):
        return (await self._run(sql, args)).statusmessage or ""

    def transaction(self):
        return self.conn.transaction()


_last_used = weakref.WeakKeyDictionary()


async def _check(conn):
    if time.monotonic() - _last_used.get(conn, 0) > 60:
        await conn.execute("SELECT 1")


class _PG:
    def __init__(self, url):
        self.pool = AsyncConnectionPool(url, min_size=5, max_size=10, open=False, max_idle=600, configure=_configure,
                                        check=_check, reconnect_timeout=30,
                                        kwargs={"prepare_threshold": None, "autocommit": True, "row_factory": dict_row})

    @asynccontextmanager
    async def acquire(self):
        async with self.pool.connection() as conn:
            try:
                yield _Con(conn)
            finally:
                _last_used[conn] = time.monotonic()

    async def close(self):
        await self.pool.close()


def _delegate(name):
    async def call(self, sql, *args):
        try:
            async with self.acquire() as con:
                return await getattr(con, name)(sql, *args)
        except OperationalError:
            async with self.acquire() as con:
                return await getattr(con, name)(sql, *args)
    return call


for _n in ("fetch", "fetchrow", "fetchval", "execute"):
    setattr(_PG, _n, _delegate(_n))

_pool = None
CACHED = {"settings", "msgs", "admins"}
_cache = {}
_cache_seq = {"next": 0}
_applied_seq = {}


class DuplicateKeyError(Exception):
    pass


class UpdateResult:
    def __init__(self, matched_count, upserted_id=None):
        self.matched_count = self.modified_count = matched_count
        self.upserted_id = upserted_id


class InsertResult:
    def __init__(self, inserted_id):
        self.inserted_id = inserted_id


class DeleteResult:
    def __init__(self, deleted_count):
        self.deleted_count = deleted_count


class ReturnDocument:
    BEFORE = False
    AFTER = True


def _enc(v):
    if isinstance(v, datetime):
        return {"$date": v.astimezone(timezone.utc).isoformat(timespec="microseconds")}
    if isinstance(v, dict):
        return {k: _enc(x) for k, x in v.items()}
    if isinstance(v, (list, tuple, set)):
        return [_enc(x) for x in v]
    return v


def _dec(v):
    if isinstance(v, dict):
        if len(v) == 1 and "$date" in v:
            return datetime.fromisoformat(v["$date"])
        return {k: _dec(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_dec(x) for x in v]
    return v


def _js(v):
    return json.dumps(_enc(v), default=str)


class _Where:
    def __init__(self):
        self.params = []

    def p(self, v):
        self.params.append(v)
        return f"${len(self.params)}"

    def eq(self, f, v):
        if v is None:
            return f"(doc->{self.p(f)} IS NULL OR doc->{self.p(f)} = 'null'::jsonb)"
        return f"COALESCE(doc->{self.p(f)} = {self.p(_js(v))}::jsonb, false)"

    def cmp(self, f, op, v):
        k = self.p(f)
        if isinstance(v, datetime):
            lhs, typ, val = f"doc->{k}->>'$date'", "object", _enc(v)["$date"]
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            lhs, typ, val = f"(doc->>{k})::float8", "number", float(v)
        else:
            lhs, typ, val = f"doc->>{k}", "string", str(v)
        return f"COALESCE(CASE WHEN jsonb_typeof(doc->{k}) = '{typ}' THEN {lhs} {op} {self.p(val)} END, false)"

    def field(self, f, cond):
        if not (isinstance(cond, dict) and cond and all(k.startswith("$") for k in cond)):
            return [self.eq(f, cond)]
        out = []
        for op, v in cond.items():
            if op == "$ne":
                out.append(f"NOT {self.eq(f, v)}")
            elif op in ("$in", "$nin"):
                ors = " OR ".join(self.eq(f, x) for x in v) or "false"
                out.append(f"({ors})" if op == "$in" else f"NOT ({ors})")
            elif op in ("$gt", "$gte", "$lt", "$lte"):
                out.append(self.cmp(f, {"$gt": ">", "$gte": ">=", "$lt": "<", "$lte": "<="}[op], v))
            elif op == "$exists":
                out.append(("" if v else "NOT ") + f"(doc ? {self.p(f)})")
            else:
                raise ValueError(f"unsupported operator {op}")
        return out

    def build(self, flt):
        parts = []
        for f, cond in (flt or {}).items():
            if f == "$or":
                parts.append("(" + " OR ".join("(" + self.build(c) + ")" for c in cond) + ")")
            else:
                parts.extend(self.field(f, cond))
        return " AND ".join(parts) or "true"


def _project(doc, projection):
    if not projection:
        return doc
    inc = {k for k, v in projection.items() if v and k != "_id"}
    if inc:
        doc = {k: v for k, v in doc.items() if k in inc or k == "_id"}
    if "_id" in projection and not projection["_id"]:
        doc.pop("_id", None)
    return doc


def _apply(doc, update, inserting):
    doc = dict(doc)
    if inserting:
        doc.update(update.get("$setOnInsert", {}))
    doc.update(update.get("$set", {}))
    for k, v in update.get("$inc", {}).items():
        doc[k] = (doc.get(k) or 0) + v
    for k in update.get("$unset", {}):
        doc.pop(k, None)
    return doc


def _row_id(doc):
    return json.dumps(_enc(doc["_id"]), default=str) if "_id" in doc else uuid.uuid4().hex


class _Cursor:
    def __init__(self, coll, flt, projection):
        self.coll, self.flt, self.projection, self._sort, self._limit = coll, flt, projection, [], None

    def sort(self, key, direction=1):
        self._sort = [(key, direction)] if isinstance(key, str) else list(key)
        return self

    def limit(self, n):
        self._limit = n
        return self

    async def to_list(self, length=None):
        w = _Where()
        sql = f'SELECT doc FROM "{self.coll.name}" WHERE {w.build(self.flt)}'
        if self._sort:
            sql += " ORDER BY " + ", ".join(
                f"doc->{w.p(k)} {'ASC NULLS FIRST' if d == 1 else 'DESC NULLS LAST'}" for k, d in self._sort)
        n = min(x for x in (self._limit, length) if x) if (self._limit or length) else None
        if n:
            sql += f" LIMIT {int(n)}"
        rows = await _pool.fetch(sql, *w.params)
        return [_project(_dec(json.loads(r["doc"])), self.projection) for r in rows]


_OPS = {"$gt": operator.gt, "$gte": operator.ge, "$lt": operator.lt, "$lte": operator.le}


def _eq(a, v):
    return a is None if v is None else a == v


def _match_cond(doc, f, cond):
    a = doc.get(f)
    if not (isinstance(cond, dict) and cond and all(k.startswith("$") for k in cond)):
        return _eq(a, cond)
    for op, v in cond.items():
        if op == "$ne" and _eq(a, v):
            return False
        if op == "$in" and not any(_eq(a, x) for x in v):
            return False
        if op == "$nin" and any(_eq(a, x) for x in v):
            return False
        if op == "$exists" and (f in doc) != bool(v):
            return False
        if op in _OPS:
            try:
                if a is None or not _OPS[op](a, v):
                    return False
            except TypeError:
                return False
    return True


def _match(doc, flt):
    for f, cond in (flt or {}).items():
        if f == "$or":
            if not any(_match(doc, c) for c in cond):
                return False
        elif not _match_cond(doc, f, cond):
            return False
    return True


class _MemCursor(_Cursor):
    async def to_list(self, length=None):
        docs = [d for d in _cache[self.coll.name].values() if _match(d, self.flt)]
        for k, d in reversed(self._sort):
            docs.sort(key=lambda x: (x.get(k) is not None, x.get(k) if x.get(k) is not None else 0), reverse=d == -1)
        n = min(x for x in (self._limit, length) if x) if (self._limit or length) else None
        return [_project(copy.deepcopy(d), self.projection) for d in docs[:n]]


class Collection:
    def __init__(self, name):
        self.name = name

    @property
    def cached(self):
        return self.name in _cache

    async def reload(self):
        _cache_seq["next"] += 1
        seq = _cache_seq["next"]
        rows = await _pool.fetch(f'SELECT id, doc FROM "{self.name}"')
        if seq > _applied_seq.get(self.name, 0):
            _applied_seq[self.name] = seq
            _cache[self.name] = {r["id"]: _dec(json.loads(r["doc"])) for r in rows}

    def _cache_put(self, rid, doc):
        if self.cached:
            _cache[self.name][rid] = copy.deepcopy(doc)

    async def _after_write(self):
        if self.cached:
            await self.reload()

    async def create_table(self):
        await _pool.execute(f'CREATE TABLE IF NOT EXISTS "{self.name}" (id TEXT PRIMARY KEY, doc JSONB NOT NULL)')

    async def create_index(self, keys, unique=False):
        keys = [keys] if isinstance(keys, str) else [k for k, _ in keys]
        name = f"{self.name}_{'_'.join(keys)}_idx"
        cols = ", ".join(f"(doc->'{k}')" for k in keys)
        await _pool.execute(
            f'CREATE {"UNIQUE " if unique else ""}INDEX IF NOT EXISTS "{name}" ON "{self.name}" ({cols})')

    async def insert_one(self, doc):
        rid = _row_id(doc)
        try:
            await _pool.execute(f'INSERT INTO "{self.name}" (id, doc) VALUES ($1, $2::jsonb)', rid, _js(doc))
        except UniqueViolation as e:
            raise DuplicateKeyError(str(e))
        self._cache_put(rid, doc)
        return InsertResult(doc.get("_id", rid))

    async def find_one(self, flt=None, projection=None):
        docs = await self.find(flt, projection).limit(1).to_list(1)
        return docs[0] if docs else None

    def find(self, flt=None, projection=None):
        return (_MemCursor if self.cached else _Cursor)(self, flt, projection)

    async def count_documents(self, flt):
        if self.cached:
            return sum(1 for d in _cache[self.name].values() if _match(d, flt))
        w = _Where()
        return await _pool.fetchval(f'SELECT COUNT(*) FROM "{self.name}" WHERE {w.build(flt)}', *w.params)

    async def distinct(self, field, flt=None):
        if self.cached:
            out = []
            for d in _cache[self.name].values():
                if d.get(field) is not None and _match(d, flt) and d[field] not in out:
                    out.append(copy.deepcopy(d[field]))
            return out
        w = _Where()
        k = w.p(field)
        rows = await _pool.fetch(
            f'SELECT DISTINCT doc->{k} AS v FROM "{self.name}" WHERE {w.build(flt)} AND doc->{k} IS NOT NULL',
            *w.params)
        return [_dec(json.loads(r["v"])) for r in rows if r["v"] != "null"]

    async def delete_many(self, flt):
        w = _Where()
        res = await _pool.execute(f'DELETE FROM "{self.name}" WHERE {w.build(flt)}', *w.params)
        await self._after_write()
        return DeleteResult(int(res.split()[-1]))

    async def _modify(self, flt, update, upsert, many, return_after):
        if self.cached and not many and set(update) <= {"$set", "$setOnInsert"}:
            hit = next((d for d in _cache[self.name].values() if _match(d, flt)), None)
            if hit is not None and all(k in hit and hit[k] == v for k, v in update.get("$set", {}).items()):
                return copy.deepcopy(hit), UpdateResult(1)
        if set(update) <= {"$set", "$setOnInsert", "$unset"}:
            res = await self._fast_modify(flt, update, upsert, many, return_after)
            if many:
                await self._after_write()
        else:
            res = await self._tx_modify(flt, update, upsert, many, return_after)
            await self._after_write()
        return res

    async def _fast_modify(self, flt, update, upsert, many, return_after):
        w = _Where()
        where = w.build(flt)
        expr = "t.doc"
        if update.get("$set"):
            expr = f"({expr} || {w.p(_js(update['$set']))}::jsonb)"
        if update.get("$unset"):
            expr = f"({expr} - {w.p(list(update['$unset']))}::text[])"
        t = f'"{self.name}"'
        if many:
            sql = f"UPDATE {t} t SET doc = {expr} WHERE {where}"
        else:
            sql = (f"WITH o AS (SELECT id AS oid, doc AS old FROM {t} WHERE {where} LIMIT 1 FOR UPDATE) "
                   f"UPDATE {t} t SET doc = {expr} FROM o WHERE t.id = o.oid RETURNING t.id, o.old, t.doc")
        for attempt in range(2):
            if many:
                n = int((await _pool.execute(sql, *w.params)).split()[-1])
                row = None
            else:
                row = await _pool.fetchrow(sql, *w.params)
                n = 1 if row else 0
            if n:
                if not many:
                    self._cache_put(row["id"], _dec(json.loads(row["doc"])))
                doc = None if many else _dec(json.loads(row["doc" if return_after else "old"]))
                return doc, UpdateResult(n)
            if not upsert:
                return None, UpdateResult(0)
            if attempt:
                raise DuplicateKeyError(f"upsert conflict on {self.name}")
            base = {k: v for k, v in (flt or {}).items()
                    if not k.startswith("$") and not (isinstance(v, dict) and any(x.startswith("$") for x in v))}
            new = _apply(base, update, True)
            rid = _row_id(new)
            ins = await _pool.fetchval(
                f"INSERT INTO {t} (id, doc) VALUES ($1, $2::jsonb) ON CONFLICT DO NOTHING RETURNING id", rid, _js(new))
            if ins:
                self._cache_put(rid, new)
                return (new if return_after else None), UpdateResult(0, new.get("_id", rid))

    async def _tx_modify(self, flt, update, upsert, many, return_after):
        w = _Where()
        sql = f'SELECT id, doc FROM "{self.name}" WHERE {w.build(flt)}{"" if many else " LIMIT 1"} FOR UPDATE'
        for attempt in range(2):
            try:
                async with _pool.acquire() as con, con.transaction():
                    rows = await con.fetch(sql, *w.params)
                    for r in rows:
                        new = _apply(_dec(json.loads(r["doc"])), update, False)
                        await con.execute(f'UPDATE "{self.name}" SET doc = $1::jsonb WHERE id = $2', _js(new), r["id"])
                    if rows:
                        before = _dec(json.loads(rows[0]["doc"]))
                        return (_apply(before, update, False) if return_after else before), UpdateResult(len(rows))
                    if not upsert:
                        return None, UpdateResult(0)
                    base = {k: v for k, v in (flt or {}).items()
                            if not k.startswith("$") and not (isinstance(v, dict) and any(x.startswith("$") for x in v))}
                    new = _apply(base, update, True)
                    rid = _row_id(new)
                    await con.execute(f'INSERT INTO "{self.name}" (id, doc) VALUES ($1, $2::jsonb)', rid, _js(new))
                    return (new if return_after else None), UpdateResult(0, new.get("_id", rid))
            except UniqueViolation as e:
                if attempt:
                    raise DuplicateKeyError(str(e))

    async def update_one(self, flt, update, upsert=False):
        return (await self._modify(flt, update, upsert, False, False))[1]

    async def update_many(self, flt, update, upsert=False):
        return (await self._modify(flt, update, upsert, True, False))[1]

    async def find_one_and_update(self, flt, update, upsert=False, return_document=False, projection=None):
        doc = (await self._modify(flt, update, upsert, False, bool(return_document)))[0]
        return _project(doc, projection) if doc is not None else None


class _DB:
    def __getattr__(self, name):
        return Collection(name)


db = _DB()

COLLECTIONS = ["visitors", "pageviews", "start_tokens", "leads", "join_requests", "admins", "login_attempts",
               "users", "members", "processed_updates", "settings", "msgs", "unrequested", "jr_notified"]


async def _cleanup_processed_updates():
    while True:
        try:
            await db.processed_updates.delete_many({"created_at": {"$lt": datetime.now(timezone.utc) - timedelta(days=3)}})
        except Exception:
            pass
        await asyncio.sleep(6 * 3600)


async def ensure_indexes():
    global _pool
    _pool = _PG(os.environ["DATABASE_URL"])
    await _pool.pool.open(wait=True)
    for c in COLLECTIONS:
        await getattr(db, c).create_table()
    for c in CACHED:
        await getattr(db, c).reload()
    await db.visitors.create_index("visitor_id", unique=True)
    await db.pageviews.create_index("event_id", unique=True)
    await db.pageviews.create_index("created_at")
    await db.start_tokens.create_index("token", unique=True)
    await db.start_tokens.create_index("created_at")
    await db.leads.create_index("telegram_user_id", unique=True)
    await db.leads.create_index("updated_at")
    await db.join_requests.create_index([("chat_id", 1), ("telegram_user_id", 1), ("status", 1)])
    await db.join_requests.create_index("created_at")
    await db.admins.create_index("user_id", unique=True)
    await db.login_attempts.create_index("user_id", unique=True)
    await db.users.create_index("user_id", unique=True)
    await db.users.create_index("joined_at")
    await db.members.create_index([("user_id", 1), ("chat_id", 1)], unique=True)
    await db.processed_updates.create_index("created_at")
    await db.unrequested.create_index("user_id", unique=True)
    asyncio.create_task(_cleanup_processed_updates())


async def close_db():
    if _pool:
        try:
            await _pool.close()
        except (Exception, asyncio.CancelledError):
            pass
