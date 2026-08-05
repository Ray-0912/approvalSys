from migrations.runner import run_migrations


def create_tables():
    run_migrations()
    print('Database setup complete.')

if __name__ == "__main__":
    create_tables()
