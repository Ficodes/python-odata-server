class attribute():

    def __init__(self, _type, static=None, default=None, required=False, items=None, min=None):
        self.type = _type
        self.static = static
        self.default = [] if _type == list and default is None else default
        self.required = required

        if self.type == list:
            if items is None:
                raise ValueError("Missing items parameter")

            self.items = items


def static_attribute(value):
    return attribute(str, static=value, default=value)

element = attribute

