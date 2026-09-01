#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
حزمة المعالجات - استيراد جميع المعالجات مرة واحدة
"""

from .handlers_command import CommandHandlers
from .handlers_callback import CallbackHandlers
from .handlers_message import MessageHandlers

__all__ = [
    "CommandHandlers",
    "CallbackHandlers",
    "MessageHandlers",
]
