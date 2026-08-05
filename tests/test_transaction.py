from database import transaction


class FakeConnection:
    def __init__(self):
        self.started = False
        self.committed = False
        self.rolled_back = False

    def start_transaction(self):
        self.started = True

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


def test_transaction_rolls_back_on_exception():
    connection = FakeConnection()

    try:
        with transaction(connection):
            raise RuntimeError('boom')
    except RuntimeError:
        pass

    assert connection.started is True
    assert connection.committed is False
    assert connection.rolled_back is True