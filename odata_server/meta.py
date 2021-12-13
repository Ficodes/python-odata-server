# Copyright (c) 2021 Future Internet Consulting and Development Solutions S.L.
from importlib import import_module


class attribute():

    def __init__(self, _type, static=None, default=None, required=False, items=None, min=None):
        if type(_type) == str:
            _type = getattr(import_module("odata_server.edm"), _type)
        self.type = _type
        self.static = static
        self.default = [] if _type == list and default is None else default
        self.required = required

        if self.type == list:
            if items is None:
                raise ValueError("Missing items parameter")

            self._items = items

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
