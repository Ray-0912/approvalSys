import os

# Get Root Path
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))


def _str_to_bool(value, default=False):
	if value is None:
		return default
	return str(value).strip().lower() in {'1', 'true', 'yes', 'on'}


class BaseConfig:
	app_env = os.getenv('APP_ENV', 'development').strip().lower()
	SECRET_KEY = os.getenv('SECRET_KEY') or ('approvalsys-dev-secret' if app_env != 'production' else None)
	SESSION_TIMEOUT_MINUTES = int(os.getenv('SESSION_TIMEOUT_MINUTES', '60'))
	SESSION_COOKIE_HTTPONLY = True
	SESSION_COOKIE_SAMESITE = os.getenv('SESSION_COOKIE_SAMESITE', 'Lax')
	SESSION_COOKIE_SECURE = _str_to_bool(os.getenv('SESSION_COOKIE_SECURE'), False)
	SESSION_COOKIE_NAME = os.getenv('SESSION_COOKIE_NAME', 'approvalsys_session')
	BABEL_DEFAULT_LOCALE = os.getenv('BABEL_DEFAULT_LOCALE', 'zh_TW')
	BABEL_DEFAULT_TIMEZONE = os.getenv('BABEL_DEFAULT_TIMEZONE', 'UTC')
	BABEL_TRANSLATION_DIRECTORIES = os.path.join(ROOT_DIR, 'translations')
	LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO').upper()


class DevelopmentConfig(BaseConfig):
	DEBUG = True


class TestingConfig(BaseConfig):
	TESTING = True
	DEBUG = False


class ProductionConfig(BaseConfig):
	DEBUG = False
	SESSION_COOKIE_SECURE = True
	SESSION_COOKIE_SAMESITE = os.getenv('SESSION_COOKIE_SAMESITE', 'Lax')


def get_config_class(app_env=None):
	env = (app_env or os.getenv('APP_ENV', 'development')).strip().lower()
	if env == 'production':
		return ProductionConfig
	if env == 'testing':
		return TestingConfig
	return DevelopmentConfig