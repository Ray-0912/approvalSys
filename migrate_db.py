from migrations.runner import run_migrations


def run_migration():
    try:
        run_migrations()
        print('Migration successful')
    except Exception as e:
        print(f'Migration failed: {e}')

if __name__ == "__main__":
    run_migration()
