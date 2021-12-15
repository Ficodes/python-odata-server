# Copyright (c) 2021 Future Internet Consulting and Development Solutions S.L.
from importlib import import_module


class attribute():

    def __init__(self, _type, static=None, default=None, required=False, items=None, min=None):
        self._type = _type
        self.static = static
        self.default = [] if _type == list and default is None else default
        self.required = required

        if _type == list:
            if items is None:
                raise ValueError("Missing items parameter")

            self._items = items

    @property
    def type(self):
        if type(self._type) == str:
            self._type = getattr(import_module("odata_server.edm"), self._type)
        return self._type

    @property
    def items(self):
        if self.type == list:
            if type(self._items) == str:
                self._items = getattr(import_module("odata_server.edm"), self._items)
            return self._items
        else:
            return None


def static_attribute(value):
    return attribute(str, static=value, default=value)


element = attribute
