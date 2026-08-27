#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
cache.py - نظام الكاش الموحد للبوت
- كاش منفصل لكل نوع بيانات
- TTL مختلف لكل نوع
- حد أقصى للحجم يمنع تسرب الذاكرة
- تنظيف تلقائي دوري
"""

import asyncio
import time
import logging
from collections import OrderedDict
from typing import Any, Optional, Dict

logger = logging.getLogger(__name__)


class TTLCache:
    """كاش TTL مع حد أقصى للحجم"""

    def __init__(self, maxsize: int = 100, ttl: int = 60):
        self.maxsize = maxsize
        self.ttl = ttl
        self._cache = OrderedDict()
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[Any]:
        """جلب قيمة من الكاش"""
        async with self._lock:
            if key not in self._cache:
                return None
            value, timestamp = self._cache[key]
            if time.time() - timestamp > self.ttl:
                del self._cache[key]
                return None
            self._cache.move_to_end(key)
            return value

    async def set(self, key: str, value: Any, ttl: int = None) -> None:
        """تخزين قيمة في الكاش"""
        effective_ttl = ttl if ttl is not None else self.ttl
        async with self._lock:
            self._cache[key] = (value, time.time())
            self._cache.move_to_end(key)
            self._cleanup_locked()

    async def delete(self, key: str) -> None:
        """حذف مفتاح"""
        async with self._lock:
            self._cache.pop(key, None)

    async def clear(self) -> None:
        """مسح الكاش بالكامل"""
        async with self._lock:
            self._cache.clear()

    async def cleanup(self) -> int:
        """تنظيف العناصر المنتهية وإرجاع عدد المحذوف"""
        async with self._lock:
            now = time.time()
            expired = [k for k, (_, ts) in self._cache.items() if now - ts > self.ttl]
            for k in expired:
                del self._cache[k]
            return len(expired)

    def _cleanup_locked(self) -> None:
        """تنظيف داخلي بدون قفل (يُستدعى داخل set)"""
        now = time.time()
        expired = [k for k, (_, ts) in self._cache.items() if now - ts > self.ttl]
        for k in expired:
            del self._cache[k]
        while len(self._cache) > self.maxsize:
            self._cache.popitem(last=False)


class SettingsCache:
    """كاش إعدادات الأمان والردود التلقائية"""

    def __init__(self):
        self.security = TTLCache(maxsize=500, ttl=30)
        self.auto_reply = TTLCache(maxsize=500, ttl=60)

    async def get_security(self, chat_id: int):
        key = f"sec_{chat_id}"
        return await self.security.get(key)

    async def set_security(self, chat_id: int, settings: Dict):
        key = f"sec_{chat_id}"
        await self.security.set(key, settings)

    async def invalidate_security(self, chat_id: int = None):
        if chat_id is not None:
            await self.security.delete(f"sec_{chat_id}")
        else:
            await self.security.clear()

    async def get_auto_reply_settings(self, chat_id: int):
        key = f"ars_{chat_id}"
        return await self.auto_reply.get(key)

    async def set_auto_reply_settings(self, chat_id: int, settings: Dict):
        key = f"ars_{chat_id}"
        await self.auto_reply.set(key, settings)

    async def invalidate_auto_reply(self, chat_id: int = None):
        if chat_id is not None:
            await self.auto_reply.delete(f"ars_{chat_id}")
        else:
            await self.auto_reply.clear()


class BannedWordsCache:
    """كاش الكلمات المحظورة"""

    def __init__(self):
        self.cache = TTLCache(maxsize=300, ttl=60)

    async def get(self, chat_id: int):
        key = f"bw_{chat_id}"
        return await self.cache.get(key)

    async def set(self, chat_id: int, words: list):
        key = f"bw_{chat_id}"
        await self.cache.set(key, words)

    async def invalidate(self, chat_id: int = None):
        if chat_id is not None:
            await self.cache.delete(f"bw_{chat_id}")
        else:
            await self.cache.clear()


class AuthCache:
    """كاش صلاحيات المشرفين"""

    def __init__(self):
        self.cache = TTLCache(maxsize=2000, ttl=15)

    async def get(self, chat_id: int, user_id: int):
        key = f"auth_{chat_id}_{user_id}"
        return await self.cache.get(key)

    async def set(self, chat_id: int, user_id: int, authorized: bool):
        key = f"auth_{chat_id}_{user_id}"
        await self.cache.set(key, authorized)

    async def invalidate(self, chat_id: int = None, user_id: int = None):
        if chat_id is not None and user_id is not None:
            await self.cache.delete(f"auth_{chat_id}_{user_id}")
        elif chat_id is not None:
            # تنظيف كل مفاتيح الدردشة
            async with self.cache._lock:
                keys = [k for k in self.cache._cache.keys() if k.startswith(f"auth_{chat_id}_")]
                for k in keys:
                    del self.cache._cache[k]
        else:
            await self.cache.clear()


# ============ نسخ عامة ============

settings_cache = SettingsCache()
banned_words_cache = BannedWordsCache()
auth_cache = AuthCache()


async def cache_cleanup_task():
    """مهمة تنظيف دورية للكاش"""
    while True:
        await asyncio.sleep(300)  # كل 5 دقائق
        try:
            c1 = await settings_cache.security.cleanup()
            c2 = await settings_cache.auto_reply.cleanup()
            c3 = await banned_words_cache.cache.cleanup()
            c4 = await auth_cache.cache.cleanup()
            total = c1 + c2 + c3 + c4
            if total > 0:
                logger.debug(f"🧹 تنظيف الكاش: {total} عنصر")
        except Exception as e:
            logger.error(f"❌ خطأ تنظيف الكاش: {e}")
