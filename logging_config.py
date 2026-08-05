import logging
from contextvars import ContextVar


LOG_FORMAT = '%(asctime)s %(levelname)s [%(service)s] [%(env)s] [%(request_id)s] [%(name)s] %(message)s'
request_id_var = ContextVar('request_id', default='-')
service_var = ContextVar('service', default='approval_system')
environment_var = ContextVar('env', default='development')


class RequestIdFilter(logging.Filter):
    def filter(self, record):
        record.request_id = request_id_var.get('-')
        record.service = service_var.get('approval_system')
        record.env = environment_var.get('development')
        return True


def setup_logging(level='INFO', service_name='approval_system', environment='development'):
    service_var.set(service_name)
    environment_var.set(environment)
    root = logging.getLogger()
    root.setLevel(getattr(logging, level, logging.INFO))

    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(LOG_FORMAT))
        root.addHandler(handler)
    else:
        for handler in root.handlers:
            handler.setFormatter(logging.Formatter(LOG_FORMAT))

    # Apply filter to all existing and future handlers on the root logger.
    filter_instance = RequestIdFilter()
    root.addFilter(filter_instance)
    for handler in root.handlers:
        handler.addFilter(filter_instance)


def set_request_id(value):
    request_id_var.set(value)
