from dotenv import load_dotenv

load_dotenv()

from cli.app import app  # noqa: E402

if __name__ == "__main__":
    app()
