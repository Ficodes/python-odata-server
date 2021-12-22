# Copyright (c) 2021 Future Internet Consulting and Development Solutions S.L.


class HTTPMethodOverrideMiddleware(object):
    """
    https://flask.palletsprojects.com/en/2.0.x/patterns/methodoverrides/
    """

    allowed_methods = frozenset([
        "GET",
        "HEAD",
        "POST",
        "DELETE",
        "PUT",
        "PATCH",
        "OPTIONS"
    ])
    bodyless_methods = frozenset(["GET", "HEAD", "OPTIONS", "DELETE"])

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        method = environ.get("HTTP_X_HTTP_METHOD", "").upper()
        if method in self.allowed_methods:
            environ["REQUEST_METHOD"] = method
        if method in self.bodyless_methods:
            environ["CONTENT_LENGTH"] = "0"
        return self.app(environ, start_response)
