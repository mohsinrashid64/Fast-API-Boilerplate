from .auth_middleware import AuthMiddleware


# A helper function to add all middlewares to FastAPI
def init_middlewares(app):
    app.add_middleware(AuthMiddleware)
    