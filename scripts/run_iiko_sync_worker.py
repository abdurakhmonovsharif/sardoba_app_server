from app.workers import IikoSyncWorker


def main() -> None:
    IikoSyncWorker().run_forever()


if __name__ == "__main__":
    main()
