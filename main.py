import uvicorn
from app.config import get_settings


# Starts the Clausely FastAPI server using configuration settings
def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "app.api:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=True,
    )


if __name__ == "__main__":
    main()
